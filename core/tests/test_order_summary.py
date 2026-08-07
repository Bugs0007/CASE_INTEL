"""Phase C: Order Overview.

The LLM is mocked everywhere in this file. Two things are being proved:

  1. **Routing** -- which orders reach the model at all. Every no-LLM
     path asserts the client was never constructed, because "we didn't
     spend money here" is the actual requirement, not an implementation
     detail.
  2. **Party-aware rendering** -- that "your side" resolves correctly for
     petitioner, respondent, AND unknown, since showing an advocate the
     other side's obligations as their own is the real harm this feature
     could do.
"""

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import Case, CourtOrder, Document
from core.services.order_summary import (
    ROUTE_LLM,
    ROUTE_ROUTINE,
    ROUTE_SHORT,
    ROUTE_UNREADABLE,
    classify_order_text,
)
from core.services.order_summary import service as summary_service

# ---------------------------------------------------------------------------
# Fixtures: text that exercises each route
# ---------------------------------------------------------------------------

EMPTY_TEXT = ""
SCANNED_TEXT = "  \n  IN THE HIGH COURT  \n "  # a few chars of OCR noise

# Between MIN_READABLE_CHARS and SHORT_TEXT_CHARS, and carrying no
# substantive marker -- a genuine procedural note.
TINY_TEXT = (
    "Heard the learned counsel appearing for the petitioner and the learned "
    "Government Pleader for the respondents. The matter could not be taken up "
    "today for want of time. Registry to note."
)

ROUTINE_TEXT = (
    "IN THE HIGH COURT FOR THE STATE OF TELANGANA AT HYDERABAD. "
    "WRIT PETITION No. 24113 of 2026. Between: Ramesh Kumar, Petitioner and "
    "State of Telangana, rep. by its Principal Secretary, Respondent. "
    "ORDER: At the request of the learned counsel for the petitioner, the "
    "matter is adjourned. Post on 12.08.2026. The interlocutory application "
    "shall also be listed along with the main matter on the said date. "
    "Registry to note. " * 2
)

SUBSTANTIVE_TEXT = (
    "IN THE HIGH COURT FOR THE STATE OF TELANGANA AT HYDERABAD. "
    "WRIT PETITION No. 24113 of 2026. ORDER: Heard the learned counsel for "
    "the petitioner and the learned Government Pleader for the respondents. "
    "The petitioner has challenged the impugned order dated 01.03.2026. "
    "Having considered the submissions, there shall be an interim direction "
    "that the respondents shall not take any coercive steps against the "
    "petitioner pending further orders. The respondents are directed to file "
    "their counter affidavit within four weeks. The petitioner shall file a "
    "rejoinder, if any, within two weeks thereafter. List the matter on "
    "15.09.2026 for further hearing. " * 3
)

# Short and adjournment-like, but carries a substantive direction -- the
# two-sided heuristic must NOT route this away from the LLM.
ROUTINE_LOOKING_BUT_SUBSTANTIVE = (
    "ORDER: At the request of the learned counsel, the matter is adjourned "
    "and posted on 12.08.2026. However, the respondents are directed to file "
    "their counter affidavit before the said date, failing which the interim "
    "order shall stand vacated automatically. "
)


VALID_LLM_JSON = json.dumps(
    {
        "what_happened": "The court heard both sides and granted an interim direction restraining coercive steps.",
        "petitioner_directions": ["File a rejoinder within two weeks of the counter affidavit."],
        "respondent_directions": [
            "File a counter affidavit within four weeks.",
            "Take no coercive steps against the petitioner pending further orders.",
        ],
        "next_date": "2026-09-15",
        "next_date_purpose": "Further hearing",
        "is_routine_adjournment": False,
    }
)


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="overview-advocate", password="pass-123")


