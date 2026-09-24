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


from core.models import CourtOrder
from core.services.india_time import india_date

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


def case_title(case) -> str:
    """The case's real title, or "" when it has none. A case added by CNR
    before its parties were known carries the CNR (or its number) as a
    placeholder title -- that is not a name to show a client."""
    title = (case.title or "").strip()
    placeholders = {(case.cnr_number or "").strip().upper(), (case.case_number or "").strip().upper()}
    if not title or title.upper() in placeholders - {""}:
        return ""
    return title


def matter_label(case) -> str:
    """What to call the matter in a subject line: its title, else its case
    number -- never the CNR."""
    return case_title(case) or (case.case_number or "").strip() or "your matter"


def matter_name(case) -> str:
    """The case title, with its number appended only when the title doesn't
    already carry it (imported titles usually start with it)."""
    title = case_title(case)
    number = (case.case_number or "").strip()
    if not number or number in title:
        return title or number
    if not title:
        return number
    return f"{title} ({number})"


def signature(profile) -> str:
    """Name, then firm on the next line -- see email_delivery.advocate_signature."""
    from core.services.email_delivery import advocate_signature

    return advocate_signature(profile)


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
    disposed: bool = False,
) -> tuple[str, str]:
    """Subject and body for a 'your matter was heard' update.

    `disposed`: the order (or eCourts) says the case is over, so there is
    no next date to wait for -- say that instead of "not fixed yet"."""
    subject = f"Update on your matter: {matter_label(case)}"[:255]

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
    elif disposed:
        lines.append(
            "With this, the court has disposed of the matter, so there is no further "
            "date of hearing. I will be in touch about the order and any next steps."
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
    subject = f"Hearing date changed: {matter_label(case)}"[:255]
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
    subject = f"{prefix}Payment reminder for invoice {fee.invoice_number} - {matter_label(case)}"[:255]
    invoiced = india_date(fee.invoiced_at)
    hearing_day = india_date(fee.hearing.hearing_date)
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
