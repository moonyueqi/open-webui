"""离线脚本：从中国行政区划区县级 shp 抽取苏州下属 10 个区/县级市，
生成 fengche/warning_server/data/districts.geojson。

用法（在仓库根目录执行）：

    python -m fengche.warning_server.scripts.build_geojson_from_shp

或直接：

    cd fengche/warning_server
    python -m scripts.build_geojson_from_shp

可选环境变量：
- COUNTY_SHP_PATH: 指定区县级 shp 路径（默认 fengche/shp_raw/县.shp）。
- SHP_ENCODING:    dbf 编码（默认 gbk）。

依赖：pyshp（纯 Python，不需要 GDAL/geopandas）。
    pip install pyshp

输出 GeoJSON 的每个 feature 都带 properties.code（拼音简码，与原本 gaoxin/gusu/sip 兼容），
便于 OWUI 上的接口与既有调用约定一致。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import shapefile  # pyshp


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
OUTPUT_PATH = PROJECT_ROOT / "data" / "districts.geojson"
# warning_server/scripts/ -> warning_server/ -> fengche/ -> fengche/shp_raw/
FENGCHE_ROOT = PROJECT_ROOT.parent
DEFAULT_SHP_PATH = (
    Path(os.environ.get("COUNTY_SHP_PATH")
         or FENGCHE_ROOT / "shp_raw" / "县.shp")
)
ENCODING = os.environ.get("SHP_ENCODING", "gbk")


# 县代码（adcode）→ 我们工程内部 code、展示名
# 注意：苏州工业园区 adcode 在 shp 里是 320571（区划上属吴中区），保留独立多边形。
SUZHOU_DISTRICTS: Dict[int, Dict[str, str]] = {
    320505: {"code": "huqiu",        "name": "虎丘区（高新区）"},
    320506: {"code": "wuzhong",      "name": "吴中区"},
    320507: {"code": "xiangcheng",   "name": "相城区"},
    320508: {"code": "gusu",         "name": "姑苏区"},
    320509: {"code": "wujiang",      "name": "吴江区"},
    320571: {"code": "sip",          "name": "苏州工业园区"},
    320581: {"code": "changshu",     "name": "常熟市"},
    320582: {"code": "zhangjiagang", "name": "张家港市"},
    320583: {"code": "kunshan",      "name": "昆山市"},
    320585: {"code": "taicang",      "name": "太仓市"},
}

# 历史兼容：原工具用的 code "gaoxin" 对应虎丘区
# build 时一并写入 properties.aliases，运行时如果旧调用方传 districts=gaoxin 也能匹配
LEGACY_ALIASES: Dict[str, List[str]] = {
    "huqiu": ["gaoxin"],  # 老接口可能用 gaoxin
}


def _shape_to_geojson_geometry(shp_shape: Any) -> Dict[str, Any]:
    """把 pyshp 的 Polygon 形状转成 GeoJSON Polygon / MultiPolygon。

    pyshp 的 Polygon 形状 parts 是各 ring 的起点索引，points 是统一坐标列表。
    我们把每个 ring 当成一个外环（不区分洞）；多个 ring 时输出 MultiPolygon。
    """
    parts = list(shp_shape.parts) + [len(shp_shape.points)]
    rings: List[List[List[float]]] = []
    for i in range(len(parts) - 1):
        coords = [list(p) for p in shp_shape.points[parts[i]: parts[i + 1]]]
        if len(coords) < 4:
            continue
        # 闭合
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        rings.append(coords)

    if not rings:
        raise ValueError("shape has no usable rings")

    if len(rings) == 1:
        return {"type": "Polygon", "coordinates": rings}
    return {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}


def main() -> int:
    shp_path = DEFAULT_SHP_PATH
    if not shp_path.exists():
        print(f"[ERROR] shp not found: {shp_path}")
        return 1

    print(f"reading {shp_path} (encoding={ENCODING}) ...")
    sf = shapefile.Reader(str(shp_path), encoding=ENCODING)
    field_names = [f[0] for f in sf.fields[1:]]

    def field_idx(name: str) -> int:
        try:
            return field_names.index(name)
        except ValueError as e:
            raise RuntimeError(
                f"shp 缺少字段 '{name}'（实际字段：{field_names}）"
            ) from e

    idx_xian_dm = field_idx("县代码")
    idx_xian = field_idx("县")
    idx_shi = field_idx("市")

    found: Dict[int, Dict[str, Any]] = {}
    for shape_rec in sf.iterShapeRecords():
        rec = shape_rec.record
        try:
            xian_dm = int(rec[idx_xian_dm])
        except (TypeError, ValueError):
            continue
        if xian_dm not in SUZHOU_DISTRICTS:
            continue
        info = SUZHOU_DISTRICTS[xian_dm]
        code = info["code"]
        try:
            geom = _shape_to_geojson_geometry(shape_rec.shape)
        except ValueError as e:
            print(f"  [WARN] {info['name']} ({xian_dm}): {e}")
            continue
        props: Dict[str, Any] = {
            "code": code,
            "name": info["name"],
            "adcode": str(xian_dm),
            "official_name": str(rec[idx_xian]).strip(),
            "city": str(rec[idx_shi]).strip(),
            "source": "shp_china_county",
        }
        aliases = LEGACY_ALIASES.get(code)
        if aliases:
            props["aliases"] = aliases
        found[xian_dm] = {
            "type": "Feature",
            "properties": props,
            "geometry": geom,
        }
        print(f"  + {info['name']} (adcode={xian_dm}, code={code})")

    missing = [
        f"{ad}={info['name']}"
        for ad, info in SUZHOU_DISTRICTS.items()
        if ad not in found
    ]
    if missing:
        print(f"[WARN] 未在 shp 中找到的区：{missing}")

    if not found:
        print("[ERROR] no Suzhou districts matched; abort")
        return 2

    fc = {
        "type": "FeatureCollection",
        "_note": (
            "由 scripts/build_geojson_from_shp.py 从 shp/县.shp 抽取生成，"
            "覆盖苏州市下属全部 10 个区/县级市。坐标系：WGS84。"
        ),
        "_source": "shp_china_county",
        # 保持稳定的输出顺序：按 adcode 升序
        "features": [found[k] for k in sorted(found.keys())],
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(fc, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nwrote {OUTPUT_PATH} ({len(found)} features)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
