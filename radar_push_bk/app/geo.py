"""地理掩膜：按雷达网格生成苏州市界/缓冲区/区县/乡镇的格点布尔掩膜，并算格点到市界距离。

先用 bbox 预筛候选格点再做 point-in-polygon；结果按网格缓存复用。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# 经纬度→km 的粗略换算（苏州约 31°N）
_KM_PER_DEG_LAT = 111.32
_KM_PER_DEG_LON = 111.32 * np.cos(np.deg2rad(31.3))


@dataclass(frozen=True)
class GridMasks:
    lat_arr: np.ndarray
    lon_arr: np.ndarray
    buffer_full: np.ndarray                 # 市界+50km 整体检测范围
    city: np.ndarray
    districts: Dict[str, np.ndarray]        # code -> bool mask
    townships: List[Tuple[str, str, np.ndarray]]  # (township_name, district_code, mask)
    dist_to_city_km: np.ndarray             # 格点到市界近似距离 km（市内为 0）
    district_names: Dict[str, str]
    upstream_cities: List[Tuple[str, np.ndarray]]  # (city_name, mask)


def _load_fc(name: str) -> dict:
    p = DATA_DIR / name
    if not p.exists():
        raise FileNotFoundError(
            f"{p} 不存在，请先运行 scripts/build_geojson.py 生成 geojson。"
        )
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


class GeoRegistry:
    def __init__(self) -> None:
        city_fc = _load_fc("suzhou_city.geojson")
        buffer_fc = _load_fc("suzhou_buffer.geojson")
        districts_fc = _load_fc("districts.geojson")
        townships_fc = _load_fc("townships.geojson")

        self.city_geom = unary_union(
            [shape(f["geometry"]) for f in city_fc["features"]]
        )

        full = [
            shape(f["geometry"])
            for f in buffer_fc["features"]
            if f.get("properties", {}).get("kind") == "full"
        ]
        if not full:
            full = [shape(f["geometry"]) for f in buffer_fc["features"]]
        self.buffer_full_geom = unary_union(full)

        self.districts: Dict[str, tuple] = {}
        self.district_names: Dict[str, str] = {}
        for f in districts_fc["features"]:
            code = f["properties"]["code"]
            geom = shape(f["geometry"])
            self.districts[code] = (geom, prep(geom))
            self.district_names[code] = f["properties"].get("name", code)

        self.townships: List[tuple] = []
        for f in townships_fc["features"]:
            name = f["properties"]["township_name"]
            dcode = f["properties"]["district_code"]
            geom = shape(f["geometry"])
            self.townships.append((name, dcode, geom, prep(geom)))

        self.upstream_cities: List[tuple] = []
        try:
            upstream_fc = _load_fc("upstream_cities.geojson")
            for f in upstream_fc["features"]:
                name = f["properties"].get("name", "")
                geom = shape(f["geometry"])
                self.upstream_cities.append((name, geom, prep(geom)))
        except FileNotFoundError:
            log.warning("upstream_cities.geojson 缺失，上游来源将退回默认城市列表")

        self._prep_buffer = prep(self.buffer_full_geom)
        self._prep_city = prep(self.city_geom)
        self._cache: Dict[tuple, GridMasks] = {}

        log.info(
            "GeoRegistry loaded: %d districts, %d townships",
            len(self.districts), len(self.townships),
        )

    @staticmethod
    def _grid_key(lat_arr: np.ndarray, lon_arr: np.ndarray) -> tuple:
        return (
            int(lat_arr.size), int(lon_arr.size),
            float(lat_arr[0]), float(lat_arr[-1]),
            float(lon_arr[0]), float(lon_arr[-1]),
        )

    def build_for_grid(self, lat_arr: np.ndarray, lon_arr: np.ndarray) -> GridMasks:
        key = self._grid_key(lat_arr, lon_arr)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        n_lat, n_lon = lat_arr.size, lon_arr.size
        lon_grid, lat_grid = np.meshgrid(lon_arr, lat_arr)

        minx, miny, maxx, maxy = self.buffer_full_geom.bounds
        in_bbox = (
            (lon_grid >= minx) & (lon_grid <= maxx)
            & (lat_grid >= miny) & (lat_grid <= maxy)
        )
        cand_idx = np.argwhere(in_bbox)
        log.info("grid %dx%d: %d candidate points in buffer bbox",
                 n_lat, n_lon, cand_idx.shape[0])

        buffer_mask = np.zeros((n_lat, n_lon), dtype=bool)
        city_mask = np.zeros((n_lat, n_lon), dtype=bool)
        district_masks = {c: np.zeros((n_lat, n_lon), dtype=bool) for c in self.districts}
        township_masks = [
            np.zeros((n_lat, n_lon), dtype=bool) for _ in self.townships
        ]
        upstream_masks = [
            np.zeros((n_lat, n_lon), dtype=bool) for _ in self.upstream_cities
        ]
        dist_km = np.full((n_lat, n_lon), np.inf, dtype=np.float32)

        city_boundary = self.city_geom.boundary

        for (i, j) in cand_idx:
            pt = Point(float(lon_grid[i, j]), float(lat_grid[i, j]))
            if not self._prep_buffer.intersects(pt):
                continue
            buffer_mask[i, j] = True

            in_city = self._prep_city.intersects(pt)
            if in_city:
                city_mask[i, j] = True
                dist_km[i, j] = 0.0
                for code, (_, pc) in self.districts.items():
                    if pc.intersects(pt):
                        district_masks[code][i, j] = True
                for ti, (_, _, _, ptp) in enumerate(self.townships):
                    if ptp.intersects(pt):
                        township_masks[ti][i, j] = True
            else:
                d_deg = pt.distance(city_boundary)
                dist_km[i, j] = float(
                    d_deg * np.sqrt(_KM_PER_DEG_LAT * _KM_PER_DEG_LON)
                )
                for ui, (_, _, pup) in enumerate(self.upstream_cities):
                    if pup.intersects(pt):
                        upstream_masks[ui][i, j] = True
                        break

        townships_out = [
            (self.townships[ti][0], self.townships[ti][1], township_masks[ti])
            for ti in range(len(self.townships))
        ]
        upstream_out = [
            (self.upstream_cities[ui][0], upstream_masks[ui])
            for ui in range(len(self.upstream_cities))
        ]

        masks = GridMasks(
            lat_arr=lat_arr,
            lon_arr=lon_arr,
            buffer_full=buffer_mask,
            city=city_mask,
            districts=district_masks,
            townships=townships_out,
            dist_to_city_km=dist_km,
            district_names=dict(self.district_names),
            upstream_cities=upstream_out,
        )
        self._cache[key] = masks
        return masks
