"""Phase A: appearance fees, invoicing, and travel bookings.

Covers the three things the feature can get wrong in a way that costs
real money or leaks data:
  - invoice numbering must be per-advocate (two advocates each get
    INV-0001; one advocate never gets a duplicate),
  - the fee lifecycle must be forward-only (no paying an un-invoiced
    fee, no un-paying a paid one, no renumbering on re-render),
  - every travel-booking endpoint must be closed to other advocates.

Multi-tenancy for the fee endpoints lives here too rather than in
test_multi_tenancy.py, so the whole Phase A surface is readable in one
file.
"""

import itertools
import logging
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    AdvocateProfile,
    AppearanceFee,
    Case,
    ClientContact,
    Hearing,
    TravelBooking,
)
from core.services import invoice_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def advocate_a(db):
    return User.objects.create_user(username="advocate-a", password="pass-123")


@pytest.fixture
def advocate_b(db):
    return User.objects.create_user(username="advocate-b", password="pass-123")


# Case.case_number is globally unique (not per-owner), so two advocates
# can't both hold a "C-001" -- auto-number instead of defaulting to a
# fixed string, or any test that builds a case for each of two advocates
# dies on an IntegrityError that has nothing to do with what it's testing.
_case_counter = itertools.count(1)


def _make_case(owner, number=None):
    number = number or f"C-{next(_case_counter):04d}"
    return Case.objects.create(
        owner=owner,
        case_number=number,
        title=f"{number} Petitioner vs Respondent",
        client_name="Test Client",
    )


def _make_hearing(owner, case):
    return Hearing.objects.create(
        owner=owner,
        case=case,
        hearing_date=timezone.now() + timezone.timedelta(days=7),
        hearing_type="motion",
        location="High Court for the State of Telangana",
        judge="Justice A. Rao",
    )


def _make_fee(owner, case=None, amount="5000.00"):
    case = case or _make_case(owner)
    hearing = _make_hearing(owner, case)
    return AppearanceFee.objects.create(
        owner=owner, hearing=hearing, amount=Decimal(amount)
    )


def _client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def client_a(advocate_a):
    return _client_for(advocate_a)


@pytest.fixture
def client_b(advocate_b):
    return _client_for(advocate_b)


@pytest.fixture
def capture_core_logs():
    """Let caplog see records from the "core" logger.

    settings.LOGGING configures "core" with propagate=False, so its
    records never reach the root logger where pytest's caplog handler is
    installed -- without this, caplog.text is empty even though the log
    line is plainly emitted.
    """
    core_logger = logging.getLogger("core")
    original = core_logger.propagate
    core_logger.propagate = True
    yield
    core_logger.propagate = original