@pytest.fixture
def capture_core_logs():
    """Let caplog see records from the "core" logger.

    settings.LOGGING configures "core" with propagate=False, so its
    records never reach the root logger where pytest's caplog handler
    lives -- without this, caplog.text is empty even though the line is
    plainly emitted.
    """
    import logging as _logging

    core_logger = _logging.getLogger("core")
    original = core_logger.propagate
    core_logger.propagate = True
    yield
    core_logger.propagate = original


def _case(owner, role="unknown", number="OV-001"):
    return Case.objects.create(
        owner=owner,
        case_number=number,
        title=f"{number} Ramesh Kumar vs State of Telangana",
        client_name="Ramesh Kumar",
        user_party_role=role,
        cnr_number="TSHC010051622026",
    )


def _order(owner, case, text=SUBSTANTIVE_TEXT, with_document=True):
    document = None
    if with_document:
        document = Document.objects.create(
            owner=owner,
            case=case,
            filename="order.pdf",
            file_path="documents/order.pdf",
            file_type="pdf",
            file_size=1024,
            document_type="court_order",
            processing_status="completed",
            extracted_text=text,
        )
    return CourtOrder.objects.create(
        owner=owner,
        case=case,
        order_number="1",
        order_date=date(2026, 8, 3),
        dedup_key="TSHC010051622026:1:2026-08-03",
        document=document,
    )


# ---------------------------------------------------------------------------
# Routing (no LLM involved)
# ---------------------------------------------------------------------------


class TestClassifyOrderText:
    def test_empty_text_is_unreadable(self):
        route, _ = classify_order_text(EMPTY_TEXT)
        assert route == ROUTE_UNREADABLE

    def test_scanned_noise_is_unreadable(self):
        route, _ = classify_order_text(SCANNED_TEXT)
        assert route == ROUTE_UNREADABLE

    def test_tiny_text_is_short(self):
        route, _ = classify_order_text(TINY_TEXT)
        assert route == ROUTE_SHORT

    def test_routine_adjournment_is_routed_away_from_the_llm(self):
        route, _ = classify_order_text(ROUTINE_TEXT)
        assert route == ROUTE_ROUTINE

    def test_substantive_order_reaches_the_llm(self):
        route, _ = classify_order_text(SUBSTANTIVE_TEXT)
        assert route == ROUTE_LLM

    def test_substantive_marker_vetoes_the_routine_path(self):
        """The two-sided rule: adjournment language is not enough on its
        own to skip the model."""
        route, reason = classify_order_text(ROUTINE_LOOKING_BUT_SUBSTANTIVE)
        assert route == ROUTE_LLM
        assert "substantive marker" in reason

    def test_a_short_order_that_issues_directions_still_reaches_the_llm(self):
        """Regression: the length shortcut must not outrank the
        substantive veto.

        This order is well under SHORT_TEXT_CHARS but plainly directs the
        respondents to do something. Routing it to the templated "no
        directions issued" path would drop the only thing on the page the
        advocate actually needed.

        Note the UNREADABLE floor still comes first and is unaffected:
        that gate asks whether text extraction worked at all, not whether
        the order is substantive, and a real order PDF never yields under
        120 characters unless extraction failed.
        """
        short_but_operative = (
            "WRIT PETITION No. 24113 of 2026. ORDER: Heard both sides. The "
            "respondents are directed to file their counter affidavit within "
            "four weeks. Interim stay granted until further orders."
        )
        assert 120 < len(short_but_operative) < 400

        route, _ = classify_order_text(short_but_operative)
        assert route == ROUTE_LLM

    def test_a_short_order_with_no_substance_still_skips_the_llm(self):
        """The counterpart: the veto must not swallow the free path
        whole, or the cost gate stops working."""
        route, _ = classify_order_text(TINY_TEXT)
        assert route == ROUTE_SHORT

    def test_every_route_gives_a_reason(self):
        for text in (EMPTY_TEXT, TINY_TEXT, ROUTINE_TEXT, SUBSTANTIVE_TEXT):
            _, reason = classify_order_text(text)
            assert reason and isinstance(reason, str)

    def test_markers_match_across_pdf_line_breaks(self):
        """Extracted PDF text wraps mid-phrase; a marker that only
        matches on one line would silently misroute."""
        from core.services.order_summary.routing import has_adjournment_marker

        assert has_adjournment_marker("the matter is adjourned\n   to 12.08.2026")


