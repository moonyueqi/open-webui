import time
import logging
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    Column,
    Text,
    Float,
    BigInteger,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Session

from open_webui.internal.db import Base, get_db_context

log = logging.getLogger(__name__)


####################
# 地面监测 - 自动站报警
####################


class MonitoringGroundAlarm(Base):
    __tablename__ = "monitoring_ground_alarm"

    id = Column(Text, primary_key=True)

    push_time = Column(BigInteger, nullable=True)  # 推送时间（文件名第1段）
    coverage_start = Column(BigInteger, nullable=True)
    coverage_end = Column(BigInteger, nullable=True)

    station_id = Column(Text, nullable=False)
    station_name = Column(Text, nullable=True)
    county = Column(Text, nullable=True)
    province = Column(Text, nullable=True)

    observed_at = Column(BigInteger, nullable=False)  # CSV 里的 Datetime 列

    pre = Column(Float, nullable=True)
    rain_5m = Column(Float, nullable=True)
    rain_10m = Column(Float, nullable=True)
    rain_15m = Column(Float, nullable=True)
    rain_20m = Column(Float, nullable=True)
    rain_25m = Column(Float, nullable=True)
    rain_30m = Column(Float, nullable=True)

    level = Column(Text, nullable=True)  # 蓝/黄/橙/红

    source_file = Column(Text, nullable=False)
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "station_id",
            "observed_at",
            "source_file",
            name="uq_ground_alarm_station_time_file",
        ),
        Index("ix_ground_alarm_observed_at", "observed_at"),
        Index("ix_ground_alarm_station_observed", "station_id", "observed_at"),
    )


class MonitoringGroundAlarmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    push_time: Optional[int] = None
    coverage_start: Optional[int] = None
    coverage_end: Optional[int] = None

    station_id: str
    station_name: Optional[str] = None
    county: Optional[str] = None
    province: Optional[str] = None

    observed_at: int

    pre: Optional[float] = None
    rain_5m: Optional[float] = None
    rain_10m: Optional[float] = None
    rain_15m: Optional[float] = None
    rain_20m: Optional[float] = None
    rain_25m: Optional[float] = None
    rain_30m: Optional[float] = None

    level: Optional[str] = None

    source_file: str
    created_at: int


class GroundAlarmListResponse(BaseModel):
    items: list[MonitoringGroundAlarmModel]
    total: int


class GroundAlarmSummaryResponse(BaseModel):
    active_count: int
    by_level: dict[str, int]
    county_count: int
    latest_alarm_at: Optional[int] = None
    updated_at: Optional[int] = None


def format_ground_alarm_text(alarm: MonitoringGroundAlarmModel) -> str:
    """播报文案的唯一拼法，前端表格展示同一份原始字段时应遵循同样的措辞。

    格式："{站名} {等级}色预警 · 30分钟雨量{X}mm"
    """
    station = alarm.station_name or alarm.station_id
    level = f"{alarm.level}色" if alarm.level else "未知等级"
    rain = f"{alarm.rain_30m:g}mm" if alarm.rain_30m is not None else "--"
    return f"{station} {level}预警 · 30分钟雨量{rain}"


