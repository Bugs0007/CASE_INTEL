"""Court-order surfacing: filename parsing, backfill, and the owner-only
serve endpoint.

Covers the three things most likely to break quietly:
  - a stored PDF whose name doesn't fit the convention must be skipped and
    logged, never crash a scan that also has good files in it;
  - the serve endpoint must be owner-only and must not leak file_path;
  - a single hearing date routinely carries several orders, which have to
    come back in portal sequence ("2" before "10", not string order).
"""

from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import Case, CourtOrder, Document
from core.services.court_order_sync import (
    ORDER_STORAGE_DIR,
    order_sequence_sort_key,
    parse_order_filename,
)

CNR_A = "MHAU010001112026"
CNR_B = "MHAU010002222026"

# A real (minimal) PDF so FileResponse streams something believable.
PDF_BYTES = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


@pytest.fixture
def user_a():
    return User.objects.create_user(username="alice", password="alice-pass-123")


@pytest.fixture
def user_b():
    return User.objects.create_user(username="bob", password="bob-pass-123")


def _authed_client(user):
    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


@pytest.fixture
def client_a(user_a):
    return _authed_client(user_a)


@pytest.fixture
def client_b(user_b):
    return _authed_client(user_b)


@pytest.fixture
def case_a(user_a):
    return Case.objects.create(
        owner=user_a,
        case_number="A-001",
        title="Alice's Case",
        client_name="Alice Client",
        cnr_number=CNR_A,
    )


@pytest.fixture
def case_b(user_b):
    return Case.objects.create(
        owner=user_b,
        case_number="B-001",
        title="Bob's Case",
        client_name="Bob Client",
        cnr_number=CNR_B,
    )


@pytest.fixture
def stored_files():
    """Write files into the configured storage and clean them up after.

    Yields a callable taking a bare filename; returns the storage key
    actually used (default_storage may rename on collision).
    """
    written = []

    def _store(filename: str, content: bytes = PDF_BYTES) -> str:
        key = default_storage.save(f"{ORDER_STORAGE_DIR}/{filename}", ContentFile(content))
        written.append(key)
        return key

    yield _store

    for key in written:
        if default_storage.exists(key):
            default_storage.delete(key)


def _make_order(case, order_number, order_date, *, with_file=True, storage_key=None):
    document = None
    if with_file:
        document = Document.objects.create(
            owner=case.owner,
            case=case,
            filename=f"{case.cnr_number}_order_{order_number}_{order_date}.pdf",
            file_path=storage_key or f"{ORDER_STORAGE_DIR}/stub-{order_number}.pdf",
            file_type="pdf",
            file_size=len(PDF_BYTES),
            document_type="court_order",
            document_date=order_date,
            processing_status="completed",
        )
    date_part = order_date.isoformat() if order_date else "unknown"
    return CourtOrder.objects.create(
        owner=case.owner,
        case=case,
        order_number=order_number,
        order_date=order_date,
        description=f"Order {order_number}",
        source="ecourts",
        dedup_key=f"{case.cnr_number}:{order_number}:{date_part}",
        document=document,
    )


class TestParseOrderFilename:
    """parse_order_filename() must survive every odd name a storage
    directory can hold -- it returns None and logs, never raises."""

    def test_round_trips_the_convention(self):
        record = parse_order_filename(f"{CNR_A}_order_3_2026-03-14.pdf")
        assert record is not None
        assert record.cnr == CNR_A
        assert record.order_number == "3"
        assert record.order_date == date(2026, 3, 14)
        assert record.dedup_key == f"{CNR_A}:3:2026-03-14"

    def test_undated_sentinel_parses_to_none_date(self):
        # _order_filename() writes "undated" when the portal listed no
        # date -- a known token, not a malformed one, so it still imports.
        record = parse_order_filename(f"{CNR_A}_order_3_undated.pdf")
        assert record is not None
        assert record.order_date is None
        assert record.dedup_key == f"{CNR_A}:3:unknown"

    def test_storage_collision_suffix_is_ignored(self):
        # default_storage.save() appends a random suffix when the name is
        # taken (Django's get_available_name), landing where the date
        # would otherwise be.
        record = parse_order_filename(f"{CNR_A}_order_3_2026-03-14_x7Kq2mZ.pdf")
        assert record is not None
        assert record.order_number == "3"
        assert record.order_date == date(2026, 3, 14)

    def test_order_number_containing_underscores_survives(self):
        record = parse_order_filename(f"{CNR_A}_order_IA_3_2026-03-14.pdf")
        assert record is not None
        assert record.order_number == "IA_3"

    @pytest.mark.parametrize(
        "filename",
        [
            f"{CNR_A}_order_2026-03-14.pdf",          # missing sequence
            f"{CNR_A}_order__2026-03-14.pdf",         # empty sequence
            f"{CNR_A}_order_3_notadate.pdf",          # unparseable date
            f"{CNR_A}_order_3_2026-13-45.pdf",        # right shape, impossible date
            f"{CNR_A}_order_3_2026-03-14.txt",        # not a PDF
            f"{CNR_A}-order-3-2026-03-14.pdf",        # no _order_ marker
            "_order_3_2026-03-14.pdf",                # empty CNR
            "random-upload.pdf",
            "",
        ],
    )
    def test_bad_names_are_skipped_not_raised(self, filename):
        assert parse_order_filename(filename) is None

    def test_sequence_sort_key_is_numeric_where_it_can_be(self):
        numbers = ["10", "2", "1", "IA-3"]
        assert sorted(numbers, key=order_sequence_sort_key) == ["1", "2", "10", "IA-3"]


