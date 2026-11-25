"""Per-user call limits (docs/MCP_PLAN.md section 6).

Per minute: counters in the process's LocMemCache. The MCP server runs as
ONE uvicorn worker, so the counter is exact; a restart resets it, which
costs at most one extra minute. Per day: counted from the audit rows
(ActivityLog), so a restart cannot reset it.
"""

from __future__ import annotations

import time
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from core.models import ActivityLog

from .access import TenantContext, scoped
from .audit import ACTIVITY_READ, ACTIVITY_WRITE

def limits() -> tuple[int, int, dict]:
    """(per minute, per day, per-bucket per minute), from settings."""
    return (
        settings.MCP_RATE_PER_MINUTE,
        settings.MCP_RATE_PER_DAY,
        {"search": settings.MCP_RATE_SEARCH_PER_MINUTE, "confirm": settings.MCP_RATE_CONFIRM_PER_MINUTE},
    )


def _count(key: str) -> int:
    cache.add(key, 0, 120)
    try:
        return cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, 120)
        return 1


def check(ctx: TenantContext, bucket: str | None) -> str | None:
    """None if the call may run, else a short reason. Counts this call."""
    per_minute, per_day, per_bucket = limits()
    minute = int(time.time() // 60)
    if _count(f"mcp:rl:{ctx.user.id}:all:{minute}") > per_minute:
        return f"More than {per_minute} calls in one minute. Wait a minute."
    if bucket and _count(f"mcp:rl:{ctx.user.id}:{bucket}:{minute}") > per_bucket[bucket]:
        return f"More than {per_bucket[bucket]} calls of this tool in one minute. Wait a minute."
    since = timezone.now() - timedelta(days=1)
    used = (
        scoped(ActivityLog, ctx)
        .filter(activity_type__in=(ACTIVITY_READ, ACTIVITY_WRITE), created_at__gte=since)
        .count()
    )
    if used >= per_day:
        return f"The limit of {per_day} calls per day is reached."
    return None
