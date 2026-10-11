"""All cause-list dates are IST, whatever the server's timezone.

`settings.TIME_ZONE` is UTC and the box's own clock is unknown, so
`timezone.localdate()` gave the UTC date: at 19:00 UTC (00:30 IST) "today"
was already yesterday's IST date. A hearing "on 12 Oct" is a calendar day
in India, so both sides of every comparison here are IST days.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


def cause_list_tz() -> ZoneInfo:
    return ZoneInfo(getattr(settings, "CAUSE_LIST_TIMEZONE", "Asia/Kolkata"))


def today(now: datetime | None = None) -> date:
    return (now or timezone.now()).astimezone(cause_list_tz()).date()


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """[start, end) of an IST calendar day, as aware datetimes."""
    tz = cause_list_tz()
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    return start, start + timedelta(days=1)


def ist_date_of(moment: datetime) -> date:
    return moment.astimezone(cause_list_tz()).date()
