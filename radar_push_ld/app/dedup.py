"""推送去重 / 抑制状态机（JSON 持久化）。

去重规则：首次检测、强度每升一档(+5dBZ)、跨里程碑(25/10/5/0km)、首次达到 >=45dBZ
各推一次；过期(gap_minutes 无强回波)自动重置轨迹。

分级节流：高优先级理由（缓冲区首次成型 / 进入市内0km / 市内首次到45 / 市内首次到55）
用短窗口 push_window_minutes；低优先级（区县首次检测 / 普通升档 / 后续区县再到45或55 /
缓冲区破45 / 新增区县 / 远距里程碑）用长窗口 push_window_low_minutes。
本轮含任一高优先级即用短窗口。"市内首次到45/55"为过程级判定（全局标志，随 gap 过期重置）。
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
    redalert_ever: bool = False         # 本过程内是否曾达到过 >=45（高优先级仅首次算）
    last_milestone_idx: int = -1        # 已跨越到的里程碑索引（越大越近）
    last_push_ts: float = 0.0
    last_seen_ts: float = 0.0
    pushed_once: bool = False


@dataclass
class CoverageState:
    """过程级"影响范围"状态（覆盖维度去重用）。"""
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
    # 过程级标志：市内本过程是否已首次达到 45 / 55（仅首次算高优先级）。
    city_redalert_ever: bool = False
    city_hail_ever: bool = False
    last_global_seen_ts: float = 0.0     # 全局最近见到强回波时刻（用于过程级标志过期重置）
    # 历次实况主威胁团质心轨迹 [(ts_epoch, lat, lon), ...]，供跨时次订正移动方向。
    # 按时间升序，gap 无强回波则整段过期清空，只保留最近若干点。
    dir_history: List[List[float]] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "districts": {k: vars(v) for k, v in self.districts.items()},
            "approach": vars(self.approach),
            "coverage": vars(self.coverage),
            "last_global_push_ts": self.last_global_push_ts,
            "city_redalert_ever": self.city_redalert_ever,
            "city_hail_ever": self.city_hail_ever,
            "last_global_seen_ts": self.last_global_seen_ts,
            "dir_history": [list(p) for p in self.dir_history],
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
        st.city_redalert_ever = bool(d.get("city_redalert_ever") or False)
        st.city_hail_ever = bool(d.get("city_hail_ever") or False)
        st.last_global_seen_ts = float(d.get("last_global_seen_ts") or 0.0)
        st.dir_history = [
            [float(x) for x in p]
            for p in (d.get("dir_history") or [])
            if p and len(p) >= 3
        ]
        return st


@dataclass(frozen=True)
class PushDecision:
    should_push: bool
    reasons: List[str]
    high_priority: bool = False         # 含高优先级理由则节流走短窗口


class DedupManager:
    def __init__(
        self,
        state_dir: str,
        *,
        level_step: float = 5.0,
        redalert_dbz: float = 45.0,
        hail_dbz: float = 55.0,
        strong_dbz: float = 35.0,
        boundary_milestones_km: Optional[List[float]] = None,
        gap_minutes: int = 30,
        push_window_minutes: int = 12,
        push_window_low_minutes: int = 48,
        full_coverage_ratio: float = 0.7,
        dir_history_max: int = 5,
    ):
        self.path = Path(state_dir) / STATE_FILENAME
        self.level_step = level_step
        self.redalert_dbz = redalert_dbz
        self.hail_dbz = hail_dbz
        self.strong_dbz = strong_dbz
        self.full_coverage_ratio = full_coverage_ratio
        # 方向订正保留的最近历史时次数（如 5 个 ≈ 30 分钟）
        self.dir_history_max = max(2, int(dir_history_max))
        # 从远到近排序，index 越大越接近市界（0km=入市）
        self.milestones = sorted(
            boundary_milestones_km or [25.0, 10.0, 5.0, 0.0], reverse=True
        )
        self.gap_seconds = gap_minutes * 60
        self.push_window_seconds = max(0, push_window_minutes) * 60
        # 低优先级长窗口不应短于高优先级短窗口
        self.push_window_low_seconds = max(
            self.push_window_seconds, max(0, push_window_low_minutes) * 60
        )
        self.state = self._load()

    def in_throttle_window(self, now_ts: float, high_priority: bool = False) -> bool:
        """分级全局节流：距上次推送不足相应窗口则返回 True（本轮应抑制）。"""
        window = self.push_window_seconds if high_priority else self.push_window_low_seconds
        if window <= 0:
            return False
        last = self.state.last_global_push_ts
        return last > 0 and (now_ts - last) < window

    def mark_pushed(self, now_ts: float) -> None:
        """记录一次实际推送时刻（用于全局节流）。"""
        self.state.last_global_push_ts = now_ts

    def update_direction_history(
        self,
        now_ts: float,
        centroid: Optional[tuple],
    ) -> Optional[tuple]:
        """把本时次实况主威胁团质心并入历史轨迹，返回订正用的首末点 (start, end)。

        start/end 均为 (lat, lon)，分别是窗口内最早、最新的实况质心。调用方用
        end-start 作位移向量、经 bearing_to_direction 得中文方位，并可据此画移动箭头。

        · centroid=None（本时次无实况强回波）时不追加，返回 None（调用方保留外推方向）。
        · 距上一历史点超过 gap_seconds 视为新过程，清空旧轨迹再记录。
        · 仅保留最近 dir_history_max 个点；点数 < 2 时返回 None（历史不足，回退外推）。
        · 首末位移代表回波近 ~30min 实际走向，比单时次外推更抗异常跳变。
        """
        if centroid is None:
            return None
        lat, lon = float(centroid[0]), float(centroid[1])

        hist = self.state.dir_history
        if hist:
            last_ts = hist[-1][0]
            if now_ts - last_ts > self.gap_seconds:
                hist = []
        hist.append([now_ts, lat, lon])
        if len(hist) > self.dir_history_max:
            hist = hist[-self.dir_history_max:]
        self.state.dir_history = hist

        if len(hist) < 2:
            return None
        start = (hist[0][1], hist[0][2])
        end = (hist[-1][1], hist[-1][2])
        return (start, end)

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

    def _maybe_reset_process_flags(self, now_ts: float) -> None:
        """过程级标志（市内首次到45/55）随全局过程过期（gap 无强回波）重置。"""
        st = self.state
        if st.last_global_seen_ts > 0 and (now_ts - st.last_global_seen_ts) > self.gap_seconds:
            st.city_redalert_ever = False
            st.city_hail_ever = False
        st.last_global_seen_ts = now_ts

    def decide_district(
        self,
        code: str,
        observed_level: int,
        observed_max_dbz: float,
        now_ts: float,
    ) -> PushDecision:
        """对某区县的实况强回波，判定是否需要推送。"""
        self._maybe_reset_process_flags(now_ts)
        track = self.state.districts.get(code)
        if track is None or self._expired(track or TrackState(), now_ts):
            track = TrackState()
            self.state.districts[code] = track

        reasons: List[str] = []
        should = False
        high_priority = False

        # 区县首次检测为低优先级（范围扩张刷屏主力），仅市内首次破45/55、进市等质变才高优先级
        if not track.pushed_once:
            should = True
            reasons.append("首次检测")
        if observed_level > track.last_level:
            should = True
            reasons.append(f"等级上升至{observed_level}dBZ")
        # ≥45dBZ：每次重新越过45都推；高优先级仅限"本过程市内首次到45"（全局标志），
        #   之后其它区再到45 仍推但走低窗口（防一堆区轮流破45刷屏）。
        if observed_max_dbz >= self.redalert_dbz:
            if not track.redalert:
                should = True
                if not self.state.city_redalert_ever:
                    high_priority = True
                reasons.append("达到≥45dBZ")
            track.redalert = True
            self.state.city_redalert_ever = True
        elif observed_max_dbz < self.redalert_dbz:
            track.redalert = False
        # ≥55dBZ（冰雹量级）：本过程市内首次到55 为高优先级（强盛期升级仍能插队，防48太长）。
        if observed_max_dbz >= self.hail_dbz:
            if not self.state.city_hail_ever:
                should = True
                high_priority = True
                reasons.append("达到≥55dBZ")
            self.state.city_hail_ever = True

        if should:
            track.pushed_once = True
            track.last_level = max(track.last_level, observed_level)
            track.last_push_ts = now_ts
        track.last_seen_ts = now_ts
        return PushDecision(should, reasons, high_priority=high_priority)

    def decide_approach(
        self,
        observed_level: int,
        observed_max_dbz: float,
        min_dist_to_city_km: float,
        now_ts: float,
    ) -> PushDecision:
        """对缓冲区内、尚未入市的强回波，按里程碑/等级判定推送。"""
        self._maybe_reset_process_flags(now_ts)
        track = self.state.approach
        if self._expired(track, now_ts):
            track = TrackState()
            self.state.approach = track

        reasons: List[str] = []
        should = False
        high_priority = False

        if observed_max_dbz < self.strong_dbz:
            track.last_seen_ts = now_ts
            return PushDecision(False, [])

        if not track.pushed_once:
            should = True
            high_priority = True
            reasons.append("首次检测(缓冲区)")

        cur_idx = self._milestone_idx(min_dist_to_city_km)
        if cur_idx > track.last_milestone_idx and cur_idx >= 0:
            should = True
            mk = self.milestones[cur_idx]
            if mk == 0:
                high_priority = True        # 进入市内(0km) 为高优先级
                reasons.append("进入市内")
            else:
                reasons.append(f"逼近至{int(mk)}km")
            track.last_milestone_idx = cur_idx

        if observed_level > track.last_level:
            should = True
            reasons.append(f"等级上升至{observed_level}dBZ")

        # 缓冲区（含市外）破45 降为低优先级：高优先级"破45"按市内口径统一在 decide_district
        #   判定，市外强回波不再插队（避免与"市内首次破45"口径冲突）。
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
        return PushDecision(should, reasons, high_priority=high_priority)

    def decide_coverage(
        self,
        affected_township_counts: Dict[str, int],
        district_township_total: Dict[str, int],
        global_level: int,
        now_ts: float,
    ) -> PushDecision:
        """覆盖维度去重：全局强度升级、或出现新影响区县、或首次全覆盖才推；
        仅乡镇增多、无新区县不推。affected_township_counts 仅含确有受影响乡镇的区县。
        """
        cov = self.state.coverage
        if cov.last_seen_ts > 0 and (now_ts - cov.last_seen_ts) > self.gap_seconds:
            cov = CoverageState()
            self.state.coverage = cov

        reasons: List[str] = []
        should = False

        cur_codes = set(affected_township_counts.keys())

        # 每个受影响区县均达 full_coverage_ratio 才算全覆盖
        full_now = bool(cur_codes)
        for code in cur_codes:
            total = district_township_total.get(code, 0)
            cnt = affected_township_counts.get(code, 0)
            if total <= 0 or cnt < self.full_coverage_ratio * total:
                full_now = False
                break

        level_rose = global_level > cov.last_push_level
        if level_rose:
            should = True
            reasons.append(f"全局强度上升至{global_level}dBZ")

        new_codes = cur_codes - set(cov.pushed_codes)
        if new_codes:
            should = True
            reasons.append(f"新增影响区县{len(new_codes)}个")
        elif not level_rose and not (full_now and not cov.full_coverage):
            reasons.append("无新影响区县（仅乡镇增多），不推")

        if full_now and not cov.full_coverage:
            cov.full_coverage = True
            should = True
            reasons.append("首次达到全市大部分乡镇覆盖")

        if should:
            cov.pushed_codes = sorted(set(cov.pushed_codes) | cur_codes)
            cov.last_push_level = max(cov.last_push_level, global_level)
        cov.last_seen_ts = now_ts
        # 覆盖维度均属低优先级
        return PushDecision(should_push=should, reasons=reasons, high_priority=False)
