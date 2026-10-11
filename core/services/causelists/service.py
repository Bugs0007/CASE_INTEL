"""Fetch -> parse -> match -> write. The only writer of Hearing.cause_list_*.

THE rule (the false-"not listed" bug lived in every route around it):

    A hearing becomes `not_listed` only when EVERY document the court's own
    index lists for its target and date was fetched and parsed, and none
    contains the case.

Anything less is, in order of what we know:
    no list for the date / documents not uploaded yet -> `not_published`
    fetch/CAPTCHA/parse trouble                        -> `fetch_failed`
    no source covers the court                         -> `unsupported`
`listed` is never overwritten by a failure. `not_listed` is assigned in
exactly one place, `decide_outcome`, and a test greps for any other.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from django.db import transaction
from django.utils import timezone

from core.models import CauseListFetch, CauseListMatch, Hearing

from . import clock, lock, registry
from .base import CauseListAdapter, FetchResult, ListingTarget, RawDoc, Resolution
from .exceptions import CauseListError, CauseListParseError
from .matcher import EntryIndex, Match, identity_for_case, find_matches

logger = logging.getLogger(__name__)

L = Hearing  # state constants live on the model

# States a failure outcome is allowed to overwrite. `listed` and an
# established `not_listed` (from a complete read) are facts a failed fetch
# must not erase.
_OVERWRITABLE_BY_FAILURE = {
    L.CAUSE_LIST_NOT_CHECKED,
    L.CAUSE_LIST_NOT_PUBLISHED,
    L.CAUSE_LIST_FETCH_FAILED,
    L.CAUSE_LIST_UNSUPPORTED,
}

_FIELDS = [
    "cause_list_status",
    "cause_list_item_number",
    "cause_list_court_hall",
    "cause_list_stage",
    "cause_list_bench",
    "cause_list_list_type",
    "cause_list_note",
    "cause_list_source_url",
    "cause_list_checked_at",
    "cause_list_source",
]


# ---------------------------------------------------------------------------
# The decision -- pure, so the invariants can be tested without a database
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    status: str
    note: str = ""


def decide_outcome(
    *,
    current_status: str,
    identity_empty: bool,
    n_matches: int,
    index_status: str,
    complete: bool,
    n_unavailable: int,
    n_failed: int,
    n_total: int,
    extra_note: str = "",
) -> Decision | None:
    """The state a hearing should move to, or None to leave it alone.

    `complete` means every document of the index was read; it is the ONLY
    input that can produce `not_listed`.
    """
    if n_matches:
        return Decision(L.CAUSE_LIST_LISTED, extra_note)

    # Nothing found. Without an identity, absence proves nothing at all.
    if identity_empty:
        return None

    if index_status == "none_available":
        failure = Decision(L.CAUSE_LIST_NOT_PUBLISHED, extra_note or "The court has no list for this date yet")
    elif index_status in ("captcha_failed", "fetch_error", "skipped_locked"):
        failure = Decision(L.CAUSE_LIST_FETCH_FAILED, extra_note)
    elif complete:
        # The single assignment of not_listed in the whole code base.
        if current_status == L.CAUSE_LIST_LISTED:
            return None  # never downgrade a known listing
        return Decision(L.CAUSE_LIST_NOT_LISTED, extra_note)
    elif n_failed:
        failure = Decision(
            L.CAUSE_LIST_FETCH_FAILED,
            extra_note or f"{n_failed} of {n_total} lists could not be read",
        )
    elif n_unavailable:
        failure = Decision(
            L.CAUSE_LIST_NOT_PUBLISHED,
            extra_note or f"{n_unavailable} of {n_total} lists not uploaded yet",
        )
    else:
        failure = Decision(L.CAUSE_LIST_FETCH_FAILED, extra_note or "The list was not read completely")

    if current_status not in _OVERWRITABLE_BY_FAILURE:
        return None
    return failure


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _reset_fields(hearing: Hearing) -> None:
    hearing.cause_list_item_number = ""
    hearing.cause_list_court_hall = ""
    hearing.cause_list_stage = ""
    hearing.cause_list_bench = ""
    hearing.cause_list_list_type = ""
    hearing.cause_list_source_url = ""


def _apply_decision(
    hearing: Hearing,
    decision: Decision,
    matches: list[Match],
    *,
    adapter_key: str,
    now,
    source_url: str = "",
) -> None:
    hearing.cause_list_status = decision.status
    hearing.cause_list_note = decision.note[:200]
    hearing.cause_list_checked_at = now
    hearing.cause_list_source = adapter_key
    _reset_fields(hearing)
    if decision.status == L.CAUSE_LIST_LISTED and matches:
        primary = matches[0].entry
        hearing.cause_list_item_number = primary.item_number[:20]
        # From the ENTRY, not the day: one date spans many halls, and the hall
        # an advocate must walk into is the one their own matter is listed in.
        hearing.cause_list_court_hall = primary.court_hall[:20]
        hearing.cause_list_stage = primary.stage[:120]
        hearing.cause_list_bench = (primary.bench or primary.court_name)[:255]
        hearing.cause_list_list_type = primary.list_type[:120]
        hearing.cause_list_source_url = source_url[:500]


def _save(hearings: list[Hearing]) -> None:
    if hearings:
        Hearing.objects.bulk_update(hearings, _FIELDS)


def _replace_matches(hearing: Hearing, matches: list[Match], fetches: dict[str, CauseListFetch]) -> None:
    CauseListMatch.objects.filter(hearing=hearing).delete()
    rows = []
    for n, m in enumerate(matches):
        e = m.entry
        rows.append(
            CauseListMatch(
                owner_id=hearing.owner_id,
                hearing=hearing,
                fetch=fetches.get(e.doc_key),
                item_number=e.item_number[:20],
                court_hall=e.court_hall[:20],
                court_name=e.court_name[:300],
                bench=e.bench[:300],
                list_type=e.list_type[:200],
                stage=e.stage[:200],
                connected=list(e.connected),
                matched_by=m.matched_by,
                is_primary=(n == 0),
            )
        )
    CauseListMatch.objects.bulk_create(rows)


def mark_unsupported(hearings: list[Hearing], reason: str, adapter_key: str = "") -> int:
    """No source covers these hearings' court. Overrides any earlier state:
    an earlier `not_listed`/`listed` for such a hearing could only have come
    from checking it against a list that never covered it."""
    now = timezone.now()
    changed = []
    for h in hearings:
        h.cause_list_status = L.CAUSE_LIST_UNSUPPORTED
        h.cause_list_note = reason[:200]
        h.cause_list_checked_at = now
        h.cause_list_source = adapter_key
        _reset_fields(h)
        changed.append(h)
    _save(changed)
    CauseListMatch.objects.filter(hearing__in=[h.pk for h in changed]).delete()
    return len(changed)


def mark_failed(hearings: list[Hearing], note: str, adapter_key: str = "") -> int:
    """`fetch_failed` for hearings we could not look at -- but never over a
    `listed`/`not_listed` already established by a complete read."""
    now = timezone.now()
    changed = []
    for h in hearings:
        if h.cause_list_status not in _OVERWRITABLE_BY_FAILURE:
            continue
        h.cause_list_status = L.CAUSE_LIST_FETCH_FAILED
        h.cause_list_note = note[:200]
        h.cause_list_checked_at = now
        h.cause_list_source = adapter_key
        changed.append(h)
    _save(changed)
    return len(changed)


# ---------------------------------------------------------------------------
# One group: (adapter, target, date) and the hearings that share it
# ---------------------------------------------------------------------------


@dataclass
class GroupReport:
    adapter: str
    target_key: str
    list_date: date
    hearings: int = 0
    index_status: str = ""
    docs_total: int = 0
    docs_ok: int = 0
    docs_unavailable: int = 0
    docs_failed: int = 0
    entries: int = 0
    listed: int = 0
    not_listed: int = 0
    not_published: int = 0
    fetch_failed: int = 0
    untouched: int = 0
    complete: bool = False
    note: str = ""
    outcomes: list[tuple[int, str, str]] = field(default_factory=list)  # (hearing id, status, note)


def _ledger(adapter: str, target_key: str, list_date: date, kind: str, doc_key: str, **values) -> CauseListFetch:
    obj, _ = CauseListFetch.objects.update_or_create(
        adapter=adapter,
        target_key=target_key,
        list_date=list_date,
        kind=kind,
        doc_key=doc_key,
        defaults=values,
    )
    return obj


def process_group(
    adapter: CauseListAdapter,
    target: ListingTarget,
    list_date: date,
    hearings: list[Hearing],
    *,
    write: bool = True,
    collect: list | None = None,
) -> GroupReport:
    """Fetch the target's lists, read them all, decide each hearing.

    With write=False nothing is stored (the doctor command): the report's
    `outcomes` say what WOULD have been written, and `collect` (if given)
    receives (RawDoc, entries) for every document read.
    """
    report = GroupReport(
        adapter=adapter.key, target_key=target.key, list_date=list_date, hearings=len(hearings)
    )
    workdir = Path(tempfile.mkdtemp(prefix="causelist_")).resolve()
    now = timezone.now()
    court = target.params.get("alias_court") or adapter.key
    try:
        result: FetchResult = adapter.fetch(target, list_date, workdir)
        report.index_status = result.status
        report.docs_total = result.doc_total
        if write:
            _ledger(
                adapter.key, target.key, list_date, CauseListFetch.KIND_INDEX, "",
                status=result.status, doc_total=result.doc_total,
                error=(result.error or result.note)[:2000],
            )

        entries_index = EntryIndex()
        fetches: dict[str, CauseListFetch] = {}
        unavailable = failed = ok = 0
        public_url = ""

        all_final = bool(hearings) and all(
            h.cause_list_status in (L.CAUSE_LIST_LISTED, L.CAUSE_LIST_NOT_LISTED) for h in hearings
        )

        for doc in result.docs:
            if doc.status != "ok":
                # not_uploaded: the court lists it but has not put the file up
                # (-> "not published"); anything else is OUR failure to get it
                # (-> "couldn't check").
                if doc.status == "not_uploaded":
                    unavailable += 1
                else:
                    failed += 1
                if write:
                    fetches[doc.doc_key] = _ledger(
                        adapter.key, target.key, list_date, CauseListFetch.KIND_DOCUMENT, doc.doc_key,
                        status=(
                            CauseListFetch.STATUS_NOT_UPLOADED
                            if doc.status == "not_uploaded"
                            else CauseListFetch.STATUS_FETCH_ERROR
                        ),
                        list_type=doc.list_type[:200], bench_label=doc.bench_label[:300],
                        source_ref=doc.source_ref[:600], source_public=doc.source_public,
                        error=doc.error[:2000],
                    )
                continue
            try:
                if all_final and write and _unchanged(adapter.key, target.key, list_date, doc):
                    ok += 1
                    continue
                parsed = adapter.parse(doc)
                if parsed.list_date is not None and parsed.list_date != list_date:
                    raise CauseListParseError(
                        f"document is for {parsed.list_date}, asked for {list_date}"
                    )
            except CauseListError as exc:
                failed += 1
                logger.warning(
                    "Cause list %s/%s %s: '%s' unreadable: %s",
                    adapter.key, target.key, list_date, doc.list_type, exc,
                )
                if write:
                    fetches[doc.doc_key] = _ledger(
                        adapter.key, target.key, list_date, CauseListFetch.KIND_DOCUMENT, doc.doc_key,
                        status=CauseListFetch.STATUS_PARSE_FAILED, list_type=doc.list_type[:200],
                        bench_label=doc.bench_label[:300], source_ref=doc.source_ref[:600],
                        source_public=doc.source_public, sha256=doc.sha256, error=str(exc)[:2000],
                    )
                _discard(doc, workdir)
                continue
            ok += 1
            entries = [
                e if e.doc_key == doc.doc_key else _with_doc(e, doc.doc_key) for e in parsed.entries
            ]
            entries_index.add(entries, court=court)
            if collect is not None:
                collect.append((doc, entries))
            report.entries += len(entries)
            if doc.source_public and doc.source_ref:
                public_url = public_url or doc.source_ref
            if write:
                fetches[doc.doc_key] = _ledger(
                    adapter.key, target.key, list_date, CauseListFetch.KIND_DOCUMENT, doc.doc_key,
                    status=(
                        CauseListFetch.STATUS_OK if entries else CauseListFetch.STATUS_EMPTY_OK
                    ),
                    list_type=doc.list_type[:200], bench_label=doc.bench_label[:300],
                    source_ref=doc.source_ref[:600], source_public=doc.source_public,
                    sha256=doc.sha256, entry_count=len(entries), error="",
                )
            _discard(doc, workdir)

        report.docs_ok, report.docs_unavailable, report.docs_failed = ok, unavailable, failed
        complete = (
            result.status == "ok"
            and result.doc_total > 0
            and unavailable == 0
            and failed == 0
            and len(result.docs) == result.doc_total
            and not result.early_exit
            and not target.params.get("incomplete_scope")
        )
        # An early exit is only legitimate because everything was found.
        report.complete = complete

        scope_note = str(target.params.get("incomplete_scope") or "")
        listed_updates: list[tuple[Hearing, list[Match]]] = []
        to_save: list[Hearing] = []
        for hearing in hearings:
            identity = identity_for_case(hearing.case, court)
            matches = [] if identity.empty else find_matches(identity, entries_index)
            decision = decide_outcome(
                current_status=hearing.cause_list_status,
                identity_empty=identity.empty,
                n_matches=len(matches),
                index_status=result.status,
                complete=complete,
                n_unavailable=unavailable,
                n_failed=failed,
                n_total=result.doc_total,
                extra_note=(result.error or "")[:150] if result.status in ("captcha_failed", "fetch_error") else scope_note,
            )
            if decision is None:
                report.untouched += 1
                if identity.empty:
                    logger.warning(
                        "Cause list: case %s (hearing %d) has no parseable case number or CNR "
                        "-- cannot be matched, left as it was.",
                        hearing.case.case_number, hearing.pk,
                    )
                report.outcomes.append((hearing.pk, "(unchanged)", ""))
                continue
            report.outcomes.append((hearing.pk, decision.status, decision.note))
            _count(report, decision.status)
            if not write:
                continue
            _apply_decision(
                hearing, decision, matches, adapter_key=adapter.key, now=now, source_url=public_url
            )
            to_save.append(hearing)
            if decision.status == L.CAUSE_LIST_LISTED:
                listed_updates.append((hearing, matches))
        if write:
            with transaction.atomic():
                _save(to_save)
                for hearing, matches in listed_updates:
                    _replace_matches(hearing, matches, fetches)
        _log_unmatched(adapter, target, list_date, entries_index, hearings)
        return report
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _count(report: GroupReport, status: str) -> None:
    attr = {
        L.CAUSE_LIST_LISTED: "listed",
        L.CAUSE_LIST_NOT_LISTED: "not_listed",
        L.CAUSE_LIST_NOT_PUBLISHED: "not_published",
        L.CAUSE_LIST_FETCH_FAILED: "fetch_failed",
    }.get(status)
    if attr:
        setattr(report, attr, getattr(report, attr) + 1)


def _with_doc(entry, doc_key: str):
    from dataclasses import replace

    return replace(entry, doc_key=doc_key)


def _discard(doc: RawDoc, workdir: Path) -> None:
    """Free a document's temp file as soon as it is read -- but only a file
    INSIDE this run's temp dir, never whatever path an adapter handed back."""
    if doc.path and workdir in Path(doc.path).resolve().parents:
        try:
            Path(doc.path).unlink()
        except OSError:
            pass