# ---------------------------------------------------------------------------
# The no-LLM paths must not call the LLM
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestNoLlmPaths:
    @patch("core.services.ai_service_factory.get_llm_client")
    def test_unreadable_order_never_calls_the_model(self, get_client, advocate):
        order = _order(advocate, _case(advocate), text=SCANNED_TEXT)

        summary_service.summarize_court_order(order)

        get_client.assert_not_called()
        order.refresh_from_db()
        assert order.summary_status == CourtOrder.SUMMARY_UNREADABLE
        assert order.summary_route == ROUTE_UNREADABLE
        assert order.summary_llm_calls == 0
        assert "could not be read" in order.summary_what_happened

    @patch("core.services.ai_service_factory.get_llm_client")
    def test_order_with_no_document_is_unreadable(self, get_client, advocate):
        order = _order(advocate, _case(advocate), with_document=False)

        summary_service.summarize_court_order(order)

        get_client.assert_not_called()
        order.refresh_from_db()
        assert order.summary_status == CourtOrder.SUMMARY_UNREADABLE

    @patch("core.services.ai_service_factory.get_llm_client")
    def test_tiny_order_is_templated_without_the_model(self, get_client, advocate):
        order = _order(advocate, _case(advocate), text=TINY_TEXT)

        summary_service.summarize_court_order(order)

        get_client.assert_not_called()
        order.refresh_from_db()
        assert order.summary_status == CourtOrder.SUMMARY_NO_DIRECTIONS
        assert order.summary_route == ROUTE_SHORT
        assert order.summary_llm_calls == 0
        assert order.summary_petitioner_directions == []

    @patch("core.services.ai_service_factory.get_llm_client")
    def test_routine_adjournment_is_templated_without_the_model(self, get_client, advocate):
        order = _order(advocate, _case(advocate), text=ROUTINE_TEXT)

        summary_service.summarize_court_order(order)

        get_client.assert_not_called()
        order.refresh_from_db()
        assert order.summary_status == CourtOrder.SUMMARY_NO_DIRECTIONS
        assert order.summary_route == ROUTE_ROUTINE
        assert order.summary_is_routine_adjournment is True
        assert "routine adjournment" in order.summary_what_happened

    @patch("core.services.ai_service_factory.get_llm_client")
    def test_each_route_is_logged(self, get_client, advocate, caplog, capture_core_logs):
        """Which path an order took has to be visible in the log -- LLM
        calls cost real money on a free product."""
        import logging

        order = _order(advocate, _case(advocate), text=ROUTINE_TEXT)
        with caplog.at_level(logging.INFO, logger="core.services.order_summary.service"):
            summary_service.summarize_court_order(order)

        assert "route=ROUTINE" in caplog.text
        assert "no LLM call" in caplog.text


