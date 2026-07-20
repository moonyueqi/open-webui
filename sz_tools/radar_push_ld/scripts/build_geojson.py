"""离线脚本：从 shp 生成 radar_push 运行时所需的 geojson。

产出（写入 radar_push/data/）：
  - suzhou_city.geojson      苏州市界（单 Feature，区县合并）
  - suzhou_buffer.geojson    苏州市外 50km 缓冲区（环形：buffer - 市界）
  - districts.geojson        苏州 10 个区/县级市（带 code/name）
  - townships.geojson        苏州乡镇（带 district_code/township_name，排除水系）
  - background.geojson       周边省界/市界底图（裁剪到苏州周边 bbox）
  - upstream_cities.geojson  苏州周边上游地级市边界（带 name，用于精确定位回波来源城市）

用法（在 radar_push/ 目录或仓库根执行，需 leadsee-webui 环境）：
    python -m radar_push.scripts.build_geojson
或：
    cd radar_push && python scripts/build_geojson.py

依赖：geopandas / shapely / pyproj。源 shp 路径可用环境变量覆盖。
坐标系统一输出 WGS84(EPSG:4326)。50km 缓冲在投影坐标系 EPSG:32651 下计算。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict

import geopandas as gpd
from shapely.geometry import mapping
from shapely.ops import unary_union


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
DATA_DIR = PROJECT_ROOT / "data"

# 源 shp 默认位置（可被环境变量覆盖）
_SHP_BASE = Path(
    os.environ.get(
        "RADAR_SHP_BASE",
        str(PROJECT_ROOT.parent / "基于雷达实况和外推产品形成企业微信自动推送提示"),
    )
)
COUNTY_SHP = Path(os.environ.get("COUNTY_SHP", str(_SHP_BASE / "最新2021年全国行政区划" / "shp" / "县.shp")))
TOWNSHIP_SHP = Path(os.environ.get("TOWNSHIP_SHP", str(_SHP_BASE / "苏州乡镇" / "苏州乡镇" / "苏州乡镇.shp")))
PROVINCE_SHP = Path(os.environ.get("PROVINCE_SHP", str(_SHP_BASE / "最新2021年全国行政区划" / "shp" / "省.shp")))
CITY_SHP = Path(os.environ.get("CITY_SHP", str(_SHP_BASE / "最新2021年全国行政区划" / "shp" / "市.shp")))
ENCODING = os.environ.get("SHP_ENCODING", "GBK")

# 背景底图裁剪范围（苏州周边，覆盖画面 extent 即可）
BG_BBOX = (118.5, 29.5, 123.5, 33.5)  # (minx, miny, maxx, maxy)

BUFFER_KM = float(os.environ.get("BUFFER_KM", "50"))
UTM_EPSG = 32651  # WGS84 / UTM zone 51N，覆盖苏州

# 县代码(adcode) -> 内部 code / 展示名
SUZHOU_DISTRICTS: Dict[int, Dict[str, str]] = {
    320505: {"code": "huqiu",        "name": "高新区"},
    320506: {"code": "wuzhong",      "name": "吴中区"},
    320507: {"code": "xiangcheng",   "name": "相城区"},
    320508: {"code": "gusu",         "name": "姑苏区"},
    320509: {"code": "wujiang",      "name": "吴江区"},
    320571: {"code": "sip",          "name": "苏州工业园区"},
    320581: {"code": "changshu",     "name": "常熟市"},
    320582: {"code": "zhangjiagang", "name": "张家港市"},
    320583: {"code": "kunshan",      "name": "昆山市"},
    320585: {"code": "taicang",      "name": "太仓市"},
    # 乡镇 shp 中吴中区部分要素 super_AREA 可能为 320586/320587（吴江/吴中历史划分），
    # 在乡镇映射里另行兼容。
}

# 乡镇 shp 用 xian(区县名) 字段归属区县（比 super_AREA adcode 更直观可靠）
TOWNSHIP_XIAN_TO_CODE: Dict[str, str] = {
    "姑苏区": "gusu",
    "苏州工业园区": "sip",
    "虎丘区": "huqiu",  # shp 源 xian 字段仍为"虎丘区"，此处为匹配键，勿改；对外展示名见 SUZHOU_DISTRICTS（高新区）
    "吴中区": "wuzhong",
    "相城区": "xiangcheng",
    "吴江区": "wujiang",
    "常熟市": "changshu",
    "张家港市": "zhangjiagang",
    "昆山市": "kunshan",
    "太仓市": "taicang",
}

# 区县展示名（与 districts 一致）
CODE_TO_NAME: Dict[str, str] = {v["code"]: v["name"] for v in SUZHOU_DISTRICTS.values()}

EXCLUDE_TOWNSHIP_CLASS = {"水系"}

# 苏州周边"上游/邻近"地级市（用于回波来源精确定位）。
# 名称需与市 shp 的"市"字段一致（含"市"后缀）。
UPSTREAM_CITY_NAMES = [
    "无锡市", "常州市", "泰州市", "南通市", "上海市", "嘉兴市", "湖州市",
]


def _find_col(gdf: gpd.GeoDataFrame, *candidates: str) -> str:
    for c in candidates:
        if c in gdf.columns:
            return c
    raise RuntimeError(f"未找到字段 {candidates}，实际列：{list(gdf.columns)}")


def _write(name: str, fc: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / name
    out.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out} ({len(fc.get('features', []))} features)")


def build_districts(county: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    code_col = _find_col(county, "县代码")
    county = county.to_crs(epsg=4326)
    rows = []
    features = []
    for _, rec in county.iterrows():
        try:
            adcode = int(rec[code_col])
        except (TypeError, ValueError):
            continue
        if adcode not in SUZHOU_DISTRICTS:
            continue
        info = SUZHOU_DISTRICTS[adcode]
        rows.append({"code": info["code"], "name": info["name"], "geometry": rec.geometry})
        features.append({
            "type": "Feature",
            "properties": {"code": info["code"], "name": info["name"], "adcode": str(adcode)},
            "geometry": mapping(rec.geometry),
        })
    _write("districts.geojson", {"type": "FeatureCollection", "features": features})
    return gpd.GeoDataFrame(rows, crs="EPSG:4326")


def build_city_and_buffer(districts: gpd.GeoDataFrame) -> None:
    # 市界 = 10 区合并
    city_union = unary_union(districts.geometry.values)
    _write("suzhou_city.geojson", {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"name": "苏州市"},
            "geometry": mapping(city_union),
        }],
    })

    # 缓冲区：在 UTM 下 buffer 后减去市界，得到"市外 50km 环"
    city_utm = gpd.GeoSeries([city_union], crs="EPSG:4326").to_crs(epsg=UTM_EPSG).iloc[0]
    buffer_utm = city_utm.buffer(BUFFER_KM * 1000.0)
    ring_utm = buffer_utm.difference(city_utm)
    ring_wgs = gpd.GeoSeries([ring_utm], crs=f"EPSG:{UTM_EPSG}").to_crs(epsg=4326).iloc[0]
    full_wgs = gpd.GeoSeries([buffer_utm], crs=f"EPSG:{UTM_EPSG}").to_crs(epsg=4326).iloc[0]
    _write("suzhou_buffer.geojson", {
        "type": "FeatureCollection",
        "_buffer_km": BUFFER_KM,
        "features": [
            {"type": "Feature", "properties": {"name": "市外50km环", "kind": "ring"},
             "geometry": mapping(ring_wgs)},
            {"type": "Feature", "properties": {"name": "市界+50km整体", "kind": "full"},
             "geometry": mapping(full_wgs)},
        ],
    })


def build_townships() -> None:
    twp = gpd.read_file(str(TOWNSHIP_SHP), encoding=ENCODING)
    # 该 shp CRS 为 CGCS2000(近似 WGS84)，统一转 4326
    try:
        twp = twp.set_crs(epsg=4326, allow_override=True)
    except Exception:
        pass
    twp = twp.to_crs(epsg=4326)

    class_col = _find_col(twp, "class")
    xian_col = _find_col(twp, "xian")
    zhen_col = _find_col(twp, "zhen")
    area_col = _find_col(twp, "AREACODE")

    features = []
    for _, rec in twp.iterrows():
        cls = str(rec[class_col]).strip()
        if cls in EXCLUDE_TOWNSHIP_CLASS:
            continue
        xian = str(rec[xian_col]).strip()
        district_code = TOWNSHIP_XIAN_TO_CODE.get(xian)
        if district_code is None:
            print(f"  [WARN] 乡镇 xian={xian} 未映射区县，跳过 {rec[zhen_col]}")
            continue
        features.append({
            "type": "Feature",
            "properties": {
                "township_name": str(rec[zhen_col]).strip(),
                "district_code": district_code,
                "district_name": CODE_TO_NAME.get(district_code, district_code),
                "areacode": str(rec[area_col]),
                "class": cls,
            },
            "geometry": mapping(rec.geometry),
        })
    _write("townships.geojson", {"type": "FeatureCollection", "features": features})


def build_background() -> None:
    """生成周边省界 / 市界底图（裁剪到苏州周边 bbox），供绘图作背景。"""
    from shapely.geometry import box

    clip = box(*BG_BBOX)

    def _clip_features(shp_path: Path, kind: str):
        if not shp_path.exists():
            print(f"  [WARN] background shp 缺失，跳过 {kind}: {shp_path}")
            return []
        gdf = gpd.read_file(str(shp_path), encoding=ENCODING).to_crs(epsg=4326)
        feats = []
        for _, rec in gdf.iterrows():
            geom = rec.geometry
            if geom is None or geom.is_empty:
                continue
            inter = geom.intersection(clip)
            if inter.is_empty:
                continue
            feats.append({
                "type": "Feature",
                "properties": {"kind": kind},
                "geometry": mapping(inter),
            })
        return feats

    province = _clip_features(PROVINCE_SHP, "province")
    city = _clip_features(CITY_SHP, "city")
    _write("background.geojson", {
        "type": "FeatureCollection",
        "_bbox": list(BG_BBOX),
        "features": province + city,
    })


def build_upstream_cities() -> None:
    """生成苏州周边上游地级市边界（带 name），用于精确定位回波来源城市。

    取市 shp 中 UPSTREAM_CITY_NAMES 列出的城市，裁剪到苏州周边 bbox（与背景同范围，
    足够覆盖 50km 缓冲区），输出 WGS84 多边形。判定时用"回波格点落在哪个市"来定位。
    """
    from shapely.geometry import box

    if not CITY_SHP.exists():
        print(f"  [WARN] 市 shp 缺失，跳过 upstream_cities: {CITY_SHP}")
        return

    clip = box(*BG_BBOX)
    gdf = gpd.read_file(str(CITY_SHP), encoding=ENCODING).to_crs(epsg=4326)
    name_col = _find_col(gdf, "市", "市名", "name", "NAME")

    features = []
    for _, rec in gdf.iterrows():
        name = str(rec[name_col]).strip()
        if name not in UPSTREAM_CITY_NAMES:
            continue
        geom = rec.geometry
        if geom is None or geom.is_empty:
            continue
        inter = geom.intersection(clip)
        if inter.is_empty:
            continue
        # 展示用短名：去掉末尾"市"
        short = name[:-1] if name.endswith("市") else name
        features.append({
            "type": "Feature",
            "properties": {"name": short, "full_name": name},
            "geometry": mapping(inter),
        })

    found = {f["properties"]["full_name"] for f in features}
    missing = [n for n in UPSTREAM_CITY_NAMES if n not in found]
    if missing:
        print(f"  [WARN] 部分上游城市未在 shp 中匹配到：{missing}")
    _write("upstream_cities.geojson", {"type": "FeatureCollection", "features": features})


def main() -> int:
    if not COUNTY_SHP.exists():
        print(f"[ERROR] county shp not found: {COUNTY_SHP}")
        return 1
    if not TOWNSHIP_SHP.exists():
        print(f"[ERROR] township shp not found: {TOWNSHIP_SHP}")
        return 1

    print(f"county   : {COUNTY_SHP}")
    print(f"township : {TOWNSHIP_SHP}")
    county = gpd.read_file(str(COUNTY_SHP), encoding=ENCODING)
    districts = build_districts(county)
    build_city_and_buffer(districts)
    build_townships()
    build_background()
    build_upstream_cities()
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
