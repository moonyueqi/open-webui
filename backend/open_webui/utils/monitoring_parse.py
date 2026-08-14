"""监测预警数据解析：地面自动站报警 + 高空闪电跃增预警。

设计约束（详见项目计划 监测预警数据接入与展示）：
    - 落地目录是"按需创建"的：某天/某单位/某产品没有预警，对应的
      `年/月/日/单位/产品/` 目录就根本不存在。所以这里一律用递归 glob 定位
      文件，不手动拼日期路径；找不到就是空列表，不是异常。
    - 本地样例数据是扁平的（`root/BMDC/station_alarm/*.csv`），生产环境是
      按日期分层的（`root/2026/07/25/BMDC/station_alarm/*.csv`）。递归 glob
      对两种目录形态一视同仁，方便本地用真实样例数据直接联调。

本模块只依赖标准库，不 import 任何 open_webui 内部模块/第三方包，这样
`scripts/test_monitoring_ingest.py` 才能在没有安装完整后端依赖的机器上，
用纯 Python 直接跑起来预览解析效果。数据库落库逻辑在
`open_webui/utils/monitoring_ingest.py` 里，那边才会依赖 SQLAlchemy。
"""

from __future__ import annotations

import csv
import glob
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# 落地路径固定包含这两级子目录，用它们做递归 glob 的锚点。
GROUND_ALARM_GLOB = os.path.join("**", "BMDC", "station_alarm", "*.csv")
LIGHTNING_ALARM_GLOB = os.path.join("**", "tance", "lightning_jump_alarm", "*.csv")

# 文件名前 3 段固定是 12 位时间戳（推送时间_覆盖起_覆盖止），后面单位/产品
# 命名并不统一（如 BMDC_Alarm、tance_lightning_jump_alarm），不在文件名里
# 强解析单位/产品，改由调用方按 glob 命中的目录来区分。
FILENAME_RE = re.compile(
    r"^(?P<push>\d{12})_(?P<cov_start>\d{12})_(?P<cov_end>\d{12})_.+\.(?P<ext>\w+)$"
)


def epoch_ns_from_12(value: str) -> Optional[int]:
    """把文件名里的 12 位时间串（YYYYMMDDHHmm）解析成 epoch 纳秒。"""
    try:
        dt = datetime.strptime(value, "%Y%m%d%H%M")
        return int(dt.timestamp() * 1_000_000_000)
    except (ValueError, TypeError):
        return None


def epoch_ns_from_datetime_str(value: str) -> Optional[int]:
    """把 CSV 里的 'YYYY-MM-DD HH:MM:SS' 时间列解析成 epoch 纳秒。"""
    if not value:
        return None
    try:
        dt = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S")
        return int(dt.timestamp() * 1_000_000_000)
    except (ValueError, TypeError):
        return None


@dataclass
class FileMeta:
    path: str
    rel_path: str
    push_time: Optional[int]
    coverage_start: Optional[int]
    coverage_end: Optional[int]


def parse_filename(path: str, root: str) -> Optional[FileMeta]:
    name = os.path.basename(path)
    m = FILENAME_RE.match(name)
    if not m:
        return None
    return FileMeta(
        path=path,
        rel_path=os.path.relpath(path, root).replace(os.sep, "/"),
        push_time=epoch_ns_from_12(m.group("push")),
        coverage_start=epoch_ns_from_12(m.group("cov_start")),
        coverage_end=epoch_ns_from_12(m.group("cov_end")),
    )


def find_files(root: str, pattern: str) -> list[str]:
    """在 root 下递归找匹配 pattern 的文件。root/pattern 任一段不存在都只是返回空列表。"""
    if not root or not os.path.isdir(root):
        return []
    return sorted(glob.glob(os.path.join(root, pattern), recursive=True))


####################
# 地面自动站报警 CSV
####################

# Station_Id_C,Station_Name,Cnty,Province,Datetime,PRE,5min,10min,15min,20min,25min,30min,alarm
_GROUND_MIN_COLS = 13