@pytest.mark.django_db
class TestBackfillCommand:
    def test_creates_rows_from_stored_files(self, case_a, stored_files):
        stored_files(f"{CNR_A}_order_1_2026-03-14.pdf")
        stored_files(f"{CNR_A}_order_2_2026-03-14.pdf")

        call_command("backfill_court_orders")

        orders = CourtOrder.objects.filter(case=case_a)
        assert orders.count() == 2
        assert {o.order_number for o in orders} == {"1", "2"}
        for order in orders:
            assert order.owner == case_a.owner
            assert order.order_date == date(2026, 3, 14)
            assert order.document is not None
            assert order.document.document_type == "court_order"

    def test_is_idempotent(self, case_a, stored_files):
        stored_files(f"{CNR_A}_order_1_2026-03-14.pdf")

        call_command("backfill_court_orders")
        call_command("backfill_court_orders")

        assert CourtOrder.objects.filter(case=case_a).count() == 1
        assert Document.objects.filter(case=case_a).count() == 1

    def test_dry_run_writes_nothing(self, case_a, stored_files):
        stored_files(f"{CNR_A}_order_1_2026-03-14.pdf")

        call_command("backfill_court_orders", "--dry-run")

        assert not CourtOrder.objects.exists()
        assert not Document.objects.exists()

    def test_bad_filename_skipped_without_stopping_the_scan(self, case_a, stored_files):
        stored_files(f"{CNR_A}_order_1_notadate.pdf")
        stored_files(f"{CNR_A}_order_2_2026-03-14.pdf")

        call_command("backfill_court_orders")

        orders = CourtOrder.objects.filter(case=case_a)
        assert [o.order_number for o in orders] == ["2"]

    def test_unknown_cnr_is_skipped(self, case_a, stored_files):
        stored_files("ZZZZ999999999999_order_1_2026-03-14.pdf")

        call_command("backfill_court_orders")

        assert not CourtOrder.objects.exists()

    def test_ambiguous_cnr_is_skipped_not_guessed(self, user_a, user_b, stored_files):
        # Two advocates tracking the same CNR: cnr_number is indexed but
        # not unique, so a filename alone can't say whose order this is.
        # Guessing would hand one user the other's document.
        Case.objects.create(
            owner=user_a, case_number="A-001", title="A", client_name="A", cnr_number=CNR_A
        )
        Case.objects.create(
            owner=user_b, case_number="B-001", title="B", client_name="B", cnr_number=CNR_A
        )
        stored_files(f"{CNR_A}_order_1_2026-03-14.pdf")

        call_command("backfill_court_orders")

        assert not CourtOrder.objects.exists()

    def test_existing_document_resolves_the_owner(self, user_a, user_b, stored_files):
        # Same ambiguous CNR, but a Document row already points at this
        # exact storage key -- that carries the real owner/case.
        case_a = Case.objects.create(
            owner=user_a, case_number="A-001", title="A", client_name="A", cnr_number=CNR_A
        )
        Case.objects.create(
            owner=user_b, case_number="B-001", title="B", client_name="B", cnr_number=CNR_A
        )
        key = stored_files(f"{CNR_A}_order_1_2026-03-14.pdf")
        Document.objects.create(
            owner=user_a,
            case=case_a,
            filename=f"{CNR_A}_order_1_2026-03-14.pdf",
            file_path=key,
            file_type="pdf",
            document_type="court_order",
            processing_status="completed",
        )

        call_command("backfill_court_orders")

        order = CourtOrder.objects.get()
        assert order.case == case_a
        assert order.owner == user_a
        # Reused the existing Document rather than creating a second one.
        assert Document.objects.count() == 1