def _unchanged(adapter: str, target_key: str, list_date: date, doc: RawDoc) -> bool:
    return bool(doc.sha256) and CauseListFetch.objects.filter(
        adapter=adapter, target_key=target_key, list_date=list_date,
        kind=CauseListFetch.KIND_DOCUMENT, doc_key=doc.doc_key,
        sha256=doc.sha256, status__in=[CauseListFetch.STATUS_OK, CauseListFetch.STATUS_EMPTY_OK],
    ).exists()


def _log_unmatched(adapter, target, list_date, index: EntryIndex, hearings) -> None:
    if index.total:
        logger.info(
            "Cause list %s/%s %s: %d entries read for %d tracked hearing(s).",
            adapter.key, target.key, list_date, index.total, len(hearings),
        )


# ---------------------------------------------------------------------------
# The run: select hearings, resolve, group, lock, process
# ---------------------------------------------------------------------------


@dataclass
class RunReport:
    dates: list[date]
    groups: list[GroupReport] = field(default_factory=list)
    unsupported_marked: int = 0
    pending: int = 0
    skipped: list[str] = field(default_factory=list)
    not_run_reason: str = ""
    elapsed: float = 0.0


def select_hearings(dates: list[date]):
    start, _ = clock.day_bounds(min(dates))
    _, end = clock.day_bounds(max(dates))
    return list(
        Hearing.objects.select_related("case")
        .filter(status="scheduled", hearing_date__gte=start, hearing_date__lt=end)
        .order_by("hearing_date", "id")
    )