@dataclass
class GroundAlarmRow:
    station_id: str
    station_name: str
    county: str
    province: str
    observed_at: Optional[int]
    observed_at_raw: str
    pre: Optional[float]
    rain_5m: Optional[float]
    rain_10m: Optional[float]
    rain_15m: Optional[float]
    rain_20m: Optional[float]
    rain_25m: Optional[float]
    rain_30m: Optional[float]
    level: str


def _to_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def parse_ground_alarm_csv(path: str) -> list[GroundAlarmRow]:
    """解析地面自动站报警 CSV。用位置读列（不用 DictReader），避开 BOM 混进表头 key 的问题。"""
    rows: list[GroundAlarmRow] = []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if header is None:
            return rows
        for cols in reader:
            if len(cols) < _GROUND_MIN_COLS:
                continue
            observed_raw = cols[4].strip()
            rows.append(
                GroundAlarmRow(
                    station_id=cols[0].strip(),
                    station_name=cols[1].strip(),
                    county=cols[2].strip(),
                    province=cols[3].strip(),
                    observed_at=epoch_ns_from_datetime_str(observed_raw),
                    observed_at_raw=observed_raw,
                    pre=_to_float(cols[5]),
                    rain_5m=_to_float(cols[6]),
                    rain_10m=_to_float(cols[7]),
                    rain_15m=_to_float(cols[8]),
                    rain_20m=_to_float(cols[9]),
                    rain_25m=_to_float(cols[10]),
                    rain_30m=_to_float(cols[11]),
                    level=cols[12].strip(),
                )
            )
    return rows


####################
# 闪电跳增预警摘要 CSV(+同名 json/png)
####################

# 单体序号,地区,闪电跃增预警时间
_LIGHTNING_MIN_COLS = 3


@dataclass
class LightningJumpRow:
    cell_seq: str
    region: str
    jump_times: str


def parse_lightning_summary_csv(path: str) -> list[LightningJumpRow]:
    rows: list[LightningJumpRow] = []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if header is None:
            return rows
        for cols in reader:
            if len(cols) < _LIGHTNING_MIN_COLS:
                continue
            rows.append(
                LightningJumpRow(
                    cell_seq=cols[0].strip(),
                    region=cols[1].strip(),
                    jump_times=cols[2].strip(),
                )
            )
    return rows


def sibling_asset_paths(csv_path: str) -> tuple[Optional[str], Optional[str]]:
    """闪电跳增每次推送的 csv/json/png 是同名不同后缀，找配套的 json/png（不存在则为 None）。"""
    base, _ext = os.path.splitext(csv_path)
    json_path = f"{base}.json"
    png_path = f"{base}.png"
    return (
        json_path if os.path.isfile(json_path) else None,
        png_path if os.path.isfile(png_path) else None,
    )


####################
# 汇总扫描（供本地测试脚本直接调用，不落库）
####################


@dataclass
class GroundScanItem:
    meta: FileMeta
    rows: list[GroundAlarmRow] = field(default_factory=list)


@dataclass
class LightningScanItem:
    meta: FileMeta
    json_path: Optional[str]
    png_path: Optional[str]
    events: list[LightningJumpRow] = field(default_factory=list)


def scan_ground_alarms(root: str) -> list[GroundScanItem]:
    items = []
    for path in find_files(root, GROUND_ALARM_GLOB):
        meta = parse_filename(path, root)
        if not meta:
            continue
        try:
            rows = parse_ground_alarm_csv(path)
        except OSError:
            continue
        items.append(GroundScanItem(meta=meta, rows=rows))
    return items


def scan_lightning_pushes(root: str) -> list[LightningScanItem]:
    items = []
    for path in find_files(root, LIGHTNING_ALARM_GLOB):
        meta = parse_filename(path, root)
        if not meta:
            continue
        try:
            events = parse_lightning_summary_csv(path)
        except OSError:
            continue
        json_path, png_path = sibling_asset_paths(path)
        items.append(
            LightningScanItem(
                meta=meta, json_path=json_path, png_path=png_path, events=events
            )
        )
    return items