class MonitoringGroundAlarmTable:
    def bulk_insert_from_file(
        self,
        source_file: str,
        push_time: Optional[int],
        coverage_start: Optional[int],
        coverage_end: Optional[int],
        rows: list[dict],
        db: Optional[Session] = None,
    ) -> int:
        """把一个推送文件里的所有行落库，已存在的 (station_id, observed_at, source_file) 组合会被跳过。"""
        if not rows:
            return 0
        with get_db_context(db) as db:
            existing = {
                r.station_id
                for r in db.query(MonitoringGroundAlarm.station_id)
                .filter(MonitoringGroundAlarm.source_file == source_file)
                .all()
            }
            now = int(time.time_ns())
            inserted = 0
            for row in rows:
                if not row.get("station_id"):
                    continue
                if row.get("observed_at") is None:
                    continue
                if row["station_id"] in existing:
                    continue
                db.add(
                    MonitoringGroundAlarm(
                        id=str(uuid4()),
                        push_time=push_time,
                        coverage_start=coverage_start,
                        coverage_end=coverage_end,
                        source_file=source_file,
                        created_at=now,
                        **row,
                    )
                )
                inserted += 1
            if inserted:
                db.commit()
            return inserted

    def get_by_id(
        self, id: str, db: Optional[Session] = None
    ) -> Optional[MonitoringGroundAlarmModel]:
        with get_db_context(db) as db:
            row = db.get(MonitoringGroundAlarm, id)
            return MonitoringGroundAlarmModel.model_validate(row) if row else None

    def list_alarms(
        self,
        level: Optional[list[str]] = None,
        county: Optional[str] = None,
        station_id: Optional[str] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        latest_only: bool = False,
        skip: int = 0,
        limit: int = 50,
        db: Optional[Session] = None,
    ) -> GroundAlarmListResponse:
        with get_db_context(db) as db:
            q = db.query(MonitoringGroundAlarm)
            if level:
                q = q.filter(MonitoringGroundAlarm.level.in_(level))
            if county:
                q = q.filter(MonitoringGroundAlarm.county == county)
            if station_id:
                q = q.filter(MonitoringGroundAlarm.station_id == station_id)
            if start:
                q = q.filter(MonitoringGroundAlarm.observed_at >= start)
            if end:
                q = q.filter(MonitoringGroundAlarm.observed_at <= end)

            q = q.order_by(MonitoringGroundAlarm.observed_at.desc())

            if latest_only:
                # 每个站点只保留 observed_at 最大的一条，代表"当前状态"。
                # 数据规模不大（按站点计，通常几十到几百），直接在 Python 侧规约，
                # 避免用 station_id/observed_at 两个 IN 条件交叉匹配导致误配对。
                rows = q.all()
                latest_by_station: dict[str, MonitoringGroundAlarm] = {}
                for row in rows:
                    prev = latest_by_station.get(row.station_id)
                    if prev is None or row.observed_at > prev.observed_at:
                        latest_by_station[row.station_id] = row
                items = sorted(
                    latest_by_station.values(),
                    key=lambda r: r.observed_at,
                    reverse=True,
                )
                total = len(items)
                if skip:
                    items = items[skip:]
                if limit:
                    items = items[:limit]
                return GroundAlarmListResponse(
                    items=[MonitoringGroundAlarmModel.model_validate(r) for r in items],
                    total=total,
                )

            total = q.count()
            if skip:
                q = q.offset(skip)
            if limit:
                q = q.limit(limit)

            rows = q.all()
            return GroundAlarmListResponse(
                items=[MonitoringGroundAlarmModel.model_validate(r) for r in rows],
                total=total,
            )

    def get_summary(
        self, db: Optional[Session] = None
    ) -> GroundAlarmSummaryResponse:
        """基于"每站最新一条"的当前活跃告警，按等级/区县聚合。"""
        latest = self.list_alarms(latest_only=True, limit=10_000, db=db)
        by_level: dict[str, int] = {}
        counties = set()
        latest_alarm_at: Optional[int] = None
        for item in latest.items:
            key = item.level or "未知"
            by_level[key] = by_level.get(key, 0) + 1
            if item.county:
                counties.add(item.county)
            if latest_alarm_at is None or item.observed_at > latest_alarm_at:
                latest_alarm_at = item.observed_at
        return GroundAlarmSummaryResponse(
            active_count=len(latest.items),
            by_level=by_level,
            county_count=len(counties),
            latest_alarm_at=latest_alarm_at,
            updated_at=int(time.time_ns()),
        )

    def get_latest_feed_items(
        self, limit: int = 5, db: Optional[Session] = None
    ) -> list[MonitoringGroundAlarmModel]:
        """给侧边栏 Ticker 用：每站最新一条，按时间倒序取前 N 条。"""
        latest = self.list_alarms(latest_only=True, limit=limit, db=db)
        return latest.items


####################
# 高空预警 - 闪电跳增预警
####################


class MonitoringLightningPush(Base):
    __tablename__ = "monitoring_lightning_push"

    id = Column(Text, primary_key=True)

    push_time = Column(BigInteger, nullable=True)
    coverage_start = Column(BigInteger, nullable=True)
    coverage_end = Column(BigInteger, nullable=True)

    csv_path = Column(Text, nullable=False)
    json_path = Column(Text, nullable=True)
    png_path = Column(Text, nullable=True)

    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("csv_path", name="uq_lightning_push_csv_path"),
        Index("ix_lightning_push_push_time", "push_time"),
    )


