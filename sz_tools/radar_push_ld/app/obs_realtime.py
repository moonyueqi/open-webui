"""由站点实况 + 回波移动方向，生成「实况提醒」行（风雨实况）。

规则（与需求一致）：
1. 仅当候选范围内存在站点「小时雨强 >= rain_mm 阈值」或「阵风 >= 风级阈值」时，才输出本行；
   否则返回空串（模板层据此整行不渲染）。
2. 空间口径：
   · 先看苏州市域内：若市内有达标站点 → 直接在市内站点取最大小时雨强 / 最大瞬时风，
     无需方向判别；市内定位写「区县+站名」（不带「苏州市」）。
   · 市内无达标、市外缓冲区（upstream_cities）有达标 → 按回波移动方向只取「上游侧」站点
     （来向一侧），排除下游侧。例：回波向东移，只取西侧无锡等上游站，排除东侧上海。
     市外定位写「城市+区县+站名」。
3. 最大小时雨强站与最大瞬时风站可不同，文案分别独立取最大。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .obs_reader import ObsStation

log = logging.getLogger(__name__)


# 八方位 -> 方位角（度，0=正北，顺时针）。与 extrapolation.bearing_to_direction 对应。
_DIR_BEARING = {
    "北": 0.0, "东北": 45.0, "东": 90.0, "东南": 135.0,
    "南": 180.0, "西南": 225.0, "西": 270.0, "西北": 315.0,
}

# 蒲福风级下界（m/s）：风速 >= 第 i 档下界即为该风级。索引即风级。
# 7 级 = 13.9 m/s 起（标准蒲福风级）。
_BEAUFORT_MIN_MS = [
    0.0, 0.3, 1.6, 3.4, 5.5, 8.0, 10.8, 13.9, 17.2, 20.8, 24.5, 28.5, 32.7,
]

_KM_PER_DEG_LAT = 111.32
_KM_PER_DEG_LON = 111.32 * math.cos(math.radians(31.3))


def wind_to_level(ms: float) -> int:
    """风速(m/s) -> 蒲福风级（整数）。超过 12 级按 12 计。"""
    if not math.isfinite(ms):
        return 0
    lvl = 0
    for i, lo in enumerate(_BEAUFORT_MIN_MS):
        if ms >= lo:
            lvl = i
    return lvl


@dataclass(frozen=True)
class ObsExtreme:
    """某要素（雨强/阵风）的极值站点。"""
    value: float
    station: ObsStation


def _bearing_from_city(centroid: Tuple[float, float], st: ObsStation) -> float:
    """站点相对苏州市质心的方位角（度，0=北，顺时针）。"""
    clat, clon = centroid
    d_lat = st.lat - clat
    d_lon = st.lon - clon
    ang = math.degrees(math.atan2(d_lon, d_lat))
    return (ang + 360.0) % 360.0


def _ang_diff(a: float, b: float) -> float:
    """两方位角最小夹角（0~180）。"""
    d = abs(a - b) % 360.0
    return d if d <= 180.0 else 360.0 - d


def _resolve_from_bearing(
    centroid: Tuple[float, float],
    direction: str,
    echo_centroid: Optional[Tuple[float, float]],
) -> Optional[float]:
    """确定「来向」方位角（站点应在的上游侧），无法确定返回 None（不做方向过滤）。

    优先用 direction（来向=去向反方向）；其次用回波团相对市质心的方位；都无则 None 保底全取。
    """
    move_bearing = _DIR_BEARING.get(direction)
    if move_bearing is not None:
        return (move_bearing + 180.0) % 360.0
    if echo_centroid is not None:
        clat, clon = centroid
        d_lat = echo_centroid[0] - clat
        d_lon = echo_centroid[1] - clon
        if abs(d_lat) > 1e-9 or abs(d_lon) > 1e-9:
            return (math.degrees(math.atan2(d_lon, d_lat)) + 360.0) % 360.0
    return None


def _on_upstream_side(
    centroid: Tuple[float, float],
    st: ObsStation,
    from_bearing: Optional[float],
    half_angle_deg: float,
) -> bool:
    """站点是否在「上游侧」：相对市质心的方位与「来向」夹角 <= half_angle_deg。

    from_bearing 为 None（方向与回波位置都无法确定）时不做过滤，全取（保底不漏报）。
    """
    if from_bearing is None:
        return True
    return _ang_diff(_bearing_from_city(centroid, st), from_bearing) <= half_angle_deg


def _location_text(st: ObsStation, in_city: bool) -> str:
    """站点定位文案。市内：区县+站名（不带苏州市）；市外：城市+区县+站名。"""
    parts: List[str] = []
    if not in_city and st.city:
        parts.append(st.city)
    if st.county:
        parts.append(st.county)
    if st.name:
        parts.append(st.name)
    return "".join(parts) if parts else (st.name or st.station_id or "未知站")


def _pick_max(
    stations: List[Tuple[ObsStation, bool]],
    value_fn,
) -> Optional[ObsExtreme]:
    best: Optional[ObsExtreme] = None
    for st, _in_city in stations:
        v = value_fn(st)
        if v is None or not math.isfinite(v):
            continue
        if best is None or v > best.value:
            best = ObsExtreme(value=v, station=st)
    return best


def build_realtime_line(
    *,
    stations: List[ObsStation],
    geo,
    direction: str,
    echo_centroid: Optional[Tuple[float, float]] = None,
    window_start_local,
    window_end_local,
    rain_threshold_mm: float = 20.0,
    gust_threshold_level: int = 7,
    upstream_half_angle_deg: float = 90.0,
) -> str:
    """生成「实况提醒」行；无达标实况返回空串。

    echo_centroid：回波主威胁团质心 (lat, lon)，用于 direction=少动/未知时确定上游侧
    （回波盘踞在市的哪一侧就取哪一侧的市外站点）。
    """
    centroid = geo.city_centroid
    from_bearing = _resolve_from_bearing(centroid, direction, echo_centroid)

    # 给每个落入缓冲区的站点打标：是否市内。
    in_city_stations: List[Tuple[ObsStation, bool]] = []
    outside_stations: List[Tuple[ObsStation, bool]] = []
    for st in stations:
        in_city, in_buffer, _up = geo.locate_point(st.lon, st.lat)
        if not in_buffer:
            continue
        if in_city:
            in_city_stations.append((st, True))
        else:
            outside_stations.append((st, False))

    gust_min_ms = _BEAUFORT_MIN_MS[min(gust_threshold_level, len(_BEAUFORT_MIN_MS) - 1)]

    def _qualifies(group: List[Tuple[ObsStation, bool]]) -> bool:
        for st, _ in group:
            if math.isfinite(st.hour_rain_mm) and st.hour_rain_mm >= rain_threshold_mm:
                return True
            if math.isfinite(st.gust_ms) and st.gust_ms >= gust_min_ms:
                return True
        return False

    # 优先市内；市内不达标再看市外上游侧。
    if _qualifies(in_city_stations):
        candidates = in_city_stations
        scope = "city"
    else:
        upstream = [
            (st, False)
            for (st, _) in outside_stations
            if _on_upstream_side(centroid, st, from_bearing, upstream_half_angle_deg)
        ]
        if _qualifies(upstream):
            candidates = upstream
            scope = "upstream"
        else:
            log.info(
                "实况提醒：候选范围无达标站点（雨>=%.0fmm 或 风>=%d级），本行不输出",
                rain_threshold_mm, gust_threshold_level,
            )
            return ""

    rain_max = _pick_max(candidates, lambda s: s.hour_rain_mm)
    gust_max = _pick_max(candidates, lambda s: s.gust_ms)

    span = f"{window_start_local.strftime('%H:%M')}-{window_end_local.strftime('%H:%M')}"
    segments: List[str] = []

    if rain_max is not None and math.isfinite(rain_max.value):
        loc = _location_text(rain_max.station, in_city=(scope == "city"))
        segments.append(f"最大小时雨强{rain_max.value:.1f}毫米（{loc}）")

    if gust_max is not None and math.isfinite(gust_max.value):
        lvl = wind_to_level(gust_max.value)
        loc = _location_text(gust_max.station, in_city=(scope == "city"))
        segments.append(f"极大风{gust_max.value:.1f}米/秒（{lvl}级，{loc}）")

    if not segments:
        return ""

    log.info("实况提醒（scope=%s, dir=%s）：%s", scope, direction, "，".join(segments))
    return f"▶ 实况提醒：{span}{'，'.join(segments)}。"