# ---------------------------------------------------------------------------
# The LLM path
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestLlmPath:
    @patch("core.services.ai_service_factory.get_llm_client")
    def test_substantive_order_is_summarized(self, get_client, advocate):
        client = MagicMock()
        client.generate_with_json.return_value = VALID_LLM_JSON
        get_client.return_value = client

        order = _order(advocate, _case(advocate))
        summary_service.summarize_court_order(order)

        assert client.generate_with_json.call_count == 1
        order.refresh_from_db()
        assert order.summary_status == CourtOrder.SUMMARY_SUMMARIZED
        assert order.summary_route == ROUTE_LLM
        assert order.summary_llm_calls == 1
        assert "interim direction" in order.summary_what_happened
        assert len(order.summary_respondent_directions) == 2
        assert order.summary_next_date == date(2026, 9, 15)
        assert order.summary_next_date_purpose == "Further hearing"

    @patch("core.services.ai_service_factory.get_llm_client")
    def test_summary_is_generated_once_and_cached(self, get_client, advocate):
        """Re-running ingest must never re-bill an already-summarised
        order."""
        client = MagicMock()
        client.generate_with_json.return_value = VALID_LLM_JSON
        get_client.return_value = client

        order = _order(advocate, _case(advocate))
        summary_service.summarize_court_order(order)
        summary_service.summarize_court_order(order)
        summary_service.summarize_court_order(order)

        assert client.generate_with_json.call_count == 1

    @patch("core.services.ai_service_factory.get_llm_client")
    def test_force_regenerates(self, get_client, advocate):
        client = MagicMock()
        client.generate_with_json.return_value = VALID_LLM_JSON
        get_client.return_value = client

        order = _order(advocate, _case(advocate))
        summary_service.summarize_court_order(order)
        summary_service.summarize_court_order(order, force=True)

        assert client.generate_with_json.call_count == 2

    @patch("core.services.ai_service_factory.get_llm_client")
    def test_the_order_text_is_actually_in_the_prompt(self, get_client, advocate):
        client = MagicMock()
        client.generate_with_json.return_value = VALID_LLM_JSON
        get_client.return_value = client

        case = _case(advocate)
        order = _order(advocate, case)
        summary_service.summarize_court_order(order)

        messages = client.generate_with_json.call_args[0][0]
        user_content = messages[-1]["content"]
        assert "counter affidavit" in user_content
        assert case.case_number in user_content
        assert "TSHC010051622026" in user_content


# ---------------------------------------------------------------------------
# JSON validation + the single retry
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestJsonRetry:
    @patch("core.services.ai_service_factory.get_llm_client")
    def test_malformed_json_is_retried_once_and_then_succeeds(self, get_client, advocate):
        client = MagicMock()
        client.generate_with_json.side_effect = [
            "Sure! Here is the summary you asked for.",  # not JSON at all
            VALID_LLM_JSON,
        ]
        get_client.return_value = client

        order = _order(advocate, _case(advocate))
        summary_service.summarize_court_order(order)

        assert client.generate_with_json.call_count == 2
        order.refresh_from_db()
        assert order.summary_status == CourtOrder.SUMMARY_SUMMARIZED
        assert order.summary_llm_calls == 2

    @patch("core.services.ai_service_factory.get_llm_client")
    def test_two_bad_responses_fail_visibly(self, get_client, advocate):
        client = MagicMock()
        client.generate_with_json.side_effect = ["not json", "still not json"]
        get_client.return_value = client

        order = _order(advocate, _case(advocate))
        summary_service.summarize_court_order(order)

        # Exactly one retry -- never an unbounded loop.
        assert client.generate_with_json.call_count == 2
        order.refresh_from_db()
        assert order.summary_status == CourtOrder.SUMMARY_FAILED
        assert "did not return valid JSON" in order.summary_error

    @patch("core.services.ai_service_factory.get_llm_client")
    def test_retry_prompt_shows_the_model_its_bad_reply(self, get_client, advocate):
        client = MagicMock()
        client.generate_with_json.side_effect = ["```oops```", VALID_LLM_JSON]
        get_client.return_value = client

        order = _order(advocate, _case(advocate))
        summary_service.summarize_court_order(order)

        retry_messages = client.generate_with_json.call_args_list[1][0][0]
        assert retry_messages[-2]["role"] == "assistant"
        assert "ONLY the JSON object" in retry_messages[-1]["content"]

    @patch("core.services.ai_service_factory.get_llm_client")
    def test_code_fenced_json_is_unwrapped_without_spending_the_retry(
        self, get_client, advocate
    ):
        client = MagicMock()
        client.generate_with_json.return_value = f"```json\n{VALID_LLM_JSON}\n```"
        get_client.return_value = client

        order = _order(advocate, _case(advocate))
        summary_service.summarize_court_order(order)

        assert client.generate_with_json.call_count == 1
        order.refresh_from_db()
        assert order.summary_status == CourtOrder.SUMMARY_SUMMARIZED

    @patch("core.services.ai_service_factory.get_llm_client")
    def test_valid_json_missing_required_field_is_a_parse_failure(
        self, get_client, advocate
    ):
        client = MagicMock()
        client.generate_with_json.side_effect = [
            json.dumps({"petitioner_directions": []}),  # no what_happened
            VALID_LLM_JSON,
        ]
        get_client.return_value = client

        order = _order(advocate, _case(advocate))
        summary_service.summarize_court_order(order)

        assert client.generate_with_json.call_count == 2
        order.refresh_from_db()
        assert order.summary_status == CourtOrder.SUMMARY_SUMMARIZED

    @patch("core.services.ai_service_factory.get_llm_client")
    def test_transport_failure_fails_without_burning_the_json_retry(
        self, get_client, advocate
    ):
        client = MagicMock()
        client.generate_with_json.side_effect = RuntimeError("connection reset")
        get_client.return_value = client

        order = _order(advocate, _case(advocate))
        summary_service.summarize_court_order(order)

        assert client.generate_with_json.call_count == 1
        order.refresh_from_db()
        assert order.summary_status == CourtOrder.SUMMARY_FAILED
        assert "LLM call failed" in order.summary_error

    @patch("core.services.ai_service_factory.get_llm_client")
    def test_unusable_next_date_does_not_fail_the_summary(self, get_client, advocate):
        """Losing the next date is a far smaller loss than losing the
        directions."""
        client = MagicMock()
        payload = json.loads(VALID_LLM_JSON)
        payload["next_date"] = "sometime in September"
        client.generate_with_json.return_value = json.dumps(payload)
        get_client.return_value = client

        order = _order(advocate, _case(advocate))
        summary_service.summarize_court_order(order)

        order.refresh_from_db()
        assert order.summary_status == CourtOrder.SUMMARY_SUMMARIZED
        assert order.summary_next_date is None
        assert order.summary_respondent_directions  # directions survived


