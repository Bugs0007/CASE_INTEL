"""Dates as the advocate and their clients see them: India time.

TIME_ZONE stays UTC -- hearing dates are stored as UTC midnights of the
portal's date, and a lot depends on that. But anything PRINTED for a
person (an invoice, a statement, a vakalatnama, a reminder email) must
carry India's date: from 00:00 to 05:30 IST the UTC date is still
yesterday, so an invoice issued at 1 am was dated the day before.

Converting a stored hearing date (00:00 UTC) gives 05:30 IST on the same
day, so hearing dates read the same either way.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.utils import timezone

INDIA_TZ = ZoneInfo("Asia/Kolkata")


def india_today() -> date:
    return timezone.localdate(timezone=INDIA_TZ)


def india_now() -> datetime:
    return timezone.localtime(timezone=INDIA_TZ)


def india_date(value: datetime | date | None) -> date | None:
    """The India calendar date of an aware datetime (a date passes through)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return timezone.localtime(value, INDIA_TZ).date()
    return value


def india_fmt(value: datetime | date | None, fmt: str = "%d %b %Y") -> str:
    day = india_date(value)
    return day.strftime(fmt) if day else ""
