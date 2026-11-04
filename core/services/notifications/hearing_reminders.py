"""Hearing reminder emails: a digest to the advocate two days and one day
before each hearing.

Driven by `manage.py send_hearing_reminders`, run by a systemd timer at
09:00 and 19:45 IST (after the 19:00 cause-list fetch). Each run looks at
the hearings whose India date is today+1 (lead 1) and today+2 (lead 2):

  * normal case: lead 2 goes out at 09:00 two days before, lead 1 at 09:00
    the day before -- both at least 24 hours ahead of a ~10:30 sitting;
  * a hearing discovered after the morning run (a case refresh at 14:00
    finds one tomorrow) goes out at 19:45 that evening -- later than 24
    hours, but better than nothing. The email says "added today".

Rules this module keeps:

  * ONE email per advocate per run, never one per hearing. Tasks and case
    events due on the same days ride along ("Also due") but never trigger an
    email on their own.
  * A hearing is reminded at most once per lead. HearingReminder is the
    dedup record (unique on hearing + hearing_date + lead_days), so an
    edited hearing date reminds again for the new date. `sent` and `logged`
    are final; `failed` is retried on a later run of the SAME lead window
    (the hearing is still ahead), up to MAX_ATTEMPTS. A lead-2 failure that
    is still unsent when the hearing becomes lead 1 is superseded by the
    lead-1 reminder rather than resent as a stale "in 2 days".
  * Days are India days. The window is built from aware IST midnights, never
    `__date` on UTC: an eCourts hearing is stored at 00:00 UTC (05:30 IST,
    same day) and a manual one can carry any time, e.g. 00:30 IST, which is
    still the previous day in UTC.
  * One advocate's failure never stops the others. A Postgres advisory lock
    keeps two overlapping runs from double-sending.

This module deliberately does not touch core/services/email_delivery.py (the
client-email path); it reuses only its `email_is_configured()` helper and the
same mail backend.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from email.utils import formataddr

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.db import connection, transaction
from django.utils import timezone

from core.models import AdvocateProfile, CaseEvent, Hearing, HearingReminder, Task
from core.services.email_delivery import email_is_configured
from core.services.india_time import INDIA_TZ, india_date, india_today

logger = logging.getLogger(__name__)

LEAD_ONE_DAY = 1
LEAD_TWO_DAYS = 2
# Failed sends are retried by later runs until this many attempts were made.
MAX_ATTEMPTS = 3
MAX_ALSO_DUE_LINES = 10
# 'HREM' -- any constant works; it only has to differ from the other
# advisory locks in the project (causelists/lock.py uses 'CAUS').
ADVISORY_LOCK_KEY = 0x4852454D
INACTIVE_CASE_STATUSES = ("closed", "archived")


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class Reminder:
    """One hearing to be reminded about at one lead."""

    hearing: Hearing
    lead: int
    # The earlier failed attempt, when this is a retry.
    row: HearingReminder | None = None


@dataclass
class Digest:
    owner: object
    recipient: str
    items: list[Reminder]
    subject: str
    body: str


@dataclass
class RunReport:
    today: date
    not_run_reason: str = ""
    digests: list[Digest] = field(default_factory=list)
    sent: int = 0
    logged: int = 0
    failed: int = 0
    crashed: int = 0
    opted_out: int = 0
    no_recipient: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Selecting what to remind about
# ---------------------------------------------------------------------------


def _ist_midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=INDIA_TZ)


def _wants(profile: AdvocateProfile | None, lead: int) -> bool:
    if profile is None:  # no profile row yet: the defaults are all on
        return True
    if not profile.hearing_reminders_enabled:
        return False
    return profile.hearing_reminder_two_days if lead == LEAD_TWO_DAYS else profile.hearing_reminder_one_day


def recipient_for(owner, profile: AdvocateProfile | None) -> str:
    """Where reminders go: the advocate's contact email, else their login email."""
    return ((profile.contact_email if profile else "") or owner.email or "").strip()


