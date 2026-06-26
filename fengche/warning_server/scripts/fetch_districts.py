"""[已废弃] 一次性脚本：调用高德 District API 拉取三区行政边界。

新版工程已改用 `scripts/build_geojson_from_shp.py` 从离线 shp 直接抽取
苏州全部 10 个区/县级市的精确多边形，不再依赖高德 API 与网络。

如仅有 3 个属地区的旧需求，可继续使用此脚本，但建议改用新脚本以获得统一边界。

使用方法（需要联网 + 高德 Web 服务 key）：

    set AMAP_KEY=你的高德key
    python scripts/fetch_districts.py

输出：fengche_warning_server/data/districts.geojson（FeatureCollection）。

注意：
- 高德 District API 仅支持 省/市/区县 级，街道级不返回 polyline；
- 苏州工业园区不是一级行政区，无独立 adcode，先尝试 keywords='苏州工业园区' 直接搜，
  如果拿不到 polyline，就保留仓库自带的 bbox 版本（脚本只覆盖能成功的 feature）。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import List, Optional


AMAP_URL = "https://restapi.amap.com/v3/config/district"
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
OUTPUT_PATH = PROJECT_ROOT / "data" / "districts.geojson"


DISTRICTS = [
    {"code": "gaoxin", "name": "高新区（虎丘区）", "adcode": "320505", "keywords": "320505"},
    {"code": "gusu",   "name": "姑苏区",           "adcode": "320508", "keywords": "320508"},
    {"code": "sip",    "name": "工业园区",         "adcode": "320500", "keywords": "苏州工业园区"},
]


def _parse_polyline(polyline: str) -> List[List[List[float]]]:
    """高德返回的 polyline 用 ';' 分隔点、',' 分隔 lng/lat；多块用 '|' 分隔。

    返回 GeoJSON Polygon 风格的 coordinates：[[ [lng, lat], ... ]]。
    若有多块，返回外环列表（不区分洞，按外环处理）。
    """
    rings: List[List[List[float]]] = []
    for piece in polyline.split("|"):
        coords: List[List[float]] = []
        for pair in piece.split(";"):
            if not pair.strip():
                continue
            lng_s, lat_s = pair.split(",")
            coords.append([float(lng_s), float(lat_s)])
        if coords:
            # 确保闭合
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            rings.append(coords)
    return rings


def fetch_one(amap_key: str, keywords: str) -> Optional[List[List[List[float]]]]:
    params = {
        "key": amap_key,
        "keywords": keywords,
        "subdistrict": "0",
        "extensions": "all",
    }
    url = f"{AMAP_URL}?{urllib.parse.urlencode(params)}"
    print(f"  GET {url}")
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  request failed: {e}")
        return None

    if data.get("status") != "1":
        print(f"  amap error: {data}")
        return None

    districts = data.get("districts") or []
    if not districts:
        print("  no districts returned")
        return None

    polyline = districts[0].get("polyline")
    if not polyline:
        print("  no polyline (probably not a district-level area)")
        return None

    return _parse_polyline(polyline)


def main() -> int:
    amap_key = os.environ.get("AMAP_KEY")
    if not amap_key:
        print("[ERROR] AMAP_KEY environment variable not set.")
        return 1

    # 加载现有的兜底 GeoJSON，作为新版本的基底
    if not OUTPUT_PATH.exists():
        print(f"[ERROR] {OUTPUT_PATH} not found")
        return 1
    fc = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))

    # 用 code 索引现有 features
    features_by_code = {f["properties"]["code"]: f for f in fc["features"]}

    any_updated = False
    for d in DISTRICTS:
        print(f"[{d['code']}] fetching {d['keywords']} ...")
        rings = fetch_one(amap_key, d["keywords"])
        if not rings:
            print(f"[{d['code']}] keep bbox fallback")
            continue
        # 单块走 Polygon，多块走 MultiPolygon（每块当外环）
        if len(rings) == 1:
            geom = {"type": "Polygon", "coordinates": rings}
        else:
            geom = {
                "type": "MultiPolygon",
                "coordinates": [[r] for r in rings],
            }
        features_by_code[d["code"]] = {
            "type": "Feature",
            "properties": {
                "code": d["code"],
                "name": d["name"],
                "adcode": d["adcode"],
                "source": "amap",
            },
            "geometry": geom,
        }
        any_updated = True
        print(f"[{d['code']}] updated with amap polyline")

    if not any_updated:
        print("nothing was updated; output unchanged.")
        return 0

    new_fc = {
        "type": "FeatureCollection",
        "_note": "由 scripts/fetch_districts.py 通过高德 District API 生成；未能成功的区保留 bbox 兜底。",
        "_source": "amap_with_bbox_fallback",
        "features": list(features_by_code.values()),
    }
    OUTPUT_PATH.write_text(
        json.dumps(new_fc, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nwrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
