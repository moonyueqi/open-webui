"""强回波块检测：在掩膜范围内对 >= 阈值的格点做四连通连通域分析。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from scipy import ndimage

_FOUR_CONN = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool)


def robust_value(values: np.ndarray, min_points: int) -> float:
    """返回一组反射率里第 min_points 高的值（防单点尖峰）。

    不足 min_points 个有效值时取最小有效值；全为无效时返回 nan。
    """
    v = np.asarray(values, dtype=np.float64)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return float("nan")
    sorted_desc = np.sort(v)[::-1]
    if sorted_desc.size >= min_points:
        return float(sorted_desc[min_points - 1])
    return float(sorted_desc[-1])


def level_floor(dbz: float, step: float = 5.0, base: float = 35.0) -> int:
    """把回波强度向下取整到 step 的等级（>=base），如 37->35, 42->40。"""
    if dbz < base:
        return int(base)
    return int(base + np.floor((dbz - base) / step) * step)


def strong_connected_mask(
    refl: np.ndarray,
    *,
    strong_dbz: float = 35.0,
    min_points: int = 4,
) -> np.ndarray:
    """返回"达到强回波且四连通连通域≥min_points"的格点布尔掩膜。

    把实况判断从"单格点达标"统一为"连片≥min_points 格点达标"，可再与区域 mask 求交。
    """
    strong = np.isfinite(refl) & (refl >= strong_dbz)
    if not strong.any():
        return np.zeros_like(strong, dtype=bool)
    labeled, n = ndimage.label(strong, structure=_FOUR_CONN)
    if n == 0:
        return np.zeros_like(strong, dtype=bool)
    counts = np.bincount(labeled.ravel())
    keep_labels = np.where(counts >= min_points)[0]
    keep_labels = keep_labels[keep_labels != 0]
    return np.isin(labeled, keep_labels)


@dataclass(frozen=True)
class EchoCluster:
    label: int
    n_points: int
    max_dbz: float            # 块内单点峰值（最高格点）
    robust_dbz: float         # 块"代表强度"：块内第 min_points 高的格点值（防单点杂波）
    level_dbz: int            # 由 robust_dbz 向下取整得到的等级
    centroid_lat: float
    centroid_lon: float
    rows: np.ndarray
    cols: np.ndarray
    min_dist_to_city_km: Optional[float] = None


@dataclass(frozen=True)
class DetectResult:
    clusters: List[EchoCluster]
    region_max_dbz: float
    has_strong: bool


def detect_clusters(
    refl: np.ndarray,
    region_mask: np.ndarray,
    lat_arr: np.ndarray,
    lon_arr: np.ndarray,
    *,
    strong_dbz: float = 35.0,
    min_points: int = 4,
    level_step: float = 5.0,
    dist_to_city_km: Optional[np.ndarray] = None,
) -> DetectResult:
    """在 region_mask 内检测强回波块；dist_to_city_km 用于计算块到市界最近距离。"""
    strong = np.isfinite(refl) & (refl >= strong_dbz) & region_mask
    region_vals = refl[region_mask & np.isfinite(refl)]
    region_max = float(region_vals.max()) if region_vals.size else float("nan")

    if not strong.any():
        return DetectResult(clusters=[], region_max_dbz=region_max, has_strong=False)

    labeled, n = ndimage.label(strong, structure=_FOUR_CONN)
    clusters: List[EchoCluster] = []
    for lab in range(1, n + 1):
        sel = labeled == lab
        npts = int(sel.sum())
        if npts < min_points:
            continue
        rows, cols = np.where(sel)
        vals = refl[rows, cols]
        max_dbz = float(np.nanmax(vals))
        # 代表强度取块内第 min_points 高的格点值，避免孤立尖峰（多为杂波）顶高整块等级。
        robust_dbz = robust_value(vals, min_points)
        if not np.isfinite(robust_dbz):
            robust_dbz = max_dbz
        clat = float(np.mean(lat_arr[rows]))
        clon = float(np.mean(lon_arr[cols]))
        min_dist = None
        if dist_to_city_km is not None:
            d = dist_to_city_km[rows, cols]
            d = d[np.isfinite(d)]
            min_dist = float(d.min()) if d.size else None
        clusters.append(EchoCluster(
            label=lab,
            n_points=npts,
            max_dbz=max_dbz,
            robust_dbz=robust_dbz,
            level_dbz=level_floor(robust_dbz, level_step, strong_dbz),
            centroid_lat=clat,
            centroid_lon=clon,
            rows=rows,
            cols=cols,
            min_dist_to_city_km=min_dist,
        ))

    # 排序：代表强度 > 单点峰值 > 块面积（格点数）。
    clusters.sort(key=lambda c: (c.robust_dbz, c.max_dbz, c.n_points), reverse=True)
    return DetectResult(
        clusters=clusters,
        region_max_dbz=region_max,
        has_strong=len(clusters) > 0,
    )
