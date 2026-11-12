"""Which appearance fees may be changed or deleted, enforced by the endpoints.

A fee may change while pending, or invoiced and not yet sent (its invoice PDF
is then rendered again under the SAME number). A paid fee, or one whose
invoice was sent or logged as sent, is refused with a 409 and a plain message.
Only a pending fee may be deleted. Another advocate's fee is a 404.
"""

from datetime import datetime
from datetime import timezone as dt_timezone
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from rest_framework.test import APIClient

from core.models import AppearanceFee, Case, Hearing
from core.services import invoice_service

pytestmark = pytest.mark.django_db


@pytest.fixture
def anil(db):
    return User.objects.create_user(username="rules-anil", password="pw-12345")


@pytest.fixture
def other(db):
    return User.objects.create_user(username="rules-other", password="pw-12345")


@pytest.fixture
def api(anil):
    client = APIClient()
    client.force_authenticate(user=anil)
    return client


@pytest.fixture
def case(anil):
    return Case.objects.create(owner=anil, title="Rao vs State", case_number="OS/1/2026")


def make_fee(owner, case, **extra):
    hearing = Hearing.objects.create(
        owner=owner,
        case=case,
        hearing_date=datetime(2026, 10, 1, tzinfo=dt_timezone.utc),
        hearing_type="other",
    )
    return AppearanceFee.objects.create(
        owner=owner, hearing=hearing, category="appearance", amount=Decimal("15000"), **extra
    )


def url(fee):
    return f"/api/appearance-fees/{fee.id}/"


class TestUpdate:
    def test_pending_fee_can_change(self, api, anil, case):
        fee = make_fee(anil, case)
        resp = api.patch(url(fee), {"amount": "20000", "category": "hotel", "description": "Two nights"}, format="json")
        assert resp.status_code == 200
        fee.refresh_from_db()
        assert (fee.amount, fee.category, fee.notes) == (Decimal("20000.00"), "hotel", "Two nights")
        assert resp.json()["description"] == "Two nights"
        assert fee.invoice_number == ""

    def test_invoiced_unsent_fee_changes_and_its_pdf_is_rendered_again_under_the_same_number(
        self, api, anil, case
    ):
        fee = invoice_service.generate_invoice(make_fee(anil, case))
        number, path = fee.invoice_number, fee.invoice_pdf_path
        with default_storage.open(path, "rb") as handle:
            before = handle.read()

        resp = api.patch(url(fee), {"amount": "99999"}, format="json")

        assert resp.status_code == 200
        fee.refresh_from_db()
        assert fee.amount == Decimal("99999.00")
        assert (fee.invoice_number, fee.invoice_pdf_path, fee.status) == (number, path, "invoiced")
        with default_storage.open(fee.invoice_pdf_path, "rb") as handle:
            after = handle.read()
        assert after != before and after.startswith(b"%PDF")
        assert invoice_service.get_or_create_profile(anil).last_invoice_sequence == 1  # none burned

    def test_failed_send_still_counts_as_not_sent(self, api, anil, case):
        fee = invoice_service.generate_invoice(make_fee(anil, case))
        AppearanceFee.objects.filter(id=fee.id).update(send_status="not_sent")
        assert api.patch(url(fee), {"amount": "1"}, format="json").status_code == 200

    @pytest.mark.parametrize("send_status", ["sent", "logged"])
    def test_sent_or_logged_invoice_is_refused(self, api, anil, case, send_status):
        fee = invoice_service.generate_invoice(make_fee(anil, case))
        AppearanceFee.objects.filter(id=fee.id).update(send_status=send_status)
        resp = api.patch(url(fee), {"amount": "1"}, format="json")
        assert resp.status_code == 409
        assert "already been sent" in resp.json()["detail"]
        fee.refresh_from_db()
        assert fee.amount == Decimal("15000.00")

    def test_paid_fee_is_refused_even_for_a_note(self, api, anil, case):
        fee = invoice_service.generate_invoice(make_fee(anil, case))
        invoice_service.mark_paid(fee)
        resp = api.patch(url(fee), {"description": "late edit"}, format="json")
        assert resp.status_code == 409
        assert "already paid" in resp.json()["detail"]

    def test_status_still_cannot_be_patched(self, api, anil, case):
        fee = make_fee(anil, case)
        api.patch(url(fee), {"status": "paid", "amount": "5"}, format="json")
        fee.refresh_from_db()
        assert fee.status == "pending"

    def test_another_owners_fee_is_a_404(self, api, other):
        theirs = make_fee(other, Case.objects.create(owner=other, title="Theirs", case_number="X/1/2026"))
        assert api.patch(url(theirs), {"amount": "1"}, format="json").status_code == 404
        assert api.delete(url(theirs)).status_code == 404
        theirs.refresh_from_db()
        assert theirs.amount == Decimal("15000.00")


class TestDelete:
    def test_pending_fee_can_be_deleted(self, api, anil, case):
        fee = make_fee(anil, case)
        assert api.delete(url(fee)).status_code == 204
        assert not AppearanceFee.objects.filter(id=fee.id).exists()

    def test_invoiced_fee_cannot_be_deleted(self, api, anil, case):
        fee = invoice_service.generate_invoice(make_fee(anil, case))
        resp = api.delete(url(fee))
        assert resp.status_code == 409
        assert "already been invoiced" in resp.json()["detail"]
        assert AppearanceFee.objects.filter(id=fee.id).exists()

    def test_paid_fee_cannot_be_deleted(self, api, anil, case):
        fee = invoice_service.generate_invoice(make_fee(anil, case))
        invoice_service.mark_paid(fee)
        resp = api.delete(url(fee))
        assert resp.status_code == 409
        assert AppearanceFee.objects.filter(id=fee.id).exists()
