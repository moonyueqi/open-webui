"""解析风掣 AI 预报 nc 字节流，取出指定 lead_hour 那一帧的逐小时降水 tp、阵风 gs 网格。

风掣 nc 结构（与 fengche/tool_server 一致）：
  · 维度：time=1（起报时刻）、step=N（预报时效, 1~24 小时）、lat、lon
  · 变量 tp：逐小时降水 mm（每个时次的当小时降水量，非累积值），4D (time, step, lat, lon)
  · 变量 gs：10 米阵风（极大风）m/s，4D (time, step, lat, lon)；缺则该帧风置 NaN。
  · step=n 对应时段 [issue+(n-1)h, issue+n)，即 step=1 表示起报当小时
    [issue, issue+1h)。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from netCDF4 import Dataset

log = logging.getLogger(__name__)


# tp/gs <= 该值视为缺测填充（如 -128/-32768）置 NaN；介于此值与 0 间的微小负值视为噪声夹到 0。
MISSING_NEG_THRESHOLD = -1.0

# 风掣 nc 中阵风（极大风）变量的候选名，按优先级取第一个存在的。
GUST_VAR_CANDIDATES = ("gs", "gust", "fg10", "i10fg")


@dataclass(frozen=True)
class FengcheRainGrid:
    lat_arr: np.ndarray
    lon_arr: np.ndarray
    tp: np.ndarray            # (n_lat, n_lon) float32，目标 lead_hour 的逐小时降水 mm，缺测为 NaN
    gs: np.ndarray            # (n_lat, n_lon) float32，目标 lead_hour 的 10m 阵风 m/s，缺测/无该变量为 NaN
    lead_hour: int            # 实际命中的 step 对应小时


def _clean_frame(frame: np.ndarray) -> np.ndarray:
    """缺测/异常处理：NaN/Inf 与大负填充值 → NaN；微小负噪声 → 夹到 0。"""
    frame = np.where(np.isfinite(frame), frame, np.nan)
    frame = np.where(frame <= MISSING_NEG_THRESHOLD, np.nan, frame)
    frame = np.where((frame < 0) & np.isfinite(frame), 0.0, frame)
    return frame


def read_tp_at_lead(nc_bytes: bytes, lead_hour: int) -> FengcheRainGrid:
    """读取风掣 nc 中 step == lead_hour 那一帧的 tp（降水）与 gs（阵风）网格。

    若 step 维度里没有恰好等于 lead_hour 的值，则回退用第 (lead_hour-1) 个索引
    （风掣 step 通常就是 1..24 连续整数，二者一致）。阵风变量缺失时 gs 全置 NaN。
    """
    ds = Dataset("fengche.nc", mode="r", memory=nc_bytes)
    try:
        lat_arr = np.asarray(ds.variables["lat"][:], dtype=np.float64)
        lon_arr = np.asarray(ds.variables["lon"][:], dtype=np.float64)
        step_arr = np.atleast_1d(np.asarray(ds.variables["step"][:]))

        # 优先按 step 值匹配，匹配不到再按位置索引兜底
        k = None
        for idx, sv in enumerate(step_arr.tolist()):
            try:
                if int(sv) == int(lead_hour):
                    k = idx
                    break
            except Exception:
                continue
        if k is None:
            k = max(0, min(int(lead_hour) - 1, step_arr.size - 1))

        if "tp" not in ds.variables:
            raise KeyError("风掣 nc 中缺少 tp（逐小时降水）变量")

        # tp 维度 (time, step, lat, lon)
        tp_frame = _clean_frame(np.asarray(ds.variables["tp"][0, k, :, :], dtype=np.float32))

        # 阵风（极大风）：按候选名取第一个存在的变量；缺失则整帧 NaN（文案里该项省略）。
        gs_frame = np.full_like(tp_frame, np.nan)
        gust_name = next((n for n in GUST_VAR_CANDIDATES if n in ds.variables), None)
        if gust_name is not None:
            gs_frame = _clean_frame(np.asarray(ds.variables[gust_name][0, k, :, :], dtype=np.float32))
        else:
            log.warning("风掣 nc 中未找到阵风变量（候选 %s），极大风将省略", GUST_VAR_CANDIDATES)

        try:
            actual_lead = int(step_arr.tolist()[k])
        except Exception:
            actual_lead = int(lead_hour)

        return FengcheRainGrid(
            lat_arr=lat_arr,
            lon_arr=lon_arr,
            tp=tp_frame,
            gs=gs_frame,
            lead_hour=actual_lead,
        )
    finally:
        ds.close()
