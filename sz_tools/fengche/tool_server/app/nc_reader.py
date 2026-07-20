"""读取 .nc 字节流，按已知结构 (time=1, step=N, lat, lon) 取最近格点。"""

from __future__ import annotations

import io
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import numpy as np
from netCDF4 import Dataset, num2date


DATA_VARS = ["t2m", "q2m", "u10m", "v10m", "ws", "gs", "cr", "tp"]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _to_naive_datetime(dt) -> datetime:
    """num2date 返回的可能是 cftime 对象或 naive datetime；统一转为标准 naive datetime。"""
    if not isinstance(dt, datetime):
        dt = datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
    return dt


def read_forecast(
    nc_bytes: io.BytesIO,
    lat: float,
    lon: float,
    variables: Optional[List[str]] = None,
    tz: str = "Asia/Shanghai",
    max_hours: Optional[int] = None,
) -> Dict[str, Any]:
    """
    解析 .nc 字节流，返回结构化字典（含 forecast 列表 / coverage / out_of_coverage 等）。
    单位换算由调用方（main.py）完成，本函数返回原始数值。

    max_hours：可选地把返回的 forecast 列表截断到前 N 个时效（按 lead_hour 升序）。
    """
    raw = nc_bytes.read() if hasattr(nc_bytes, "read") else nc_bytes
    ds = Dataset("inmem.nc", mode="r", memory=raw)

    try:
        lat_arr = np.asarray(ds.variables["lat"][:])
        lon_arr = np.asarray(ds.variables["lon"][:])
        step_arr = np.atleast_1d(np.asarray(ds.variables["step"][:]))

        coverage = {
            "lat": [float(lat_arr.min()), float(lat_arr.max())],
            "lon": [float(lon_arr.min()), float(lon_arr.max())],
        }

        if not (
            coverage["lat"][0] <= lat <= coverage["lat"][1]
            and coverage["lon"][0] <= lon <= coverage["lon"][1]
        ):
            return {
                "out_of_coverage": True,
                "coverage": coverage,
            }

        i = int(np.argmin(np.abs(lat_arr - lat)))
        j = int(np.argmin(np.abs(lon_arr - lon)))
        grid_lat = float(lat_arr[i])
        grid_lon = float(lon_arr[j])
        distance_km = round(_haversine_km(lat, lon, grid_lat, grid_lon), 3)

        tvar = ds.variables["time"]
        units = getattr(tvar, "units", "hours since 1970-01-01 00:00:00")
        cal = getattr(tvar, "calendar", "standard")
        issue_raw = num2date(tvar[:], units=units, calendar=cal)
        issue_naive = _to_naive_datetime(np.atleast_1d(issue_raw)[0])
        # 风掣 AI 模型预报文件的 time.units 字符串使用的是本地时间（北京时间，与文件名 YYYYMMDDTHH 一致），
        # 因此解码后直接附加配置的本地时区即可，不能按 CF 的"默认 UTC"再做 astimezone。
        issue_time = issue_naive.replace(tzinfo=ZoneInfo(tz))

        all_data_vars = [
            v for v in ds.variables
            if v not in ds.dimensions and v not in ("lat", "lon", "step", "time")
        ]
        if variables:
            requested = [v for v in variables if v in ds.variables]
        else:
            # 优先按已知顺序，未知的追加在后面
            ordered = [v for v in DATA_VARS if v in all_data_vars]
            extras = [v for v in all_data_vars if v not in ordered]
            requested = ordered + extras

        # 一次性把 (steps,) 切片读出来
        series: Dict[str, list] = {}
        for v in requested:
            arr = np.asarray(ds.variables[v][0, :, i, j])
            series[v] = arr.tolist()

        forecast: list[Dict[str, Any]] = []
        for k, step_val in enumerate(step_arr.tolist()):
            try:
                lead_h = int(step_val)
            except Exception:
                lead_h = k + 1
            valid_time = issue_time + timedelta(hours=lead_h)
            row_values: Dict[str, Any] = {}
            for v in requested:
                val = series[v][k]
                if val is None or (isinstance(val, float) and math.isnan(val)):
                    row_values[v] = None
                else:
                    row_values[v] = float(val)
            forecast.append({
                "lead_hour": lead_h,
                "valid_time": valid_time.isoformat(),
                "values": row_values,
            })

        forecast.sort(key=lambda r: r["lead_hour"])
        if max_hours is not None and max_hours > 0:
            forecast = forecast[:max_hours]

        return {
            "out_of_coverage": False,
            "issue_time": issue_time.isoformat(),
            "grid_point": {
                "lat": grid_lat,
                "lon": grid_lon,
                "distance_km": distance_km,
            },
            "available_variables": all_data_vars,
            "returned_variables": requested,
            "forecast": forecast,
            "coverage": coverage,
            "step_interpretation": "lead hours after issue time (e.g. step=1 means issue+1h)",
        }
    finally:
        ds.close()
