"""加载行政区 GeoJSON，针对特定的 lat/lon 网格生成各区的格点布尔掩膜。

掩膜是 shape=(n_lat, n_lon) 的 bool 数组，True 表示该格点在该区内。
首次为某个网格生成掩膜后会缓存到内存，后续相同网格直接复用。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from shapely.geometry import Point, shape
from shapely.prepared import prep


log = logging.getLogger(__name__)


DEFAULT_GEOJSON_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "districts.geojson"
)


@dataclass(frozen=True)
class DistrictMask:
    code: str
    name: str
    mask: np.ndarray         # (n_lat, n_lon) bool
    n_points: int
    source: str              # "amap" / "bbox_fallback" / etc.


def _grid_key(lat_arr: np.ndarray, lon_arr: np.ndarray) -> tuple:
    """用网格的尺寸+四角值生成缓存键（避免对整个数组做 hash）。"""
    return (
        int(lat_arr.size), int(lon_arr.size),
        float(lat_arr[0]), float(lat_arr[-1]),
        float(lon_arr[0]), float(lon_arr[-1]),
    )


class DistrictMaskRegistry:
    """各区的 GeoJSON 多边形 + 按网格生成的掩膜缓存。"""

    def __init__(self, geojson_path: Optional[str] = None):
        path = Path(geojson_path) if geojson_path else DEFAULT_GEOJSON_PATH
        if not path.exists():
            raise FileNotFoundError(
                f"districts.geojson not found at {path}. "
                f"Run scripts/fetch_districts.py to generate (or use bbox fallback)."
            )
        with open(path, "r", encoding="utf-8") as f:
            fc = json.load(f)

        self._geojson_path = str(path)
        self._source = fc.get("_source", "unknown")

        # code -> (shapely geom, prepared geom, name, source)
        # 同一区可有多个别名（历史 code），全部注册到同一份几何上
        self._geoms: Dict[str, tuple] = {}
        self._primary_codes: List[str] = []
        for feat in fc.get("features", []):
            props = feat.get("properties", {})
            code = props.get("code")
            if not code:
                continue
            geom = shape(feat["geometry"])
            entry = (
                geom,
                prep(geom),
                props.get("name", code),
                props.get("source", "unknown"),
            )
            self._geoms[code] = entry
            self._primary_codes.append(code)
            for alias in props.get("aliases", []) or []:
                if alias and alias not in self._geoms:
                    self._geoms[alias] = entry

        log.info(
            "DistrictMaskRegistry loaded %d features from %s (source=%s)",
            len(self._geoms), path, self._source,
        )

        # 网格键 -> { code: DistrictMask }
        self._cache: Dict[tuple, Dict[str, DistrictMask]] = {}

    @property
    def geojson_path(self) -> str:
        return self._geojson_path

    @property
    def overall_source(self) -> str:
        return self._source

    def district_codes(self) -> List[str]:
        """返回主 code 列表（不含别名）。"""
        return list(self._primary_codes)

    def resolve_code(self, code: str) -> str:
        """把别名解析回主 code；如果传入的本身就是主 code 或未知 code 则原样返回。

        别名共享同一个 geometry 对象，因此只要在 _geoms 中找得到，
        就遍历 _primary_codes 找哪个主 code 指向同一对象。
        """
        if code in self._primary_codes:
            return code
        entry = self._geoms.get(code)
        if entry is None:
            return code
        for primary in self._primary_codes:
            if self._geoms[primary] is entry:
                return primary
        return code

    def district_name(self, code: str) -> str:
        if code not in self._geoms:
            return code
        return self._geoms[code][2]

    def per_district_source(self) -> Dict[str, str]:
        return {code: self._geoms[code][3] for code in self._primary_codes}

    def build_for_grid(
        self,
        lat_arr: np.ndarray,
        lon_arr: np.ndarray,
    ) -> Dict[str, DistrictMask]:
        """根据给定网格生成（或返回缓存的）所有主 code 的掩膜。

        别名 code 不会单独生成 mask，运行时由调用方按主 code 解引用。
        """
        key = _grid_key(lat_arr, lon_arr)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        lon_grid, lat_grid = np.meshgrid(lon_arr, lat_arr)
        flat_lon = lon_grid.ravel()
        flat_lat = lat_grid.ravel()
        n_lat, n_lon = lat_arr.size, lon_arr.size

        result: Dict[str, DistrictMask] = {}
        for code in self._primary_codes:
            geom, prepared, name, source = self._geoms[code]
            minx, miny, maxx, maxy = geom.bounds
            in_bbox = (
                (flat_lon >= minx) & (flat_lon <= maxx) &
                (flat_lat >= miny) & (flat_lat <= maxy)
            )
            mask_flat = np.zeros(flat_lon.size, dtype=bool)
            candidate_idx = np.where(in_bbox)[0]
            for idx in candidate_idx:
                if prepared.intersects(Point(flat_lon[idx], flat_lat[idx])):
                    mask_flat[idx] = True
            mask_2d = mask_flat.reshape(n_lat, n_lon)
            n_points = int(mask_2d.sum())
            result[code] = DistrictMask(
                code=code,
                name=name,
                mask=mask_2d,
                n_points=n_points,
                source=source,
            )
            log.info(
                "  district %s (%s): %d grid points (source=%s)",
                code, name, n_points, source,
            )

        self._cache[key] = result
        return result