# ---------------------------------------------------------------------------
# Invoice numbering
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestInvoiceNumberingIsolation:
    def test_each_advocate_gets_their_own_sequence_starting_at_one(
        self, advocate_a, advocate_b
    ):
        """The headline requirement: numbering is per-user, so both
        advocates legitimately hold an INV-0001."""
        fee_a = invoice_service.generate_invoice(_make_fee(advocate_a))
        fee_b = invoice_service.generate_invoice(_make_fee(advocate_b))

        assert fee_a.invoice_number == "INV-0001"
        assert fee_b.invoice_number == "INV-0001"
        assert fee_a.invoice_sequence == 1
        assert fee_b.invoice_sequence == 1

    def test_one_advocates_sequence_increments_independently(
        self, advocate_a, advocate_b
    ):
        first_a = invoice_service.generate_invoice(_make_fee(advocate_a, _make_case(advocate_a, "A-1")))
        # B invoicing in between must not advance A's counter.
        invoice_service.generate_invoice(_make_fee(advocate_b, _make_case(advocate_b, "B-1")))
        invoice_service.generate_invoice(_make_fee(advocate_b, _make_case(advocate_b, "B-2")))
        second_a = invoice_service.generate_invoice(_make_fee(advocate_a, _make_case(advocate_a, "A-2")))

        assert first_a.invoice_number == "INV-0001"
        assert second_a.invoice_number == "INV-0002"

        profile_b = AdvocateProfile.objects.get(owner=advocate_b)
        assert profile_b.last_invoice_sequence == 2

    def test_regenerating_keeps_the_same_number_and_does_not_burn_the_counter(
        self, advocate_a
    ):
        """A re-render must not mint a second number -- a number already
        sent to a client has to keep meaning the same document."""
        fee = invoice_service.generate_invoice(_make_fee(advocate_a))
        original = fee.invoice_number

        fee = invoice_service.generate_invoice(fee)

        assert fee.invoice_number == original
        profile = AdvocateProfile.objects.get(owner=advocate_a)
        assert profile.last_invoice_sequence == 1

    def test_invoice_prefix_is_taken_from_the_profile(self, advocate_a):
        profile = invoice_service.get_or_create_profile(advocate_a)
        profile.invoice_prefix = "TSHC"
        profile.save()

        fee = invoice_service.generate_invoice(_make_fee(advocate_a))
        assert fee.invoice_number == "TSHC-0001"

    def test_duplicate_invoice_number_per_owner_is_rejected_by_the_db(self, advocate_a):
        """The per-owner unique constraint is the backstop if the
        counter is ever bypassed."""
        from django.db import IntegrityError, transaction

        fee = invoice_service.generate_invoice(_make_fee(advocate_a))
        other = _make_fee(advocate_a, _make_case(advocate_a, "C-002"))

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                other.invoice_number = fee.invoice_number
                other.save()

    def test_many_unnumbered_fees_coexist(self, advocate_a):
        """The unique constraint is partial -- the empty default must not
        collide across the many not-yet-invoiced rows."""
        _make_fee(advocate_a, _make_case(advocate_a, "C-100"))
        _make_fee(advocate_a, _make_case(advocate_a, "C-101"))
        _make_fee(advocate_a, _make_case(advocate_a, "C-102"))

        assert AppearanceFee.objects.filter(owner=advocate_a, invoice_number="").count() == 3


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFeeStatusTransitions:
    def test_new_fee_starts_pending(self, advocate_a):
        assert _make_fee(advocate_a).status == AppearanceFee.STATUS_PENDING

    def test_generate_invoice_moves_pending_to_invoiced(self, advocate_a):
        fee = invoice_service.generate_invoice(_make_fee(advocate_a))
        assert fee.status == AppearanceFee.STATUS_INVOICED
        assert fee.invoiced_at is not None
        assert fee.invoice_pdf_path

    def test_mark_paid_moves_invoiced_to_paid(self, advocate_a):
        fee = invoice_service.generate_invoice(_make_fee(advocate_a))
        fee = invoice_service.mark_paid(fee)
        assert fee.status == AppearanceFee.STATUS_PAID
        assert fee.paid_at is not None

    def test_cannot_mark_paid_before_invoicing(self, advocate_a):
        fee = _make_fee(advocate_a)
        with pytest.raises(invoice_service.InvalidFeeTransitionError):
            invoice_service.mark_paid(fee)
        fee.refresh_from_db()
        assert fee.status == AppearanceFee.STATUS_PENDING

    def test_cannot_mark_paid_twice(self, advocate_a):
        fee = invoice_service.mark_paid(
            invoice_service.generate_invoice(_make_fee(advocate_a))
        )
        with pytest.raises(invoice_service.InvalidFeeTransitionError):
            invoice_service.mark_paid(fee)

    def test_regenerating_a_paid_invoice_does_not_unpay_it(self, advocate_a):
        """PAID is terminal -- a client asking for a copy of the receipt
        must not roll the fee back to INVOICED."""
        fee = invoice_service.mark_paid(
            invoice_service.generate_invoice(_make_fee(advocate_a))
        )
        fee = invoice_service.generate_invoice(fee)
        assert fee.status == AppearanceFee.STATUS_PAID

    def test_mark_paid_endpoint_returns_409_when_not_invoiced(self, advocate_a, client_a):
        fee = _make_fee(advocate_a)
        response = client_a.post(f"/api/appearance-fees/{fee.id}/mark-paid/")
        assert response.status_code == 409

    def test_full_lifecycle_over_the_api(self, advocate_a, client_a):
        fee = _make_fee(advocate_a)

        invoiced = client_a.post(f"/api/appearance-fees/{fee.id}/invoice/")
        assert invoiced.status_code == 200
        assert invoiced.data["status"] == "invoiced"
        assert invoiced.data["invoice_number"] == "INV-0001"

        paid = client_a.post(f"/api/appearance-fees/{fee.id}/mark-paid/")
        assert paid.status_code == 200
        assert paid.data["status"] == "paid"

    def test_status_is_read_only_over_patch(self, advocate_a, client_a):
        """Status must move only through the action endpoints, so the
        transition rules can't be stepped around with a PATCH."""
        fee = _make_fee(advocate_a)
        response = client_a.patch(
            f"/api/appearance-fees/{fee.id}/", {"status": "paid"}, format="json"
        )
        assert response.status_code == 200
        fee.refresh_from_db()
        assert fee.status == AppearanceFee.STATUS_PENDING


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestInvoicePdf:
    def test_pdf_is_written_to_storage_and_looks_like_a_pdf(self, advocate_a):
        profile = invoice_service.get_or_create_profile(advocate_a)
        profile.letterhead_name = "A. Advocate & Co."
        profile.address = "12 Court Road\nHyderabad 500001"
        profile.bar_registration_number = "TS/1234/2010"
        profile.save()

        fee = invoice_service.generate_invoice(_make_fee(advocate_a))

        assert default_storage.exists(fee.invoice_pdf_path)
        with default_storage.open(fee.invoice_pdf_path, "rb") as handle:
            data = handle.read()
        assert data.startswith(b"%PDF")
        assert len(data) > 500

    def test_render_handles_non_latin1_characters(self, advocate_a):
        """fpdf2's core fonts are Latin-1 only; a party name outside it
        must be substituted, not raise and fail the whole invoice."""
        case = Case.objects.create(
            owner=advocate_a,
            case_number="C-UNI",
            title="M/s Ünïcode Traders — vs — State",
            client_name="Ünïcode",
        )
        fee = _make_fee(advocate_a, case)
        profile = invoice_service.get_or_create_profile(advocate_a)
        fee.invoice_number = "INV-0001"

        pdf_bytes = invoice_service.render_invoice_pdf(fee, profile)
        assert pdf_bytes.startswith(b"%PDF")

    def test_invoice_file_endpoint_streams_the_pdf(self, advocate_a, client_a):
        fee = invoice_service.generate_invoice(_make_fee(advocate_a))
        response = client_a.get(f"/api/appearance-fees/{fee.id}/invoice/file/")
        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"

    def test_invoice_file_404s_before_generation(self, advocate_a, client_a):
        fee = _make_fee(advocate_a)
        response = client_a.get(f"/api/appearance-fees/{fee.id}/invoice/file/")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Sending to the billing contact
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestInvoiceSending:
    def test_sends_to_the_billing_contact_when_email_is_configured(
        self, advocate_a, client_a, settings, monkeypatch
    ):
        case = _make_case(advocate_a)
        ClientContact.objects.create(
            owner=advocate_a, case=case, name="Assistant", email="assistant@example.com"
        )
        ClientContact.objects.create(
            owner=advocate_a,
            case=case,
            name="Billing Person",
            email="billing@example.com",
            is_billing_contact=True,
        )
        fee = invoice_service.generate_invoice(_make_fee(advocate_a, case))

        settings.INVOICE_EMAIL_CONFIGURED = True
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        mail.outbox.clear()

        response = client_a.post(f"/api/appearance-fees/{fee.id}/send/")

        assert response.status_code == 200
        assert response.data["sent"] is True
        assert len(mail.outbox) == 1
        message = mail.outbox[0]
        # The billing contact, not the other contact on the same case.
        assert message.to == ["billing@example.com"]
        assert fee.invoice_number in message.subject
        assert len(message.attachments) == 1
        assert message.attachments[0][0] == f"{fee.invoice_number}.pdf"

        fee.refresh_from_db()
        assert fee.send_status == AppearanceFee.SEND_SENT

    def test_logs_instead_of_failing_when_email_is_not_configured(
        self, advocate_a, client_a, settings, caplog, capture_core_logs
    ):
        case = _make_case(advocate_a)
        ClientContact.objects.create(
            owner=advocate_a,
            case=case,
            name="Billing Person",
            email="billing@example.com",
            is_billing_contact=True,
        )
        fee = invoice_service.generate_invoice(_make_fee(advocate_a, case))

        settings.INVOICE_EMAIL_CONFIGURED = False
        mail.outbox.clear()

        with caplog.at_level("WARNING"):
            response = client_a.post(f"/api/appearance-fees/{fee.id}/send/")

        # Not an error -- the action "succeeds" but reports sent=false.
        assert response.status_code == 200
        assert response.data["sent"] is False
        assert response.data["recipient"] == "billing@example.com"
        assert "RESEND_API_KEY" in response.data["missing_env_vars"]
        # The full checklist is returned too, so the caller is told every
        # var it needs, not only the ones that gate the config flag.
        assert "DEFAULT_FROM_EMAIL" in response.data["required_env_vars"]
        assert len(mail.outbox) == 0
        assert "EMAIL NOT CONFIGURED" in caplog.text
        assert "billing@example.com" in caplog.text

        fee.refresh_from_db()
        # Recorded as logged, never as sent.
        assert fee.send_status == AppearanceFee.SEND_LOGGED

    def test_send_fails_clearly_with_no_billing_contact(self, advocate_a, client_a):
        case = _make_case(advocate_a)
        ClientContact.objects.create(
            owner=advocate_a, case=case, name="Someone", email="someone@example.com"
        )
        fee = invoice_service.generate_invoice(_make_fee(advocate_a, case))

        response = client_a.post(f"/api/appearance-fees/{fee.id}/send/")
        assert response.status_code == 400
        assert "billing contact" in response.data["detail"].lower()

    def test_send_fails_when_billing_contact_has_no_email(self, advocate_a, client_a):
        case = _make_case(advocate_a)
        ClientContact.objects.create(
            owner=advocate_a, case=case, name="No Email", is_billing_contact=True
        )
        fee = invoice_service.generate_invoice(_make_fee(advocate_a, case))

        response = client_a.post(f"/api/appearance-fees/{fee.id}/send/")
        assert response.status_code == 400
        assert "no email" in response.data["detail"].lower()

    def test_cannot_send_before_generating(self, advocate_a, client_a):
        case = _make_case(advocate_a)
        ClientContact.objects.create(
            owner=advocate_a,
            case=case,
            name="Billing",
            email="billing@example.com",
            is_billing_contact=True,
        )
        fee = _make_fee(advocate_a, case)

        response = client_a.post(f"/api/appearance-fees/{fee.id}/send/")
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Case-page fee summary
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCaseFeeSummary:
    def test_summary_buckets_pending_invoiced_and_paid(self, advocate_a, client_a):
        case = _make_case(advocate_a)

        pending = AppearanceFee.objects.create(
            owner=advocate_a, hearing=_make_hearing(advocate_a, case), amount=Decimal("1000.00")
        )
        invoiced = AppearanceFee.objects.create(
            owner=advocate_a, hearing=_make_hearing(advocate_a, case), amount=Decimal("2000.00")
        )
        paid = AppearanceFee.objects.create(
            owner=advocate_a, hearing=_make_hearing(advocate_a, case), amount=Decimal("3000.00")
        )
        invoice_service.generate_invoice(invoiced)
        invoice_service.mark_paid(invoice_service.generate_invoice(paid))
        assert pending.status == AppearanceFee.STATUS_PENDING

        response = client_a.get(f"/api/cases/{case.id}/")
        summary = response.data["fee_summary"]

        assert Decimal(summary["pending_amount"]) == Decimal("1000.00")
        assert Decimal(summary["invoiced_amount"]) == Decimal("2000.00")
        assert Decimal(summary["paid_amount"]) == Decimal("3000.00")
        assert Decimal(summary["outstanding_amount"]) == Decimal("3000.00")
        assert Decimal(summary["total_amount"]) == Decimal("6000.00")
        assert summary["pending_count"] == 1

    def test_summary_is_zeroed_for_a_case_with_no_fees(self, advocate_a, client_a):
        case = _make_case(advocate_a)
        response = client_a.get(f"/api/cases/{case.id}/")
        summary = response.data["fee_summary"]
        assert Decimal(summary["total_amount"]) == Decimal("0.00")
        assert summary["paid_count"] == 0

    def test_summary_excludes_another_advocates_fees(
        self, advocate_a, advocate_b, client_a
    ):
        """A case id is unique across the system, so the summary query
        must be constrained by the case itself -- this proves no other
        advocate's rows can leak into the total."""
        case = _make_case(advocate_a)
        AppearanceFee.objects.create(
            owner=advocate_a, hearing=_make_hearing(advocate_a, case), amount=Decimal("1000.00")
        )
        # advocate_b's own separate case and fee.
        other_case = _make_case(advocate_b, "C-B-1")
        AppearanceFee.objects.create(
            owner=advocate_b,
            hearing=_make_hearing(advocate_b, other_case),
            amount=Decimal("9999.00"),
        )

        response = client_a.get(f"/api/cases/{case.id}/")
        assert Decimal(response.data["fee_summary"]["total_amount"]) == Decimal("1000.00")