# ---------------------------------------------------------------------------
# Party-aware rendering -- all three role values
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPartyAwareRendering:
    def _summarized_order(self, advocate, role):
        case = _case(advocate, role=role)
        order = _order(advocate, case)
        order.summary_status = CourtOrder.SUMMARY_SUMMARIZED
        order.summary_route = ROUTE_LLM
        order.summary_what_happened = "Interim direction granted."
        order.summary_petitioner_directions = ["File a rejoinder within two weeks."]
        order.summary_respondent_directions = ["File a counter affidavit within four weeks."]
        order.save()
        return case, order

    def _fetch(self, advocate, case):
        client = APIClient()
        client.force_authenticate(user=advocate)
        response = client.get(f"/api/cases/{case.id}/orders/")
        assert response.status_code == 200
        return response.data[0]["summary"]

    def test_petitioner_sees_petitioner_directions_as_their_own(self, advocate):
        case, _ = self._summarized_order(advocate, "petitioner")
        summary = self._fetch(advocate, case)

        assert summary["party_role"] == "petitioner"
        assert summary["your_side_directions"] == ["File a rejoinder within two weeks."]
        assert summary["other_side_directions"] == [
            "File a counter affidavit within four weeks."
        ]
        assert summary["your_side_label"] == "You (Petitioner)"

    def test_respondent_sees_respondent_directions_as_their_own(self, advocate):
        case, _ = self._summarized_order(advocate, "respondent")
        summary = self._fetch(advocate, case)

        assert summary["party_role"] == "respondent"
        assert summary["your_side_directions"] == [
            "File a counter affidavit within four weeks."
        ]
        assert summary["other_side_directions"] == ["File a rejoinder within two weeks."]
        assert summary["your_side_label"] == "You (Respondent)"

    def test_unknown_role_shows_both_sides_neutrally(self, advocate):
        """Guessing a side would be worse than showing both -- acting on
        the other side's directions is the actual harm here."""
        case, _ = self._summarized_order(advocate, "unknown")
        summary = self._fetch(advocate, case)

        assert summary["party_role"] == "unknown"
        assert summary["your_side_directions"] is None
        assert summary["other_side_directions"] is None
        assert summary["your_side_label"] is None
        # Both sides are still available, unlabelled.
        assert summary["petitioner_directions"] == ["File a rejoinder within two weeks."]
        assert summary["respondent_directions"] == [
            "File a counter affidavit within four weeks."
        ]

    def test_correcting_the_role_reframes_without_regenerating(self, advocate):
        """The your-side split is applied at render time, so a corrected
        role must not require a second LLM call."""
        case, order = self._summarized_order(advocate, "unknown")
        generated_at = order.summary_generated_at

        case.user_party_role = "respondent"
        case.save()

        summary = self._fetch(advocate, case)
        assert summary["your_side_directions"] == [
            "File a counter affidavit within four weeks."
        ]
        order.refresh_from_db()
        assert order.summary_generated_at == generated_at
        assert order.summary_llm_calls == 0

    def test_failed_summary_is_visible_to_the_client(self, advocate):
        case = _case(advocate)
        order = _order(advocate, case)
        order.summary_status = CourtOrder.SUMMARY_FAILED
        order.summary_error = "The model did not return valid JSON after 2 attempts."
        order.save()

        summary = self._fetch(advocate, case)
        assert summary["status"] == "failed"
        assert summary["status_display"] == "Summary failed"
        assert "valid JSON" in summary["error"]

    def test_another_advocate_cannot_read_the_summary(self, advocate, db):
        case, _ = self._summarized_order(advocate, "petitioner")
        intruder = User.objects.create_user(username="intruder", password="pass-123")

        client = APIClient()
        client.force_authenticate(user=intruder)
        assert client.get(f"/api/cases/{case.id}/orders/").status_code == 404


