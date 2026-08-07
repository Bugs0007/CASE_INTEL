"""Match a parsed cause list against tracked hearings and record the
result on the Hearing rows.

Split from the parser on purpose: the parser is pure
(PDF bytes -> CauseListDocument) and the whole matching/storage policy
lives here, so the tests can exercise matching against the real fixtures
without any network.

Works against a CauseListDay -- every document published for a date, ~58
of them across several court halls -- rather than a single document. The
court hall therefore comes from the matched ITEM, not from the day.
"""

from __future__ import annotations

import logging
from datetime import date

from django.utils import timezone

from core.models import Case, Hearing

from .exceptions import (
    CauseListNotConfiguredError,
    CauseListNotPublishedError,
    CauseListParseError,
)
from .telangana_hc import (
    COURT_KEY,
    CauseListDay,
    fetch_cause_list_day,
    normalize_case_token,
)

logger = logging.getLogger(__name__)


def candidate_keys_for_case(case: Case) -> set[tuple[str, str, str]]:
    """Every normalized (TYPE, NUMBER, YEAR) this case might be listed as.

    Drawn from more than one field because there is no single reliable
    one: `case_number` is free text that advocate_import fills from the
    portal's case_number when it has one and falls back to the CNR when
    it doesn't, and `tracking_config` carries case_type/case_number/year
    only for cases set up through the cascade form (CNR-first setups have
    just {'court_type', 'cnr'}).

    A case that yields no keys at all simply cannot be matched by number
    -- reported as "unmatchable" rather than "not listed", since those
    mean different things to the advocate.
    """
    keys: set[tuple[str, str, str]] = set()

    for value in (case.case_number, case.title):
        key = normalize_case_token(value or "")
        if key is not None:
            keys.add(key)

    config = case.tracking_config or {}
    case_type = str(config.get("case_type") or "").strip()
    case_number = str(config.get("case_number") or "").strip()
    year = str(config.get("year") or "").strip()
    if case_type and case_number and year:
        # District configs carry a portal code like "2^2" here rather
        # than a readable type; normalize_case_token rejects those, which
        # is correct -- a code can't be matched against the printed list.
        key = normalize_case_token(f"{case_type}/{case_number}/{year}")
        if key is not None:
            keys.add(key)

    return keys


def apply_cause_list(
    cause_list: CauseListDay, hearings: list[Hearing], *, court_key: str = COURT_KEY
) -> dict:
    """Record each hearing's listing state against a PUBLISHED list.

    Every hearing passed in is resolved to exactly one of:
      - "listed"     -- found; item number + court hall stored
      - "not_listed" -- the list is out and this case isn't in it
      - "unmatchable" -- the case carries no parseable case number, so
        absence proves nothing (stored as not_listed=False; the row keeps
        its previous state and the case is logged for the operator)

    Unmatched ITEMS (matters in the list belonging to no tracked case)
    are counted and a sample logged -- that is the signal the court is
    listing something the advocate isn't tracking.
    """
    index = cause_list.index_by_case()
    now = timezone.now()

    listed: list[Hearing] = []
    not_listed: list[Hearing] = []
    unmatchable: list[Hearing] = []
    matched_keys: set[tuple[str, str, str]] = set()

    for hearing in hearings:
        keys = candidate_keys_for_case(hearing.case)
        if not keys:
            unmatchable.append(hearing)
            logger.warning(
                "Cause list: case %s (hearing %d) has no parseable case number "
                "(case_number=%r) -- cannot be matched against the list.",
                hearing.case.case_number,
                hearing.id,
                hearing.case.case_number,
            )
            continue

        item = next((index[key] for key in keys if key in index), None)
        if item is None:
            hearing.cause_list_status = Hearing.CAUSE_LIST_NOT_LISTED
            hearing.cause_list_item_number = ""
            hearing.cause_list_court_hall = ""
            hearing.cause_list_stage = ""
            hearing.cause_list_checked_at = now
            hearing.cause_list_source = court_key
            not_listed.append(hearing)
            continue

        matched_keys.update(key for key in keys if key in index)
        hearing.cause_list_status = Hearing.CAUSE_LIST_LISTED
        hearing.cause_list_item_number = item.item_number
        # From the ITEM, not the day: one date spans many halls, and the
        # hall an advocate must walk into is the one their own matter is
        # listed in.
        hearing.cause_list_court_hall = item.court_hall
        hearing.cause_list_stage = item.stage
        hearing.cause_list_checked_at = now
        hearing.cause_list_source = court_key
        listed.append(hearing)

    _save(listed + not_listed)

    unmatched_items = [
        item for key, item in index.items() if key not in matched_keys
    ]
    if unmatched_items:
        logger.info(
            "Cause list %s (%s, %d document(s)): %d of %d listed matters belong to "
            "no tracked case. Sample: %s",
            court_key,
            cause_list.list_date.isoformat() if cause_list.list_date else "undated",
            len(cause_list.documents),
            len(unmatched_items),
            len(index),
            ", ".join(
                f"item {i.item_number} {i.case_token} (hall {i.court_hall or '?'})"
                for i in unmatched_items[:5]
            ),
        )

    logger.info(
        "Cause list %s applied: %d listed, %d not listed, %d unmatchable.",
        court_key,
        len(listed),
        len(not_listed),
        len(unmatchable),
    )

    return {
        "listed": len(listed),
        "not_listed": len(not_listed),
        "unmatchable": len(unmatchable),
        "unmatched_items": len(unmatched_items),
        "total_items": len(index),
        "documents": len(cause_list.documents),
        "court_halls": sorted({d.court_hall for d in cause_list.documents if d.court_hall}),
        "list_date": cause_list.list_date,
    }


