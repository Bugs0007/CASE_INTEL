"""Hearing prep sheet: assembly, the cached briefing paragraph, the API/PDF,
and the case_briefing worker job. The LLM is always mocked."""

from datetime import date, datetime, timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from core.management.commands.process_jobs import Command as ProcessJobsCommand
from core.models import (
    Case,
    CaseBriefing,
    CourtFetchLog,
    CourtOrder,
    Document,
    Hearing,
    ProcessingJob,
    Task,
)
from core.services.hearing_digest import (
    BriefingError,
    assemble_hearing_digest,
    generate_case_briefing,
    get_briefing_state,
    request_briefing,
)
from core.services.hearing_digest.briefing import briefing_inputs, fingerprint
from core.services.hearing_digest.prompt import SYSTEM_PROMPT, build_messages

LLM_FACTORY = "core.services.ai_service_factory.get_llm_client"
BRIEFING_TEXT = "The respondent was directed to file a counter affidavit; the matter is listed for admission."


def _midnight(day: date):
    return timezone.make_aware(datetime.combine(day, datetime.min.time()))


def _llm(text=BRIEFING_TEXT):
    client = MagicMock()
    client.generate.return_value = text
    return client


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="prep-advocate", password="pw-12345")


@pytest.fixture
def other_advocate(db):
    return User.objects.create_user(username="prep-other", password="pw-12345")


@pytest.fixture
def api(advocate):
    client = APIClient()
    client.force_authenticate(user=advocate)
    return client


@pytest.fixture
def today():
    return timezone.localdate()


@pytest.fixture
def case(advocate):
    return Case.objects.create(
        owner=advocate,
        case_number="WP/23998/2026",
        title="Rao vs State of Telangana",
        user_party_role="respondent",
        court_type="high_court",
        tracking_enabled=True,
    )


@pytest.fixture
def hearing(advocate, case, today):
    return Hearing.objects.create(
        owner=advocate,
        case=case,
        hearing_date=_midnight(today + timedelta(days=1)),
        hearing_type="other",
        source="ecourts",
        purpose="FOR ADMISSION",
        cause_list_status=Hearing.CAUSE_LIST_LISTED,
        cause_list_item_number="14",
        cause_list_court_hall="3",
        cause_list_stage="FOR ADMISSION (FRESH MATTERS)",
    )


def _order(owner, case, order_date, *, number="1", status=CourtOrder.SUMMARY_SUMMARIZED, **fields):
    return CourtOrder.objects.create(
        owner=owner,
        case=case,
        order_number=number,
        order_date=order_date,
        dedup_key=f"CNR:{number}:{order_date}",
        summary_status=status,
        summary_what_happened=fields.get("what_happened", "Notice issued to the respondent."),
        summary_petitioner_directions=fields.get("petitioner", []),
        summary_respondent_directions=fields.get("respondent", ["File counter within 4 weeks."]),
        summary_next_date=fields.get("next_date"),
        summary_next_date_purpose=fields.get("next_date_purpose", ""),
    )


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAssembleHearingDigest:
    def test_last_order_is_the_latest_resolved_one_before_the_hearing(
        self, advocate, case, hearing, today
    ):
        _order(advocate, case, today - timedelta(days=30), number="1")
        latest = _order(advocate, case, today - timedelta(days=5), number="2")
        _order(advocate, case, today - timedelta(days=2), number="3", status=CourtOrder.SUMMARY_PENDING)

        digest = assemble_hearing_digest(hearing)

        assert digest.last_order == latest

    def test_no_orders_is_fine(self, hearing):
        digest = assemble_hearing_digest(hearing)
        assert digest.last_order is None
        assert digest.purposes == ["FOR ADMISSION"]

    def test_open_tasks_and_documents_on_file(self, advocate, case, hearing):
        open_task = Task.objects.create(owner=advocate, case=case, title="Collect certified copy")
        Task.objects.create(owner=advocate, case=case, title="Done", status=Task.STATUS_COMPLETED)
        petition = Document.objects.create(
            owner=advocate, case=case, filename="petition.pdf", file_path="d/p.pdf", document_type="pleading"
        )
        Document.objects.create(
            owner=advocate, case=case, filename="order.pdf", file_path="d/o.pdf", document_type="court_order"
        )

        digest = assemble_hearing_digest(hearing)

        assert digest.open_tasks == [open_task]
        # Orders have their own section; documents are what the advocate filed.
        assert digest.documents == [petition]

    def test_order_purpose_leads_when_the_order_set_this_date(self, advocate, case, hearing, today):
        _order(
            advocate,
            case,
            today - timedelta(days=5),
            next_date=hearing.hearing_date.date(),
            next_date_purpose="Filing of counter affidavit",
        )

        digest = assemble_hearing_digest(hearing)

        assert digest.purposes == ["Filing of counter affidavit", "FOR ADMISSION"]