# ---------------------------------------------------------------------------
# Calendar surface (the summary on the hearing for that date)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestHearingOrderSummary:
    def _setup(self, advocate, role="respondent"):
        from django.utils import timezone as tz
        from datetime import datetime

        from core.models import Hearing

        case = _case(advocate, role=role)
        order = _order(advocate, case)
        order.summary_status = CourtOrder.SUMMARY_SUMMARIZED
        order.summary_what_happened = "Interim direction granted."
        order.summary_petitioner_directions = ["File a rejoinder."]
        order.summary_respondent_directions = ["File a counter affidavit."]
        order.save()

        hearing = Hearing.objects.create(
            owner=advocate,
            case=case,
            hearing_date=tz.make_aware(datetime(2026, 8, 3, 0, 0)),
            hearing_type="other",
            source="ecourts",
        )
        return case, order, hearing

    def _get(self, advocate, hearing_id):
        client = APIClient()
        client.force_authenticate(user=advocate)
        response = client.get(f"/api/hearings/{hearing_id}/")
        assert response.status_code == 200
        return response.data

    def test_hearing_carries_the_summary_for_its_own_date(self, advocate):
        _, _, hearing = self._setup(advocate)
        data = self._get(advocate, hearing.id)

        assert data["order_summary"] is not None
        assert data["order_summary"]["what_happened"] == "Interim direction granted."
        # Party-aware in the calendar too, not just on the case page.
        assert data["order_summary"]["your_side_directions"] == ["File a counter affidavit."]

    def test_hearing_on_a_different_date_has_no_summary(self, advocate):
        from datetime import datetime

        from django.utils import timezone as tz

        from core.models import Hearing

        case, _, _ = self._setup(advocate)
        other = Hearing.objects.create(
            owner=advocate,
            case=case,
            hearing_date=tz.make_aware(datetime(2026, 9, 15, 0, 0)),
            hearing_type="other",
            source="manual",
        )
        assert self._get(advocate, other.id)["order_summary"] is None

    def test_unsummarized_order_is_not_surfaced(self, advocate):
        from datetime import datetime

        from django.utils import timezone as tz

        from core.models import Hearing

        case = _case(advocate)
        _order(advocate, case)  # left at summary_status="pending"
        hearing = Hearing.objects.create(
            owner=advocate,
            case=case,
            hearing_date=tz.make_aware(datetime(2026, 8, 3, 0, 0)),
            hearing_type="other",
            source="ecourts",
        )
        assert self._get(advocate, hearing.id)["order_summary"] is None

    def test_hearing_list_query_count_does_not_grow_with_hearings(self, advocate):
        """The calendar renders every upcoming hearing at once, so the
        list endpoint's query count must not scale with the diary.

        Asserts CONSTANCY (5 hearings costs the same as 25) rather than a
        magic number, which is the property that actually matters and
        won't break on unrelated query churn.

        Regression: the embedded appearance_fee is a reverse OneToOne,
        which Django does not fetch with the row -- before
        select_related("appearance_fee") this was 8 queries for 5
        hearings and 28 for 25.
        """
        from datetime import datetime, timedelta

        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from django.utils import timezone as tz

        from core.models import Hearing

        case, _, _ = self._setup(advocate)
        client = APIClient()
        client.force_authenticate(user=advocate)

        def count_queries_with(total_hearings: int) -> int:
            Hearing.objects.filter(case=case).exclude(
                hearing_date=tz.make_aware(datetime(2026, 8, 3, 0, 0))
            ).delete()
            for offset in range(1, total_hearings):
                Hearing.objects.create(
                    owner=advocate,
                    case=case,
                    hearing_date=tz.make_aware(datetime(2026, 8, 3, 0, 0))
                    + timedelta(days=offset),
                    hearing_type="other",
                    source="manual",
                )
            with CaptureQueriesContext(connection) as ctx:
                response = client.get("/api/hearings/")
            assert response.status_code == 200
            assert len(response.data) == total_hearings
            return len(ctx)

        few = count_queries_with(5)
        many = count_queries_with(25)
        assert few == many, f"query count scales with hearings: {few} -> {many}"


