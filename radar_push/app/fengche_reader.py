"""解析风掣 AI 预报 nc 字节流，取出指定 lead_hour 那一帧的逐小时降水 tp 网格。

风掣 nc 结构（与 fengche/tool_server 一致）：
  · 维度：time=1（起报时刻）、step=N（预报时效, 1~24 小时）、lat、lon
  · 变量 tp：逐小时降水 mm（每个时次的当小时降水量，非累积值），4D (time, step, lat, lon)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from netCDF4 import Dataset

log = logging.getLogger(__name__)


# tp 小于等于该值视为缺测填充（如 -128 / -32768），置 NaN 不参与统计；
# 介于该值与 0 之间的微小负值视为数值噪声，夹到 0。
MISSING_NEG_THRESHOLD = -1.0


@dataclass(frozen=True)
class FengcheRainGrid:
    lat_arr: np.ndarray
    lon_arr: np.ndarray
    tp: np.ndarray            # (n_lat, n_lon) float32，目标 lead_hour 的逐小时降水 mm，缺测为 NaN
    lead_hour: int            # 实际命中的 step 对应小时


def read_tp_at_lead(nc_bytes: bytes, lead_hour: int) -> FengcheRainGrid:
    """读取风掣 nc 中 step == lead_hour 那一帧的 tp 网格。

    若 step 维度里没有恰好等于 lead_hour 的值，则回退用第 (lead_hour-1) 个索引
    （风掣 step 通常就是 1..24 连续整数，二者一致）。
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
        tp_var = ds.variables["tp"]
        frame = np.asarray(tp_var[0, k, :, :], dtype=np.float32)
        # 缺测/异常处理（风掣 tp 为模型输出的物理量 mm，官方 warning_server 直接用，
        # 这里统一三类口径）：
        #   1) 非有限值（NaN/Inf）→ NaN（无数据，不参与区县统计）
        #   2) 明显的缺测填充值（大负数，如 -128 / -32768）→ NaN（不能当成 0 降水）
        #   3) 物理上不可能的微小负噪声（如 -0.01）→ 夹到 0
        frame = np.where(np.isfinite(frame), frame, np.nan)
        frame = np.where(frame <= MISSING_NEG_THRESHOLD, np.nan, frame)
        frame = np.where((frame < 0) & np.isfinite(frame), 0.0, frame)

        try:
            actual_lead = int(step_arr.tolist()[k])
        except Exception:
            actual_lead = int(lead_hour)

        return FengcheRainGrid(
            lat_arr=lat_arr,
            lon_arr=lon_arr,
            tp=frame,
            lead_hour=actual_lead,
        )
    finally:
        ds.close()
