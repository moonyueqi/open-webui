"""强回波块检测：在掩膜范围内对 >= 阈值的格点做四连通连通域分析。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from scipy import ndimage

_FOUR_CONN = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool)


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

    用于把所有实况判断从"单格点达标"统一为"连片≥min_points 格点达标"：
    先全网格做 refl>=strong_dbz 的四连通标注，再剔除小于 min_points 的连通域，
    剩余格点即视为有效强回波格点，可与任意区域 mask 求交后再判断。
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
    max_dbz: float
    level_dbz: int
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
            level_dbz=level_floor(max_dbz, level_step, strong_dbz),
            centroid_lat=clat,
            centroid_lon=clon,
            rows=rows,
            cols=cols,
            min_dist_to_city_km=min_dist,
        ))

    clusters.sort(key=lambda c: c.max_dbz, reverse=True)
    return DetectResult(
        clusters=clusters,
        region_max_dbz=region_max,
        has_strong=len(clusters) > 0,
    )