# ---------------------------------------------------------------------------
# Ingest hook
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestIngestHook:
    @patch("core.services.ai_service_factory.get_llm_client")
    def test_worker_summarizes_a_court_order_after_processing(self, get_client, advocate):
        from core.management.commands.process_jobs import Command

        client = MagicMock()
        client.generate_with_json.return_value = VALID_LLM_JSON
        get_client.return_value = client

        order = _order(advocate, _case(advocate))
        Command()._summarize_order_if_any(order.document_id)

        order.refresh_from_db()
        assert order.summary_status == CourtOrder.SUMMARY_SUMMARIZED

    @patch("core.services.ai_service_factory.get_llm_client")
    def test_ordinary_document_is_not_summarized(self, get_client, advocate):
        from core.management.commands.process_jobs import Command

        document = Document.objects.create(
            owner=advocate,
            case=_case(advocate),
            filename="contract.pdf",
            file_path="documents/contract.pdf",
            file_type="pdf",
            file_size=1024,
            processing_status="completed",
            extracted_text=SUBSTANTIVE_TEXT,
        )

        Command()._summarize_order_if_any(document.id)

        get_client.assert_not_called()

    @patch("core.services.ai_service_factory.get_llm_client")
    def test_summary_failure_never_fails_the_document_job(self, get_client, advocate):
        """A broken summary must not take down a perfectly good,
        searchable document."""
        from core.management.commands.process_jobs import Command

        get_client.side_effect = RuntimeError("provider exploded")
        order = _order(advocate, _case(advocate))

        # Must not raise.
        Command()._summarize_order_if_any(order.document_id)
