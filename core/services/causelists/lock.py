"""Who may talk to which portal, and when.

Rules (owner's decision, 2026-10-10):

- One cause-list run at a time: a Postgres advisory lock.
- NO cause-list work while an advocate search or advocate import is
  running, whatever the portal -- RAM on the t3.small is the constraint,
  and those jobs are the heavy ones.
- Per portal, the cause-list adapter also yields to the other fan-outs that
  hit the same portal: the District Courts adapter waits on a tracked-case
  refresh; the hcservices adapter waits on one too (a refresh covers both
  portals and its payload does not say which, so it blocks both).
  The Supreme Court site (sci.gov.in) is nobody else's portal: no lock.

Only a RUNNING job with a fresh heartbeat counts. A merely queued job
doesn't (it may sit forever behind a stopped worker), and a "running" row
whose heartbeat is stale belongs to a crashed worker.

Not detectable from here: an interactive CNR lookup in a web request leaves
no row. The run is sequential and paced, so the worst overlap is one extra
request.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import timedelta

from django.db import connection
from django.utils import timezone

from .base import PORTAL_DISTRICT, PORTAL_HCSERVICES, PORTAL_SCI

logger = logging.getLogger(__name__)

# 'CAUS' -- any constant works; it only has to be the same everywhere.
ADVISORY_LOCK_KEY = 0x43415553

HEARTBEAT_FRESH = timedelta(minutes=15)

# Blocks everything.
GLOBAL_BLOCKERS = ("advocate_search", "advocate_import")
# Blocks the portals a tracked-case refresh talks to.
REFRESH_BLOCKERS = {
    PORTAL_DISTRICT: ("tracking_refresh",),
    PORTAL_HCSERVICES: ("tracking_refresh",),
    PORTAL_SCI: (),
}


def _running(job_types) -> str | None:
    from core.models import ProcessingJob

    if not job_types:
        return None
    cutoff = timezone.now() - HEARTBEAT_FRESH
    hit = (
        ProcessingJob.objects.filter(
            job_type__in=list(job_types), status="running", updated_at__gte=cutoff
        )
        .values_list("job_type", flat=True)
        .first()
    )
    return hit


def blocked_reason(portal: str | None = None) -> str | None:
    """Why cause-list work must wait right now ('' / None = go ahead).

    With `portal=None` only the global blockers are checked."""
    hit = _running(GLOBAL_BLOCKERS)
    if hit:
        return f"a {hit.replace('_', ' ')} job is running"
    if portal:
        hit = _running(REFRESH_BLOCKERS.get(portal, ()))
        if hit:
            return f"a {hit.replace('_', ' ')} job is running ({portal} portal)"
    return None


@contextmanager
def run_lock():
    """Hold the cause-list advisory lock for the duration of a run.

    Yields True when acquired, False when another run holds it (the caller
    exits quietly; the next timer firing will do the work). The lock is
    session-level, so it is released explicitly and also dies with the
    connection if the process is killed.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [ADVISORY_LOCK_KEY])
        acquired = bool(cursor.fetchone()[0])
    try:
        yield acquired
    finally:
        if acquired:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [ADVISORY_LOCK_KEY])
