"""Backfill the two columns 0035 added.

ClientMessage.event_date -- read back out of the dedup key the draft was
created under ("case_update:<case>:<heard-on date>"; a "next:" draft is
dated the day it was created). Reschedule drafts and payment reminders
stay NULL: they sit outside the one-open-update-per-case chain.

CourtOrder.disposes_case -- the same pattern match the worker now runs on
every new order (core/services/disposal.py), over the text already
extracted for the orders we hold. Read in chunks, text only.

Both are plain UPDATEs on small tables; no schema change, no lock beyond
the rows touched. Reverse is a no-op (0035's reverse drops the columns).
"""

from datetime import date

from django.db import migrations


def _event_date(dedup_key: str, created_at):
    parts = (dedup_key or "").split(":")
    if len(parts) == 3 and parts[0] == "case_update":
        try:
            return date.fromisoformat(parts[2])
        except ValueError:
            return None
    if len(parts) == 4 and parts[0] == "case_update" and parts[2] == "next":
        return created_at.date() if created_at else None
    return None


def backfill(apps, schema_editor):
    from core.services.disposal import order_text_disposes_case

    ClientMessage = apps.get_model("core", "ClientMessage")
    for message in ClientMessage.objects.filter(kind="case_update", event_date__isnull=True).only(
        "id", "dedup_key", "created_at"
    ):
        day = _event_date(message.dedup_key, message.created_at)
        if day is not None:
            ClientMessage.objects.filter(id=message.id).update(event_date=day)

    CourtOrder = apps.get_model("core", "CourtOrder")
    disposing = [
        order_id
        for order_id, text in CourtOrder.objects.filter(document__isnull=False)
        .values_list("id", "document__extracted_text")
        .iterator(chunk_size=200)
        if order_text_disposes_case(text or "")
    ]
    if disposing:
        CourtOrder.objects.filter(id__in=disposing).update(disposes_case=True)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0035_event_date_and_disposal"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
