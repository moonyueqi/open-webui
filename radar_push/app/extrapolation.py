"""外推分析：遍历未来 1 小时帧，推断移动方向、受影响区县乡镇、强度等级与趋势，
并判定强回波是否会移入苏州市内。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from .echo_detect import detect_clusters, level_floor
from .geo import GridMasks


_DIRS_8 = [
    (0.0, "北"), (45.0, "东北"), (90.0, "东"), (135.0, "东南"),
    (180.0, "南"), (225.0, "西南"), (270.0, "西"), (315.0, "西北"),
]


def bearing_to_direction(d_lat: float, d_lon: float, move_threshold_deg: float) -> str:
    """位移向量 -> 八方位中文（去向），位移过小则"少动"。"""
    dist = float(np.hypot(d_lat, d_lon))
    if dist < move_threshold_deg:
        return "少动"
    ang = (np.degrees(np.arctan2(d_lon, d_lat)) + 360.0) % 360.0
    best = min(_DIRS_8, key=lambda t: min(abs(ang - t[0]), 360 - abs(ang - t[0])))
    return best[1]


def threat_score(cluster) -> float:
    """主威胁团评分：距市界越近、强度越大越高。"""
    dist = cluster.min_dist_to_city_km
    dist = 9999.0 if dist is None else float(dist)
    return -dist + 0.1 * float(cluster.max_dbz)


# 兼容旧的模块内私有引用。
_threat_score = threat_score


def _track_strongest_centroids(
    per_frame_clusters: List[list],
    max_jump_deg: float,
    current_centroid: Optional[Tuple[float, float]] = None,
) -> List[Tuple[int, float, float]]:
    """锁定主威胁团并跨帧最近邻跟踪，返回其质心轨迹 [(frame_idx, lat, lon), ...]。

    current_centroid 为实况主威胁团质心（可选）。给定时，以它作为轨迹起点
    （frame_idx=-1），外推帧用最近邻续在其后，使方向锚定到"实况正在盯的这个团"
    而非外推内部独立选出的团；若实况质心与外推首个匹配团跳变 > max_jump_deg
    （疑似不是同一团），则丢弃实况起点、回退到纯外推轨迹。
    """
    track: List[Tuple[int, float, float]] = []
    prev: Optional[Tuple[float, float]] = None
    if current_centroid is not None:
        track.append((-1, current_centroid[0], current_centroid[1]))
        prev = current_centroid
    for k, clusters in enumerate(per_frame_clusters):
        if not clusters:
            if prev is not None:
                break
            continue
        if prev is None:
            c = max(clusters, key=_threat_score)
        else:
            c = min(
                clusters,
                key=lambda cc: (cc.centroid_lat - prev[0]) ** 2
                + (cc.centroid_lon - prev[1]) ** 2,
            )
            jump = float(np.hypot(c.centroid_lat - prev[0], c.centroid_lon - prev[1]))
            if jump > max_jump_deg:
                # 实况起点与外推首团跳变过大：疑似非同一团，丢弃实况起点回退纯外推。
                if track and track[0][0] == -1:
                    return _track_strongest_centroids(
                        per_frame_clusters, max_jump_deg, current_centroid=None
                    )
                break
        track.append((k, c.centroid_lat, c.centroid_lon))
        prev = (c.centroid_lat, c.centroid_lon)
    return track


@dataclass
class FrameImpact:
    frame_index: int
    valid_time: object
    max_dbz_in_city: float
    affected: Dict[str, Set[str]] = field(default_factory=dict)
    centroid: Optional[Tuple[float, float]] = None


@dataclass
class ExtrapResult:
    direction: str
    will_enter_city: bool
    max_level_in_city: int
    affected: Dict[str, Set[str]]
    trend: str
    max_dbz_in_city: float = float("nan")   # 未来各帧市内最大反射率（原始 dBZ）
    frames: List[FrameImpact] = field(default_factory=list)
    # 方向判定所用主威胁团质心轨迹的首/末点 (lat, lon)，供实况图画移动方向箭头。
    # 轨迹点不足或"少动"时为 None（此时不应画箭头）。
    track_start: Optional[Tuple[float, float]] = None
    track_end: Optional[Tuple[float, float]] = None


def _affected_in_frame(
    refl: np.ndarray,
    masks: GridMasks,
    strong_dbz: float,
) -> Tuple[Dict[str, Set[str]], float]:
    """单帧：市内 >=strong_dbz 落入的区县/乡镇集合 + 市内最大反射率。

    预报（外推）刻意采用宽松口径：只要单个格点达标即计入，不做四连通过滤，
    以尽量不漏报未来可能受影响的区域。实况判断仍用四连通（见 main.py）。
    """
    affected: Dict[str, Set[str]] = {}
    strong_city = np.isfinite(refl) & (refl >= strong_dbz) & masks.city
    if not strong_city.any():
        max_in_city = float("nan")
        cityvals = refl[masks.city & np.isfinite(refl)]
        if cityvals.size:
            max_in_city = float(cityvals.max())
        return affected, max_in_city

    for tname, dcode, tmask in masks.townships:
        if (strong_city & tmask).any():
            affected.setdefault(dcode, set()).add(tname)

    # 市内强回波但不属任何乡镇多边形时，至少记区县
    for code, dmask in masks.districts.items():
        if (strong_city & dmask).any():
            affected.setdefault(code, set())

    cityvals = refl[masks.city & np.isfinite(refl)]
    max_in_city = float(cityvals.max()) if cityvals.size else float("nan")
    return affected, max_in_city


def analyze_extrapolation(
    frames: np.ndarray,                      # (n_frame, n_lat, n_lon) NaN 缺测
    valid_times: List,
    masks: GridMasks,
    *,
    current_city_max_dbz: float,
    current_centroid: Optional[Tuple[float, float]] = None,
    strong_dbz: float = 35.0,
    min_points: int = 4,
    level_step: float = 5.0,
    move_threshold_deg: float = 0.03,        # 约 3km，小于则视为少动
    max_jump_deg: float = 0.30,              # 约 30km，相邻帧质心跳变超此值视为跨团
) -> ExtrapResult:
    n_frame = frames.shape[0]

    affected_all: Dict[str, Set[str]] = {}
    max_level_in_city = 0
    max_dbz_city_overall = float("nan")
    frame_impacts: List[FrameImpact] = []
    per_frame_clusters: List[list] = []

    for k in range(n_frame):
        refl = frames[k]
        aff, max_in_city = _affected_in_frame(refl, masks, strong_dbz)
        for code, twset in aff.items():
            affected_all.setdefault(code, set()).update(twset)
        if np.isfinite(max_in_city):
            if not np.isfinite(max_dbz_city_overall) or max_in_city > max_dbz_city_overall:
                max_dbz_city_overall = max_in_city
            if max_in_city >= strong_dbz:
                lvl = level_floor(max_in_city, level_step, strong_dbz)
                max_level_in_city = max(max_level_in_city, lvl)

        det = detect_clusters(
            refl, masks.buffer_full, masks.lat_arr, masks.lon_arr,
            strong_dbz=strong_dbz, min_points=min_points, level_step=level_step,
            dist_to_city_km=masks.dist_to_city_km,
        )
        per_frame_clusters.append(det.clusters)
        centroid = (det.clusters[0].centroid_lat, det.clusters[0].centroid_lon) \
            if det.clusters else None

        frame_impacts.append(FrameImpact(
            frame_index=k,
            valid_time=valid_times[k] if k < len(valid_times) else None,
            max_dbz_in_city=max_in_city,
            affected={c: set(s) for c, s in aff.items()},
            centroid=centroid,
        ))

    # 方向：用主威胁团轨迹首末位移定方向，避免多回波时最强块跳变产生伪移动。
    # 给定实况质心时以其为轨迹起点，把方向锚定到实况正在盯的同一个团（见函数说明）。
    direction = "少动"
    track_start: Optional[Tuple[float, float]] = None
    track_end: Optional[Tuple[float, float]] = None
    track = _track_strongest_centroids(
        per_frame_clusters, max_jump_deg, current_centroid=current_centroid
    )
    if len(track) >= 2:
        (_, lat0, lon0) = track[0]
        (_, lat1, lon1) = track[-1]
        direction = bearing_to_direction(lat1 - lat0, lon1 - lon0, move_threshold_deg)
        # 仅当确有可辨移动（非"少动"）时暴露轨迹首末点，供画箭头。
        if direction != "少动":
            track_start = (lat0, lon0)
            track_end = (lat1, lon1)

    will_enter_city = max_level_in_city >= strong_dbz or len(affected_all) > 0

    trend = "维持"
    if np.isfinite(max_dbz_city_overall) and np.isfinite(current_city_max_dbz):
        diff = max_dbz_city_overall - current_city_max_dbz
        if diff >= level_step:
            trend = "增强"
        elif diff <= -level_step:
            trend = "减弱"
    elif np.isfinite(max_dbz_city_overall) and not np.isfinite(current_city_max_dbz):
        trend = "增强"

    return ExtrapResult(
        direction=direction,
        will_enter_city=will_enter_city,
        max_level_in_city=max_level_in_city,
        affected=affected_all,
        trend=trend,
        max_dbz_in_city=max_dbz_city_overall,
        frames=frame_impacts,
        track_start=track_start,
        track_end=track_end,
    )
