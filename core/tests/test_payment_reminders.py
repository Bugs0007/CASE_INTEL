"""Payment-reminder drafts (manage.py draft_payment_reminders).

The rules that protect a client relationship: never after PAID, never more
than 3, never before the advocate's interval, never to an opted-out or
email-less contact, never a second draft while one waits -- and the
command only ever DRAFTS; the advocate sends.
"""

from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import AdvocateProfile, AppearanceFee, Case, ClientContact, ClientMessage, Hearing, SentMessage
from core.services import invoice_service
from core.services.client_updates import next_reminder_due


@pytest.fixture
def advocate(db):
    user = User.objects.create_user(username="reminder-advocate", password="pw-12345")
    invoice_service.get_or_create_profile(user)
    AdvocateProfile.objects.filter(owner=user).update(contact_email="me@example.com", advocate_name="A. Rao")
    return user


@pytest.fixture
def api(advocate):
    client = APIClient()
    client.force_authenticate(user=advocate)
    return client


_counter = iter(range(1, 10_000))


def _invoiced_fee(owner, *, days_ago, email="billing@example.com", **contact_extra):
    n = next(_counter)
    case = Case.objects.create(owner=owner, case_number=f"OS/{n}/2026", title=f"OS/{n}/2026 A vs B", client_name="A")
    if email is not False:
        ClientContact.objects.create(
            owner=owner, case=case, name="Billing Person", email=email, is_billing_contact=True, **contact_extra
        )
    hearing = Hearing.objects.create(
        owner=owner, case=case, hearing_date=timezone.now() - timedelta(days=days_ago + 1, minutes=n),
        hearing_type="other",
    )
    fee = AppearanceFee.objects.create(owner=owner, hearing=hearing, amount=Decimal("5000.00"))
    fee = invoice_service.generate_invoice(fee)
    AppearanceFee.objects.filter(id=fee.id).update(invoiced_at=timezone.now() - timedelta(days=days_ago))
    fee.refresh_from_db()
    return fee


def _run(*args) -> str:
    out = StringIO()
    call_command("draft_payment_reminders", *args, stdout=out)
    return out.getvalue()


def _mark_reminder_delivered(fee, *, days_ago):
    msg = ClientMessage.objects.get(fee=fee, status=ClientMessage.STATUS_DRAFT)
    msg.status = ClientMessage.STATUS_LOGGED
    msg.sent_at = timezone.now() - timedelta(days=days_ago)
    msg.save()


@pytest.mark.django_db
class TestEligibility:
    def test_not_due_before_the_interval(self, advocate):
        fee = _invoiced_fee(advocate, days_ago=10)
        assert next_reminder_due(fee, after_days=15) == (None, "not due yet")

    def test_first_reminder_after_the_interval(self, advocate):
        fee = _invoiced_fee(advocate, days_ago=16)
        assert next_reminder_due(fee, after_days=15) == (1, "due")

    def test_paid_is_never_due(self, advocate):
        fee = invoice_service.mark_paid(_invoiced_fee(advocate, days_ago=60))
        assert next_reminder_due(fee, after_days=15)[0] is None