class MonitoringLightningJumpEvent(Base):
    __tablename__ = "monitoring_lightning_jump_event"

    id = Column(Text, primary_key=True)
    push_id = Column(Text, nullable=False)

    cell_seq = Column(Text, nullable=True)  # 单体序号：本次推送内的编号，非跨推送稳定 id
    region = Column(Text, nullable=False)  # 地区，可能是"县1；县2"
    jump_times = Column(Text, nullable=True)  # 原始字符串，如 "17:04;17:24"

    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (Index("ix_lightning_jump_push_id", "push_id"),)


class MonitoringLightningPushModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    push_time: Optional[int] = None
    coverage_start: Optional[int] = None
    coverage_end: Optional[int] = None
    csv_path: str
    json_path: Optional[str] = None
    png_path: Optional[str] = None
    created_at: int


class MonitoringLightningJumpEventModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    push_id: str
    cell_seq: Optional[str] = None
    region: str
    jump_times: Optional[str] = None
    created_at: int


class LightningPushSummary(MonitoringLightningPushModel):
    event_count: int = 0
    events: list["MonitoringLightningJumpEventModel"] = []


class LightningPushListResponse(BaseModel):
    items: list[LightningPushSummary]
    total: int


class LightningPushDetailResponse(BaseModel):
    push: MonitoringLightningPushModel
    events: list[MonitoringLightningJumpEventModel]


def format_lightning_event_text(event: MonitoringLightningJumpEventModel) -> str:
    """播报文案的唯一拼法："{地区} 闪电跃增预警 · {最新一个跳增时刻}"。"""
    times = [t for t in (event.jump_times or "").split(";") if t]
    latest_time = times[-1] if times else "--"
    return f"{event.region} 闪电跃增预警 · {latest_time}"


