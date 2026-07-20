"""定位覆盖目标时段的地面站点实况文件（小时雨强 + 瞬时风快照）。

实况文件为「某一时刻的全省站点快照」，其中「小时降水量」记录该时刻**过去 1 小时**
累计雨量。文件名时间戳为 **UTC**（与雷达 nc 一致），代表快照时刻 = 实况窗口的**结束**时刻。

窗口规则（与雷达 observe_time 对齐，示例：观测 14:18 → 窗口 13:10-14:10）：
  · 窗口结束 = 观测时刻向下取整到最近的 10 分钟（:00/:10/:20/:30/:40/:50）；
  · 窗口 = [end - 1h, end]，「小时降水量」即此窗口的逐十分钟滚动小时累计雨量。

定位：以窗口结束时刻为基准，按 obs_step_minutes（默认 10 min，逐十分钟出文件）
向前回退查找首个存在的实况文件，最多回退 max_lookback_minutes。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ObsFile:
    relative_path: str
    window_end_local: datetime      # 实况窗口结束时刻（本地时区）
    window_start_local: datetime    # 实况窗口起点 = end - 1h（本地时区）
    file_dt_utc: datetime           # 实际命中文件对应的 UTC 时刻


def resolve_window_end(observe_time: datetime, step_minutes: int = 10) -> datetime:
    """观测时刻 → 实况窗口结束时刻（向下对齐到最近的 step_minutes 边界）。

    例：step_minutes=10 时，14:18 → 14:10，14:09 → 14:00。窗口 = [end-1h, end]。
    """
    step = max(1, step_minutes)
    floored_min = (observe_time.minute // step) * step
    return observe_time.replace(minute=floored_min, second=0, microsecond=0)


def format_relative_path(dt_utc: datetime, template: str) -> str:
    """按模板生成相对路径。占位符基于 **UTC** 时刻渲染。

    支持：
      {Y} 年(4位)  {m} 月(2位)  {d} 日(2位)  {HH} 时(2位)  {MM} 分(2位)
      {Ym} 年月(6位)  {ymd} 年月日(8位)  {ymdHM} = YYYYMMDDHHMM
    例：
      "{Y}/{m}/{d}/PROCESSED_{ymdHM}.xlsx"
        -> 2026/07/01/PROCESSED_202607010010.xlsx
      "PROCESSED_{ymdHM}.xlsx"  -> PROCESSED_202607010010.xlsx（平铺）
    """
    return template.format(
        Y=dt_utc.strftime("%Y"),
        m=dt_utc.strftime("%m"),
        d=dt_utc.strftime("%d"),
        Ym=dt_utc.strftime("%Y%m"),
        ymd=dt_utc.strftime("%Y%m%d"),
        HH=dt_utc.strftime("%H"),
        MM=dt_utc.strftime("%M"),
        ymdHM=dt_utc.strftime("%Y%m%d%H%M"),
    )


def find_obs_for_observe_time(
    ds,
    observe_time: datetime,
    path_template: str,
    *,
    half_hour_boundary: bool = True,
    obs_step_minutes: int = 10,
    max_lookback_minutes: int = 60,
) -> Optional[ObsFile]:
    """由雷达观测时刻定位实况文件。

    observe_time 为带时区的本地时刻（如北京时）。窗口结束时刻换算成 UTC 后
    按 path_template 套路径；不存在则按 obs_step_minutes 逐步回退。

    half_hour_boundary 已弃用（历史整点/半点对齐），窗口统一按 obs_step_minutes
    逐十分钟对齐；保留该参数仅为调用方签名兼容。
    """
    window_end_local = resolve_window_end(observe_time, step_minutes=obs_step_minutes)
    window_start_local = window_end_local - timedelta(hours=1)

    steps = max(1, max_lookback_minutes // max(1, obs_step_minutes)) + 1
    for k in range(steps):
        cand_local = window_end_local - timedelta(minutes=obs_step_minutes * k)
        cand_utc = cand_local.astimezone(timezone.utc)
        rel = format_relative_path(cand_utc, path_template)
        if ds.exists(rel):
            log.info(
                "obs file hit: %s (window=%s~%s local, file_utc=%s)",
                rel,
                window_start_local.isoformat(),
                window_end_local.isoformat(),
                cand_utc.isoformat(),
            )
            return ObsFile(
                relative_path=rel,
                window_end_local=window_end_local,
                window_start_local=window_start_local,
                file_dt_utc=cand_utc,
            )
    log.warning(
        "no obs file found within %d min lookback (window_end=%s local, template=%s)",
        max_lookback_minutes, window_end_local.isoformat(), path_template,
    )
    return None
