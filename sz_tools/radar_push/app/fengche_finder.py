"""定位能覆盖目标小时时段的最近一份风掣 AI 预报 nc。

风掣按整点逐小时起报，每份文件覆盖未来 1~24 小时。step 是「预报时效」，
step=n 覆盖时段 [issue_time+(n-1)h, issue_time+n)，即 step=1 表示起报当小时
[issue_time, issue_time+1h)。
推送时按「逐小时为界」确定目标时段 [target_start, target_start+1h)：
  · 观测分钟 <= boundary_minute（默认 30）→ target_start = 当前整点；
  · 观测分钟  > boundary_minute            → target_start = 下一整点。

要报某目标时段 [target_start, target_start+1h)，需要一份起报时刻
issue_time <= target_start 的风掣文件，其 step = (target_start - issue_time) + 1
落在 [1, 24] 内。从「target_start」这个整点自身出发逐小时回退，找到首个就绪
文件即可（这样得到的 lead_hour 最小、时效最新；命中 issue_time == target_start
时 lead_hour=1，即用当前整点起报的最新预报）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FengcheFile:
    relative_path: str
    issue_time: datetime          # 起报整点（本地时区）
    target_start: datetime        # 目标时段起点整点（本地时区）
    lead_hour: int                # 覆盖目标时段的 step = (target_start - issue_time) + 1（1~24）


def _floor_to_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def resolve_target_start(observe_time: datetime, boundary_minute: int = 30) -> datetime:
    """按「逐小时为界」规则，由观测时刻算出目标时段起点整点。"""
    floored = _floor_to_hour(observe_time)
    if observe_time.minute > boundary_minute:
        return floored + timedelta(hours=1)
    return floored


def format_relative_path(dt: datetime, template: str) -> str:
    return template.format(
        Y=dt.strftime("%Y"),
        Ym=dt.strftime("%Y%m"),
        ymd=dt.strftime("%Y%m%d"),
        HH=dt.strftime("%H"),
    )


def find_forecast_for_target(
    ds,
    target_start: datetime,
    path_template: str,
    max_lookback_hours: int = 24,
    horizon_hours: int = 24,
) -> Optional[FengcheFile]:
    """从 target_start 整点自身起逐小时回退，找首个能覆盖目标时段的风掣文件。

    step=n 覆盖 [issue+(n-1)h, issue+n)，故覆盖目标时段需
    lead_hour = (target_start - issue_time) + 1，要求 1 <= lead_hour <= horizon_hours。
    回退第 k 步对应 issue_time = target_start - k 小时，lead_hour = k + 1
    （k=0 时 issue_time == target_start、lead_hour=1，即用当前整点起报的最新预报）。
    """
    for k in range(0, max_lookback_hours):
        lead_hour = k + 1
        if lead_hour > horizon_hours:
            break
        issue_time = target_start - timedelta(hours=k)
        rel = format_relative_path(issue_time, path_template)
        if ds.exists(rel):
            log.info(
                "fengche forecast hit: %s (issue=%s, target_start=%s, lead=%dh)",
                rel, issue_time.isoformat(), target_start.isoformat(), lead_hour,
            )
            return FengcheFile(
                relative_path=rel,
                issue_time=issue_time,
                target_start=target_start,
                lead_hour=lead_hour,
            )
    log.warning(
        "no fengche forecast covers target_start=%s within %dh lookback (template=%s)",
        target_start.isoformat(), max_lookback_hours, path_template,
    )
    return None
