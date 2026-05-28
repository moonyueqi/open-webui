"""
Calendar utilities.

RRULE expansion reusing the automation infra, plus the reminder worker
that polls upcoming events and emits `calendar:reminder` over WebSocket.
"""

import asyncio
import logging
import os
import random
import time
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from open_webui.utils.automations import _parse_rule

log = logging.getLogger(__name__)

CALENDAR_ALERT_POLL_INTERVAL = int(os.getenv('CALENDAR_ALERT_POLL_INTERVAL', '30'))
CALENDAR_ALERT_DEFAULT_MINUTES = int(os.getenv('CALENDAR_ALERT_DEFAULT_MINUTES', '10'))


def expand_recurring_event(
    event_dict: dict,
    range_start_ns: int,
    range_end_ns: int,
    tz: Optional[str] = None,
    max_instances: int = 5000,
) -> list[dict]:
    """Expand a recurring event into individual instances within a date range.

    Takes an event dict (from CalendarEventModel.model_dump()) and produces
    one dict per occurrence, with adjusted start_at / end_at.
    """
    from dateutil.rrule import rrulestr

    rrule_str = event_dict.get('rrule')
    if not rrule_str:
        return [event_dict]

    range_start_dt = datetime.fromtimestamp(range_start_ns / 1_000_000_000)
    range_end_dt = datetime.fromtimestamp(range_end_ns / 1_000_000_000)
    scan_start = range_start_dt - timedelta(days=1)

    try:
        # Parse with dtstart near the range so we never iterate from epoch
        rule = rrulestr(rrule_str, dtstart=scan_start, ignoretz=True)
    except Exception:
        log.warning(f'Failed to parse RRULE for event {event_dict.get("id")}: {rrule_str}')
        return [event_dict]

    original_start_ns = event_dict['start_at']
    original_end_ns = event_dict.get('end_at')
    duration_ns = (original_end_ns - original_start_ns) if original_end_ns else None

    instances = []
    dt = rule.after(scan_start, inc=True)

    while dt and dt < range_end_dt and len(instances) < max_instances:
        if tz:
            try:
                dt_tz = dt.replace(tzinfo=ZoneInfo(tz))
                instance_start_ns = int(dt_tz.timestamp() * 1_000_000_000)
            except Exception:
                instance_start_ns = int(dt.timestamp() * 1_000_000_000)
        else:
            instance_start_ns = int(dt.timestamp() * 1_000_000_000)

        if instance_start_ns >= range_start_ns:
            instance = {
                **event_dict,
                'start_at': instance_start_ns,
                'end_at': (instance_start_ns + duration_ns) if duration_ns else None,
                'instance_id': f'{event_dict["id"]}_{instance_start_ns}',
            }
            instances.append(instance)

        dt = rule.after(dt)

    return instances


def ns_from_date(year: int, month: int, day: int, tz: Optional[str] = None) -> int:
    """Create epoch nanoseconds from a date."""
    if tz:
        dt = datetime(year, month, day, tzinfo=ZoneInfo(tz))
    else:
        dt = datetime(year, month, day)
    return int(dt.timestamp() * 1_000_000_000)


############################
# Reminder Worker
############################


async def _emit_reminder(event, attendee_user_ids: list[str]) -> None:
    """Emit `calendar:reminder` to the owner and every attendee.

    Recipients are deduplicated. Frontend listens in (app)/+layout.svelte
    and pops a toast / browser Notification.
    """
    from open_webui.socket.main import sio

    payload = {
        'event_id': event.id,
        'calendar_id': event.calendar_id,
        'title': event.title,
        'description': event.description,
        'location': event.location,
        'start_at': event.start_at,
        'end_at': event.end_at,
        'all_day': event.all_day,
        'color': event.color,
    }

    recipients = {event.user_id, *(uid for uid in attendee_user_ids if uid)}
    for user_id in recipients:
        try:
            await sio.emit('calendar:reminder', payload, room=f'user:{user_id}')
        except Exception:
            log.exception(f'Failed to emit calendar:reminder to user {user_id}')


async def calendar_alert_worker_loop(app) -> None:
    """Poll for upcoming events and emit reminders.

    MVP scope:
    - Non-recurring events only (rrule events are skipped — `get_upcoming_events`
      filters by `start_at` which never advances for stored RRULE rows).
    - No offline catch-up: if the user is not connected at fire time, the
      socket emit is silently dropped. Reminders are NEVER re-sent for an
      event once `meta.last_alerted_at` is stamped.
    - Per-event lookahead comes from `meta.alert_minutes`
      (CALENDAR_ALERT_DEFAULT_MINUTES applied when missing; negative means
      "no alert"; see `get_upcoming_events`).
    """
    from open_webui.models.calendar import CalendarEvents

    default_lookahead_ns = CALENDAR_ALERT_DEFAULT_MINUTES * 60 * 1_000_000_000
    log.info(
        f'Calendar alert worker started '
        f'(poll={CALENDAR_ALERT_POLL_INTERVAL}s, '
        f'default_alert={CALENDAR_ALERT_DEFAULT_MINUTES}m)'
    )

    while True:
        try:
            now_ns = int(time.time_ns())
            upcoming = await CalendarEvents.get_upcoming_events(
                now_ns=now_ns,
                default_lookahead_ns=default_lookahead_ns,
            )
            if upcoming:
                log.debug(f'Calendar alert: {len(upcoming)} event(s) inside alert window')
            for event, _tz in upcoming:
                if event.rrule:
                    log.debug(f'Calendar alert: skipping rrule event {event.id}')
                    continue
                if event.meta and event.meta.get('last_alerted_at'):
                    continue

                claimed = await CalendarEvents.mark_alerted(event.id, now_ns)
                if not claimed:
                    continue

                attendee_ids = [a.user_id for a in (event.attendees or [])]
                log.info(
                    f'Calendar alert firing: event={event.id} '
                    f'title={event.title!r} owner={event.user_id} '
                    f'attendees={len(attendee_ids)}'
                )
                await _emit_reminder(event, attendee_ids)
        except Exception:
            log.exception('Calendar alert worker error')

        await asyncio.sleep(CALENDAR_ALERT_POLL_INTERVAL + random.uniform(0, 2))
