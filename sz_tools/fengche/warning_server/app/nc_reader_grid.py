"""读取 .nc 字节流，保留完整 (step, lat, lon) 网格的 gs / tp，以及坐标轴和起报时间。

与 fengche_tool_server.app.nc_reader 不同的是：本模块不取最近格点（不做空间检索），
因为预警判定需要在整个网格上做区域掩膜聚合。
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List
from zoneinfo import ZoneInfo

import numpy as np
from netCDF4 import Dataset, num2date


@dataclass(frozen=True)
class ForecastGrid:
    issue_time: datetime              # 起报时刻（已附带时区）
    lat_arr: np.ndarray               # (n_lat,)
    lon_arr: np.ndarray               # (n_lon,)
    step_arr: np.ndarray              # (n_step,)，每个值是 lead hours
    valid_times: List[datetime]       # issue_time + step h，每个 step 对应的预报有效时刻
    gs: np.ndarray                    # (n_step, n_lat, n_lon) 阵风 m/s
    tp: np.ndarray                    # (n_step, n_lat, n_lon) 逐小时降水 mm
    coverage_lat: tuple               # (min, max)
    coverage_lon: tuple               # (min, max)


def _to_naive_datetime(dt) -> datetime:
    if not isinstance(dt, datetime):
        dt = datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
    return dt


def read_forecast_grid(nc_bytes: io.BytesIO, tz: str = "Asia/Shanghai") -> ForecastGrid:
    """解析 .nc 字节流，返回完整网格的 gs / tp + 坐标 + issue_time。"""
    raw = nc_bytes.read() if hasattr(nc_bytes, "read") else nc_bytes
    ds = Dataset("inmem.nc", mode="r", memory=raw)

    try:
        lat_arr = np.asarray(ds.variables["lat"][:])
        lon_arr = np.asarray(ds.variables["lon"][:])
        step_arr = np.atleast_1d(np.asarray(ds.variables["step"][:]))

        # 起报时间解析（与 fengche_tool_server.app.nc_reader 保持一致：time.units 已是本地时间）
        tvar = ds.variables["time"]
        units = getattr(tvar, "units", "hours since 1970-01-01 00:00:00")
        cal = getattr(tvar, "calendar", "standard")
        issue_raw = num2date(tvar[:], units=units, calendar=cal)
        issue_naive = _to_naive_datetime(np.atleast_1d(issue_raw)[0])
        issue_time = issue_naive.replace(tzinfo=ZoneInfo(tz))

        # 读取整个网格 (time=1, step, lat, lon) → 切第 0 个 time 维
        gs = np.asarray(ds.variables["gs"][0, :, :, :], dtype=np.float32)
        tp = np.asarray(ds.variables["tp"][0, :, :, :], dtype=np.float32)

        # 计算每个 step 对应的预报有效时刻
        valid_times = [
            issue_time + timedelta(hours=int(s)) for s in step_arr.tolist()
        ]

        return ForecastGrid(
            issue_time=issue_time,
            lat_arr=lat_arr,
            lon_arr=lon_arr,
            step_arr=step_arr,
            valid_times=valid_times,
            gs=gs,
            tp=tp,
            coverage_lat=(float(lat_arr.min()), float(lat_arr.max())),
            coverage_lon=(float(lon_arr.min()), float(lon_arr.max())),
        )
    finally:
        ds.close()
