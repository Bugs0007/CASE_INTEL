"""Client-update drafts: "your matter was heard on X, next date Y".

Covers what can go wrong in a way a client would notice:
  - the text: a real summary is used, anything unreliable falls back to
    date + purpose only (never a guess);
  - one draft per hearing event however many times generation runs, and a
    draft the advocate touched is never rewritten;
  - the three entry points (order summary in the worker, a refresh finding
    a new date, a manual reschedule) and the first-fetch exclusion;
  - sending: logged vs sent, the audit row, opt-outs re-checked at send
    time, and nothing ever sent without the advocate pressing Send.
"""

from datetime import date, datetime, timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from core.management.commands.process_jobs import Command as ProcessJobsCommand
from core.models import (
    AdvocateProfile,
    Case,
    ClientContact,
    ClientMessage,
    CourtOrder,
    Document,
    Hearing,
    SentMessage,
)
from core.services.client_updates import (
    draft_update_for_order,
    draft_updates_for_new_dates,
    send_client_message,
)
from core.services.client_updates.compose import compose_case_update
from core.services.court_data.models import CourtCaseData, HearingRecord
from core.services.court_tracking import refresh_case_tracking
from core.services.email_delivery import body_sha256
from core.services.invoice_service import get_or_create_profile


@pytest.fixture
def advocate(db):
    user = User.objects.create_user(username="update-advocate", password="pw-12345")
    get_or_create_profile(user)
    AdvocateProfile.objects.filter(owner=user).update(
        advocate_name="A. Rao", contact_email="rao@example.com"
    )
    return user


@pytest.fixture
def api(advocate):
    client = APIClient()
    client.force_authenticate(user=advocate)
    return client


@pytest.fixture
def today():
    return timezone.localdate()


def _case(owner, number="OS/10/2026", **extra):
    return Case.objects.create(
        owner=owner, case_number=number, title=f"{number} Rao vs Reddy", client_name="Rao", **extra
    )


def _contact(case, name="Client One", email="client1@example.com", **extra):
    return ClientContact.objects.create(owner=case.owner, case=case, name=name, email=email, **extra)


def _hearing(case, day: date, **extra):
    return Hearing.objects.create(
        owner=case.owner,
        case=case,
        hearing_date=timezone.make_aware(datetime.combine(day, datetime.min.time())),
        hearing_type="other",
        source=extra.pop("source", "ecourts"),
        status=extra.pop("status", "scheduled" if day >= timezone.localdate() else "completed"),
        **extra,
    )


def _order(case, order_date, *, status=CourtOrder.SUMMARY_SUMMARIZED, what="Notice issued to the respondents."):
    return CourtOrder.objects.create(
        owner=case.owner,
        case=case,
        order_number="1",
        order_date=order_date,
        dedup_key=f"CNR:1:{order_date}",
        summary_status=status,
        summary_what_happened=what,
    )


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCompose:
    def _body(self, advocate, order):
        case = order.case
        _, body = compose_case_update(
            case=case,
            profile=get_or_create_profile(advocate),
            recipient_names=["Client One"],
            heard_on=order.order_date,
            order=order,
            next_date=date(2026, 12, 1),
            next_purpose="FOR ARGUMENTS",
        )
        return body

    def test_uses_the_summary_when_there_is_a_real_one(self, advocate):
        order = _order(_case(advocate), date(2026, 9, 1))
        body = self._body(advocate, order)
        assert "heard on 01 September 2026. Notice issued to the respondents." in body
        assert "next date of hearing is 01 December 2026 (listed for: For arguments)." in body
        assert body.startswith("Dear Client One,")
        assert body.rstrip().endswith("A. Rao")

    @pytest.mark.parametrize(
        "status", [CourtOrder.SUMMARY_FAILED, CourtOrder.SUMMARY_PENDING, CourtOrder.SUMMARY_UNREADABLE]
    )
    def test_falls_back_to_date_and_purpose_when_the_summary_is_unreliable(self, advocate, status):
        order = _order(_case(advocate), date(2026, 9, 1), status=status, what="SHOULD NOT APPEAR")
        body = self._body(advocate, order)
        assert "SHOULD NOT APPEAR" not in body
        assert "The matter was heard on 01 September 2026.\n" in body
        assert "01 December 2026" in body

    def test_case_number_is_not_repeated_when_the_title_carries_it(self, advocate):
        from core.services.client_updates.compose import matter_name

        with_number = _case(advocate, number="OS/11/2026")  # title "OS/11/2026 Rao vs Reddy"
        without = Case.objects.create(owner=advocate, case_number="OS/12/2026", title="Rao vs Reddy", client_name="R")
        assert matter_name(with_number) == "OS/11/2026 Rao vs Reddy"
        assert matter_name(without) == "Rao vs Reddy (OS/12/2026)"

    def test_routine_adjournment_reads_plainly(self, advocate):
        order = _order(
            _case(advocate), date(2026, 9, 1), status=CourtOrder.SUMMARY_NO_DIRECTIONS,
            what="No directions were issued -- the order records a routine adjournment",
        )
        body = self._body(advocate, order)
        assert "adjourned the matter without issuing any directions" in body
        assert "--" not in body


