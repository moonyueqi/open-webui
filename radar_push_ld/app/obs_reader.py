"""解析地面站点实况 xlsx（PROCESSED_YYYYMMDDHHMM.xlsx）。

文件为某一时刻的全省（江苏-上海一带）站点观测快照，每行一个站。关键列：
  · 站点ID / 纬度 / 经度 / 城市 / 站点名称 / 区县 / 时间
  · 小时降水量(mm)        —— 过去 1 小时累计雨量，即「小时雨强」
  · 最大瞬时风速(m/s)     —— 瞬时风（极大风）主用
  · 最大风速(m/s)         —— 备用风字段

缺测填充值为 999999（及以上），统一置 NaN 不参与统计。
列名按「包含关键字」稳健匹配，避免不同批次表头细微差异导致 KeyError。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# 缺测填充阈值：数值 >= 此值视为缺测（表内为 999999）。
MISSING_THRESHOLD = 999990.0


@dataclass(frozen=True)
class ObsStation:
    station_id: str
    name: str
    city: str               # 城市（如「苏州市」「无锡市」「上海市」）
    county: str             # 区县（如「吴中区」「宜兴市」）
    lat: float
    lon: float
    hour_rain_mm: float     # 小时雨强（过去1h累计），缺测为 NaN
    gust_ms: float          # 瞬时风（极大风），缺测为 NaN


# 各字段的候选列名关键字（按优先级匹配第一个命中的列）。
_COL_KEYS = {
    "station_id": ["站点ID", "站号", "区站号"],
    "name": ["站点名称", "站名"],
    "city": ["城市", "市"],
    "county": ["区县", "县", "区"],
    "lat": ["纬度"],
    "lon": ["经度"],
    "hour_rain": ["小时降水量", "小时雨量"],
    # 风：用「最大瞬时风速」（不使用最大阵风）；可由调用方通过 gust_col 覆盖
    "gust": ["最大瞬时风速", "极大风速", "最大风速"],
}


def _find_col(df: pd.DataFrame, keys: List[str]) -> Optional[str]:
    cols = [str(c) for c in df.columns]
    for key in keys:
        # 精确优先
        for c in cols:
            if c == key or c.startswith(key):
                return c
    for key in keys:
        for c in cols:
            if key in c:
                return c
    return None


def _num(series: pd.Series) -> np.ndarray:
    arr = np.array(
        pd.to_numeric(series, errors="coerce").to_numpy(dtype=float),
        dtype=float,
        copy=True,
    )
    arr[arr >= MISSING_THRESHOLD] = np.nan
    return arr


def read_obs_xlsx(
    path_or_bytes,
    *,
    gust_col_key: Optional[str] = None,
) -> List[ObsStation]:
    """读取实况 xlsx，返回站点列表（缺测字段为 NaN）。

    gust_col_key：可选，指定风用列的关键字（如「最大瞬时风速」），
    覆盖默认优先级，对应配置项 OBS_GUST_COLUMN。
    """
    df = pd.read_excel(path_or_bytes)
    if df.empty:
        return []

    col_id = _find_col(df, _COL_KEYS["station_id"])
    col_name = _find_col(df, _COL_KEYS["name"])
    col_city = _find_col(df, _COL_KEYS["city"])
    col_county = _find_col(df, _COL_KEYS["county"])
    col_lat = _find_col(df, _COL_KEYS["lat"])
    col_lon = _find_col(df, _COL_KEYS["lon"])
    col_rain = _find_col(df, _COL_KEYS["hour_rain"])
    gust_keys = [gust_col_key] + _COL_KEYS["gust"] if gust_col_key else _COL_KEYS["gust"]
    col_gust = _find_col(df, [k for k in gust_keys if k])

    if col_lat is None or col_lon is None:
        raise ValueError("实况表缺少经纬度列，无法定位站点")

    lat = _num(df[col_lat])
    lon = _num(df[col_lon])
    rain = _num(df[col_rain]) if col_rain else np.full(len(df), np.nan)
    gust = _num(df[col_gust]) if col_gust else np.full(len(df), np.nan)

    def _txt(col: Optional[str], i: int) -> str:
        if col is None:
            return ""
        v = df[col].iloc[i]
        return "" if pd.isna(v) else str(v).strip()

    out: List[ObsStation] = []
    for i in range(len(df)):
        if not (np.isfinite(lat[i]) and np.isfinite(lon[i])):
            continue
        out.append(
            ObsStation(
                station_id=_txt(col_id, i),
                name=_txt(col_name, i),
                city=_txt(col_city, i),
                county=_txt(col_county, i),
                lat=float(lat[i]),
                lon=float(lon[i]),
                hour_rain_mm=float(rain[i]),
                gust_ms=float(gust[i]),
            )
        )
    log.info(
        "obs xlsx parsed: %d stations (rain_col=%s, gust_col=%s)",
        len(out), col_rain, col_gust,
    )
    return out
