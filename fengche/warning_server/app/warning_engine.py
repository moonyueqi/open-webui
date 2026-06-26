"""核心：对每个区、每个小时做阈值定级（任意格点达标即触发），再合并成连续时段。

输入：ForecastGrid（含整网格 gs、tp）+ 各区的 DistrictMask。
输出：每区两种预警类型（strong_convection / rainstorm）的 segments 列表 + advisory。

定级规则：区内只要有任意 1 个格点 ≥ 某等级阈值，即认为达标；从高级别向
低级别测试，取首个达标的最高级。纯提示性质，是否真正发布由预报员研判。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .config import Thresholds
from .district_mask import DistrictMask
from .nc_reader_grid import ForecastGrid
from .rules import (
    gs_thresholds,
    level_label,
    rain_thresholds,
)
from .templates import build_advisory


log = logging.getLogger(__name__)


# --------- 单小时定级 ---------
# 定级策略：只要区内有「任意一个格点」达到阈值，即认为达标（提示性质，
# 由预报员复核是否真正发布）。不再使用覆盖率比例门槛。
def _classify_wind_hour(
    gs_in: np.ndarray,
    n_points: int,
    thresholds: Thresholds,
    coverage_ratio: float,  # 保留参数仅为向后兼容，函数体内已忽略
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """对区内格点的当小时阵风定级：从高到低，第一个出现任意达标格点的级别即定级。"""
    if n_points == 0 or gs_in.size == 0:
        return None, None
    grades = gs_thresholds(thresholds)  # [(yellow,17.2), (orange,24.5), (red,32.7)]
    max_gs = float(np.nanmax(gs_in))
    for level, thr in reversed(grades):  # red → orange → yellow
        meet = gs_in >= thr
        hit = int(meet.sum())
        if hit > 0:
            return level, {
                "max_gs_ms": round(max_gs, 2),
                "hit_points": hit,
                "hit_ratio": round(hit / n_points, 3),
                "threshold_ms": thr,
            }
    return None, {
        "max_gs_ms": round(max_gs, 2),
        "hit_points": 0,
        "hit_ratio": 0.0,
        "threshold_ms": None,
    }


def _classify_rain_hour(
    rain1h_in: np.ndarray,
    rain6h_in: Optional[np.ndarray],
    rain24h_in: Optional[np.ndarray],
    n_points: int,
    thresholds: Thresholds,
    coverage_ratio: float,  # 保留参数仅为向后兼容，函数体内已忽略
) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
    """对区内格点的当小时降水定级（1h / 6h / 24h 三窗口 OR）。

    只要区内任意一个格点在任一窗口达标即定级。返回 (level, metrics, triggered_by)，
    triggered_by 取值 '1h' / '6h' / '24h'，按"达标格点数"最多的窗口选定。
    """
    if n_points == 0 or rain1h_in.size == 0:
        return None, None, None

    grades = rain_thresholds(thresholds)
    max_1h = float(np.nanmax(rain1h_in))
    max_6h = float(np.nanmax(rain6h_in)) if rain6h_in is not None else None
    max_24h = float(np.nanmax(rain24h_in)) if rain24h_in is not None else None

    zero_mask = np.zeros_like(rain1h_in, dtype=bool)

    def _window_meet(arr: Optional[np.ndarray], thr: Optional[float]) -> np.ndarray:
        if thr is None or arr is None:
            return zero_mask
        return arr >= thr

    for level, t_1h, t_6h, t_24h in reversed(grades):  # red → orange → yellow → blue
        meet_1h = _window_meet(rain1h_in, t_1h)
        meet_6h = _window_meet(rain6h_in, t_6h)
        meet_24h = _window_meet(rain24h_in, t_24h)
        meet = meet_1h | meet_6h | meet_24h
        hit = int(meet.sum())
        if hit > 0:
            hit_1h = int(meet_1h.sum())
            hit_6h = int(meet_6h.sum())
            hit_24h = int(meet_24h.sum())
            # 选达标格点最多的窗口作为主触发；都为 0 时按可用窗口顺序兜底（蓝色只有 6h 阈值）
            candidates = []
            if t_1h is not None:
                candidates.append(("1h", hit_1h))
            if t_6h is not None:
                candidates.append(("6h", hit_6h))
            if t_24h is not None and rain24h_in is not None:
                candidates.append(("24h", hit_24h))
            triggered_by = (
                max(candidates, key=lambda kv: kv[1])[0] if candidates else "6h"
            )
            return level, {
                "max_rain_1h_mm":  round(max_1h, 2),
                "max_rain_6h_mm":  round(max_6h, 2) if max_6h is not None else None,
                "max_rain_24h_mm": round(max_24h, 2) if max_24h is not None else None,
                "hit_points":      hit,
                "hit_points_1h":   hit_1h,
                "hit_points_6h":   hit_6h,
                "hit_points_24h":  hit_24h,
                "hit_ratio":       round(hit / n_points, 3),
                "threshold_1h_mm":  t_1h,
                "threshold_6h_mm":  t_6h,
                "threshold_24h_mm": t_24h,
            }, triggered_by

    return None, {
        "max_rain_1h_mm":  round(max_1h, 2),
        "max_rain_6h_mm":  round(max_6h, 2) if max_6h is not None else None,
        "max_rain_24h_mm": round(max_24h, 2) if max_24h is not None else None,
        "hit_points":  0,
        "hit_ratio":   0.0,
        "threshold_1h_mm":  None,
        "threshold_6h_mm":  None,
        "threshold_24h_mm": None,
    }, None


# --------- 滚动窗口（6h / 24h） ---------
def _compute_rolling_sum(
    tp_district: np.ndarray, window_hours: int
) -> List[Optional[np.ndarray]]:
    """对区内格点按 step 维滚动 N 小时求和。

    输入 tp_district：(n_step, n_points) 数组（已用 mask 取过区内格点）。
    返回长度 n_step 的列表，第 k 项是 (n_points,) 的窗口降水累计数组，
    或 None（当前 k 之前的小时数不足 window_hours-1 时）。
    """
    n_step = tp_district.shape[0]
    need = window_hours - 1
    out: List[Optional[np.ndarray]] = [None] * n_step
    for k in range(n_step):
        if k < need:
            out[k] = None
        else:
            out[k] = tp_district[k - need: k + 1, :].sum(axis=0)
    return out


# --------- 时段合并 ---------
def _merge_into_segments(
    warning_type: str,
    levels: List[Optional[str]],
    triggered_by_list: List[Optional[str]],
    valid_times: List[datetime],
    metrics: List[Optional[Dict[str, Any]]],
    area_code: str,
    issue_time: datetime,
) -> List[Dict[str, Any]]:
    """把逐小时的 levels 序列合并成连续同级时段（带 advisory）。"""
    segments: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    def _finalize(seg: Dict[str, Any]) -> Dict[str, Any]:
        # 段内主触发窗口：取 hour_metrics 里 hit_points 最多那一小时的 triggered_by
        if warning_type == "rainstorm":
            tb_list = seg.pop("_tb_per_hour")
            hit_list = [
                hm.get("hit_points", 0) for hm in seg["hour_metrics"]
            ]
            best_idx = int(np.argmax(hit_list)) if hit_list else 0
            seg["triggered_by"] = tb_list[best_idx]
        else:
            seg.pop("_tb_per_hour", None)
            seg["triggered_by"] = None

        seg["advisory"] = build_advisory(
            warning_type=warning_type,
            level=seg["level"],
            triggered_by=seg["triggered_by"],
            start=datetime.fromisoformat(seg["start_time"]),
            end=datetime.fromisoformat(seg["end_time"]),
            area_code=area_code,
            issue_time=issue_time,
        )
        return seg

    for i, lvl in enumerate(levels):
        if lvl is None:
            if current is not None:
                segments.append(_finalize(current))
                current = None
            continue
        vt = valid_times[i]
        m = dict(metrics[i] or {})
        m["valid_time"] = vt.isoformat()
        if current is not None and current["level"] == lvl:
            current["end_time"] = vt.isoformat()
            current["hour_metrics"].append(m)
            current["_tb_per_hour"].append(triggered_by_list[i])
        else:
            if current is not None:
                segments.append(_finalize(current))
            current = {
                "level": lvl,
                "level_label": level_label(warning_type, lvl),
                "start_time": vt.isoformat(),
                "end_time": vt.isoformat(),
                "hour_metrics": [m],
                "_tb_per_hour": [triggered_by_list[i]],
            }

    if current is not None:
        segments.append(_finalize(current))

    return segments


# --------- 顶层：逐区评估 ---------
def evaluate_district(
    code: str,
    district: DistrictMask,
    grid: ForecastGrid,
    thresholds: Thresholds,
    gs_coverage_ratio: float,
    rain_coverage_ratio: float,
) -> Dict[str, Any]:
    """对单个区做完整评估，返回 strong_convection / rainstorm 两块结构。"""
    mask = district.mask
    n_pts = district.n_points

    # 区内格点的时间序列：(n_step, n_points)
    gs_dist = grid.gs[:, mask]  # (n_step, n_points)
    tp_dist = grid.tp[:, mask]

    n_step = grid.gs.shape[0]
    rain_6h_series = _compute_rolling_sum(tp_dist, window_hours=6)
    rain_24h_series = _compute_rolling_sum(tp_dist, window_hours=24)

    # --- 强对流 ---
    wind_levels: List[Optional[str]] = [None] * n_step
    wind_metrics: List[Optional[Dict[str, Any]]] = [None] * n_step
    for k in range(n_step):
        lvl, m = _classify_wind_hour(
            gs_dist[k], n_pts, thresholds, gs_coverage_ratio
        )
        wind_levels[k] = lvl
        wind_metrics[k] = m
    wind_segments = _merge_into_segments(
        warning_type="strong_convection",
        levels=wind_levels,
        triggered_by_list=[None] * n_step,
        valid_times=grid.valid_times,
        metrics=wind_metrics,
        area_code=code,
        issue_time=grid.issue_time,
    )

    # --- 暴雨 ---
    rain_levels: List[Optional[str]] = [None] * n_step
    rain_metrics: List[Optional[Dict[str, Any]]] = [None] * n_step
    rain_tb: List[Optional[str]] = [None] * n_step
    for k in range(n_step):
        lvl, m, tb = _classify_rain_hour(
            tp_dist[k],
            rain_6h_series[k],
            rain_24h_series[k],
            n_pts,
            thresholds,
            rain_coverage_ratio,
        )
        rain_levels[k] = lvl
        rain_metrics[k] = m
        rain_tb[k] = tb
    rain_segments = _merge_into_segments(
        warning_type="rainstorm",
        levels=rain_levels,
        triggered_by_list=rain_tb,
        valid_times=grid.valid_times,
        metrics=rain_metrics,
        area_code=code,
        issue_time=grid.issue_time,
    )

    return {
        "name": district.name,
        "grid_points_in_district": n_pts,
        "boundary_source": district.source,
        "strong_convection": {
            "segments": wind_segments,
        },
        "rainstorm": {
            "segments": rain_segments,
        },
    }


def evaluate_all(
    grid: ForecastGrid,
    masks: Dict[str, DistrictMask],
    thresholds: Thresholds,
    gs_coverage_ratio: float,
    rain_coverage_ratio: float,
    districts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """对所有（或指定）区做评估，返回 { code: 区块 } 字典。"""
    codes = districts if districts else list(masks.keys())
    result: Dict[str, Any] = {}
    for code in codes:
        if code not in masks:
            log.warning("district code %r not found in masks; skipped", code)
            continue
        result[code] = evaluate_district(
            code=code,
            district=masks[code],
            grid=grid,
            thresholds=thresholds,
            gs_coverage_ratio=gs_coverage_ratio,
            rain_coverage_ratio=rain_coverage_ratio,
        )
    return result
