"""One way to write money (core/services/money.py): Indian digit grouping,
no ".00" for whole rupees -- the same as the frontend's formatINR. Emails
say "₹1,31,000"; PDFs say "Rs. 1,31,000" (their core fonts have no ₹).
"""

import io
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from pdfminer.high_level import extract_text

from core.models import AppearanceFee, Case, Client, Hearing
from core.services.billing_portfolio import render_client_statement_pdf
from core.services.client_updates.compose import compose_payment_reminder
from core.services.invoice_service import get_or_create_profile, render_invoice_pdf
from core.services.money import format_inr, pdf_inr


@pytest.mark.parametrize(
    "amount, expected",
    [
        ("0", "₹0"),
        ("999", "₹999"),
        ("1000", "₹1,000"),
        (Decimal("15000.00"), "₹15,000"),
        ("131000", "₹1,31,000"),
        ("13100000", "₹1,31,00,000"),
        ("1234567.5", "₹12,34,567.50"),
        ("2500.25", "₹2,500.25"),
        ("-2500", "-₹2,500"),
    ],
)
def test_format_inr(amount, expected):
    assert format_inr(amount) == expected


def test_pdf_amounts_spell_out_rs():
    assert pdf_inr("131000.00") == "Rs. 1,31,000"
    assert pdf_inr("99.5") == "Rs. 99.50"


@pytest.fixture
def fee(db):
    owner = User.objects.create_user(username="money-advocate", password="pw-12345")
    client = Client.objects.create(owner=owner, name="Karthik Bablu")
    case = Case.objects.create(owner=owner, case_number="WP/1/2026", title="A vs B", client_name="", client=client)
    hearing = Hearing.objects.create(
        owner=owner, case=case, hearing_date=datetime(2026, 9, 22, tzinfo=dt_timezone.utc), hearing_type="other"
    )
    return AppearanceFee.objects.create(
        owner=owner, hearing=hearing, amount=Decimal("131000.00"), status=AppearanceFee.STATUS_INVOICED,
        invoice_number="INV-0001", invoiced_at=datetime(2026, 9, 23, 6, tzinfo=dt_timezone.utc),
    )


def _text(pdf_bytes: bytes) -> str:
    return extract_text(io.BytesIO(pdf_bytes))


@pytest.mark.django_db
class TestWhereAmountsAppear:
    def test_payment_reminder_email(self, fee):
        _, body = compose_payment_reminder(
            fee=fee, profile=get_or_create_profile(fee.owner), recipient_name="Karthik", reminder_number=1
        )
        assert "for ₹1,31,000, is still unpaid" in body
        assert ".00" not in body

    def test_invoice_pdf(self, fee):
        text = _text(render_invoice_pdf(fee, get_or_create_profile(fee.owner)))
        assert "Rs. 1,31,000" in text
        assert "131,000.00" not in text

    def test_statement_pdf(self, fee):
        text = _text(
            render_client_statement_pdf(
                fee.hearing.case.client, AppearanceFee.objects.all(), get_or_create_profile(fee.owner)
            )
        )
        assert text.count("Rs. 1,31,000") >= 2  # the row and the total