# ---------------------------------------------------------------------------
# Briefing: facts, fingerprint, states
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBriefingState:
    def test_nothing_on_record_is_unavailable_and_never_enqueued(self, case):
        state, enqueued = request_briefing(case)
        assert state["status"] == "unavailable"
        assert enqueued is False
        assert not ProcessingJob.objects.exists()

    def test_missing_then_generating_then_ready(self, advocate, case, hearing, today):
        _order(advocate, case, today - timedelta(days=5))
        assert get_briefing_state(case)["status"] == "missing"

        state, enqueued = request_briefing(case)
        assert (state["status"], enqueued) == ("generating", True)
        # A second request while queued doesn't enqueue again.
        _, enqueued_again = request_briefing(case)
        assert enqueued_again is False
        assert ProcessingJob.objects.filter(job_type="case_briefing").count() == 1

        ProcessingJob.objects.update(status="succeeded")
        with patch(LLM_FACTORY, return_value=_llm()):
            generate_case_briefing(case)

        state = get_briefing_state(case)
        assert state["status"] == "ready"
        assert state["text"] == BRIEFING_TEXT
        _, enqueued = request_briefing(case)
        assert enqueued is False

    def test_new_facts_make_it_stale_but_keep_the_old_text(self, advocate, case, hearing, today):
        _order(advocate, case, today - timedelta(days=20), number="1")
        with patch(LLM_FACTORY, return_value=_llm()):
            generate_case_briefing(case)

        _order(advocate, case, today - timedelta(days=2), number="2")

        state = get_briefing_state(case)
        assert state["status"] == "stale"
        assert state["text"] == BRIEFING_TEXT

    def test_party_role_is_not_part_of_the_facts(self, advocate, case, hearing, today):
        _order(advocate, case, today - timedelta(days=5))
        before = fingerprint(briefing_inputs(case))

        case.user_party_role = "petitioner"
        case.save()

        assert fingerprint(briefing_inputs(case)) == before
        assert "user_party_role" not in str(briefing_inputs(case))

    def test_fingerprint_follows_court_status(self, advocate, case, hearing):
        before = fingerprint(briefing_inputs(case))
        CourtFetchLog.objects.create(
            owner=advocate,
            case=case,
            success=True,
            fields_changed={"snapshot": {"case_status": "CASE DISPOSED", "case_stage": ""}},
        )
        assert fingerprint(briefing_inputs(case)) != before


@pytest.mark.django_db
class TestGenerateCaseBriefing:
    def test_fresh_briefing_is_not_regenerated(self, advocate, case, hearing, today):
        _order(advocate, case, today - timedelta(days=5))
        client = _llm()
        with patch(LLM_FACTORY, return_value=client):
            generate_case_briefing(case)
            generate_case_briefing(case)

        assert client.generate.call_count == 1
        assert CaseBriefing.objects.get(case=case).llm_calls == 1

    def test_llm_failure_is_recorded_and_raised(self, advocate, case, hearing, today):
        _order(advocate, case, today - timedelta(days=5))
        client = MagicMock()
        client.generate.side_effect = RuntimeError("provider down")

        with patch(LLM_FACTORY, return_value=client), pytest.raises(BriefingError):
            generate_case_briefing(case)

        state = get_briefing_state(case)
        assert state["status"] == "failed"
        assert "provider down" in state["error"]
        # A failed attempt can be retried.
        _, enqueued = request_briefing(case)
        assert enqueued is True

    def test_empty_reply_is_a_failure(self, advocate, case, hearing, today):
        _order(advocate, case, today - timedelta(days=5))
        with patch(LLM_FACTORY, return_value=_llm("   ")), pytest.raises(BriefingError):
            generate_case_briefing(case)
        assert CaseBriefing.objects.get(case=case).status == CaseBriefing.STATUS_FAILED

    @pytest.mark.parametrize(
        "raw, expected",
        [
            (f"```text\n{BRIEFING_TEXT}\n```", BRIEFING_TEXT),
            (f'"{BRIEFING_TEXT}"', BRIEFING_TEXT),
            ("Text of the order was\n  read out.", "Text of the order was read out."),
        ],
    )
    def test_model_wrapping_is_removed(self, advocate, case, hearing, today, raw, expected):
        _order(advocate, case, today - timedelta(days=5))
        with patch(LLM_FACTORY, return_value=_llm(raw)):
            briefing = generate_case_briefing(case)
        assert briefing.text == expected

    def test_prompt_is_neutral_and_carries_the_facts(self, advocate, case, hearing, today):
        _order(advocate, case, today - timedelta(days=5), respondent=["File counter within 4 weeks."])

        messages = build_messages(briefing_inputs(case))

        assert messages[0]["content"] == SYSTEM_PROMPT
        assert "never 'you'" in SYSTEM_PROMPT
        assert "File counter within 4 weeks." in messages[1]["content"]
        assert "WP/23998/2026" in messages[1]["content"]


