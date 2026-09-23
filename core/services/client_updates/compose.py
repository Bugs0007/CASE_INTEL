"""Plain-language text for client emails. Pure functions, no DB writes.

A case update tells the client three things: when the matter was heard,
what the court did, and when it comes up next. "What the court did" comes
from the order summary only when there is a real one; for an unreadable,
failed or not-yet-generated summary the email falls back to date and
purpose alone -- it never guesses.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.utils import timezone

from core.models import CourtOrder

# Client-facing wording for the orders the summariser resolves without an
# LLM. The advocate-facing texts in order_summary/service.py talk about
# "directions" and "procedural notes", which a lay client shouldn't need to
# decode.
_NO_DIRECTIONS_TEXT = "The court adjourned the matter without issuing any directions."


def _fmt(day: date) -> str:
    return day.strftime("%d %B %Y")


def _greeting(names: list[str]) -> str:
    names = [n for n in names if n]
    if not names:
        return "Dear Sir/Madam,"
    if len(names) == 1:
        return f"Dear {names[0]},"
    return f"Dear {', '.join(names[:-1])} and {names[-1]},"


def _display_purpose(purpose: str) -> str:
    """eCourts purposes arrive in capitals ("CALL WITH IAS"); sentence-case
    them for a client email. Mixed-case text is left as the advocate typed it."""
    purpose = (purpose or "").strip().rstrip(".")
    if purpose.isupper():
        purpose = purpose.capitalize()
    return purpose


def matter_name(case) -> str:
    """The case title, with its number appended only when the title doesn't
    already carry it (imported titles usually start with it)."""
    title = (case.title or "").strip()
    number = (case.case_number or "").strip()
    if not number or number in title:
        return title or number
    return f"{title} ({number})"


def signature(profile) -> str:
    return profile.advocate_name or profile.letterhead_name or "Your advocate"


def what_happened_line(order: CourtOrder | None) -> str:
    """The "what the court did" sentence, or "" when there's nothing
    trustworthy to say (the caller then uses the date-only template)."""
    if order is None:
        return ""
    if order.summary_status == CourtOrder.SUMMARY_SUMMARIZED:
        return (order.summary_what_happened or "").strip()
    if order.summary_status == CourtOrder.SUMMARY_NO_DIRECTIONS:
        return _NO_DIRECTIONS_TEXT
    # pending / failed / unreadable: nothing reliable to report.
    return ""


def compose_case_update(
    *,
    case,
    profile,
    recipient_names: list[str],
    heard_on: date | None,
    order: CourtOrder | None,
    next_date: date | None,
    next_purpose: str = "",
) -> tuple[str, str]:
    """Subject and body for a 'your matter was heard' update."""
    subject = f"Update on your matter: {case.title}"[:255]

    lines = [_greeting(recipient_names), ""]
    lines.append(f"This is an update on your matter {matter_name(case)}.")
    lines.append("")

    if heard_on is not None:
        happened = what_happened_line(order)
        lines.append(f"The matter was heard on {_fmt(heard_on)}." + (f" {happened}" if happened else ""))
        lines.append("")

    if next_date is not None:
        purpose = _display_purpose(next_purpose)
        lines.append(
            f"The next date of hearing is {_fmt(next_date)}"
            + (f" (listed for: {purpose})." if purpose else ".")
        )
    else:
        lines.append("The next date of hearing has not been fixed yet. I will let you know once it is.")
    lines.append("")

    lines.append("Please feel free to get in touch if you have any questions.")
    lines.append("")
    lines.append("Regards,")
    lines.append(signature(profile))
    return subject, "\n".join(lines) + "\n"


def compose_reschedule_update(
    *, case, profile, recipient_names: list[str], old_date: date, new_date: date, purpose: str = ""
) -> tuple[str, str]:
    """A hearing the advocate moved by hand: 'now listed on B'."""
    subject = f"Hearing date changed: {case.title}"[:255]
    purpose = _display_purpose(purpose)
    lines = [
        _greeting(recipient_names),
        "",
        f"The hearing in your matter {matter_name(case)}, previously "
        f"scheduled for {_fmt(old_date)}, is now listed on {_fmt(new_date)}"
        + (f" (listed for: {purpose})." if purpose else "."),
        "",
        "Please feel free to get in touch if you have any questions.",
        "",
        "Regards,",
        signature(profile),
    ]
    return subject, "\n".join(lines) + "\n"


def _money(amount: Decimal) -> str:
    return f"Rs. {Decimal(amount):,.2f}"


_ORDINAL = {1: "", 2: "Second reminder: ", 3: "Final reminder: "}


def compose_payment_reminder(*, fee, profile, recipient_name: str, reminder_number: int) -> tuple[str, str]:
    case = fee.hearing.case
    prefix = _ORDINAL.get(reminder_number, "Reminder: ")
    subject = f"{prefix}Payment reminder for invoice {fee.invoice_number} - {case.title}"[:255]
    invoiced = timezone.localtime(fee.invoiced_at).date() if fee.invoiced_at else None
    hearing_day = timezone.localtime(fee.hearing.hearing_date).date()
    lines = [
        _greeting([recipient_name]),
        "",
        f"This is a gentle reminder that invoice {fee.invoice_number}"
        + (f" dated {_fmt(invoiced)}" if invoiced else "")
        + f" ({fee.get_category_display().lower()}) for the hearing on {_fmt(hearing_day)} "
        f"in {matter_name(case)}, for {_money(fee.amount)}, is still unpaid.",
        "",
        "If you have already made this payment, please ignore this message, and thank you.",
        "",
        "Regards,",
        signature(profile),
    ]
    return subject, "\n".join(lines) + "\n"
