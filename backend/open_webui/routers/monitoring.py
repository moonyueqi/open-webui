import os
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from open_webui.models.users import UserModel
from open_webui.models.monitoring import (
    GroundAlarms,
    LightningPushes,
    LightningJumpEvents,
    GroundAlarmListResponse,
    GroundAlarmSummaryResponse,
    LightningPushListResponse,
    LightningPushDetailResponse,
    AlertFeedItem,
    AlertFeedResponse,
    format_ground_alarm_text,
    format_lightning_event_text,
)
from open_webui.utils.auth import get_verified_user
from open_webui.utils.monitoring_ingest import MONITORING_DATA_ROOT
from open_webui.constants import ERROR_MESSAGES

log = logging.getLogger(__name__)

router = APIRouter()


####################
# 地面监测 - 自动站报警
####################


@router.get("/ground/alarms", response_model=GroundAlarmListResponse)
async def get_ground_alarms(
    level: Optional[list[str]] = Query(default=None),
    county: Optional[str] = None,
    station_id: Optional[str] = None,
    start: Optional[int] = None,
    end: Optional[int] = None,
    latest_only: bool = True,
    skip: int = 0,
    limit: int = 50,
    user: UserModel = Depends(get_verified_user),
):
    return GroundAlarms.list_alarms(
        level=level,
        county=county,
        station_id=station_id,
        start=start,
        end=end,
        latest_only=latest_only,
        skip=skip,
        limit=limit,
    )


@router.get("/ground/summary", response_model=GroundAlarmSummaryResponse)
async def get_ground_summary(user: UserModel = Depends(get_verified_user)):
    return GroundAlarms.get_summary()


@router.get("/ground/alarms/{id}")
async def get_ground_alarm_by_id(id: str, user: UserModel = Depends(get_verified_user)):
    alarm = GroundAlarms.get_by_id(id)
    if not alarm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )
    return alarm


####################
# 高空预警 - 闪电跳增预警
####################


@router.get("/lightning/pushes", response_model=LightningPushListResponse)
async def get_lightning_pushes(
    skip: int = 0,
    limit: int = 30,
    user: UserModel = Depends(get_verified_user),
):
    return LightningPushes.list_pushes(skip=skip, limit=limit)


@router.get("/lightning/pushes/{id}", response_model=LightningPushDetailResponse)
async def get_lightning_push_detail(id: str, user: UserModel = Depends(get_verified_user)):
    push = LightningPushes.get_by_id(id)
    if not push:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )
    events = LightningJumpEvents.get_by_push(id)
    return LightningPushDetailResponse(push=push, events=events)


@router.get("/lightning/pushes/{id}/image")
async def get_lightning_push_image(id: str, user: UserModel = Depends(get_verified_user)):
    push = LightningPushes.get_by_id(id)
    if not push or not push.png_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )
    # png_path 是相对 MONITORING_DATA_ROOT 的相对路径，拼回绝对路径再校验存在性，
    # 避免相对路径穿越到数据根目录之外。
    root = os.path.abspath(MONITORING_DATA_ROOT)
    abs_path = os.path.abspath(os.path.join(root, push.png_path))
    if not abs_path.startswith(root) or not os.path.isfile(abs_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )
    return FileResponse(abs_path, media_type="image/png")


####################
# 侧边栏播报 Feed（地面+高空合并，最新优先）
####################


@router.get("/alerts/feed", response_model=AlertFeedResponse)
async def get_alerts_feed(
    limit: int = 5,
    user: UserModel = Depends(get_verified_user),
):
    items: list[AlertFeedItem] = []

    for alarm in GroundAlarms.get_latest_feed_items(limit=limit):
        level_map = {"蓝": "info", "黄": "warning", "橙": "danger", "红": "danger"}
        items.append(
            AlertFeedItem(
                id=f"ground-{alarm.id}",
                type="ground",
                level=level_map.get(alarm.level or "", "info"),
                text=format_ground_alarm_text(alarm),
                target=f"/monitoring/ground?alarm_id={alarm.id}",
                record_id=alarm.id,
                occurred_at=alarm.observed_at,
            )
        )

    for event, push in LightningJumpEvents.get_recent_events(limit=limit):
        items.append(
            AlertFeedItem(
                id=f"lightning-{event.id}",
                type="lightning",
                level="warning",
                text=format_lightning_event_text(event),
                target=(
                    f"/monitoring/upper-air/lightning-jump"
                    f"?push_id={push.id}&event_id={event.id}"
                ),
                record_id=event.id,
                occurred_at=push.push_time or push.created_at,
            )
        )

    items.sort(key=lambda i: i.occurred_at, reverse=True)
    return AlertFeedResponse(items=items[:limit])