def plan(hearings: list[Hearing], adapter_keys: set[str] | None = None):
    """Resolve every hearing. Returns (groups, unsupported, pending).

    groups:      {(adapter, target.key, date): (target, [hearings])}
    unsupported: {reason: [hearings]}
    pending:     [hearings]  (covered court, location not yet known)
    """
    groups: dict[tuple, tuple[ListingTarget, list[Hearing]]] = {}
    unsupported: dict[str, list[Hearing]] = {}
    pending: list[Hearing] = []
    cache: dict[int, Resolution] = {}
    for hearing in hearings:
        res = cache.get(hearing.case_id)
        if res is None:
            res = cache[hearing.case_id] = registry.resolve_case(hearing.case)
        if res.kind == "unsupported":
            unsupported.setdefault(res.reason, []).append(hearing)
            continue
        if res.kind == "pending":
            pending.append(hearing)
            continue
        if adapter_keys is not None and res.target.adapter not in adapter_keys:
            continue
        day = clock.ist_date_of(hearing.hearing_date)
        key = (res.target.adapter, res.target.key, day)
        entry = groups.setdefault(key, (res.target, []))
        entry[1].append(hearing)
    # Let each adapter tailor a shared target to ALL hearings that landed on it.
    for key, (target, rows) in list(groups.items()):
        groups[key] = (registry.get_adapter(key[0]).finalize_target(target, rows), rows)
    return groups, unsupported, pending


