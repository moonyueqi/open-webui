"""推送去重 / 抑制状态机（JSON 持久化）。

去重规则：首次检测推一次；强度每上升一个等级(+5dBZ)推一次；距市界跨越里程碑
(25/10/5/0km)推一次；首次达到 >=45dBZ 推一次（之后维持不再每帧推，跌破再升可再推）；
新区县单独开轨迹。过期(超过 gap_minutes 无强回波)自动重置轨迹。

覆盖范围抑制（process 级，见 decide_coverage）：
  · 出现"此前未推送过的新影响区县"才因覆盖变化而推；单纯某区县乡镇增多、无新区县则不推。
  · 全局最强回波等级上升始终允许推送（强度升级绕过出口）。
  · 首次达成"全市每个区县大部分乡镇（街道）覆盖"时，作为重要节点推送一次。
  · 已取消"全覆盖后仅强度升级才推"的旧规则7静默限制——全覆盖后不再长期沉默，
    防刷屏统一由 12 分钟全局节流兜底。
  · 状态随轨迹一并过期重置（gap_minutes 无强回波即清空，过程结束自动重来）。
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

STATE_FILENAME = "dedup_state.json"


def _now() -> float:
    return time.time()


@dataclass
class TrackState:
    last_level: int = 0
    redalert: bool = False              # 是否进入 >=45 持续推送态
    last_milestone_idx: int = -1        # 已跨越到的里程碑索引（越大越近）
    last_push_ts: float = 0.0
    last_seen_ts: float = 0.0
    pushed_once: bool = False


@dataclass
class CoverageState:
    """过程级"影响范围"状态（规则7/8 用）。

    pushed_codes：本过程内曾经因覆盖被推送过的区县集合（判定"是否出现新区县"）。
    full_coverage：是否已进入"全市大部分乡镇均受影响"的全覆盖态。
    last_push_level：覆盖维度最近一次推送时记录的全局最强等级（判定强度是否再上升）。
    last_seen_ts：最近一次有强回波的时刻（用于与轨迹一致的过期重置）。
    """
    pushed_codes: List[str] = field(default_factory=list)
    full_coverage: bool = False
    last_push_level: int = 0
    last_seen_ts: float = 0.0


@dataclass
class DedupState:
    districts: Dict[str, TrackState] = field(default_factory=dict)
    approach: TrackState = field(default_factory=TrackState)
    coverage: CoverageState = field(default_factory=CoverageState)
    last_global_push_ts: float = 0.0     # 最近一次实际推送时刻（全局节流用）

    def to_json(self) -> dict:
        return {
            "districts": {k: vars(v) for k, v in self.districts.items()},
            "approach": vars(self.approach),
            "coverage": vars(self.coverage),
            "last_global_push_ts": self.last_global_push_ts,
        }

    @classmethod
    def from_json(cls, d: dict) -> "DedupState":
        st = cls()
        for k, v in (d.get("districts") or {}).items():
            st.districts[k] = TrackState(**v)
        ap = d.get("approach")
        if ap:
            st.approach = TrackState(**ap)
        cov = d.get("coverage")
        if cov:
            st.coverage = CoverageState(
                pushed_codes=list(cov.get("pushed_codes") or []),
                full_coverage=bool(cov.get("full_coverage") or False),
                last_push_level=int(cov.get("last_push_level") or 0),
                last_seen_ts=float(cov.get("last_seen_ts") or 0.0),
            )
        st.last_global_push_ts = float(d.get("last_global_push_ts") or 0.0)
        return st


@dataclass(frozen=True)
class PushDecision:
    should_push: bool
    reasons: List[str]


class DedupManager:
    def __init__(
        self,
        state_dir: str,
        *,
        level_step: float = 5.0,
        redalert_dbz: float = 45.0,
        strong_dbz: float = 35.0,
        boundary_milestones_km: Optional[List[float]] = None,
        gap_minutes: int = 30,
        push_window_minutes: int = 12,
        full_coverage_ratio: float = 0.7,
    ):
        self.path = Path(state_dir) / STATE_FILENAME
        self.level_step = level_step
        self.redalert_dbz = redalert_dbz
        self.strong_dbz = strong_dbz
        self.full_coverage_ratio = full_coverage_ratio
        # 从远到近排序，index 越大越接近市界（0km=入市）
        self.milestones = sorted(
            boundary_milestones_km or [25.0, 10.0, 5.0, 0.0], reverse=True
        )
        self.gap_seconds = gap_minutes * 60
        self.push_window_seconds = max(0, push_window_minutes) * 60
        self.state = self._load()

    def in_throttle_window(self, now_ts: float) -> bool:
        """全局节流：距上次实际推送不足窗口期则返回 True（本轮应抑制）。"""
        if self.push_window_seconds <= 0:
            return False
        last = self.state.last_global_push_ts
        return last > 0 and (now_ts - last) < self.push_window_seconds

    def mark_pushed(self, now_ts: float) -> None:
        """记录一次实际推送时刻（用于全局节流）。"""
        self.state.last_global_push_ts = now_ts

    def _load(self) -> DedupState:
        if self.path.exists():
            try:
                return DedupState.from_json(
                    json.loads(self.path.read_text(encoding="utf-8"))
                )
            except Exception as e:
                log.warning("dedup state 读取失败，重置: %s", e)
        return DedupState()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self.state.to_json(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    def _milestone_idx(self, dist_km: float) -> int:
        """返回 dist_km 已跨越到的最近里程碑索引（-1 表示比最远里程碑还远）。"""
        idx = -1
        for i, mk in enumerate(self.milestones):
            if dist_km <= mk:
                idx = i
        return idx

    def _expired(self, track: TrackState, now_ts: float) -> bool:
        return track.last_seen_ts > 0 and (now_ts - track.last_seen_ts) > self.gap_seconds

    def decide_district(
        self,
        code: str,
        observed_level: int,
        observed_max_dbz: float,
        now_ts: float,
    ) -> PushDecision:
        """对某区县的实况强回波，判定是否需要推送。"""
        track = self.state.districts.get(code)
        if track is None or self._expired(track or TrackState(), now_ts):
            track = TrackState()
            self.state.districts[code] = track

        reasons: List[str] = []
        should = False

        if not track.pushed_once:
            should = True
            reasons.append("首次检测")
        if observed_level > track.last_level:
            should = True
            reasons.append(f"等级上升至{observed_level}dBZ")
        # ≥45dBZ：仅"首次达到"推一次（重要节点提醒）；之后维持≥45 不再每帧持续推，
        #   避免强度维持高位时每个节流窗口都刷一条。后续仍可被"等级再上升/新区县/
        #   里程碑"等变化触发。
        if observed_max_dbz >= self.redalert_dbz:
            if not track.redalert:
                should = True
                reasons.append("达到≥45dBZ")
            track.redalert = True
        elif observed_max_dbz < self.redalert_dbz:
            # 跌破 45 后清除 redalert 态，使其再次升到 45 时能再触发一次"达到≥45dBZ"。
            track.redalert = False

        if should:
            track.pushed_once = True
            track.last_level = max(track.last_level, observed_level)
            track.last_push_ts = now_ts
        track.last_seen_ts = now_ts
        return PushDecision(should_push=should, reasons=reasons)

    def decide_approach(
        self,
        observed_level: int,
        observed_max_dbz: float,
        min_dist_to_city_km: float,
        now_ts: float,
    ) -> PushDecision:
        """对缓冲区内、尚未入市的强回波，按里程碑/等级判定推送。"""
        track = self.state.approach
        if self._expired(track, now_ts):
            track = TrackState()
            self.state.approach = track

        reasons: List[str] = []
        should = False

        if observed_max_dbz < self.strong_dbz:
            track.last_seen_ts = now_ts
            return PushDecision(False, [])

        if not track.pushed_once:
            should = True
            reasons.append("首次检测(缓冲区)")

        cur_idx = self._milestone_idx(min_dist_to_city_km)
        if cur_idx > track.last_milestone_idx and cur_idx >= 0:
            should = True
            mk = self.milestones[cur_idx]
            reasons.append("进入市内" if mk == 0 else f"逼近至{int(mk)}km")
            track.last_milestone_idx = cur_idx

        if observed_level > track.last_level:
            should = True
            reasons.append(f"等级上升至{observed_level}dBZ")

        # ≥45dBZ：仅"首次达到"推一次；之后维持不再每帧持续推（与 decide_district 一致）。
        if observed_max_dbz >= self.redalert_dbz:
            if not track.redalert:
                should = True
                reasons.append("达到≥45dBZ")
            track.redalert = True
        else:
            track.redalert = False

        if should:
            track.pushed_once = True
            track.last_level = max(track.last_level, observed_level)
            track.last_push_ts = now_ts
        track.last_seen_ts = now_ts
        return PushDecision(should_push=should, reasons=reasons)

    def decide_coverage(
        self,
        affected_township_counts: Dict[str, int],
        district_township_total: Dict[str, int],
        global_level: int,
        now_ts: float,
    ) -> PushDecision:
        """按"影响范围变化 + 全局强度"判定本轮是否构成推送理由。

        参数：
          affected_township_counts：本轮各受影响区县 -> 该区县内受影响乡镇(街道)数。
              仅包含确有受影响乡镇的区县（空集合的区县不应传入）。
          district_township_total：各区县乡镇(街道)总数（来自掩膜统计）。
          global_level：本轮全局最强回波等级（dBZ 档位）。

        判定：
          · 强度等级较上次覆盖推送时上升 -> 推（强度升级始终允许的绕过出口）。
          · 出现"此前未推送过的新影响区县" -> 推；仅乡镇增多、无新区县 -> 不推。
          · 首次达成"每个有强回波区县均覆盖大部分乡镇" -> 推一次，并置 full_coverage。
          · 注：已取消"全覆盖后仅强度升级才推"的旧静默限制，全覆盖后仍按上述统一规则，
            防刷屏由 12 分钟全局节流兜底。

        副作用：命中推送时更新 pushed_codes / last_push_level；并刷新 last_seen_ts。
        过期(gap)后状态清空，过程结束自动重来。
        """
        cov = self.state.coverage
        if cov.last_seen_ts > 0 and (now_ts - cov.last_seen_ts) > self.gap_seconds:
            cov = CoverageState()
            self.state.coverage = cov

        reasons: List[str] = []
        should = False

        cur_codes = set(affected_township_counts.keys())

        # 是否"全市每个受影响区县都覆盖了大部分乡镇(街道)"。
        # 口径（per_district）：所有有强回波的区县均达 full_coverage_ratio 才算全覆盖。
        full_now = bool(cur_codes)
        for code in cur_codes:
            total = district_township_total.get(code, 0)
            cnt = affected_township_counts.get(code, 0)
            if total <= 0 or cnt < self.full_coverage_ratio * total:
                full_now = False
                break

        # 出口1：全局强度等级上升（始终允许推送）。
        level_rose = global_level > cov.last_push_level
        if level_rose:
            should = True
            reasons.append(f"全局强度上升至{global_level}dBZ")

        # 统一规则（原规则8，已取消"全覆盖后仅强度升级才推"的规则7静默限制）：
        #   出现"此前未推送过的新影响区县"即推；仅乡镇增多、无新区县则不因范围推。
        #   防刷屏由 12 分钟全局节流兜底，不再因"已全覆盖"而长期静默。
        new_codes = cur_codes - set(cov.pushed_codes)
        if new_codes:
            should = True
            reasons.append(f"新增影响区县{len(new_codes)}个")
        elif not level_rose and not (full_now and not cov.full_coverage):
            # 首次达成全覆盖会在下方单独触发推送，此处不追加"不推"理由以免自相矛盾。
            reasons.append("无新影响区县（仅乡镇增多），不推")

        # 首次达成全覆盖：作为一次重要预警节点推送一次（"全市大部分乡镇均将受影响"）。
        if full_now and not cov.full_coverage:
            cov.full_coverage = True
            should = True
            reasons.append("首次达到全市大部分乡镇覆盖")

        if should:
            cov.pushed_codes = sorted(set(cov.pushed_codes) | cur_codes)
            cov.last_push_level = max(cov.last_push_level, global_level)
        cov.last_seen_ts = now_ts
        return PushDecision(should_push=should, reasons=reasons)