@pytest.mark.django_db
class TestCommand:
    def test_drafts_and_never_sends(self, advocate, settings):
        settings.INVOICE_EMAIL_CONFIGURED = True
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        mail.outbox.clear()
        fee = _invoiced_fee(advocate, days_ago=20)

        _run()

        message = ClientMessage.objects.get()
        assert message.kind == ClientMessage.KIND_PAYMENT_REMINDER
        assert message.status == ClientMessage.STATUS_DRAFT
        assert message.fee == fee
        assert message.reminder_number == 1
        assert fee.invoice_number in message.subject
        assert not mail.outbox
        assert not SentMessage.objects.exists()

    def test_idempotent_and_one_waiting_draft_at_a_time(self, advocate):
        _invoiced_fee(advocate, days_ago=40)
        _run()
        _run()
        assert ClientMessage.objects.count() == 1

    def test_dry_run_writes_nothing(self, advocate):
        _invoiced_fee(advocate, days_ago=40)
        out = _run("--dry-run")
        assert "would draft" in out
        assert not ClientMessage.objects.exists()

    def test_next_reminder_waits_the_interval_after_the_last_one(self, advocate):
        fee = _invoiced_fee(advocate, days_ago=60)
        _run()
        _mark_reminder_delivered(fee, days_ago=5)

        _run()
        assert ClientMessage.objects.filter(fee=fee).count() == 1  # too soon

        ClientMessage.objects.filter(fee=fee).update(sent_at=timezone.now() - timedelta(days=16))
        _run()
        second = ClientMessage.objects.get(fee=fee, status=ClientMessage.STATUS_DRAFT)
        assert second.reminder_number == 2
        assert second.subject.startswith("Second reminder")

    def test_at_most_three(self, advocate):
        fee = _invoiced_fee(advocate, days_ago=200)
        for _ in range(3):
            _run()
            _mark_reminder_delivered(fee, days_ago=30)
        _run()
        assert ClientMessage.objects.filter(fee=fee).count() == 3
        assert not ClientMessage.objects.filter(status=ClientMessage.STATUS_DRAFT).exists()

    def test_respects_the_advocates_own_interval(self, advocate):
        AdvocateProfile.objects.filter(owner=advocate).update(reminder_after_days=45)
        _invoiced_fee(advocate, days_ago=30)
        _run()
        assert not ClientMessage.objects.exists()

    def test_skips_opted_out_and_email_less_billing_contacts(self, advocate):
        _invoiced_fee(advocate, days_ago=30, receive_payment_reminders=False)
        _invoiced_fee(advocate, days_ago=30, email=None)
        _invoiced_fee(advocate, days_ago=30, email=False)  # no billing contact at all
        out = _run()
        assert not ClientMessage.objects.exists()
        assert "no billing contact email" in out

    def test_discarding_a_reminder_stops_further_ones(self, advocate):
        fee = _invoiced_fee(advocate, days_ago=40)
        _run()
        ClientMessage.objects.filter(fee=fee).update(status=ClientMessage.STATUS_DISCARDED)
        _run()
        assert ClientMessage.objects.filter(fee=fee).count() == 1


@pytest.mark.django_db
class TestNeverAfterPaid:
    def test_marking_paid_discards_the_waiting_draft(self, advocate):
        fee = _invoiced_fee(advocate, days_ago=40)
        _run()
        invoice_service.mark_paid(fee)
        message = ClientMessage.objects.get(fee=fee)
        assert message.status == ClientMessage.STATUS_DISCARDED
        assert "paid" in message.discard_reason.lower()

    def test_send_refused_if_the_fee_was_paid_meanwhile(self, api, advocate):
        fee = _invoiced_fee(advocate, days_ago=40)
        _run()
        message = ClientMessage.objects.get(fee=fee)
        # Paid by some path that bypassed mark_paid's clean-up.
        AppearanceFee.objects.filter(id=fee.id).update(status=AppearanceFee.STATUS_PAID)

        resp = api.post(f"/api/client-messages/{message.id}/send/")

        assert resp.status_code == 409
        assert resp.data["code"] == "invoice_paid"
        message.refresh_from_db()
        assert message.status == ClientMessage.STATUS_DISCARDED
        assert not SentMessage.objects.exists()

    def test_sending_a_reminder_goes_to_the_billing_contact(self, api, advocate, settings):
        settings.INVOICE_EMAIL_CONFIGURED = True
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        mail.outbox.clear()
        fee = _invoiced_fee(advocate, days_ago=40)
        _run()
        message = ClientMessage.objects.get(fee=fee)

        resp = api.post(f"/api/client-messages/{message.id}/send/")

        assert resp.status_code == 200, resp.data
        sent = mail.outbox[0]
        assert sent.to == ["billing@example.com"]
        assert sent.attachments[0][0] == f"{fee.invoice_number}.pdf"
        audit = SentMessage.objects.get()
        assert audit.kind == SentMessage.KIND_CHOICES[1][0]  # payment_reminder
        assert audit.fee == fee
