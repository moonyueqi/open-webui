"""监测预警数据入库：定时扫描 MONITORING_DATA_ROOT，把新出现的地面自动站
报警 / 闪电跳增预警文件解析后写入数据库。

Environment:
    MONITORING_DATA_ROOT           数据根目录（容器内路径，默认 /app/data/alarm）
    MONITORING_SCAN_INTERVAL_SECONDS  扫描间隔秒数（默认 60）
    MONITORING_INGEST_ENABLED      是否启用后台扫描（默认 true，方便应急关闭）

落地目录是"按需创建"的：某天/某单位/某产品没有预警，对应目录就不存在。
所以这里全部走递归 glob（见 monitoring_parse.py），不手动拼日期路径。
"""

import os
import time
import random
import asyncio
import logging
from dataclasses import asdict

from open_webui.internal.db import get_db
from open_webui.utils.monitoring_parse import (
    scan_ground_alarms as _scan_ground_files,
    scan_lightning_pushes as _scan_lightning_files,
)

log = logging.getLogger(__name__)

MONITORING_DATA_ROOT = os.getenv("MONITORING_DATA_ROOT", "/app/data/alarm")
MONITORING_SCAN_INTERVAL_SECONDS = int(
    os.getenv("MONITORING_SCAN_INTERVAL_SECONDS", "60")
)
MONITORING_INGEST_ENABLED = (
    os.getenv("MONITORING_INGEST_ENABLED", "true").lower() == "true"
)


def _ground_row_to_dict(row) -> dict:
    d = asdict(row)
    d.pop("observed_at_raw", None)
    return d


def scan_ground_alarms(root: str = None) -> int:
    """扫描地面自动站报警 CSV，写入尚未处理过的文件，返回本轮新增行数。"""
    from open_webui.models.monitoring import GroundAlarms, MonitoringIngestFiles

    root = root or MONITORING_DATA_ROOT
    items = _scan_ground_files(root)
    if not items:
        return 0

    inserted_total = 0
    with get_db() as db:
        processed = MonitoringIngestFiles.get_processed(kind="ground", db=db)
        for item in items:
            rel = item.meta.rel_path
            if rel in processed:
                continue
            rows = [_ground_row_to_dict(r) for r in item.rows]
            try:
                inserted = GroundAlarms.bulk_insert_from_file(
                    source_file=rel,
                    push_time=item.meta.push_time,
                    coverage_start=item.meta.coverage_start,
                    coverage_end=item.meta.coverage_end,
                    rows=rows,
                    db=db,
                )
            except Exception:
                log.exception(f"monitoring ingest: 写入地面报警失败 {item.meta.path}")
                continue
            inserted_total += inserted
            MonitoringIngestFiles.mark("ground", rel, db=db)
    return inserted_total


def scan_lightning_pushes(root: str = None) -> int:
    """扫描闪电跳增预警推送（csv+json+png），写入尚未处理过的文件，返回本轮新增事件数。"""
    from open_webui.models.monitoring import (
        LightningPushes,
        LightningJumpEvents,
        MonitoringIngestFiles,
    )

    root = root or MONITORING_DATA_ROOT
    items = _scan_lightning_files(root)
    if not items:
        return 0

    inserted_total = 0
    with get_db() as db:
        processed = MonitoringIngestFiles.get_processed(kind="lightning", db=db)
        for item in items:
            rel = item.meta.rel_path
            if rel in processed:
                continue
            try:
                push = LightningPushes.upsert_push(
                    csv_path=rel,
                    push_time=item.meta.push_time,
                    coverage_start=item.meta.coverage_start,
                    coverage_end=item.meta.coverage_end,
                    json_path=(
                        os.path.relpath(item.json_path, root).replace(os.sep, "/")
                        if item.json_path
                        else None
                    ),
                    png_path=(
                        os.path.relpath(item.png_path, root).replace(os.sep, "/")
                        if item.png_path
                        else None
                    ),
                    db=db,
                )
                event_rows = [
                    {
                        "cell_seq": e.cell_seq,
                        "region": e.region,
                        "jump_times": e.jump_times,
                    }
                    for e in item.events
                ]
                inserted = LightningJumpEvents.insert_many(
                    push_id=push.id, rows=event_rows, db=db
                )
            except Exception:
                log.exception(
                    f"monitoring ingest: 写入闪电跳增预警失败 {item.meta.path}"
                )
                continue
            inserted_total += inserted
            MonitoringIngestFiles.mark("lightning", rel, db=db)
    return inserted_total


async def monitoring_ingest_worker_loop(app) -> None:
    """后台周期扫描任务，风格参照 automation_worker_loop / calendar_alert_worker_loop。"""
    if not MONITORING_INGEST_ENABLED:
        log.info("Monitoring ingest worker disabled (MONITORING_INGEST_ENABLED=false)")
        return

    log.info(
        f"Monitoring ingest worker started "
        f"(root={MONITORING_DATA_ROOT}, poll={MONITORING_SCAN_INTERVAL_SECONDS}s)"
    )
    while True:
        try:
            ground_count = await asyncio.to_thread(scan_ground_alarms)
            lightning_count = await asyncio.to_thread(scan_lightning_pushes)
            if ground_count or lightning_count:
                log.info(
                    f"monitoring ingest: +{ground_count} 条地面告警记录，"
                    f"+{lightning_count} 条闪电跳增事件"
                )
        except Exception:
            log.exception("Monitoring ingest worker error")

        # 加抖动，避免多实例部署时扫描请求同时打到共享存储上
        await asyncio.sleep(MONITORING_SCAN_INTERVAL_SECONDS + random.uniform(0, 2))
