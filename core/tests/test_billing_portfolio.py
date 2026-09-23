"""Billing portfolio: aging buckets, outstanding per client, uninvoiced
hearings this month, and the per-client statement PDF."""

import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from pdfminer.high_level import extract_text
from rest_framework.test import APIClient

from core.models import AppearanceFee, Case, Client, Hearing
from core.services import invoice_service
from core.services.billing_portfolio import bucket_for


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="portfolio-advocate", password="pw-12345")


@pytest.fixture
def api(advocate):
    client = APIClient()
    client.force_authenticate(user=advocate)
    return client


_n = iter(range(1, 10_000))


def _case(owner, client=None, client_name="Walk-in"):
    n = next(_n)
    return Case.objects.create(
        owner=owner, case_number=f"OS/{n}/2026", title=f"OS/{n}/2026 A vs B", client_name=client_name, client=client
    )


def _hearing(case, when):
    return Hearing.objects.create(
        owner=case.owner, case=case, hearing_date=when + timedelta(minutes=next(_n)), hearing_type="other"
    )


def _fee(case, *, status, invoiced_days_ago=None, amount="1000.00", when=None):
    hearing = _hearing(case, when or timezone.now() - timedelta(days=200))
    fee = AppearanceFee.objects.create(owner=case.owner, hearing=hearing, amount=Decimal(amount))
    if status != AppearanceFee.STATUS_PENDING:
        fee = invoice_service.generate_invoice(fee)
        AppearanceFee.objects.filter(id=fee.id).update(
            invoiced_at=timezone.now() - timedelta(days=invoiced_days_ago or 0)
        )
        if status == AppearanceFee.STATUS_PAID:
            invoice_service.mark_paid(fee)
    return fee


@pytest.mark.parametrize(
    "age, label", [(0, "0-30"), (30, "0-30"), (31, "31-60"), (60, "31-60"), (61, "61-90"), (90, "61-90"), (91, "90+"), (400, "90+")]
)
def test_bucket_boundaries(age, label):
    assert bucket_for(age) == label


@pytest.mark.django_db
class TestPortfolio:
    def test_aging_counts_only_invoiced_unpaid(self, api, advocate):
        case = _case(advocate)
        for days, amount in ((10, "100"), (45, "200"), (75, "300"), (120, "400")):
            _fee(case, status=AppearanceFee.STATUS_INVOICED, invoiced_days_ago=days, amount=amount)
        _fee(case, status=AppearanceFee.STATUS_PAID, invoiced_days_ago=200, amount="999")
        _fee(case, status=AppearanceFee.STATUS_PENDING, amount="50")

        data = api.get("/api/billing/portfolio/").data

        assert [(b["label"], b["count"], b["amount"]) for b in data["aging"]] == [
            ("0-30", 1, "100.00"),
            ("31-60", 1, "200.00"),
            ("61-90", 1, "300.00"),
            ("90+", 1, "400.00"),
        ]
        assert data["totals"]["invoiced_amount"] == "1000.00"
        assert data["totals"]["pending_amount"] == "50.00"

    def test_outstanding_per_client_and_unassigned(self, api, advocate):
        acme = Client.objects.create(owner=advocate, name="Acme", client_type=Client.TYPE_BUSINESS)
        _fee(_case(advocate, client=acme), status=AppearanceFee.STATUS_INVOICED, invoiced_days_ago=70, amount="500")
        _fee(_case(advocate, client=acme), status=AppearanceFee.STATUS_INVOICED, invoiced_days_ago=5, amount="250")
        loose = _case(advocate, client_name="Ramesh")
        _fee(loose, status=AppearanceFee.STATUS_PENDING, amount="75")

        data = api.get("/api/billing/portfolio/").data

        (row,) = data["clients"]
        assert row["client_name"] == "Acme"
        assert row["invoiced_amount"] == "750.00"
        assert row["invoiced_count"] == 2
        assert row["oldest_invoice_days"] == 70
        assert row["case_count"] == 2
        (unassigned,) = data["unassigned"]
        assert unassigned["case_id"] == loose.id
        assert unassigned["client_name"] == "Ramesh"
        assert unassigned["pending_amount"] == "75.00"

    def test_uninvoiced_hearings_this_month(self, api, advocate):
        today = timezone.localdate()
        if today.day == 1:
            pytest.skip("No 'earlier this month' on the 1st.")
        case = _case(advocate)
        earlier = timezone.now() - timedelta(days=1)
        unbilled = _hearing(case, earlier)
        pending_only = _hearing(case, earlier)
        AppearanceFee.objects.create(owner=advocate, hearing=pending_only, amount=Decimal("100"))
        billed = _fee(case, status=AppearanceFee.STATUS_INVOICED, invoiced_days_ago=0, when=earlier)
        _hearing(case, timezone.now() + timedelta(days=40))  # future: not yet due
        cancelled = _hearing(case, earlier)
        Hearing.objects.filter(id=cancelled.id).update(status="cancelled")

        rows = api.get("/api/billing/portfolio/").data["uninvoiced_hearings"]

        ids = {r["hearing_id"] for r in rows}
        assert ids == {unbilled.id, pending_only.id}
        assert billed.hearing_id not in ids


@pytest.mark.django_db
class TestStatementPdf:
    def test_statement_lists_the_clients_unpaid_invoices(self, api, advocate):
        acme = Client.objects.create(
            owner=advocate, name="Acme Traders", client_type=Client.TYPE_BUSINESS, gstin="36ABCDE1234F1Z5"
        )
        unpaid = _fee(_case(advocate, client=acme), status=AppearanceFee.STATUS_INVOICED, invoiced_days_ago=40)
        paid = _fee(_case(advocate, client=acme), status=AppearanceFee.STATUS_PAID, invoiced_days_ago=10)
        other_clients = _fee(_case(advocate), status=AppearanceFee.STATUS_INVOICED, invoiced_days_ago=3)

        resp = api.get(f"/api/clients/{acme.id}/statement/pdf/")

        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/pdf"
        text = " ".join(extract_text(io.BytesIO(resp.content)).split())
        assert "STATEMENT OF ACCOUNT" in text
        assert unpaid.invoice_number in text
        assert paid.invoice_number not in text
        assert other_clients.invoice_number not in text
        assert "36ABCDE1234F1Z5" in text
        assert invoice_service.REVERSE_CHARGE_LINE in text
