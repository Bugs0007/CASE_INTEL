"""Remove court orders stored twice because the portal renumbered them.

Why it happened (see core/services/court_order_sync.py): HC Services
numbers a case's Orders table 1..n by date when it renders the page. An
order uploaded late shifts every later one up a number. WP/26147/2026 was
first synced when the portal listed {1: 07 Aug, 2: 14 Aug}; after the
13 Aug order was uploaded it listed {1: 07 Aug, 2: 13 Aug, 3: 14 Aug}, and
since the order's identity was "<cnr>:<number>:<date>", the 14 Aug order
was downloaded a second time as order 3, next to the first copy labelled
order 2. "Order 2" then showed on both the 13 Aug and 14 Aug hearings.
The sync now relabels a renumbered order instead (reconcile_renumbered).

This migration removes the extra copies already stored. A row is removed
only when a LATER row provably holds the same order:
  - same text: the two documents' extracted text is identical once
    whitespace/punctuation are ignored (the PDFs themselves never hash
    alike -- the portal stamps a fresh creation date and /ID into every
    download), and they share either the number or the date; or
  - the renumbering signature: a later row took its number AND a later
    row holds its date. The later row with its date is the same order
    under its current number -- unless both texts are readable and differ.
Anything that can't be proven is kept (and printed) for a human to look at.

The newest row is kept -- it carries the portal's current number. Before
the old row goes, what hangs off it moves to the survivor: its summary
(only if the survivor has none), the disposal flag, direction tasks,
client-message links, chat citations (document only; the old chunks go
with the old document), email-attachment links and document tags. The
duplicate PDF's FILE is left in storage -- this only deletes rows.

Irreversible (reverse is a no-op): the removed rows were duplicates.
"""

import re

from django.db import migrations
from django.db.models import Count

_RESOLVED = ("unreadable", "no_directions", "summarized")
_SUMMARY_FIELDS = (
    "summary_status",
    "summary_route",
    "summary_what_happened",
    "summary_petitioner_directions",
    "summary_respondent_directions",
    "summary_next_date",
    "summary_next_date_purpose",
    "summary_is_routine_adjournment",
    "summary_generated_at",
    "summary_error",
    "summary_llm_calls",
)


def _text(order) -> str:
    document = order.document
    return re.sub(r"[^a-z0-9]+", "", (document.extracted_text or "").lower()) if document else ""


def _survivor(old, later):
    """The later row that holds the same order as `old`, or None."""
    old_text = _text(old)
    if len(old_text) >= 200:
        for row in sorted(later, key=lambda r: r.order_date != old.order_date):
            shares = row.order_date == old.order_date or row.order_number == old.order_number
            if shares and _text(row) == old_text:
                return row
    took_number = [r for r in later if r.order_number == old.order_number and r.order_date != old.order_date]
    holds_date = [
        r for r in later if old.order_date is not None and r.order_date == old.order_date
        and r.order_number != old.order_number
    ]
    if took_number and len(holds_date) == 1:
        twin = holds_date[0]
        twin_text = _text(twin)
        if len(old_text) >= 200 and len(twin_text) >= 200 and twin_text != old_text:
            return None  # both readable and different: not the same order
        return twin
    return None


def _merge(apps, old, keep):
    CourtOrder = apps.get_model("core", "CourtOrder")
    Task = apps.get_model("core", "Task")
    ClientMessage = apps.get_model("core", "ClientMessage")
    Citation = apps.get_model("core", "Citation")
    EmailAttachment = apps.get_model("core", "EmailAttachment")
    DocumentTagMap = apps.get_model("core", "DocumentTagMap")
    Document = apps.get_model("core", "Document")

    updates = {}
    if keep.summary_status not in _RESOLVED and old.summary_status in _RESOLVED:
        updates.update({f: getattr(old, f) for f in _SUMMARY_FIELDS})
    if old.disposes_case and not keep.disposes_case:
        updates["disposes_case"] = True
    if updates:
        CourtOrder.objects.filter(id=keep.id).update(**updates)

    Task.objects.filter(source_order_id=old.id).update(source_order_id=keep.id)
    ClientMessage.objects.filter(court_order_id=old.id).update(court_order_id=keep.id)

    if old.document_id:
        Citation.objects.filter(document_id=old.document_id).update(
            document_id=keep.document_id, chunk_id=None
        )
        EmailAttachment.objects.filter(document_id=old.document_id).update(document_id=keep.document_id)
        if keep.document_id:
            held = set(DocumentTagMap.objects.filter(document_id=keep.document_id).values_list("tag_id", flat=True))
            for tag_id in DocumentTagMap.objects.filter(document_id=old.document_id).values_list("tag_id", flat=True):
                if tag_id not in held:
                    DocumentTagMap.objects.create(document_id=keep.document_id, tag_id=tag_id)
        document_id = old.document_id
        CourtOrder.objects.filter(id=old.id).delete()
        # Cascades its chunks, versions, tag maps and finished jobs; the
        # historical model has no custom delete(), so the file stays.
        Document.objects.filter(id=document_id).delete()
    else:
        CourtOrder.objects.filter(id=old.id).delete()


def dedupe(apps, schema_editor):
    CourtOrder = apps.get_model("core", "CourtOrder")

    by_number = (
        CourtOrder.objects.values("case_id", "order_number").annotate(n=Count("id")).filter(n__gt=1)
    )
    by_date = (
        CourtOrder.objects.filter(order_date__isnull=False)
        .values("case_id", "order_date")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    )
    case_ids = {row["case_id"] for row in by_number} | {row["case_id"] for row in by_date}

    removed = kept_for_review = 0
    for case_id in sorted(case_ids):
        rows = list(
            CourtOrder.objects.filter(case_id=case_id).select_related("document").order_by("created_at", "id")
        )
        gone = set()
        for index, old in enumerate(rows):
            later = [r for r in rows[index + 1:] if r.id not in gone]
            keep = _survivor(old, later)
            if keep is None:
                clash = [r for r in later if r.order_number == old.order_number]
                if clash:
                    kept_for_review += 1
                    print(
                        f"\n  case {case_id}: order {old.order_number} ({old.order_date}) kept -- "
                        f"can't prove it is the same order as the one now dated {clash[0].order_date}."
                    )
                continue
            print(
                f"\n  case {case_id}: order {old.order_number} ({old.order_date}, id {old.id}) is a copy of "
                f"order {keep.order_number} ({keep.order_date}, id {keep.id}); removing the copy."
            )
            _merge(apps, old, keep)
            gone.add(old.id)
            removed += 1
    if removed or kept_for_review:
        print(f"\n  Court orders: {removed} duplicate(s) removed, {kept_for_review} left for review.")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0036_backfill_event_date_and_disposal"),
    ]

    operations = [
        migrations.RunPython(dedupe, migrations.RunPython.noop),
    ]