@pytest.mark.django_db
class TestCaseOrdersEndpoint:
    def test_returns_all_orders_for_a_hearing_date_in_sequence(self, client_a, case_a):
        hearing_day = date(2026, 3, 14)
        _make_order(case_a, "10", hearing_day)
        _make_order(case_a, "2", hearing_day)
        _make_order(case_a, "1", hearing_day)

        resp = client_a.get(f"/api/cases/{case_a.id}/orders/?date=2026-03-14")

        assert resp.status_code == 200
        # "2" ahead of "10" -- order_number is a CharField, so a plain
        # string sort would get this backwards.
        assert [o["order_number"] for o in resp.data] == ["1", "2", "10"]

    def test_date_filter_excludes_other_dates(self, client_a, case_a):
        _make_order(case_a, "1", date(2026, 3, 14))
        _make_order(case_a, "2", date(2026, 4, 20))

        resp = client_a.get(f"/api/cases/{case_a.id}/orders/?date=2026-03-14")

        assert resp.status_code == 200
        assert [o["order_number"] for o in resp.data] == ["1"]

    def test_without_date_returns_every_order(self, client_a, case_a):
        _make_order(case_a, "1", date(2026, 3, 14))
        _make_order(case_a, "2", date(2026, 4, 20))

        resp = client_a.get(f"/api/cases/{case_a.id}/orders/")

        assert resp.status_code == 200
        assert len(resp.data) == 2
        # Newest date first.
        assert resp.data[0]["order_date"] == "2026-04-20"

    def test_malformed_date_is_a_400(self, client_a, case_a):
        resp = client_a.get(f"/api/cases/{case_a.id}/orders/?date=14-03-2026")
        assert resp.status_code == 400

    def test_never_exposes_the_storage_path(self, client_a, case_a):
        _make_order(case_a, "1", date(2026, 3, 14))

        resp = client_a.get(f"/api/cases/{case_a.id}/orders/")

        assert resp.status_code == 200
        assert "file_path" not in resp.data[0]
        assert ORDER_STORAGE_DIR not in str(resp.data)

    def test_flags_orders_with_no_file(self, client_a, case_a):
        _make_order(case_a, "1", date(2026, 3, 14), with_file=False)

        resp = client_a.get(f"/api/cases/{case_a.id}/orders/")

        assert resp.data[0]["has_file"] is False

    def test_other_users_case_404s(self, client_a, case_b):
        _make_order(case_b, "1", date(2026, 3, 14))

        resp = client_a.get(f"/api/cases/{case_b.id}/orders/")

        assert resp.status_code == 404

    def test_unauthenticated_is_rejected(self, case_a):
        resp = APIClient().get(f"/api/cases/{case_a.id}/orders/")
        assert resp.status_code in (401, 403)


@pytest.mark.django_db
class TestCourtOrderFileEndpoint:
    def test_owner_gets_the_pdf_bytes(self, client_a, case_a, stored_files):
        key = stored_files(f"{CNR_A}_order_1_2026-03-14.pdf")
        order = _make_order(case_a, "1", date(2026, 3, 14), storage_key=key)

        resp = client_a.get(f"/api/orders/{order.id}/file/")

        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/pdf"
        # inline, so the frontend's new tab renders it instead of downloading.
        assert "inline" in resp["Content-Disposition"]
        assert b"".join(resp.streaming_content) == PDF_BYTES

    def test_other_users_order_404s(self, client_b, case_a, stored_files):
        key = stored_files(f"{CNR_A}_order_1_2026-03-14.pdf")
        order = _make_order(case_a, "1", date(2026, 3, 14), storage_key=key)

        resp = client_b.get(f"/api/orders/{order.id}/file/")

        assert resp.status_code == 404

    def test_unauthenticated_is_rejected(self, case_a, stored_files):
        key = stored_files(f"{CNR_A}_order_1_2026-03-14.pdf")
        order = _make_order(case_a, "1", date(2026, 3, 14), storage_key=key)

        resp = APIClient().get(f"/api/orders/{order.id}/file/")

        assert resp.status_code in (401, 403)

    def test_order_without_a_document_404s(self, client_a, case_a):
        order = _make_order(case_a, "1", date(2026, 3, 14), with_file=False)

        resp = client_a.get(f"/api/orders/{order.id}/file/")

        assert resp.status_code == 404

    def test_missing_file_on_disk_404s_rather_than_500s(self, client_a, case_a):
        order = _make_order(case_a, "1", date(2026, 3, 14))  # stub path, never written

        resp = client_a.get(f"/api/orders/{order.id}/file/")

        assert resp.status_code == 404