def run(
    dates: list[date],
    *,
    adapter_keys: list[str] | None = None,
    max_minutes: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> RunReport:
    """One scheduled pass over `dates` (IST days)."""
    from django.conf import settings

    started = monotonic()
    report = RunReport(dates=list(dates))
    max_minutes = max_minutes if max_minutes is not None else float(
        getattr(settings, "CAUSE_LIST_MAX_RUN_MINUTES", 25)
    )
    deadline = started + max_minutes * 60
    wait_budget = float(getattr(settings, "CAUSE_LIST_LOCK_WAIT_SECONDS", 600))
    poll = float(getattr(settings, "CAUSE_LIST_LOCK_POLL_SECONDS", 30))

    selected = set(adapter_keys) if adapter_keys else None
    hearings = select_hearings(dates)
    groups, unsupported, pending = plan(hearings, selected)
    report.pending = len(pending)

    with lock.run_lock() as acquired:
        if not acquired:
            report.not_run_reason = "another cause-list run holds the lock"
            return report

        for reason, rows in unsupported.items():
            report.unsupported_marked += mark_unsupported(rows, reason)

        order = {key: n for n, key in enumerate(registry.ADAPTER_ORDER)}
        todo = sorted(groups.items(), key=lambda kv: (order.get(kv[0][0], 99), kv[0][2], kv[0][1]))
        waited_until = monotonic() + wait_budget

        while todo:
            blocked_global = lock.blocked_reason(None)
            progressed = False
            still: list = []
            for (adapter_key, target_key, day), (target, rows) in todo:
                if monotonic() > deadline:
                    # Cut by the budget: we did not look, so say we couldn't check.
                    mark_failed(rows, "Run time budget reached before this court was checked", adapter_key)
                    report.skipped.append(f"{adapter_key}/{target_key} {day}: run time budget reached")
                    continue
                adapter = registry.get_adapter(adapter_key)
                reason = blocked_global or lock.blocked_reason(adapter.portal)
                if reason:
                    still.append(((adapter_key, target_key, day), (target, rows)))
                    continue
                try:
                    report.groups.append(process_group(adapter, target, day, rows))
                except Exception:  # noqa: BLE001 -- one bad group must not stop the rest
                    logger.exception("Cause list %s/%s %s failed", adapter_key, target_key, day)
                    report.skipped.append(f"{adapter_key}/{target_key} {day}: unexpected error (see log)")
                progressed = True
            todo = still
            if todo and not progressed:
                if monotonic() >= min(waited_until, deadline):
                    for (adapter_key, target_key, day), _ in todo:
                        report.skipped.append(
                            f"{adapter_key}/{target_key} {day}: waiting on "
                            f"{lock.blocked_reason(None) or lock.blocked_reason(registry.get_adapter(adapter_key).portal)}"
                        )
                    break
                sleep(poll)

    report.elapsed = monotonic() - started
    return report