# ---------------------------------------------------------------------------
# Draft generation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDraftGeneration:
    def test_order_drafts_one_update_to_opted_in_contacts_with_email(self, advocate, today):
        case = _case(advocate)
        _contact(case, "Client One", "client1@example.com", is_billing_contact=True)
        _contact(case, "No Email", None)
        _contact(case, "Opted Out", "out@example.com", receive_case_updates=False)
        heard = today - timedelta(days=1)
        _hearing(case, heard)
        _hearing(case, today + timedelta(days=30), purpose="ARGUMENTS")

        message, outcome = draft_update_for_order(_order(case, heard))

        assert outcome == "created"
        assert message.status == ClientMessage.STATUS_DRAFT
        assert [r["email"] for r in message.recipients] == ["client1@example.com"]
        assert "(listed for: Arguments)" in message.body
        assert ClientMessage.objects.count() == 1
        assert not mail.outbox  # a draft is never sent on its own
        assert not SentMessage.objects.exists()

    def test_regenerating_is_idempotent_and_upgrades_an_untouched_draft(self, advocate, today):
        case = _case(advocate)
        _contact(case)
        heard = today - timedelta(days=1)
        order = _order(case, heard, status=CourtOrder.SUMMARY_FAILED, what="")

        first, _ = draft_update_for_order(order)
        assert "Notice issued" not in first.body

        order.summary_status = CourtOrder.SUMMARY_SUMMARIZED
        order.summary_what_happened = "Notice issued."
        order.save()
        second, outcome = draft_update_for_order(order)

        assert second.id == first.id
        assert outcome == "updated"
        assert "Notice issued." in second.body
        assert ClientMessage.objects.count() == 1

    def test_an_edited_draft_is_never_rewritten(self, advocate, today):
        case = _case(advocate)
        _contact(case)
        order = _order(case, today - timedelta(days=1))
        message, _ = draft_update_for_order(order)
        ClientMessage.objects.filter(id=message.id).update(body="My own words.", edited_by_user=True)

        order.summary_what_happened = "Something else."
        order.save()
        again, outcome = draft_update_for_order(order)

        assert outcome == "skipped"
        assert again.body == "My own words."

    def test_a_discarded_draft_is_not_recreated(self, advocate, today):
        case = _case(advocate)
        _contact(case)
        order = _order(case, today - timedelta(days=1))
        message, _ = draft_update_for_order(order)
        ClientMessage.objects.filter(id=message.id).update(status=ClientMessage.STATUS_DISCARDED)

        _, outcome = draft_update_for_order(order)

        assert outcome == "skipped"
        assert ClientMessage.objects.count() == 1

    def test_undated_order_drafts_nothing(self, advocate):
        case = _case(advocate)
        order = CourtOrder.objects.create(owner=advocate, case=case, order_number="9", dedup_key="x")
        assert draft_update_for_order(order) == (None, "skipped")

    def test_new_future_date_and_later_order_land_on_one_draft(self, advocate, today):
        """The refresh sees the next date first; the order summary for the
        hearing arrives later. Same hearing event -> same draft."""
        case = _case(advocate)
        _contact(case)
        heard = today - timedelta(days=1)
        nxt = today + timedelta(days=21)
        _hearing(case, heard)
        _hearing(case, nxt, purpose="HEARING")

        assert draft_updates_for_new_dates(case, [nxt]) == 1
        draft = ClientMessage.objects.get()
        assert "Notice issued" not in draft.body

        draft_update_for_order(_order(case, heard))

        draft.refresh_from_db()
        assert ClientMessage.objects.count() == 1
        assert "Notice issued" in draft.body
        assert nxt.strftime("%d %B %Y") in draft.body

    def test_only_past_new_dates_wait_for_their_order(self, advocate, today):
        case = _case(advocate)
        _contact(case)
        assert draft_updates_for_new_dates(case, [today - timedelta(days=3)]) == 0
        assert not ClientMessage.objects.exists()

    def test_draft_without_recipients_is_still_kept(self, advocate, today):
        case = _case(advocate)
        message, outcome = draft_update_for_order(_order(case, today - timedelta(days=1)))
        assert outcome == "created"
        assert message.recipients == []
        assert message.body.startswith("Dear Sir/Madam,")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEntryPoints:
    def test_worker_drafts_after_the_order_summary(self, advocate, today):
        case = _case(advocate)
        _contact(case)
        order = _order(case, today - timedelta(days=1))
        order.document = Document.objects.create(
            owner=advocate, case=case, filename="o.pdf", file_path="documents/o.pdf",
            file_type="pdf", document_type="court_order", processing_status="completed",
            extracted_text="(already summarised)",
        )
        order.save()

        ProcessJobsCommand(stdout=StringIO())._summarize_order_if_any(order.document_id)

        assert ClientMessage.objects.filter(court_order=order).count() == 1

    def test_a_draft_failure_never_fails_the_document_job(self, advocate, today):
        case = _case(advocate)
        order = _order(case, today - timedelta(days=1))
        order.document = Document.objects.create(
            owner=advocate, case=case, filename="o.pdf", file_path="documents/o.pdf",
            file_type="pdf", document_type="court_order", processing_status="completed",
        )
        order.save()
        with patch(
            "core.services.client_updates.draft_update_for_order", side_effect=RuntimeError("boom")
        ):
            ProcessJobsCommand(stdout=StringIO())._summarize_order_if_any(order.document_id)
        assert not ClientMessage.objects.exists()

    def _tracked(self, advocate):
        return _case(
            advocate,
            number="OS/77/2026",
            court_type="district",
            tracking_config={"court_type": "district", "cnr": "TSHY010000772026"},
            tracking_enabled=True,
        )

    @patch("core.services.court_tracking.get_provider")
    def test_first_fetch_drafts_nothing_but_a_later_new_date_does(self, get_provider, advocate, today):
        case = self._tracked(advocate)
        _contact(case)
        heard = today - timedelta(days=2)
        provider = MagicMock()
        provider.fetch_case.return_value = CourtCaseData(
            cnr="TSHY010000772026",
            hearing_history=[HearingRecord(hearing_date=heard, purpose="HEARING")],
        )
        get_provider.return_value = provider

        first = refresh_case_tracking(case, force=True)
        assert first["client_update_drafts"] == 0
        assert not ClientMessage.objects.exists()

        nxt = today + timedelta(days=14)
        provider.fetch_case.return_value = CourtCaseData(
            cnr="TSHY010000772026",
            hearing_history=[
                HearingRecord(hearing_date=heard, purpose="HEARING"),
                HearingRecord(hearing_date=nxt, purpose="EVIDENCE"),
            ],
        )
        case.refresh_from_db()
        second = refresh_case_tracking(case, force=True)

        assert second["client_update_drafts"] == 1
        draft = ClientMessage.objects.get()
        assert heard.strftime("%d %B %Y") in draft.body
        assert "(listed for: Evidence)" in draft.body

    def test_manual_reschedule_drafts_an_update(self, api, advocate, today):
        case = _case(advocate)
        _contact(case)
        hearing = _hearing(case, today + timedelta(days=5), source="manual")
        new_date = today + timedelta(days=12)

        resp = api.patch(
            f"/api/hearings/{hearing.id}/",
            {"hearing_date": timezone.make_aware(datetime.combine(new_date, datetime.min.time())).isoformat()},
            format="json",
        )

        assert resp.status_code == 200, resp.data
        draft = ClientMessage.objects.get()
        assert "is now listed on " + new_date.strftime("%d %B %Y") in draft.body

    def test_editing_other_hearing_fields_drafts_nothing(self, api, advocate, today):
        case = _case(advocate)
        _contact(case)
        hearing = _hearing(case, today + timedelta(days=5), source="manual")
        api.patch(f"/api/hearings/{hearing.id}/", {"notes": "Bring file"}, format="json")
        assert not ClientMessage.objects.exists()


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSending:
    def _draft(self, advocate, today, **contact_extra):
        case = _case(advocate)
        _contact(case, **contact_extra)
        message, _ = draft_update_for_order(_order(case, today - timedelta(days=1)))
        return message

    def test_logged_when_email_is_not_configured(self, api, advocate, today, settings):
        settings.INVOICE_EMAIL_CONFIGURED = False
        message = self._draft(advocate, today)

        resp = api.post(f"/api/client-messages/{message.id}/send/")

        assert resp.status_code == 200, resp.data
        assert resp.data["sent"] is False
        assert "RESEND_API_KEY" in resp.data["missing_env_vars"]
        assert resp.data["message"]["status"] == "logged"
        assert not mail.outbox
        audit = SentMessage.objects.get()
        assert audit.delivery == SentMessage.DELIVERY_LOGGED
        assert audit.to_emails == ["client1@example.com"]
        assert audit.sent_by == advocate
        assert audit.body_sha256 == body_sha256(message.body)

    def test_sent_through_the_shared_path_when_configured(self, api, advocate, today, settings):
        settings.INVOICE_EMAIL_CONFIGURED = True
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        mail.outbox.clear()
        message = self._draft(advocate, today)

        resp = api.post(f"/api/client-messages/{message.id}/send/")

        assert resp.status_code == 200, resp.data
        assert resp.data["sent"] is True
        sent = mail.outbox[0]
        assert sent.to == ["client1@example.com"]
        assert sent.reply_to == ["rao@example.com"]
        assert sent.cc == ["rao@example.com"]
        message.refresh_from_db()
        assert message.status == ClientMessage.STATUS_SENT
        assert SentMessage.objects.get().delivery == SentMessage.DELIVERY_SENT

    def test_opt_out_after_drafting_is_honoured_at_send_time(self, api, advocate, today):
        message = self._draft(advocate, today)
        ClientContact.objects.update(receive_case_updates=False)

        resp = api.post(f"/api/client-messages/{message.id}/send/")

        assert resp.status_code == 400
        assert not SentMessage.objects.exists()
        message.refresh_from_db()
        assert message.status == ClientMessage.STATUS_DRAFT

    def test_blocked_without_the_advocates_contact_email(self, api, advocate, today):
        AdvocateProfile.objects.filter(owner=advocate).update(contact_email="")
        message = self._draft(advocate, today)

        resp = api.post(f"/api/client-messages/{message.id}/send/")

        assert resp.status_code == 400
        assert "contact email" in resp.data["detail"].lower()
        assert not SentMessage.objects.exists()

    def test_cannot_send_twice(self, api, advocate, today):
        message = self._draft(advocate, today)
        api.post(f"/api/client-messages/{message.id}/send/")
        resp = api.post(f"/api/client-messages/{message.id}/send/")
        assert resp.status_code == 409
        assert SentMessage.objects.count() == 1

    def test_editing_marks_the_draft_as_the_advocates(self, api, advocate, today):
        message = self._draft(advocate, today)
        resp = api.patch(
            f"/api/client-messages/{message.id}/", {"body": "Edited text."}, format="json"
        )
        assert resp.status_code == 200
        message.refresh_from_db()
        assert message.body == "Edited text."
        assert message.edited_by_user is True

    def test_recipients_are_limited_to_eligible_contacts_on_the_case(self, api, advocate, today):
        message = self._draft(advocate, today)
        second = _contact(message.case, "Client Two", "two@example.com")
        other_case_contact = _contact(_case(advocate, number="OS/99/2026"), "Elsewhere", "x@example.com")

        ok = api.patch(
            f"/api/client-messages/{message.id}/", {"recipient_contact_ids": [second.id]}, format="json"
        )
        bad = api.patch(
            f"/api/client-messages/{message.id}/",
            {"recipient_contact_ids": [other_case_contact.id]},
            format="json",
        )

        assert ok.status_code == 200
        assert [r["email"] for r in ok.data["recipients"]] == ["two@example.com"]
        assert bad.status_code == 400

    def test_discard_keeps_the_row(self, api, advocate, today):
        message = self._draft(advocate, today)
        resp = api.delete(f"/api/client-messages/{message.id}/")
        assert resp.status_code == 200
        message.refresh_from_db()
        assert message.status == ClientMessage.STATUS_DISCARDED

    def test_send_service_requires_a_draft(self, advocate, today):
        message = self._draft(advocate, today)
        ClientMessage.objects.filter(id=message.id).update(status=ClientMessage.STATUS_SENT)
        message.refresh_from_db()
        from core.services.client_updates import NotADraftError

        with pytest.raises(NotADraftError):
            send_client_message(message, user=advocate)

    def test_list_filters_by_status_and_case(self, api, advocate, today):
        message = self._draft(advocate, today)
        drafts = api.get("/api/client-messages/", {"status": "draft"})
        by_case = api.get("/api/client-messages/", {"case_id": message.case_id})
        sent = api.get("/api/client-messages/", {"status": "sent"})
        assert [m["id"] for m in drafts.data] == [message.id]
        assert [m["id"] for m in by_case.data] == [message.id]
        assert sent.data == []
