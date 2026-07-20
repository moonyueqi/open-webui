"""解析雷达 nc 字节流（Cr / Et / TreRef）。

缺测约定：NO_COVER=-32768（超出覆盖）、NO_ECHO=-128（无回波）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

import numpy as np
from netCDF4 import Dataset


@dataclass(frozen=True)
class RadarGrid:
    lat_arr: np.ndarray
    lon_arr: np.ndarray
    refl: np.ndarray                  # (n_lat, n_lon) float32，缺测处为 np.nan
    valid_time: datetime


@dataclass(frozen=True)
class ExtrapSequence:
    lat_arr: np.ndarray
    lon_arr: np.ndarray
    frames: np.ndarray                # (n_frame, n_lat, n_lon) float32，缺测处 np.nan
    valid_times: List[datetime]


def _mask_invalid(
    arr: np.ndarray,
    no_cover: float,
    no_echo: float,
) -> np.ndarray:
    out = np.asarray(arr, dtype=np.float32)
    invalid = (
        (out <= no_cover + 1e-3)
        | (np.isclose(out, no_echo))
        | ~np.isfinite(out)
    )
    out = out.copy()
    out[invalid] = np.nan
    return out


def _local_from_epoch(epoch_sec: int, tz: str) -> datetime:
    return datetime.fromtimestamp(int(epoch_sec), tz=timezone.utc).astimezone(
        ZoneInfo(tz)
    )


def _global_issue_time(ds: Dataset, tz: str) -> Optional[datetime]:
    ts = getattr(ds, "productGenerateTimeStamp", None)
    if ts is not None:
        try:
            return _local_from_epoch(int(np.asarray(ts).ravel()[0]), tz)
        except Exception:
            pass
    txt = getattr(ds, "productGenerateTime", None)
    if txt:
        try:
            naive = datetime.strptime(str(txt).strip(), "%Y-%m-%d %H:%M:%S")
            return naive.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))
        except Exception:
            pass
    return None


def read_cr(
    nc_bytes: bytes,
    *,
    observe_time: Optional[datetime] = None,
    no_cover: float = -32768.0,
    no_echo: float = -128.0,
    tz: str = "Asia/Shanghai",
) -> RadarGrid:
    """解析实况 Cr 文件。observe_time 优先作为 valid_time，缺省退回全局属性/当前时间。"""
    ds = Dataset("cr.nc", mode="r", memory=nc_bytes)
    try:
        lat_arr = np.asarray(ds.variables["lat"][:], dtype=np.float64)
        lon_arr = np.asarray(ds.variables["lon"][:], dtype=np.float64)
        data = np.asarray(ds.variables["data"][:])
        if data.ndim == 3:
            frame = data[0]
        elif data.ndim == 4:
            frame = data[0, 0]
        else:
            frame = np.squeeze(data)
        refl = _mask_invalid(frame, no_cover, no_echo)

        valid_time = observe_time or _global_issue_time(ds, tz)
        if valid_time is None:
            valid_time = datetime.now(ZoneInfo(tz))

        return RadarGrid(
            lat_arr=lat_arr,
            lon_arr=lon_arr,
            refl=refl,
            valid_time=valid_time,
        )
    finally:
        ds.close()


def read_z(
    nc_bytes: bytes,
    *,
    observe_time: Optional[datetime] = None,
    layer_index: int = 3,
    no_cover: float = -32768.0,
    no_echo: float = -128.0,
    tz: str = "Asia/Shanghai",
) -> RadarGrid:
    """解析多层反射率 Z 文件，取固定层索引（默认 3 = 2000m）作为实况反射率。

    data 维度为 (layerNum, lat, lon)，layerNum=[0.5,1.0,1.5,2.0,...]km，
    故 2000m=2.0km 固定对应索引 3。
    observe_time 优先作为 valid_time，缺省退回全局属性/当前时间。
    """
    ds = Dataset("z.nc", mode="r", memory=nc_bytes)
    try:
        lat_arr = np.asarray(ds.variables["lat"][:], dtype=np.float64)
        lon_arr = np.asarray(ds.variables["lon"][:], dtype=np.float64)
        data = np.asarray(ds.variables["data"][:])

        if data.ndim == 3:
            frame = data[layer_index]
        elif data.ndim == 4:
            frame = data[0, layer_index]
        else:
            frame = np.squeeze(data)
        refl = _mask_invalid(frame, no_cover, no_echo)

        valid_time = observe_time or _global_issue_time(ds, tz)
        if valid_time is None:
            valid_time = datetime.now(ZoneInfo(tz))

        return RadarGrid(
            lat_arr=lat_arr,
            lon_arr=lon_arr,
            refl=refl,
            valid_time=valid_time,
        )
    finally:
        ds.close()


def read_et(
    nc_bytes: bytes,
    *,
    no_cover: float = -32768.0,
    no_echo: float = -128.0,
) -> np.ndarray:
    """解析回波顶高 Et 文件，返回 (n_lat, n_lon) 顶高网格（单位 km，缺测为 NaN）。"""
    ds = Dataset("et.nc", mode="r", memory=nc_bytes)
    try:
        data = np.asarray(ds.variables["data"][:])
        if data.ndim == 3:
            frame = data[0]
        elif data.ndim == 4:
            frame = data[0, 0]
        else:
            frame = np.squeeze(data)
        return _mask_invalid(frame, no_cover, no_echo)
    finally:
        ds.close()


def read_treref(
    nc_bytes: bytes,
    *,
    max_frames: Optional[int] = None,
    skip_first: bool = True,
    no_cover: float = -32768.0,
    no_echo: float = -128.0,
    tz: str = "Asia/Shanghai",
) -> ExtrapSequence:
    """解析外推 TreRef 文件。skip_first 跳过起报当刻，max_frames 限制返回帧数。"""
    ds = Dataset("treref.nc", mode="r", memory=nc_bytes)
    try:
        lat_arr = np.asarray(ds.variables["lat"][:], dtype=np.float64)
        lon_arr = np.asarray(ds.variables["lon"][:], dtype=np.float64)
        data = np.asarray(ds.variables["data"][:])
        if data.ndim == 4:
            seq = data[:, 0]
        elif data.ndim == 3:
            seq = data
        else:
            seq = data[np.newaxis, ...]

        tss = ds.variables["tss"][:] if "tss" in ds.variables else None
        n_total = seq.shape[0]
        if tss is not None:
            valid_times_all = [
                _local_from_epoch(int(t), tz) for t in np.asarray(tss).ravel().tolist()
            ]
        else:
            base = _global_issue_time(ds, tz) or datetime.now(ZoneInfo(tz))
            valid_times_all = [base + timedelta(minutes=6 * i) for i in range(n_total)]

        start = 1 if skip_first and n_total > 1 else 0
        end = n_total
        if max_frames is not None:
            end = min(n_total, start + max_frames)

        frames = np.stack(
            [_mask_invalid(seq[i], no_cover, no_echo) for i in range(start, end)],
            axis=0,
        ) if end > start else np.empty((0,) + seq.shape[1:], dtype=np.float32)
        valid_times = valid_times_all[start:end]

        return ExtrapSequence(
            lat_arr=lat_arr,
            lon_arr=lon_arr,
            frames=frames,
            valid_times=valid_times,
        )
    finally:
        ds.close()