def _pending(today: date, owner_username: str | None, report: RunReport):
    """{owner_id: [Reminder, ...]} for this run, plus {owner_id: profile}."""
    window_start = _ist_midnight(today + timedelta(days=LEAD_ONE_DAY))
    window_end = _ist_midnight(today + timedelta(days=LEAD_TWO_DAYS + 1))
    queryset = (
        Hearing.objects.filter(
            status="scheduled",
            hearing_date__gte=window_start,
            hearing_date__lt=window_end,
            owner__is_active=True,
        )
        .exclude(case__status__in=INACTIVE_CASE_STATUSES)
        .select_related("case", "owner")
        .order_by("hearing_date", "id")
    )
    if owner_username:
        queryset = queryset.filter(owner__username=owner_username)
    hearings = list(queryset)

    profiles = {
        p.owner_id: p
        for p in AdvocateProfile.objects.filter(owner_id__in={h.owner_id for h in hearings})
    }
    existing = {
        (r.hearing_id, r.hearing_date, r.lead_days): r
        for r in HearingReminder.objects.filter(hearing_id__in=[h.id for h in hearings])
    }

    by_owner: dict[int, list[Reminder]] = {}
    for hearing in hearings:
        lead = (india_date(hearing.hearing_date) - today).days
        if not _wants(profiles.get(hearing.owner_id), lead):
            report.opted_out += 1
            continue
        row = existing.get((hearing.id, hearing.hearing_date, lead))
        if row is not None and (
            row.delivery != HearingReminder.DELIVERY_FAILED or row.attempts >= MAX_ATTEMPTS
        ):
            continue
        by_owner.setdefault(hearing.owner_id, []).append(Reminder(hearing, lead, row))
    return by_owner, profiles


# ---------------------------------------------------------------------------
# Composing the email
# ---------------------------------------------------------------------------


def _fmt_day(day: date) -> str:
    return f"{day:%a} {day.day} {day:%b}"


def _case_url(case_id: int) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/cases/{case_id}"


def _one_line(text: str, limit: int | None = None) -> str:
    text = " ".join((text or "").split())
    return text[:limit] if limit else text


def _display_items(items: list[Reminder]) -> list[Reminder]:
    """One entry per case per day. An advocate can hold a manual hearing and
    an eCourts one for the same sitting; the email lists the case once,
    preferring the richer (eCourts, cause-list-listed) record."""

    def rank(hearing: Hearing):
        return (hearing.source == "ecourts", hearing.cause_list_status == Hearing.CAUSE_LIST_LISTED)

    best: dict[tuple[int, int], Reminder] = {}
    for item in items:
        key = (item.hearing.case_id, item.lead)
        current = best.get(key)
        if current is None or rank(item.hearing) > rank(current.hearing):
            best[key] = item
    return list(best.values())


def _cause_list_line(hearing: Hearing) -> str:
    if hearing.cause_list_status == Hearing.CAUSE_LIST_LISTED:
        parts = []
        if hearing.cause_list_item_number:
            parts.append(f"Item {hearing.cause_list_item_number}")
        if hearing.cause_list_court_hall:
            parts.append(f"court hall {hearing.cause_list_court_hall}")
        return "Cause list: " + (", ".join(parts) if parts else hearing.get_cause_list_status_display())
    return f"Cause list: {hearing.get_cause_list_status_display()}"


def _hearing_block(hearing: Hearing, today: date) -> list[str]:
    case = hearing.case
    heading = f"* {_one_line(case.title)} ({_one_line(case.case_number)})"
    if india_date(hearing.created_at) == today:
        heading += " -- added today"
    lines = [heading]
    court = hearing.location or case.get_court_type_display() or ""
    if court:
        lines.append(f"  Court: {_one_line(court)}")
    if hearing.purpose:
        lines.append(f"  Purpose: {_one_line(hearing.purpose)}")
    lines.append(f"  {_cause_list_line(hearing)}")
    lines.append(f"  {_case_url(case.id)}")
    return lines


