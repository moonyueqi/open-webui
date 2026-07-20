"""推送去重 / 抑制状态机（JSON 持久化）。

去重规则：首次检测、强度每升一档(+5dBZ)、跨里程碑(25/10/5/0km)各推一次；
>=45dBZ 只要当前维持红色级别就持续产生推送理由（首次达到 / 维持均推）；
过期(gap_minutes 无强回波)自动重置轨迹。持续推的实际频率由全局节流窗口兜底。
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
    redalert: bool = False              # 当前是否处于 >=45 持续推送态（区分"首次达到"与"维持"文案）
    last_milestone_idx: int = -1        # 已跨越到的里程碑索引（越大越近）
    last_push_ts: float = 0.0
    last_seen_ts: float = 0.0
    pushed_once: bool = False


@dataclass
class DedupState:
    districts: Dict[str, TrackState] = field(default_factory=dict)
    approach: TrackState = field(default_factory=TrackState)
    last_global_push_ts: float = 0.0     # 最近一次实际推送时刻（全局节流用）

    def to_json(self) -> dict:
        return {
            "districts": {k: vars(v) for k, v in self.districts.items()},
            "approach": vars(self.approach),
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
    ):
        self.path = Path(state_dir) / STATE_FILENAME
        self.level_step = level_step
        self.redalert_dbz = redalert_dbz
        self.strong_dbz = strong_dbz
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
        # ≥45dBZ：只要当前维持在红色级别就持续产生推送理由（首次达到 / 维持均推），
        #   实际推送频率由全局节流窗口（push_window_minutes）兜底控制。
        if observed_max_dbz >= self.redalert_dbz:
            should = True
            reasons.append("达到≥45dBZ" if not track.redalert else "维持≥45dBZ")
            track.redalert = True
        else:
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

        # ≥45dBZ：只要当前维持在红色级别就持续产生推送理由（与 decide_district 一致），
        #   实际推送频率由全局节流窗口兜底控制。
        if observed_max_dbz >= self.redalert_dbz:
            should = True
            reasons.append("达到≥45dBZ" if not track.redalert else "维持≥45dBZ")
            track.redalert = True
        else:
            track.redalert = False

        if should:
            track.pushed_once = True
            track.last_level = max(track.last_level, observed_level)
            track.last_push_ts = now_ts
        track.last_seen_ts = now_ts
        return PushDecision(should_push=should, reasons=reasons)