# ---------------------------------------------------------------------------
# Hearing card badge payload
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestHearingFeeBadge:
    def test_hearing_embeds_its_fee_and_bookings(self, advocate_a, client_a):
        case = _make_case(advocate_a)
        hearing = _make_hearing(advocate_a, case)
        AppearanceFee.objects.create(
            owner=advocate_a, hearing=hearing, amount=Decimal("2500.00")
        )
        TravelBooking.objects.create(
            owner=advocate_a, hearing=hearing, booking_type="hotel"
        )

        response = client_a.get(f"/api/hearings/{hearing.id}/")
        assert response.status_code == 200
        assert response.data["appearance_fee"]["status"] == "pending"
        assert Decimal(response.data["appearance_fee"]["amount"]) == Decimal("2500.00")
        assert len(response.data["travel_bookings"]) == 1

    def test_hearing_without_a_fee_returns_null(self, advocate_a, client_a):
        hearing = _make_hearing(advocate_a, _make_case(advocate_a))
        response = client_a.get(f"/api/hearings/{hearing.id}/")
        assert response.data["appearance_fee"] is None
        assert response.data["travel_bookings"] == []


# ---------------------------------------------------------------------------
# Travel bookings: upload + auth
# ---------------------------------------------------------------------------


def _ticket_file(name="ticket.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 fake ticket bytes", content_type="application/pdf")