def mark_not_published(hearings: list[Hearing], *, court_key: str = COURT_KEY) -> int:
    """Record that the list for these hearings' date isn't out yet.

    This is what the frontend renders as "Not yet listed". Deliberately
    distinct from "not listed": before publication, absence carries no
    information at all, and showing an advocate "not listed" the evening
    before a hearing when the court simply hasn't published would be
    actively misleading.

    Never downgrades a hearing that is already `listed` -- once an item
    number is known, a later failed fetch must not erase it.
    """
    now = timezone.now()
    updated = []
    for hearing in hearings:
        if hearing.cause_list_status == Hearing.CAUSE_LIST_LISTED:
            continue
        hearing.cause_list_status = Hearing.CAUSE_LIST_NOT_PUBLISHED
        hearing.cause_list_checked_at = now
        hearing.cause_list_source = court_key
        updated.append(hearing)

    _save(updated)
    return len(updated)


def _save(hearings: list[Hearing]) -> None:
    if not hearings:
        return
    Hearing.objects.bulk_update(
        hearings,
        [
            "cause_list_status",
            "cause_list_item_number",
            "cause_list_court_hall",
            "cause_list_stage",
            "cause_list_checked_at",
            "cause_list_source",
        ],
    )


def tracked_hearings_on(target_date: date) -> list[Hearing]:
    """Scheduled hearings on `target_date` for cases tracked at the court
    this module handles.

    Scoped to high_court cases with tracking enabled -- a district-court
    case would never appear in this list, and checking it against the
    High Court's list would produce a false "not listed".

    Not owner-scoped: this runs as a system job across every advocate's
    cases, exactly like the order-sync worker. The results are written to
    each hearing's own row, which stays owner-scoped on read.
    """
    return list(
        Hearing.objects.select_related("case")
        .filter(
            hearing_date__date=target_date,
            status="scheduled",
            case__tracking_enabled=True,
            case__court_type="high_court",
        )
        .order_by("id")
    )


def check_cause_list_for_date(
    target_date: date, *, cause_list_day: CauseListDay | None = None
) -> dict:
    """Fetch (or accept) every list for `target_date` and apply it.

    `cause_list_day` is an injection point for tests and for re-running
    against saved documents; when given, nothing is downloaded.

    Returns a result dict; never raises for the ordinary
    "not published yet" case, which is recorded and reported instead.
    """
    hearings = tracked_hearings_on(target_date)
    if not hearings:
        logger.info("Cause list: no tracked High Court hearings on %s.", target_date)
        return {"date": target_date, "hearings": 0, "status": "no_hearings"}

    try:
        cause_list = (
            cause_list_day
            if cause_list_day is not None
            else fetch_cause_list_day(target_date)
        )
    except CauseListNotPublishedError as exc:
        count = mark_not_published(hearings)
        logger.info(
            "Cause list for %s not published yet (%s) -- %d hearing(s) marked "
            "'not yet listed'.",
            target_date,
            exc,
            count,
        )
        return {
            "date": target_date,
            "hearings": len(hearings),
            "status": "not_published",
            "marked": count,
        }
    except CauseListNotConfiguredError:
        # An operator problem, not a court one -- do NOT record these
        # hearings as "not published", which would misreport a missing
        # setting as a court that hasn't published.
        raise
    except CauseListParseError:
        logger.exception(
            "Cause list for %s could not be parsed -- leaving %d hearing(s) "
            "untouched rather than recording a false 'not listed'.",
            target_date,
            len(hearings),
        )
        return {
            "date": target_date,
            "hearings": len(hearings),
            "status": "parse_error",
        }

    # A published list is for one specific date; if the document's own
    # date disagrees with what was asked for, the portal served a
    # different day's list and applying it would stamp wrong item
    # numbers onto real hearings.
    if cause_list.list_date is not None and cause_list.list_date != target_date:
        logger.error(
            "Cause list date mismatch: asked for %s, document is for %s. "
            "Not applying it.",
            target_date,
            cause_list.list_date,
        )
        return {
            "date": target_date,
            "hearings": len(hearings),
            "status": "date_mismatch",
            "document_date": cause_list.list_date,
        }

    result = apply_cause_list(cause_list, hearings)
    result.update({"date": target_date, "hearings": len(hearings), "status": "applied"})
    return result
