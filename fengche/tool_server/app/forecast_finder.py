"""根据当前时间向前回退查找最近一次风掣预报文件。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from .datasource import DataSource


log = logging.getLogger(__name__)


# 默认路径模板：与本地仓库 fengche/20260507/20260507T15.nc 兼容
DEFAULT_PATH_TEMPLATE = "{ymd}/{ymd}T{HH}.nc"


@dataclass(frozen=True)
class ForecastFile:
    relative_path: str
    issue_time: datetime
    steps_back: int


def _floor_to_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def format_relative_path(dt: datetime, template: str = DEFAULT_PATH_TEMPLATE) -> str:
    """根据模板生成相对路径。

    支持的占位符：
      {Y}    年（4 位）          -> 2026
      {Ym}   年月（6 位）        -> 202605
      {ymd}  年月日（8 位）      -> 20260509
      {HH}   小时（2 位 0~23）   -> 08

    例：
      "{ymd}/{ymd}T{HH}.nc"           -> 20260509/20260509T08.nc        (本地默认)
      "{Y}/{Ym}/{ymd}/{ymd}T{HH}.nc"  -> 2026/202605/20260509/20260509T08.nc  (FTP)
    """
    return template.format(
        Y=dt.strftime("%Y"),
        Ym=dt.strftime("%Y%m"),
        ymd=dt.strftime("%Y%m%d"),
        HH=dt.strftime("%H"),
    )


def find_latest_forecast(
    ds: DataSource,
    now_local: datetime,
    max_lookback_hours: int = 24,
    path_template: str = DEFAULT_PATH_TEMPLATE,
) -> Optional[ForecastFile]:
    """从 now_local 当前整点出发，逐小时回退查找首个存在的预报文件。"""
    start = _floor_to_hour(now_local)
    for steps in range(0, max_lookback_hours + 1):
        candidate_time = start - timedelta(hours=steps)
        rel = format_relative_path(candidate_time, path_template)
        if ds.exists(rel):
            log.info("found forecast: %s (steps_back=%d)", rel, steps)
            return ForecastFile(
                relative_path=rel,
                issue_time=candidate_time,
                steps_back=steps,
            )
    log.warning(
        "no forecast file found within %d hours from %s (template=%s)",
        max_lookback_hours,
        start.isoformat(),
        path_template,
    )
    return None