@pytest.mark.django_db
class TestTravelBookingUpload:
    def test_upload_creates_a_booking_and_marks_it_booked(self, advocate_a, client_a):
        hearing = _make_hearing(advocate_a, _make_case(advocate_a))

        response = client_a.post(
            "/api/travel-bookings/upload/",
            {"file": _ticket_file(), "hearing_id": hearing.id, "booking_type": "hotel"},
            format="multipart",
        )

        assert response.status_code == 201
        assert response.data["status"] == "booked"
        assert response.data["booking_type"] == "hotel"
        assert response.data["filename"] == "ticket.pdf"

        booking = TravelBooking.objects.get(id=response.data["id"])
        assert booking.owner == advocate_a
        assert default_storage.exists(booking.file_path)

    def test_upload_against_an_existing_pending_booking_flips_it(self, advocate_a, client_a):
        hearing = _make_hearing(advocate_a, _make_case(advocate_a))
        booking = TravelBooking.objects.create(owner=advocate_a, hearing=hearing)
        assert booking.status == TravelBooking.STATUS_PENDING

        response = client_a.post(
            "/api/travel-bookings/upload/",
            {"file": _ticket_file(), "booking_id": booking.id},
            format="multipart",
        )

        assert response.status_code == 201
        booking.refresh_from_db()
        assert booking.status == TravelBooking.STATUS_BOOKED

    def test_booking_created_without_a_file_stays_pending(self, advocate_a, client_a):
        hearing = _make_hearing(advocate_a, _make_case(advocate_a))
        response = client_a.post(
            "/api/travel-bookings/", {"hearing": hearing.id}, format="json"
        )
        assert response.status_code == 201
        assert response.data["status"] == "pending"

    def test_upload_rejects_an_unsupported_file_type(self, advocate_a, client_a):
        hearing = _make_hearing(advocate_a, _make_case(advocate_a))
        response = client_a.post(
            "/api/travel-bookings/upload/",
            {
                "file": SimpleUploadedFile("ticket.exe", b"MZ", content_type="application/x-msdownload"),
                "hearing_id": hearing.id,
            },
            format="multipart",
        )
        assert response.status_code == 400

    def test_upload_requires_a_hearing_or_booking(self, advocate_a, client_a):
        response = client_a.post(
            "/api/travel-bookings/upload/", {"file": _ticket_file()}, format="multipart"
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestTravelBookingAuth:
    def test_upload_requires_authentication(self, advocate_a):
        hearing = _make_hearing(advocate_a, _make_case(advocate_a))
        anonymous = APIClient()
        response = anonymous.post(
            "/api/travel-bookings/upload/",
            {"file": _ticket_file(), "hearing_id": hearing.id},
            format="multipart",
        )
        assert response.status_code in (401, 403)
        assert TravelBooking.objects.count() == 0

    def test_cannot_upload_against_another_advocates_hearing(
        self, advocate_a, advocate_b, client_b
    ):
        hearing = _make_hearing(advocate_a, _make_case(advocate_a))

        response = client_b.post(
            "/api/travel-bookings/upload/",
            {"file": _ticket_file(), "hearing_id": hearing.id},
            format="multipart",
        )

        assert response.status_code == 400
        assert TravelBooking.objects.filter(hearing=hearing).count() == 0

    def test_cannot_attach_a_file_to_another_advocates_booking(
        self, advocate_a, advocate_b, client_b
    ):
        hearing = _make_hearing(advocate_a, _make_case(advocate_a))
        booking = TravelBooking.objects.create(owner=advocate_a, hearing=hearing)

        response = client_b.post(
            "/api/travel-bookings/upload/",
            {"file": _ticket_file(), "booking_id": booking.id},
            format="multipart",
        )

        assert response.status_code == 400
        booking.refresh_from_db()
        assert booking.status == TravelBooking.STATUS_PENDING

    def test_cannot_read_another_advocates_booking_or_its_file(
        self, advocate_a, advocate_b, client_a, client_b
    ):
        hearing = _make_hearing(advocate_a, _make_case(advocate_a))
        created = client_a.post(
            "/api/travel-bookings/upload/",
            {"file": _ticket_file(), "hearing_id": hearing.id},
            format="multipart",
        )
        booking_id = created.data["id"]

        assert client_b.get(f"/api/travel-bookings/{booking_id}/").status_code == 404
        assert client_b.get(f"/api/travel-bookings/{booking_id}/file/").status_code == 404
        # And the owner can still read both.
        assert client_a.get(f"/api/travel-bookings/{booking_id}/").status_code == 200
        assert client_a.get(f"/api/travel-bookings/{booking_id}/file/").status_code == 200

    def test_list_is_scoped_even_with_a_hearing_id_filter(
        self, advocate_a, advocate_b, client_b
    ):
        hearing = _make_hearing(advocate_a, _make_case(advocate_a))
        TravelBooking.objects.create(owner=advocate_a, hearing=hearing)

        response = client_b.get(f"/api/travel-bookings/?hearing_id={hearing.id}")
        assert response.status_code == 200
        assert response.data == []

    def test_cannot_delete_another_advocates_booking(
        self, advocate_a, advocate_b, client_b
    ):
        hearing = _make_hearing(advocate_a, _make_case(advocate_a))
        booking = TravelBooking.objects.create(owner=advocate_a, hearing=hearing)

        assert client_b.delete(f"/api/travel-bookings/{booking.id}/").status_code == 404
        assert TravelBooking.objects.filter(id=booking.id).exists()


# ---------------------------------------------------------------------------
# Fee endpoint isolation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAppearanceFeeIsolation:
    def test_cannot_attach_a_fee_to_another_advocates_hearing(
        self, advocate_a, advocate_b, client_b
    ):
        hearing = _make_hearing(advocate_a, _make_case(advocate_a))
        response = client_b.post(
            "/api/appearance-fees/",
            {"hearing": hearing.id, "amount": "100.00"},
            format="json",
        )
        assert response.status_code == 400
        assert AppearanceFee.objects.filter(hearing=hearing).count() == 0

    def test_cannot_invoice_send_or_pay_another_advocates_fee(
        self, advocate_a, advocate_b, client_b
    ):
        fee = _make_fee(advocate_a)
        assert client_b.post(f"/api/appearance-fees/{fee.id}/invoice/").status_code == 404
        assert client_b.post(f"/api/appearance-fees/{fee.id}/send/").status_code == 404
        assert client_b.post(f"/api/appearance-fees/{fee.id}/mark-paid/").status_code == 404

        fee.refresh_from_db()
        assert fee.status == AppearanceFee.STATUS_PENDING
        assert fee.invoice_number == ""

    def test_cannot_read_another_advocates_invoice_pdf(
        self, advocate_a, advocate_b, client_b
    ):
        fee = invoice_service.generate_invoice(_make_fee(advocate_a))
        response = client_b.get(f"/api/appearance-fees/{fee.id}/invoice/file/")
        assert response.status_code == 404

    def test_list_is_scoped_even_with_a_case_id_filter(
        self, advocate_a, advocate_b, client_b
    ):
        case = _make_case(advocate_a)
        AppearanceFee.objects.create(
            owner=advocate_a, hearing=_make_hearing(advocate_a, case), amount=Decimal("1.00")
        )
        response = client_b.get(f"/api/appearance-fees/?case_id={case.id}")
        assert response.status_code == 200
        assert response.data == []

    def test_fee_endpoints_require_authentication(self, advocate_a):
        fee = _make_fee(advocate_a)
        anonymous = APIClient()
        for url in (
            "/api/appearance-fees/",
            f"/api/appearance-fees/{fee.id}/",
            f"/api/appearance-fees/{fee.id}/invoice/",
            f"/api/appearance-fees/{fee.id}/invoice/file/",
            f"/api/appearance-fees/{fee.id}/send/",
            f"/api/appearance-fees/{fee.id}/mark-paid/",
            "/api/advocate-profile/",
        ):
            assert anonymous.get(url).status_code in (401, 403), url


# ---------------------------------------------------------------------------
# Advocate profile
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAdvocateProfile:
    def test_profile_is_auto_created_on_first_read(self, advocate_a, client_a):
        assert not AdvocateProfile.objects.filter(owner=advocate_a).exists()
        response = client_a.get("/api/advocate-profile/")
        assert response.status_code == 200
        assert AdvocateProfile.objects.filter(owner=advocate_a).exists()

    def test_letterhead_fields_round_trip(self, advocate_a, client_a):
        response = client_a.patch(
            "/api/advocate-profile/",
            {
                "letterhead_name": "A. Advocate & Co.",
                "address": "12 Court Road\nHyderabad",
                "bar_registration_number": "TS/1234/2010",
                "default_fee_amount": "7500.00",
            },
            format="json",
        )
        assert response.status_code == 200
        assert response.data["letterhead_name"] == "A. Advocate & Co."
        assert Decimal(response.data["default_fee_amount"]) == Decimal("7500.00")

    def test_default_fee_is_applied_to_a_new_fee_with_no_amount(
        self, advocate_a, client_a
    ):
        client_a.patch(
            "/api/advocate-profile/", {"default_fee_amount": "4500.00"}, format="json"
        )
        hearing = _make_hearing(advocate_a, _make_case(advocate_a))

        response = client_a.post(
            "/api/appearance-fees/", {"hearing": hearing.id}, format="json"
        )
        assert response.status_code == 201
        assert Decimal(response.data["amount"]) == Decimal("4500.00")

    def test_invoice_counter_is_not_writable(self, advocate_a, client_a):
        """Rewinding the counter would let an advocate mint a duplicate
        number for an invoice already sent to a client."""
        invoice_service.generate_invoice(_make_fee(advocate_a))

        client_a.patch(
            "/api/advocate-profile/", {"last_invoice_sequence": 0}, format="json"
        )

        profile = AdvocateProfile.objects.get(owner=advocate_a)
        assert profile.last_invoice_sequence == 1

    def test_one_profile_per_user(self, advocate_a):
        from django.db import IntegrityError, transaction

        invoice_service.get_or_create_profile(advocate_a)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                AdvocateProfile.objects.create(owner=advocate_a)

    def test_profile_is_not_shared_between_advocates(
        self, advocate_a, advocate_b, client_a, client_b
    ):
        client_a.patch(
            "/api/advocate-profile/", {"letterhead_name": "A & Co."}, format="json"
        )
        response = client_b.get("/api/advocate-profile/")
        assert response.data["letterhead_name"] == ""