def _also_due(owner, today: date, dates: set[date], furthest: date) -> list[str]:
    """Open tasks due on or before the furthest date (overdue ones marked)
    and scheduled case events on the digest's dates -- across ALL of the
    advocate's cases, sorted soonest first, capped."""
    entries: list[tuple[date, time, str]] = []

    tasks = (
        Task.objects.filter(
            owner=owner,
            status__in=Task.OPEN_STATUSES,
            due_date__isnull=False,
            due_date__lte=furthest,
        )
        .exclude(case__status__in=INACTIVE_CASE_STATUSES)
        .select_related("case")
    )
    for task in tasks:
        label = (
            f"OVERDUE (was {_fmt_day(task.due_date)})"
            if task.due_date < today
            else f"Due {_fmt_day(task.due_date)}"
        )
        suffix = f" -- {_one_line(task.case.title)}" if task.case else ""
        entries.append((task.due_date, time.min, f"{label}: {_one_line(task.title or 'Task')}{suffix}"))

    events = (
        CaseEvent.objects.filter(
            owner=owner, status=CaseEvent.STATUS_SCHEDULED, date__in=dates
        )
        .exclude(case__status__in=INACTIVE_CASE_STATUSES)
        .select_related("case")
    )
    for event in events:
        when = _fmt_day(event.date)
        if event.start_time:
            when += f", {event.start_time:%H:%M}"
            if event.end_time:
                when += f"-{event.end_time:%H:%M}"
        entries.append(
            (
                event.date,
                event.start_time or time.min,
                f"{when}: {event.get_event_type_display()} - {_one_line(event.title)} "
                f"-- {_one_line(event.case.title)}",
            )
        )

    entries.sort(key=lambda e: (e[0], e[1], e[2]))
    lines = [f"* {text}" for _, _, text in entries[:MAX_ALSO_DUE_LINES]]
    if len(entries) > MAX_ALSO_DUE_LINES:
        lines.append(f"+{len(entries) - MAX_ALSO_DUE_LINES} more in Case Intel")
    return lines


def _subject(display: list[Reminder], today: date) -> str:
    if len(display) == 1:
        only = display[0]
        when = "tomorrow" if only.lead == LEAD_ONE_DAY else f"in {only.lead} days"
        return f"Hearing {when}: {_one_line(only.hearing.case.title, 80)}"
    parts = []
    for lead in (LEAD_ONE_DAY, LEAD_TWO_DAYS):
        count = sum(1 for item in display if item.lead == lead)
        if not count:
            continue
        noun = "Hearing" if count == 1 else "Hearings"
        if lead == LEAD_ONE_DAY:
            parts.append(f"{noun} tomorrow ({count})")
        else:
            day = _fmt_day(today + timedelta(days=lead))
            parts.append(f"{day} ({count})" if parts else f"{noun} {day} ({count})")
    return " · ".join(parts)


def build_digest(owner, recipient: str, items: list[Reminder], today: date) -> Digest:
    display = _display_items(items)
    lines: list[str] = []
    dates: set[date] = set()

    for lead in (LEAD_ONE_DAY, LEAD_TWO_DAYS):
        section = sorted(
            (item for item in display if item.lead == lead),
            key=lambda item: (item.hearing.hearing_date, item.hearing.case.title),
        )
        if not section:
            continue
        day = today + timedelta(days=lead)
        dates.add(day)
        heading = f"Tomorrow, {_fmt_day(day)}" if lead == LEAD_ONE_DAY else f"{_fmt_day(day)}, in 2 days"
        lines += [heading, "-" * len(heading)]
        for item in section:
            lines += _hearing_block(item.hearing, today)
            lines.append("")

    also_due = _also_due(owner, today, dates, furthest=max(dates))
    if also_due:
        lines += ["Also due", "--------", *also_due, ""]

    lines += [
        "You get these because hearing reminders are on. "
        f"Change it in Settings: {settings.FRONTEND_URL.rstrip('/')}/settings"
    ]
    return Digest(
        owner=owner,
        recipient=recipient,
        items=items,
        subject=_subject(display, today),
        body="\n".join(lines),
    )


# ---------------------------------------------------------------------------
# Sending and recording
# ---------------------------------------------------------------------------


def _short_error(exc: Exception) -> str:
    return _one_line(f"{type(exc).__name__}: {exc}", 255)


