"""Billing across all of an advocate's cases: who owes what, for how long,
and which hearings never got billed.

Everything here reads from a queryset the caller has ALREADY scoped to one
owner (the view passes OwnerScopedMixin's get_queryset()), so nothing in
this module can reach another advocate's rows.

"Outstanding" follows the case page's fee summary: INVOICED fees are
billed-and-unpaid (these age), PENDING fees are charges recorded but not yet
invoiced (these don't age -- nothing has been sent). Aging is per fee from
`invoiced_at`, because each fee is its own invoice.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal


from core.models import AppearanceFee, Client
from core.services.india_time import india_date, india_fmt, india_today
from core.services.money import pdf_inr
from core.services.pdf_utils import draw_letterhead, pdf_safe

AGING_BUCKETS = (
    ("0-30", 0, 30),
    ("31-60", 31, 60),
    ("61-90", 61, 90),
    ("90+", 91, None),
)
MAX_ROWS = 200  # cap on list payloads (t3.small; the UI pages beyond this)

ZERO = Decimal("0.00")


def _age_days(fee: AppearanceFee, today: date) -> int:
    invoiced = india_date(fee.invoiced_at) or today
    return max((today - invoiced).days, 0)


def bucket_for(age: int) -> str:
    for label, low, high in AGING_BUCKETS:
        if age >= low and (high is None or age <= high):
            return label
    return AGING_BUCKETS[-1][0]


def portfolio(fees_qs, hearings_qs, *, today: date | None = None) -> dict:
    """The whole billing picture for one advocate.

    fees_qs / hearings_qs must already be owner-scoped.
    """
    today = today or india_today()
    fees = list(
        fees_qs.filter(status__in=(AppearanceFee.STATUS_INVOICED, AppearanceFee.STATUS_PENDING))
        .select_related("hearing__case__client")
    )

    buckets = {label: {"label": label, "count": 0, "amount": ZERO} for label, _, _ in AGING_BUCKETS}
    by_client: dict[int, dict] = {}
    unassigned: dict[int, dict] = {}

    for fee in fees:
        case = fee.hearing.case
        invoiced = fee.status == AppearanceFee.STATUS_INVOICED
        age = _age_days(fee, today) if invoiced else None
        if invoiced:
            bucket = buckets[bucket_for(age)]
            bucket["count"] += 1
            bucket["amount"] += fee.amount

        if case.client_id:
            row = by_client.setdefault(
                case.client_id,
                {
                    "client_id": case.client_id,
                    "client_name": case.client.name,
                    "client_type": case.client.client_type,
                    "invoiced_amount": ZERO,
                    "invoiced_count": 0,
                    "pending_amount": ZERO,
                    "pending_count": 0,
                    "oldest_invoice_days": None,
                    "case_ids": set(),
                },
            )
        else:
            row = unassigned.setdefault(
                case.id,
                {
                    "case_id": case.id,
                    "case_title": case.title,
                    "case_number": case.case_number,
                    "client_name": case.client_name,
                    "invoiced_amount": ZERO,
                    "invoiced_count": 0,
                    "pending_amount": ZERO,
                    "pending_count": 0,
                    "oldest_invoice_days": None,
                },
            )
        if invoiced:
            row["invoiced_amount"] += fee.amount
            row["invoiced_count"] += 1
            if row["oldest_invoice_days"] is None or age > row["oldest_invoice_days"]:
                row["oldest_invoice_days"] = age
        else:
            row["pending_amount"] += fee.amount
            row["pending_count"] += 1
        if "case_ids" in row:
            row["case_ids"].add(case.id)

    # A row is only worth showing when money is actually owed: a Rs. 0
    # charge (an appearance fee recorded before a default fee was set) put
    # "WP/23998/2026 -- Rs. 0.00" under "cases not linked to a client" next
    # to text saying money was owed.
    by_client = {k: r for k, r in by_client.items() if r["invoiced_amount"] + r["pending_amount"] > ZERO}
    unassigned = {k: r for k, r in unassigned.items() if r["invoiced_amount"] + r["pending_amount"] > ZERO}

    clients = sorted(
        by_client.values(),
        key=lambda r: (-(r["oldest_invoice_days"] or -1), -r["invoiced_amount"], r["client_name"]),
    )
    for row in clients:
        row["case_count"] = len(row.pop("case_ids"))

    unassigned_rows = sorted(
        unassigned.values(), key=lambda r: (-(r["oldest_invoice_days"] or -1), r["case_title"])
    )

    uninvoiced = uninvoiced_hearings_this_month(hearings_qs, today=today)

    return {
        "as_of": today,
        "aging": [_money_fields(b, "amount") for b in buckets.values()],
        "totals": {
            "invoiced_amount": str(sum((b["amount"] for b in buckets.values()), ZERO)),
            "invoiced_count": sum(b["count"] for b in buckets.values()),
            "pending_amount": str(sum((f.amount for f in fees if f.status == AppearanceFee.STATUS_PENDING), ZERO)),
            "pending_count": sum(1 for f in fees if f.status == AppearanceFee.STATUS_PENDING),
        },
        "clients": [_money_fields(r, "invoiced_amount", "pending_amount") for r in clients[:MAX_ROWS]],
        "clients_total": len(clients),
        "unassigned": [_money_fields(r, "invoiced_amount", "pending_amount") for r in unassigned_rows[:MAX_ROWS]],
        "unassigned_total": len(unassigned_rows),
        "uninvoiced_hearings": uninvoiced[:MAX_ROWS],
        "uninvoiced_hearings_total": len(uninvoiced),
    }


def _money_fields(row: dict, *keys: str) -> dict:
    out = dict(row)
    for key in keys:
        out[key] = str(out[key])
    return out


def uninvoiced_hearings_this_month(hearings_qs, *, today: date | None = None) -> list[dict]:
    """Hearings this calendar month that have happened but aren't billed:
    no charge recorded at all, or only charges still PENDING."""
    today = today or india_today()
    month_start = today.replace(day=1)
    hearings = (
        hearings_qs.filter(hearing_date__date__gte=month_start, hearing_date__date__lte=today)
        .exclude(status__in=("cancelled", "postponed"))
        .select_related("case")
        .prefetch_related("appearance_fees")
        .order_by("hearing_date", "id")
    )
    rows = []
    for hearing in hearings:
        fees = list(hearing.appearance_fees.all())
        if any(f.status != AppearanceFee.STATUS_PENDING for f in fees):
            continue
        rows.append(
            {
                "hearing_id": hearing.id,
                "hearing_date": hearing.hearing_date,
                "case_id": hearing.case_id,
                "case_title": hearing.case.title,
                "case_number": hearing.case.case_number,
                "pending_amount": str(sum((f.amount for f in fees), ZERO)),
                "has_fee": bool(fees),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Per-client statement PDF
# ---------------------------------------------------------------------------


def _money(amount: Decimal) -> str:
    return pdf_inr(amount)


def render_client_statement_pdf(client: Client, fees_qs, profile, *, today: date | None = None) -> bytes:
    """Outstanding (invoiced, unpaid) invoices across the client's cases,
    oldest first, plus charges recorded but not yet invoiced."""
    from fpdf import FPDF

    from core.services.invoice_service import REVERSE_CHARGE_LINE

    today = today or india_today()
    fees = list(
        fees_qs.filter(hearing__case__client=client)
        .filter(status__in=(AppearanceFee.STATUS_INVOICED, AppearanceFee.STATUS_PENDING))
        .select_related("hearing__case")
        .order_by("invoiced_at", "hearing__hearing_date", "id")
    )
    invoiced = [f for f in fees if f.status == AppearanceFee.STATUS_INVOICED]
    pending = [f for f in fees if f.status == AppearanceFee.STATUS_PENDING]

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    draw_letterhead(pdf, profile)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "STATEMENT OF ACCOUNT", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, pdf_safe(f"Date: {today.strftime('%d %b %Y')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5, pdf_safe(client.name), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for line in (client.address or "").splitlines():
        if line.strip():
            pdf.cell(0, 5, pdf_safe(line.strip()), new_x="LMARGIN", new_y="NEXT")
    if client.is_business and client.gstin:
        pdf.cell(0, 5, pdf_safe(f"GSTIN: {client.gstin}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    widths = (26, 22, 62, 24, 24, 12)  # invoice, date, case, hearing, amount, age
    headers = ("Invoice", "Date", "Case", "Hearing", "Amount", "Days")

    def table_header():
        pdf.set_font("Helvetica", "B", 9)
        for w, h in zip(widths, headers):
            pdf.cell(w, 7, h, border=1, align="C")
        pdf.ln()

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Invoices awaiting payment", new_x="LMARGIN", new_y="NEXT")
    if invoiced:
        table_header()
        pdf.set_font("Helvetica", "", 9)
        for fee in invoiced:
            case = fee.hearing.case
            invoiced_on = india_date(fee.invoiced_at)
            cells = (
                fee.invoice_number,
                invoiced_on.strftime("%d %b %Y") if invoiced_on else "",
                f"{case.case_number} {case.title}"[:40],
                india_fmt(fee.hearing.hearing_date),
                _money(fee.amount),
                str(_age_days(fee, today)),
            )
            for i, (w, value) in enumerate(zip(widths, cells)):
                pdf.cell(w, 7, pdf_safe(value), border=1, align="R" if i >= 4 else "L")
            pdf.ln()
        total = sum((f.amount for f in invoiced), ZERO)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(sum(widths[:4]), 8, "Total outstanding", border=1, align="R")
        pdf.cell(widths[4] + widths[5], 8, pdf_safe(_money(total)), border=1, align="R",
                 new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, "No invoices are awaiting payment.", new_x="LMARGIN", new_y="NEXT")

    if pending:
        pdf.ln(5)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "Charges not yet invoiced", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        for fee in pending:
            case = fee.hearing.case
            pdf.cell(
                0,
                6,
                pdf_safe(
                    f"{india_fmt(fee.hearing.hearing_date)}  "
                    f"{case.case_number} {case.title[:40]}  {fee.get_category_display()}  {_money(fee.amount)}"
                ),
                new_x="LMARGIN",
                new_y="NEXT",
            )

    if client.is_business:
        pdf.ln(5)
        pdf.set_font("Helvetica", "B", 10)
        pdf.multi_cell(0, 5, pdf_safe(REVERSE_CHARGE_LINE))

    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(0, 4, "This is a computer-generated statement issued via Case Intel.")
    return bytes(pdf.output())


def group_cases_for_backfill(cases) -> list[dict]:
    """Group an owner's unassigned cases into would-be Clients for
    manage.py backfill_clients: by billing-contact email (case-insensitive),
    else by normalised client name -- the case's legacy client_name, else
    the billing (then primary) contact's name. Cases imported from eCourts
    have no client_name, so without the contact fallback a contact with no
    email (the common case) was skipped and /clients stayed empty. Pure --
    returns the plan, writes nothing."""
    from core.services.name_matching import normalize_name

    groups: dict[str, dict] = defaultdict(lambda: {"cases": [], "names": [], "emails": set()})
    for case in cases:
        contacts = list(case.client_contacts.all())
        contact = next((c for c in contacts if c.is_billing_contact), None)
        email = (contact.email or "").strip().lower() if contact and contact.email else ""
        named = contact or next((c for c in contacts if c.role == "primary"), None)
        name = (case.client_name or "").strip() or (named.name.strip() if named else "")
        if email:
            key = f"email:{email}"
        elif normalize_name(name):
            key = f"name:{normalize_name(name)}"
        else:
            continue  # nothing to group on -- left unassigned
        group = groups[key]
        group["cases"].append(case)
        if name:
            group["names"].append(name)
        if email:
            group["emails"].add(email)

    plan = []
    for key, group in groups.items():
        names = group["names"]
        # The most common spelling among the grouped cases, longest on a tie.
        best = max(set(names), key=lambda n: (names.count(n), len(n))) if names else ""
        contact_name = ""
        if not best:
            contact = next(
                (c for case in group["cases"] for c in case.client_contacts.all() if c.is_billing_contact),
                None,
            )
            contact_name = contact.name if contact else ""
        plan.append(
            {
                "key": key,
                "name": best or contact_name or sorted(group["emails"])[0],
                "email": sorted(group["emails"])[0] if group["emails"] else "",
                "cases": group["cases"],
            }
        )
    return sorted(plan, key=lambda g: g["name"].lower())