# ---------------------------------------------------------------------------
# API and PDF
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestHearingDigestApi:
    def test_digest_shape(self, api, advocate, case, hearing, today):
        _order(advocate, case, today - timedelta(days=5))
        Task.objects.create(owner=advocate, case=case, title="Collect certified copy")

        resp = api.get(f"/api/hearings/{hearing.id}/digest/")

        assert resp.status_code == 200
        body = resp.data
        assert body["hearing"]["cause_list"]["item_number"] == "14"
        assert body["hearing"]["cause_list"]["court_hall"] == "3"
        assert body["case"]["case_number"] == "WP/23998/2026"
        assert body["purposes"] == ["FOR ADMISSION"]
        # Party-aware, same shape as the case page's Order Overview.
        assert body["last_order"]["summary"]["your_side_directions"] == ["File counter within 4 weeks."]
        assert [t["title"] for t in body["open_tasks"]] == ["Collect certified copy"]
        assert body["briefing"]["status"] == "missing"

    def test_reading_the_digest_never_calls_the_llm(self, api, advocate, case, hearing, today):
        _order(advocate, case, today - timedelta(days=5))
        with patch(LLM_FACTORY) as factory:
            api.get(f"/api/hearings/{hearing.id}/digest/")
            api.get(f"/api/hearings/{hearing.id}/digest/pdf/")
        factory.assert_not_called()

    def test_briefing_request_is_202_then_200(self, api, advocate, case, hearing, today):
        _order(advocate, case, today - timedelta(days=5))

        first = api.post(f"/api/hearings/{hearing.id}/digest/briefing/")
        second = api.post(f"/api/hearings/{hearing.id}/digest/briefing/")

        assert (first.status_code, first.data["status"]) == (202, "generating")
        assert (second.status_code, second.data["status"]) == (200, "generating")

    def test_pdf_download(self, api, advocate, case, hearing, today):
        _order(
            advocate,
            case,
            today - timedelta(days=5),
            # Non-Latin-1 text must not break the core fonts.
            what_happened="Notice issued – returnable in 4 weeks “forthwith”.",
            petitioner=["సమాధానం దాఖలు చేయాలి"],
        )
        with patch(LLM_FACTORY, return_value=_llm()):
            generate_case_briefing(case)

        resp = api.get(f"/api/hearings/{hearing.id}/digest/pdf/")

        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")
        assert 'filename="prep-WP-23998-2026-' in resp["Content-Disposition"]

    @pytest.mark.parametrize(
        "method, suffix",
        [("get", "digest/"), ("get", "digest/pdf/"), ("post", "digest/briefing/")],
    )
    def test_another_advocates_hearing_is_404(
        self, other_advocate, hearing, method, suffix
    ):
        intruder = APIClient()
        intruder.force_authenticate(user=other_advocate)

        resp = getattr(intruder, method)(f"/api/hearings/{hearing.id}/{suffix}")

        assert resp.status_code == 404
        assert not ProcessingJob.objects.exists()


@pytest.mark.django_db
class TestCaseBriefingJob:
    def test_worker_runs_the_job(self, advocate, case, hearing, today):
        _order(advocate, case, today - timedelta(days=5))
        request_briefing(case)
        job = ProcessingJob.objects.get(job_type="case_briefing")

        with patch(LLM_FACTORY, return_value=_llm()):
            ProcessJobsCommand(stdout=StringIO())._process_job(job, processor=None)

        job.refresh_from_db()
        assert job.status == "succeeded"
        assert get_briefing_state(case)["status"] == "ready"

    def test_failed_generation_fails_the_job(self, advocate, case, hearing, today):
        _order(advocate, case, today - timedelta(days=5))
        request_briefing(case)
        job = ProcessingJob.objects.get(job_type="case_briefing")
        client = MagicMock()
        client.generate.side_effect = RuntimeError("provider down")

        with patch(LLM_FACTORY, return_value=client):
            ProcessJobsCommand(stdout=StringIO())._process_job(job, processor=None)

        job.refresh_from_db()
        assert job.status == "failed"
        assert "provider down" in job.error
