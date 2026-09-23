"""Clients (billing entities spanning cases), the owner-scoped case.client
FK, manage.py backfill_clients, and the GST lines on invoices."""

import io
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone
from pdfminer.high_level import extract_text
from rest_framework.test import APIClient

from core.models import AppearanceFee, Case, Client, ClientContact, Hearing
from core.services import invoice_service


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="client-advocate", password="pw-12345")


@pytest.fixture
def other(db):
    return User.objects.create_user(username="other-advocate", password="pw-12345")


@pytest.fixture
def api(advocate):
    client = APIClient()
    client.force_authenticate(user=advocate)
    return client


_n = iter(range(1, 10_000))


def _case(owner, client_name="Ramesh", **extra):
    n = next(_n)
    return Case.objects.create(
        owner=owner, case_number=f"OS/{n}/2026", title=f"OS/{n}/2026 X vs Y", client_name=client_name, **extra
    )


@pytest.mark.django_db
class TestClientApi:
    def test_create_list_and_case_count(self, api, advocate):
        resp = api.post("/api/clients/", {"name": "Acme Traders", "client_type": "business"}, format="json")
        assert resp.status_code == 201, resp.data
        client = Client.objects.get()
        assert client.owner == advocate
        _case(advocate, client=client)

        listed = api.get("/api/clients/")
        assert [c["case_count"] for c in listed.data] == [1]

    def test_gstin_is_normalised_and_validated(self, api):
        ok = api.post(
            "/api/clients/",
            {"name": "Acme", "client_type": "business", "gstin": " 36abcde1234f1z5 "},
            format="json",
        )
        bad = api.post(
            "/api/clients/", {"name": "Acme", "client_type": "business", "gstin": "123"}, format="json"
        )
        assert ok.status_code == 201, ok.data
        assert ok.data["gstin"] == "36ABCDE1234F1Z5"
        assert bad.status_code == 400
        assert "gstin" in bad.data

    def test_gstin_only_for_business_clients(self, api):
        resp = api.post(
            "/api/clients/",
            {"name": "Person", "client_type": "individual", "gstin": "36ABCDE1234F1Z5"},
            format="json",
        )
        assert resp.status_code == 400

    def test_deleting_a_client_unassigns_its_cases(self, api, advocate):
        client = Client.objects.create(owner=advocate, name="Acme")
        case = _case(advocate, client=client)
        assert api.delete(f"/api/clients/{client.id}/").status_code == 204
        case.refresh_from_db()
        assert case.client_id is None


@pytest.mark.django_db
class TestCaseClientField:
    def test_link_a_case_to_own_client(self, api, advocate):
        client = Client.objects.create(owner=advocate, name="Acme")
        case = _case(advocate)
        resp = api.patch(f"/api/cases/{case.id}/", {"client": client.id}, format="json")
        assert resp.status_code == 200, resp.data
        assert resp.data["client_detail"] == {"id": client.id, "name": "Acme", "client_type": "individual"}

    def test_cannot_link_another_advocates_client(self, api, advocate, other):
        theirs = Client.objects.create(owner=other, name="Not yours")
        case = _case(advocate)
        resp = api.patch(f"/api/cases/{case.id}/", {"client": theirs.id}, format="json")
        assert resp.status_code == 400
        case.refresh_from_db()
        assert case.client_id is None

    def test_manual_case_create_accepts_only_own_client(self, api, advocate, other):
        mine = Client.objects.create(owner=advocate, name="Acme")
        theirs = Client.objects.create(owner=other, name="Not yours")
        ok = api.post("/api/cases/", {"case_number": "M/1/2026", "title": "M1", "client": mine.id}, format="json")
        bad = api.post("/api/cases/", {"case_number": "M/2/2026", "title": "M2", "client": theirs.id}, format="json")
        assert ok.status_code == 201, ok.data
        assert Case.objects.get(case_number="M/1/2026").client == mine
        assert bad.status_code == 400

    def test_serializer_without_a_request_accepts_no_client(self, advocate):
        """Fail closed: a context-less serializer (e.g. a future call site
        that forgets context) must not accept any client id."""
        from core.serializers import CaseCnrCreateSerializer

        client = Client.objects.create(owner=advocate, name="Acme")
        serializer = CaseCnrCreateSerializer(data={"case_number": "Z/1", "title": "Z", "client": client.id})
        assert not serializer.is_valid()
        assert "client" in serializer.errors


@pytest.mark.django_db
class TestBackfillClients:
    def _billing(self, case, email):
        ClientContact.objects.create(
            owner=case.owner, case=case, name="Billing", email=email, is_billing_contact=True
        )

    def test_groups_by_billing_email_then_name_per_owner(self, advocate, other):
        a = _case(advocate, client_name="Acme Traders Pvt Ltd")
        b = _case(advocate, client_name="ACME TRADERS")
        self._billing(a, "Accounts@Acme.example")
        self._billing(b, "accounts@acme.example")
        c = _case(advocate, client_name="Shri Ramesh")
        d = _case(advocate, client_name="ramesh")
        linked = _case(advocate, client_name="Acme Traders Pvt Ltd", client=Client.objects.create(owner=advocate, name="Kept"))
        theirs = _case(other, client_name="Ramesh")

        call_command("backfill_clients", stdout=StringIO())

        for case in (a, b, c, d, linked, theirs):
            case.refresh_from_db()
        assert a.client_id == b.client_id is not None
        assert a.client.email == "accounts@acme.example"
        assert c.client_id == d.client_id is not None
        assert c.client_id != a.client_id
        assert linked.client.name == "Kept"  # already linked -- untouched
        assert theirs.client.owner == other  # never merged across owners
        assert theirs.client_id != c.client_id

    def test_dry_run_writes_nothing(self, advocate):
        _case(advocate, client_name="Acme")
        out = StringIO()
        call_command("backfill_clients", "--dry-run", stdout=out)
        assert "dry run" in out.getvalue()
        assert not Client.objects.exists()


@pytest.mark.django_db
class TestGstOnInvoices:
    def _invoice_text(self, advocate, client):
        case = _case(advocate, client=client)
        hearing = Hearing.objects.create(
            owner=advocate, case=case, hearing_date=timezone.now(), hearing_type="other"
        )
        fee = AppearanceFee.objects.create(owner=advocate, hearing=hearing, amount=Decimal("10000"))
        fee.invoice_number = "INV-0001"
        pdf = invoice_service.render_invoice_pdf(fee, invoice_service.get_or_create_profile(advocate))
        return " ".join(extract_text(io.BytesIO(pdf)).split())

    def test_business_client_gets_gstin_and_reverse_charge_line(self, advocate):
        client = Client.objects.create(
            owner=advocate, name="Acme", client_type=Client.TYPE_BUSINESS, gstin="36ABCDE1234F1Z5"
        )
        text = self._invoice_text(advocate, client)
        assert "36ABCDE1234F1Z5" in text
        assert invoice_service.REVERSE_CHARGE_LINE in text

    def test_individual_and_unlinked_get_neither(self, advocate):
        individual = Client.objects.create(owner=advocate, name="Person")
        for client in (individual, None):
            text = self._invoice_text(advocate, client)
            assert "reverse charge" not in text.lower()
            assert "GSTIN" not in text
