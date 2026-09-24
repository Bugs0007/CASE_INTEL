"""Printed dates are India's dates, not the server's UTC ones.

TIME_ZONE is UTC, so between 00:00 and 05:30 IST the UTC calendar is still
on yesterday: an invoice issued at 1:30 am IST on 24 Sep was dated 23 Sep.
Every test here pins "now" to 20:00 UTC on 23 Sep 2026 = 01:30 IST on 24 Sep.
"""

import io
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from pdfminer.high_level import extract_text

from core.models import AppearanceFee, Case, Client, Hearing
from core.services.billing_portfolio import render_client_statement_pdf
from core.services.client_updates.compose import compose_payment_reminder
from core.services.india_time import india_date, india_today
from core.services.invoice_service import get_or_create_profile, render_invoice_pdf

LATE_NIGHT_UTC = datetime(2026, 9, 23, 20, 0, tzinfo=dt_timezone.utc)  # 01:30 IST, 24 Sep
HEARING_UTC_MIDNIGHT = datetime(2026, 9, 22, 0, 0, tzinfo=dt_timezone.utc)


@pytest.fixture
def fee(db):
    owner = User.objects.create_user(username="ist-advocate", password="pw-12345")
    client = Client.objects.create(owner=owner, name="Karthik Bablu")
    case = Case.objects.create(owner=owner, case_number="WP/1/2026", title="A vs B", client_name="", client=client)
    hearing = Hearing.objects.create(owner=owner, case=case, hearing_date=HEARING_UTC_MIDNIGHT, hearing_type="other")
    return AppearanceFee.objects.create(
        owner=owner, hearing=hearing, amount=Decimal("15000"), status=AppearanceFee.STATUS_INVOICED,
        invoice_number="INV-0001", invoiced_at=LATE_NIGHT_UTC,
    )


def _text(pdf_bytes: bytes) -> str:
    return extract_text(io.BytesIO(pdf_bytes))


class TestHelpers:
    def test_late_night_utc_is_the_next_day_in_india(self):
        assert india_date(LATE_NIGHT_UTC).isoformat() == "2026-09-24"
        with patch("django.utils.timezone.now", return_value=LATE_NIGHT_UTC):
            assert india_today().isoformat() == "2026-09-24"

    def test_a_stored_hearing_date_keeps_its_day(self):
        assert india_date(HEARING_UTC_MIDNIGHT).isoformat() == "2026-09-22"


@pytest.mark.django_db
class TestPrintedDates:
    def test_invoice_pdf_is_dated_in_india(self, fee):
        text = _text(render_invoice_pdf(fee, get_or_create_profile(fee.owner)))
        assert "Invoice Date: 24 Sep 2026" in text
        assert "22 Sep 2026" in text  # the hearing keeps its own date

    def test_statement_pdf_is_dated_in_india(self, fee):
        with patch("django.utils.timezone.now", return_value=LATE_NIGHT_UTC):
            pdf = render_client_statement_pdf(
                fee.hearing.case.client, AppearanceFee.objects.all(), get_or_create_profile(fee.owner)
            )
        text = _text(pdf)
        assert "Date: 24 Sep 2026" in text
        assert "INV-0001" in text and "24 Sep 2026" in text  # invoiced-on column

    def test_payment_reminder_quotes_the_india_invoice_date(self, fee):
        _, body = compose_payment_reminder(
            fee=fee, profile=get_or_create_profile(fee.owner), recipient_name="Karthik", reminder_number=1
        )
        assert "dated 24 September 2026" in body
        assert "hearing on 22 September 2026" in body
