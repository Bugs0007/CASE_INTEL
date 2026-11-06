"""
District Courts "Daily Status" (Business on Date) for tracked cases.

High Courts publish order documents; most district courts publish only a
short business text per hearing date ("Petitioner counsel present ... call
on 19.11.2026", next purpose, next date). This stores that text as
CaseBusinessEntry rows.

Runs ONLY inside the process_jobs worker, as a step of the existing
order_sync job (which court_tracking enqueues after a confirm/refresh, so it
inherits the per-case refresh cooldown) -- no web request ever reaches the
portal through here. Deliberately gentle with the portal:

  - only district cases with a CNR, and only business dates the case's own
    hearing history already lists (Hearing.business_date);
  - only the latest COURT_BUSINESS_HISTORY_WINDOW of those dates are ever
    fetched (older history is never backfilled), and of the ones not stored
    yet at most COURT_BUSINESS_FETCHES_PER_SYNC per sync, newest first;
  - nothing missing -> no portal call at all;
  - one portal session per sync (one CAPTCHA'd CNR search, then one POST per
    date), strictly sequential, COURT_BUSINESS_DELAY_SECONDS apart;
  - per-date failure isolation; two dates failing in a row stop the sync;
  - entries are immutable: a date already stored is never fetched again or
    rewritten.

Never raises: a failure here must not fail the order sync it rides on. Logs
case ids, dates and error classes only -- never party names or page text.
"""

from __future__ import annotations

import logging
import time

from django.conf import settings
from django.db import IntegrityError, transaction

from core.models import Case, CaseBusinessEntry, Hearing
from core.services.court_data import get_provider

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILURES = 2


def _empty_result(skipped: str = "") -> dict:
    return {"wanted": 0, "stored": 0, "failed": 0, "unlisted": 0, "stopped_early": False, "skipped": skipped}


def missing_business_dates(case: Case) -> list:
    """Business dates (newest first) within the case's window that have no
    stored entry yet, capped at COURT_BUSINESS_FETCHES_PER_SYNC."""
    window = max(0, int(settings.COURT_BUSINESS_HISTORY_WINDOW))
    per_sync = max(0, int(settings.COURT_BUSINESS_FETCHES_PER_SYNC))
    recent = list(
        Hearing.objects.filter(case=case, owner=case.owner, business_date__isnull=False)
        .order_by("-business_date")
        .values_list("business_date", flat=True)
        .distinct()[:window]
    )
    stored = set(
        CaseBusinessEntry.objects.filter(case=case, business_date__in=recent).values_list("business_date", flat=True)
    )
    return [d for d in recent if d not in stored][:per_sync]


def sync_case_business(case: Case, provider=None) -> dict:
    """Fetch and store the missing Daily Status entries of one tracked
    district case. Returns {"wanted", "stored", "failed", "unlisted",
    "stopped_early", "skipped"}; never raises."""
    config = dict(case.tracking_config or {})
    if not case.tracking_enabled or config.get("court_type") != "district":
        return _empty_result("not_district")
    if not config.get("cnr") and case.cnr_number:
        config["cnr"] = case.cnr_number
    if not config.get("cnr"):
        return _empty_result("no_cnr")

    try:
        wanted = missing_business_dates(case)
    except Exception:  # noqa: BLE001 -- never fail the order sync
        logger.exception("Daily status for case %s: could not work out missing dates.", case.id)
        return _empty_result("error")
    result = _empty_result()
    result["wanted"] = len(wanted)
    if not wanted:
        return result

    provider = provider or get_provider()
    delay = float(settings.COURT_BUSINESS_DELAY_SECONDS)
    try:
        session = provider.business_session(config)
        with session:
            links = {link.business_date: link for link in session.links}
            consecutive = 0
            fetched_any = False
            for business_date in wanted:
                if consecutive >= MAX_CONSECUTIVE_FAILURES:
                    result["stopped_early"] = True
                    logger.warning(
                        "Daily status for case %s stopped after %d failures in a row.", case.id, consecutive
                    )
                    break
                link = links.get(business_date)
                if link is None:
                    # The portal no longer links that date; nothing to ask for.
                    result["unlisted"] += 1
                    continue
                if fetched_any and delay > 0:
                    time.sleep(delay)
                fetched_any = True
                try:
                    record = session.fetch(link)
                except Exception as exc:  # noqa: BLE001 -- isolate one date
                    record = None
                    logger.warning(
                        "Daily status for case %s, %s: fetch failed (%s).",
                        case.id, business_date, type(exc).__name__,
                    )
                if record is None:
                    result["failed"] += 1
                    consecutive += 1
                    continue
                consecutive = 0
                if _store(case, business_date, record):
                    result["stored"] += 1
    except Exception as exc:  # noqa: BLE001 -- the session (CNR search) itself failed
        result["failed"] += 1
        result["skipped"] = "portal"
        logger.warning("Daily status for case %s: portal session failed (%s).", case.id, type(exc).__name__)
    return result


def _store(case: Case, business_date, record) -> bool:
    """Create the entry for `business_date` unless one exists. Never updates
    an existing row (entries are immutable). True if a row was created."""
    try:
        with transaction.atomic():
            _entry, created = CaseBusinessEntry.objects.get_or_create(
                case=case,
                business_date=business_date,
                defaults={
                    "owner": case.owner,
                    "court_name": (record.court_name or "")[:255],
                    "business_text": record.business_text or "",
                    "next_purpose": (record.next_purpose or "")[:255],
                    "next_hearing_date": record.next_hearing_date,
                },
            )
    except IntegrityError:  # a concurrent sync stored it first
        return False
    return created
