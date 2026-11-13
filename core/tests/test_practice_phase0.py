"""Phase 0 of the Case Bot quality plan: requests the assistant cannot do get
an honest answer, keywords no longer hijack a request, the second half of a
two-part request is named, and the model wait is bounded on every provider.

Pure routing tests (no database, no model): the model factory raises if any
of these questions reaches it.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from core.services.graph import practice_nodes
from core.services.practice_assistant import actions, boundaries, parsing

NOW = datetime(2026, 11, 12, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))  # a Thursday
TODAY = NOW.date()


def select(query: str) -> dict:
    state = {"query": query, "selected_day": None, "case_id": None, "now": NOW}
    with patch.object(practice_nodes, "get_llm_client", side_effect=AssertionError("model called")):
        return practice_nodes.select_intent(state)


class TestBoundaryAnswers:
    @pytest.mark.parametrize(
        "query",
        [
            "what is section 138 NI Act?",
            "explain the limitation act",
            "is cheating bailable",
            "any case law on adverse possession",
            "what does order 39 rule 1 say",
        ],
    )
    def test_general_law_is_declined(self, query):
        update = select(query)
        assert update["answer"] == boundaries.LAW_QUESTION
        assert update["status"] == "answer" and update.get("intent") is None

    def test_a_question_about_my_records_is_not_a_law_question(self):
        assert select("is the Rao case listed tomorrow").get("answer") != boundaries.LAW_QUESTION

    def test_court_filings_are_declined_with_what_can_be_drafted(self):
        update = select("draft a bail application for my client")
        assert "can't draft court filings such as a bail application" in update["answer"]
        assert "**list of dates**" in update["answer"]

    def test_supported_drafts_still_route(self):
        assert select("draft a list of dates for OS 12/2026")["intent"] == "propose_draft"

    @pytest.mark.parametrize(
        "query, kind",
        [
            ("what billings are quite low compared to others?", "fee_ranking"),
            ("which client owes me the most?", "outstanding_by_client"),
            ("which of my cases is the oldest pending one?", "case_age"),
            ("am I busier this week or next week?", "compare_periods"),
        ],
    )
    def test_comparisons_route_to_a_comparison(self, query, kind):
        update = select(query)
        assert (update["intent"], update["args"]["compare"]) == ("compare", kind)

    def test_a_comparison_it_cannot_make_still_says_so(self):
        assert select("which judge is the strictest compared to others?")["answer"].startswith("I can't compare or rank")

    def test_the_most_recent_hearing_is_not_a_comparison(self):
        assert select("add a fee of 5000 for the most recent hearing in OS 12/2026")["intent"] == "propose_fee_create"

    def test_tasks_mark_paid_bulk_billing_are_cards(self):
        assert select("add a task to file the counter in Rao by Monday")["intent"] == "propose_task"
        assert select("mark INV-0001 as paid")["intent"] == "propose_mark_paid"
        assert select("bill all my hearings from last week")["intent"] == "propose_bulk_fees"
        assert select("send all unpaid invoices")["intent"] == "propose_bulk_send"


class TestNoKeywordHijacking:
    def test_talking_points_are_the_hearing_brief(self):
        update = select(
            "I need talking points for all the hearings that I have in the next few days. "
            "prepare me a document containing all that"
        )
        assert update["intent"] == "practice_report"
        assert update["args"]["report_kind"] == "brief"
        assert update["args"]["period"] == (TODAY, TODAY + timedelta(days=6))
        assert update["notes"] == []

    def test_a_pdf_of_statuses_and_talking_points_is_not_the_cases_report(self):
        update = select("gimme case statuses and talking points for each hearing separately. I'd like it in a PDF doc")
        assert update["args"]["report_kind"] == "brief"

    def test_tomorrows_brief(self):
        update = select("prepare a one page brief for tomorrow's matters")
        assert update["args"]["period"] == (TODAY + timedelta(days=1),) * 2

    def test_earnings_are_the_billing_report(self):
        update = select("how much did I earn this month?")
        assert (update["intent"], update["args"]) == ("practice_report", {"report_kind": "billing"})

    def test_fee_bump_by_an_amount_is_an_update(self):
        assert select("bump the Rao fee up by 2k")["intent"] == "propose_fee_update"


class TestSecondHalfIsNamed:
    def test_email_clients_is_named_not_dropped(self):
        update = select("list my hearings this week and email the clients about them")
        assert update["intent"] == "calendar"
        assert len(update["notes"]) == 1
        assert '("email the clients about them")' in update["notes"][0]
        assert boundaries.EMAIL_NOT_YET in update["notes"][0]

    def test_a_format_request_stays_with_its_request(self):
        assert boundaries.split_request("show hearings tomorrow and give it to me as a pdf") == [
            "show hearings tomorrow and give it to me as a pdf"
        ]

    def test_party_names_and_draft_instructions_are_not_split(self):
        assert boundaries.split_request("rao and state next date") == ["rao and state next date"]
        assert len(boundaries.split_request("draft a client letter for rao and tell him the next date")) == 1

    def test_present_appends_notes(self):
        state = {"answer": "", "summary": None, "notes": ["Note one."]}
        assert practice_nodes.present({**state, "answer": "Answer."})["answer"] == "Answer.\n\nNote one."


class TestEverydayPhrasing:
    @pytest.mark.parametrize(
        "query, expected",
        [
            ("what do I have coming up?", (TODAY, TODAY + timedelta(days=6))),
            ("hearngs tmrw", (TODAY + timedelta(days=1), TODAY + timedelta(days=1))),
            ("what happened in court last week?", (TODAY - timedelta(days=7), TODAY - timedelta(days=1))),
            ("hearings yesterday", (TODAY - timedelta(days=1), TODAY - timedelta(days=1))),
        ],
    )
    def test_calendar_phrasings(self, query, expected):
        update = select(query)
        assert update["intent"] == "calendar"
        assert (update["args"]["date_from"], update["args"]["date_to"]) == expected

    def test_a_case_named_the_way_people_say_it(self):
        update = select("rao case next date pls")
        assert (update["intent"], update["args"]) == ("case_facts", {"case_text": "rao"})

    def test_which_case_is_not_a_case_name(self):
        assert boundaries.named_case_text("which case has the next date tomorrow") is None

    def test_attention_and_focus(self):
        assert select("which cases need my attention and why?")["intent"] == "attention"
        assert select("what should I focus on today?")["intent"] == "today_focus"


class TestRelativeFeeChange:
    def fee(self, amount):
        return SimpleNamespace(amount=Decimal(amount), category="appearance", notes="", invoice_number="")

    def test_up_by(self):
        assert actions.proposed_changes(self.fee("15000"), "bump the Rao fee up by 2k") == {"amount": "17000.00"}

    def test_down_by(self):
        assert actions.proposed_changes(self.fee("15000"), "reduce the Rao fee by 500") == {"amount": "14500.00"}

    def test_a_cut_below_zero_proposes_nothing(self):
        assert actions.proposed_changes(self.fee("1000"), "reduce the fee by 5000") == {}

    def test_a_new_amount_is_absolute(self):
        assert parsing.parse_amount_change("change the Rao fee to 20000") == 0


class TestModelWaitIsBounded:
    def test_ollama_with_a_timeout_makes_one_attempt(self):
        from core.services.ollama_llm_client import OllamaLLMClient

        client = OllamaLLMClient.__new__(OllamaLLMClient)
        client.model = "m"
        client._client = MagicMock()
        client._client.chat.side_effect = ConnectionError("down")
        with patch("core.services.ollama_llm_client.time.sleep") as sleep, pytest.raises(ConnectionError):
            client.generate([{"role": "user", "content": "x"}], timeout=6)
        assert client._client.chat.call_count == 1
        sleep.assert_not_called()

    def test_unplaceable_text_waits_at_most_the_classifier_budget(self, settings):
        settings.PRACTICE_CLASSIFIER_TIMEOUT_SECONDS = 0.2
        llm = MagicMock()
        llm.generate.side_effect = lambda *a, **k: __import__("time").sleep(3)
        started = datetime.now()
        with patch.object(practice_nodes, "get_llm_client", return_value=llm):
            proposal = practice_nodes._classify_with_model("kal kya hai", date(2026, 11, 12))
        assert proposal is None
        assert (datetime.now() - started).total_seconds() < 2
