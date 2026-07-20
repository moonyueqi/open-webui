"""定位最新的雷达实况(Z，2000m 反射率) nc，以及与之同时间戳的 Et / TreRef。

目录结构（相对 nc_base_dir）：{YYYYMMDD}/{Z,Cr,Et,TreRef}/Mosaic{YYYYMMDDHHMMSS}_*.nc。
文件名时间戳为 UTC，同一时间戳的 Z/Cr/Et/TreRef 一一对应。
实况反射率与画图改用 Z（多层，取 2000m 高度层）；Et / TreRef 仍沿用原产品。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from .datasource import DataSource

log = logging.getLogger(__name__)

_FNAME_RE = re.compile(r"^Mosaic(\d{14})_(Z|Cr|Et|TreRef)\.nc$")


@dataclass(frozen=True)
class RadarFile:
    timestamp: str                    # 14 位 UTC 时间戳
    dt_utc: datetime
    date_dir: str                     # YYYYMMDD
    z_rel_path: str                   # 实况主数据：2000m 反射率 Z
    cr_rel_path: str                  # 兼容保留（旧组合反射率，现已不用于实况）
    et_rel_path: str
    treref_rel_path: str


def _parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def _date_dirs_to_scan(now_utc: datetime) -> List[str]:
    """返回要扫描的日期目录（今天 + 昨天，兼顾 UTC 跨日）。"""
    return [
        now_utc.strftime("%Y%m%d"),
        (now_utc - timedelta(days=1)).strftime("%Y%m%d"),
    ]


def _z_rel(date_dir: str, fname: str) -> str:
    return f"{date_dir}/Z/{fname}"


def _cr_rel(date_dir: str, ts: str) -> str:
    return f"{date_dir}/Cr/Mosaic{ts}_Cr.nc"


def _et_rel(date_dir: str, ts: str) -> str:
    return f"{date_dir}/Et/Mosaic{ts}_Et.nc"


def _treref_rel(date_dir: str, ts: str) -> str:
    return f"{date_dir}/TreRef/Mosaic{ts}_TreRef.nc"


def find_latest_z(
    ds: DataSource,
    now_utc: Optional[datetime] = None,
) -> Optional[RadarFile]:
    """在今天/昨天的日期目录里找时间戳最大的 Z 文件（2000m 反射率实况）。"""
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    best: Optional[RadarFile] = None
    for date_dir in _date_dirs_to_scan(now_utc):
        names = ds.list_dir(f"{date_dir}/Z")
        for name in names:
            m = _FNAME_RE.match(name)
            if not m or m.group(2) != "Z":
                continue
            ts = m.group(1)
            try:
                dt_utc = _parse_ts(ts)
            except ValueError:
                continue
            candidate = RadarFile(
                timestamp=ts,
                dt_utc=dt_utc,
                date_dir=date_dir,
                z_rel_path=_z_rel(date_dir, name),
                cr_rel_path=_cr_rel(date_dir, ts),
                et_rel_path=_et_rel(date_dir, ts),
                treref_rel_path=_treref_rel(date_dir, ts),
            )
            if best is None or candidate.dt_utc > best.dt_utc:
                best = candidate
    if best is not None:
        log.debug("latest Z: %s (utc=%s)", best.z_rel_path, best.dt_utc.isoformat())
    else:
        log.warning("no Z file found in date dirs %s", _date_dirs_to_scan(now_utc))
    return best


# 兼容旧调用名：内部已改为以 Z 为实况主数据源。
find_latest_cr = find_latest_z


def has_et(ds: DataSource, rf: RadarFile) -> bool:
    return ds.exists(rf.et_rel_path)


def has_treref(ds: DataSource, rf: RadarFile) -> bool:
    return ds.exists(rf.treref_rel_path)