class MonitoringLightningPushTable:
    def upsert_push(
        self,
        csv_path: str,
        push_time: Optional[int],
        coverage_start: Optional[int],
        coverage_end: Optional[int],
        json_path: Optional[str] = None,
        png_path: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> MonitoringLightningPushModel:
        with get_db_context(db) as db:
            existing = (
                db.query(MonitoringLightningPush)
                .filter(MonitoringLightningPush.csv_path == csv_path)
                .first()
            )
            if existing:
                return MonitoringLightningPushModel.model_validate(existing)
            row = MonitoringLightningPush(
                id=str(uuid4()),
                push_time=push_time,
                coverage_start=coverage_start,
                coverage_end=coverage_end,
                csv_path=csv_path,
                json_path=json_path,
                png_path=png_path,
                created_at=int(time.time_ns()),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return MonitoringLightningPushModel.model_validate(row)

    def get_by_id(
        self, id: str, db: Optional[Session] = None
    ) -> Optional[MonitoringLightningPushModel]:
        with get_db_context(db) as db:
            row = db.get(MonitoringLightningPush, id)
            return MonitoringLightningPushModel.model_validate(row) if row else None

    def list_pushes(
        self, skip: int = 0, limit: int = 30, db: Optional[Session] = None
    ) -> LightningPushListResponse:
        with get_db_context(db) as db:
            q = db.query(MonitoringLightningPush).order_by(
                MonitoringLightningPush.push_time.desc()
            )
            total = q.count()
            if skip:
                q = q.offset(skip)
            if limit:
                q = q.limit(limit)
            pushes = q.all()
            push_ids = [p.id for p in pushes]
            events_by_push: dict[str, list[MonitoringLightningJumpEventModel]] = {}
            if push_ids:
                event_rows = (
                    db.query(MonitoringLightningJumpEvent)
                    .filter(MonitoringLightningJumpEvent.push_id.in_(push_ids))
                    .all()
                )
                for row in event_rows:
                    events_by_push.setdefault(row.push_id, []).append(
                        MonitoringLightningJumpEventModel.model_validate(row)
                    )
            return LightningPushListResponse(
                items=[
                    LightningPushSummary(
                        **MonitoringLightningPushModel.model_validate(p).model_dump(),
                        event_count=len(events_by_push.get(p.id, [])),
                        events=events_by_push.get(p.id, []),
                    )
                    for p in pushes
                ],
                total=total,
            )


class MonitoringLightningJumpEventTable:
    def insert_many(
        self,
        push_id: str,
        rows: list[dict],
        db: Optional[Session] = None,
    ) -> int:
        if not rows:
            return 0
        with get_db_context(db) as db:
            now = int(time.time_ns())
            for row in rows:
                db.add(
                    MonitoringLightningJumpEvent(
                        id=str(uuid4()),
                        push_id=push_id,
                        created_at=now,
                        **row,
                    )
                )
            db.commit()
            return len(rows)

    def get_by_push(
        self, push_id: str, db: Optional[Session] = None
    ) -> list[MonitoringLightningJumpEventModel]:
        with get_db_context(db) as db:
            rows = (
                db.query(MonitoringLightningJumpEvent)
                .filter(MonitoringLightningJumpEvent.push_id == push_id)
                .all()
            )
            return [
                MonitoringLightningJumpEventModel.model_validate(r) for r in rows
            ]

    def get_by_id(
        self, id: str, db: Optional[Session] = None
    ) -> Optional[MonitoringLightningJumpEventModel]:
        with get_db_context(db) as db:
            row = db.get(MonitoringLightningJumpEvent, id)
            return (
                MonitoringLightningJumpEventModel.model_validate(row) if row else None
            )

    def get_recent_events(
        self, limit: int = 5, db: Optional[Session] = None
    ) -> list[tuple[MonitoringLightningJumpEventModel, MonitoringLightningPushModel]]:
        """给侧边栏 Ticker 用：按推送时间倒序，(region, jump_times) 去重，取最近 N 条。"""
        with get_db_context(db) as db:
            rows = (
                db.query(MonitoringLightningJumpEvent, MonitoringLightningPush)
                .join(
                    MonitoringLightningPush,
                    MonitoringLightningPush.id == MonitoringLightningJumpEvent.push_id,
                )
                .order_by(MonitoringLightningPush.push_time.desc())
                .limit(limit * 5)  # 多取一些，去重后再截断
                .all()
            )
            seen = set()
            out = []
            for event, push in rows:
                key = (event.region, event.jump_times)
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    (
                        MonitoringLightningJumpEventModel.model_validate(event),
                        MonitoringLightningPushModel.model_validate(push),
                    )
                )
                if len(out) >= limit:
                    break
            return out


####################
# 入库文件去重登记表
####################


class MonitoringIngestFile(Base):
    __tablename__ = "monitoring_ingest_file"

    id = Column(Text, primary_key=True)
    kind = Column(Text, nullable=False)  # 'ground' | 'lightning'
    source_file = Column(Text, nullable=False)
    ingested_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("kind", "source_file", name="uq_ingest_file_kind_source"),
    )


class MonitoringIngestFileTable:
    def get_processed(self, kind: str, db: Optional[Session] = None) -> set[str]:
        with get_db_context(db) as db:
            rows = (
                db.query(MonitoringIngestFile.source_file)
                .filter(MonitoringIngestFile.kind == kind)
                .all()
            )
            return {r[0] for r in rows}

    def mark(
        self, kind: str, source_file: str, db: Optional[Session] = None
    ) -> None:
        with get_db_context(db) as db:
            existing = (
                db.query(MonitoringIngestFile)
                .filter(
                    MonitoringIngestFile.kind == kind,
                    MonitoringIngestFile.source_file == source_file,
                )
                .first()
            )
            if existing:
                return
            db.add(
                MonitoringIngestFile(
                    id=str(uuid4()),
                    kind=kind,
                    source_file=source_file,
                    ingested_at=int(time.time_ns()),
                )
            )
            db.commit()


####################
# 合并告警 Feed（侧边栏 Ticker）
####################


class AlertFeedItem(BaseModel):
    id: str
    type: str  # 'ground' | 'lightning'
    level: Optional[str] = None
    text: str
    target: str
    record_id: str
    occurred_at: int


class AlertFeedResponse(BaseModel):
    items: list[AlertFeedItem]


GroundAlarms = MonitoringGroundAlarmTable()
LightningPushes = MonitoringLightningPushTable()
LightningJumpEvents = MonitoringLightningJumpEventTable()
MonitoringIngestFiles = MonitoringIngestFileTable()