def _deliver(digest: Digest) -> tuple[str, str]:
    """(delivery, error). Never raises for a mail problem."""
    if not email_is_configured():
        logger.warning(
            "EMAIL NOT CONFIGURED -- hearing reminder NOT sent. Would have emailed %s: %s",
            digest.recipient,
            digest.subject,
        )
        return HearingReminder.DELIVERY_LOGGED, ""
    try:
        sent = EmailMessage(
            subject=digest.subject,
            body=digest.body,
            from_email=formataddr(("Case Intel", settings.DEFAULT_FROM_EMAIL)),
            to=[digest.recipient],
            connection=get_connection(),
        ).send(fail_silently=False)
    except Exception as exc:  # noqa: BLE001 -- any mail failure is recorded and retried
        logger.warning("Hearing reminder to %s failed: %s", digest.recipient, _short_error(exc))
        return HearingReminder.DELIVERY_FAILED, _short_error(exc)
    if not sent:
        return HearingReminder.DELIVERY_FAILED, "The mail backend accepted no messages."
    return HearingReminder.DELIVERY_SENT, ""


def _record(digest: Digest, delivery: str, error: str) -> None:
    now = timezone.now()
    sent_at = now if delivery == HearingReminder.DELIVERY_SENT else None
    with transaction.atomic():
        for item in digest.items:
            row = item.row
            if row is None:
                HearingReminder.objects.create(
                    owner=digest.owner,
                    hearing=item.hearing,
                    hearing_date=item.hearing.hearing_date,
                    lead_days=item.lead,
                    recipient=digest.recipient,
                    delivery=delivery,
                    error=error,
                    attempts=1,
                    sent_at=sent_at,
                )
            else:
                row.attempts += 1
                row.recipient = digest.recipient
                row.delivery = delivery
                row.error = error
                row.sent_at = sent_at
                row.save(update_fields=["attempts", "recipient", "delivery", "error", "sent_at"])


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


@contextmanager
def _run_lock():
    """Hold the reminder advisory lock for the run. Yields True when acquired,
    False when another run holds it (the caller exits quietly; the next timer
    firing does the work). Session-level, so it also dies with the connection."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [ADVISORY_LOCK_KEY])
        acquired = bool(cursor.fetchone()[0])
    try:
        yield acquired
    finally:
        if acquired:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [ADVISORY_LOCK_KEY])


def _process(today: date, owner_username: str | None, dry_run: bool, report: RunReport) -> None:
    by_owner, profiles = _pending(today, owner_username, report)
    for owner_id, items in by_owner.items():
        owner = items[0].hearing.owner
        try:
            recipient = recipient_for(owner, profiles.get(owner_id))
            if not recipient:
                logger.info(
                    "Hearing reminders: %s has no contact or login email; skipping.",
                    owner.username,
                )
                report.no_recipient.append(owner.username)
                continue
            digest = build_digest(owner, recipient, items, today)
            report.digests.append(digest)
            if dry_run:
                continue
            delivery, error = _deliver(digest)
            _record(digest, delivery, error)
            if delivery == HearingReminder.DELIVERY_SENT:
                report.sent += 1
            elif delivery == HearingReminder.DELIVERY_LOGGED:
                report.logged += 1
            else:
                report.failed += 1
        except Exception:  # noqa: BLE001 -- one advocate must not stop the rest
            logger.exception("Hearing reminders: user %s failed; carrying on.", owner_id)
            report.crashed += 1


def run(
    *, today: date | None = None, owner_username: str | None = None, dry_run: bool = False
) -> RunReport:
    """Send (or, with dry_run, only compose) this run's reminder digests.

    `today` overrides the India date, for testing. A dry run writes and sends
    nothing and takes no lock."""
    report = RunReport(today=today or india_today())
    if dry_run:
        _process(report.today, owner_username, True, report)
        return report
    with _run_lock() as acquired:
        if not acquired:
            report.not_run_reason = "another hearing-reminder run holds the lock"
            return report
        _process(report.today, owner_username, False, report)
    return report
