"""The practice assistant API: GET /api/practice-assistant/overview/ and
POST /api/practice-assistant/chat/.

No model is ever called: `get_llm_client` (as the practice nodes see it) is
patched in every test, and by default it fails the test if it is reached, so
a deterministic route that drifts to the classifier shows up here.
"""

import json
import logging
import uuid
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import Case, CaseEvent, Conversation, Hearing, Message, Task
from core.services.ai_workflow import AIWorkflowService
from core.services.graph import practice_nodes
from core.services.india_time import INDIA_TZ
from core.services.practice_assistant import answers, reads
from core.views import chat as chat_view

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 11, 11, 10, 0, tzinfo=INDIA_TZ)
TODAY = date(2026, 11, 11)
OVERVIEW_URL = "/api/practice-assistant/overview/"
CHAT_URL = "/api/practice-assistant/chat/"

CHIP_OVERVIEW = "Give me an overview of my practice."
CHIP_CALENDAR = "What is on my calendar this week?"
CHIP_DEADLINES = "What deadlines are open?"
CHIP_MISSING = "Which cases have no next date?"


def utc_day(year, month, day):
    """A hearing as eCourts stores it: 00:00 UTC of the date (untimed)."""
    return datetime(year, month, day, tzinfo=dt_timezone.utc)


def rid():
    return str(uuid.uuid4())


def as_json(value):
    return json.loads(json.dumps(value))


@pytest.fixture(autouse=True)
def enabled(settings):
    settings.PRACTICE_ASSISTANT_ENABLED = True


@pytest.fixture(autouse=True)
def clock():
    with patch("core.views.practice_assistant.india_now", return_value=NOW):
        yield


@pytest.fixture(autouse=True)
def no_llm():
    """Reaching the model in a test that did not ask for one is a failure."""
    with patch.object(
        practice_nodes, "get_llm_client", side_effect=AssertionError("the model was reached")
    ) as factory:
        yield factory


def fake_llm(*, returns=None, raises=None):
    llm = MagicMock()
    if raises is not None:
        llm.generate.side_effect = raises
    else:
        llm.generate.return_value = returns
    return patch.object(practice_nodes, "get_llm_client", return_value=llm), llm


@pytest.fixture
def anil():
    return User.objects.create_user(username="practice-anil", password="pw-12345")


@pytest.fixture
def api(anil):
    client = APIClient()
    client.force_authenticate(user=anil)
    return client


@pytest.fixture
def practice(anil):
    """Three cases (two active), one upcoming hearing, three open tasks (one
    overdue, one undated), one completed task, one event."""
    rao = Case.objects.create(owner=anil, title="Rao vs State", case_number="OS/101/2026")
    mehta = Case.objects.create(owner=anil, title="Mehta vs Union", case_number="OS/102/2026")
    old = Case.objects.create(owner=anil, title="Old Matter", case_number="OS/9/2019", status="closed")
    for case in (rao, mehta, old):
        case.refresh_from_db()
    hearing = Hearing.objects.create(
        owner=anil, case=rao, hearing_date=utc_day(2026, 11, 12), hearing_type="other", purpose="Arguments"
    )
    overdue = Task.objects.create(owner=anil, case=rao, title="File counter", due_date=date(2026, 11, 10))
    loose = Task.objects.create(owner=anil, case=None, title="Renew bar card", due_date=date(2026, 11, 13))
    undated = Task.objects.create(owner=anil, case=mehta, title="Call client")
    Task.objects.create(
        owner=anil, case=rao, title="Done already", due_date=date(2026, 11, 12), status=Task.STATUS_COMPLETED
    )
    event = CaseEvent.objects.create(owner=anil, case=mehta, title="Mediation", date=date(2026, 11, 12))
    return {
        "rao": rao,
        "mehta": mehta,
        "old": old,
        "hearing": hearing,
        "overdue": overdue,
        "loose": loose,
        "undated": undated,
        "event": event,
    }


def ask(api, query, **extra):
    body = {"query": query, "client_request_id": rid(), **extra}
    return api.post(CHAT_URL, body, format="json")


def source_keys(turn):
    return {(ref["kind"], ref["id"]) for ref in turn["sources"]}


# ---------------------------------------------------------------------------
# Flag and auth
# ---------------------------------------------------------------------------


class TestFlagAndAuth:
    def test_flag_off_is_404_on_both(self, api, settings, practice):
        settings.PRACTICE_ASSISTANT_ENABLED = False
        assert api.get(OVERVIEW_URL).status_code == 404
        resp = ask(api, CHIP_OVERVIEW)
        assert resp.status_code == 404
        assert not Conversation.objects.exists()

    def test_anonymous_is_refused(self):
        client = APIClient()
        assert client.get(OVERVIEW_URL).status_code in (401, 403)
        body = {"query": "q", "client_request_id": "x"}
        assert client.post(CHAT_URL, body, format="json").status_code in (401, 403)


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


class TestOverview:
    def test_defaults_to_india_today_plus_six_days(self, api, anil, practice):
        resp = api.get(OVERVIEW_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert set(data) == {"portfolio", "calendar"}
        assert data["calendar"]["date_from"] == "2026-11-11"
        assert data["calendar"]["date_to"] == "2026-11-17"
        assert data["calendar"] == as_json(
            reads.calendar_window(owner=anil, date_from=TODAY, date_to=TODAY + timedelta(days=6), now=NOW)
        )
        assert data["portfolio"] == as_json(reads.portfolio_snapshot(owner=anil, page=1, now=NOW))
        assert data["portfolio"]["total_cases"] == 3
        assert data["portfolio"]["active_cases"] == 2
        assert data["portfolio"]["active_without_next_date"] == 1
        # hearing 12th, completed task 12th, event 12th, task 13th
        assert data["calendar"]["total"] == 4

    def test_explicit_range(self, api, practice):
        data = api.get(OVERVIEW_URL, {"from": "2026-11-10", "to": "2026-11-10"}).json()
        assert data["calendar"]["date_from"] == data["calendar"]["date_to"] == "2026-11-10"
        assert [e["id"] for e in data["calendar"]["entries"]] == [practice["overdue"].id]

    def test_from_alone_gets_a_week(self, api):
        data = api.get(OVERVIEW_URL, {"from": "2026-12-01"}).json()
        assert data["calendar"]["date_to"] == "2026-12-07"

    def test_31_days_is_allowed_and_32_is_not(self, api):
        assert api.get(OVERVIEW_URL, {"from": "2026-11-01", "to": "2026-12-01"}).status_code == 200
        resp = api.get(OVERVIEW_URL, {"from": "2026-11-01", "to": "2026-12-02"})
        assert resp.status_code == 400
        assert "31 days" in resp.json()["detail"]

    @pytest.mark.parametrize(
        "params",
        [
            {"from": "11-11-2026"},
            {"from": "2026-11-11", "to": "tomorrow"},
            {"from": "2026-02-30"},
            {"from": "2026-11-12", "to": "2026-11-11"},
            {"case_page": "0"},
            {"case_page": "-1"},
            {"case_page": "two"},
        ],
    )
    def test_bad_input_is_400_with_a_detail(self, api, params):
        resp = api.get(OVERVIEW_URL, params)
        assert resp.status_code == 400
        assert resp.json()["detail"]

    def test_case_page(self, api, anil):
        for index in range(reads.PAGE_SIZE + 2):
            Case.objects.create(owner=anil, title=f"Matter {index}", case_number=f"OS/{index + 1}/2025")
        first = api.get(OVERVIEW_URL).json()["portfolio"]
        second = api.get(OVERVIEW_URL, {"case_page": 2}).json()["portfolio"]
        assert first["page"] == 1 and len(first["cases"]) == reads.PAGE_SIZE
        assert second["page"] == 2 and len(second["cases"]) == 2
        assert second["total"] == reads.PAGE_SIZE + 2
        assert not {c["id"] for c in first["cases"]} & {c["id"] for c in second["cases"]}


# ---------------------------------------------------------------------------
# Deterministic intents
# ---------------------------------------------------------------------------


class TestDeterministicIntents:
    def test_turn_shape_and_persistence(self, api, anil, practice):
        resp = ask(api, CHIP_OVERVIEW)
        assert resp.status_code == 200
        turn = resp.json()
        assert set(turn) == {
            "conversation_id", "user_message_id", "assistant_message_id", "answer", "intent",
            "status", "sources", "summary", "case_candidates", "action_card", "report", "as_of",
        }
        assert turn["as_of"] == NOW.isoformat()
        assert turn["action_card"] is None and turn["case_candidates"] == []

        conversation = Conversation.objects.get(id=turn["conversation_id"])
        assert conversation.owner == anil
        assert conversation.scope == Conversation.SCOPE_PRACTICE
        assert conversation.case_id is None
        assert conversation.title == "Give me an overview of my practice."
        assert conversation.last_message_at is not None
        user_message = Message.objects.get(id=turn["user_message_id"])
        assistant = Message.objects.get(id=turn["assistant_message_id"])
        assert (user_message.owner, user_message.role, user_message.content) == (anil, "user", CHIP_OVERVIEW)
        assert (assistant.owner, assistant.role, assistant.content) == (anil, "assistant", turn["answer"])
        assert assistant.references == turn["sources"]

    def test_overview(self, api, anil, practice):
        turn = ask(api, CHIP_OVERVIEW).json()
        assert (turn["intent"], turn["status"]) == ("overview", "answer")
        assert turn["summary"] == as_json(reads.portfolio_snapshot(owner=anil, page=1, now=NOW))
        assert "**3 cases** recorded (2 open, 1 closed)" in turn["answer"]
        assert "2 cases are active" in turn["answer"]
        assert "1 with a scheduled next hearing recorded and 1 with none recorded" in turn["answer"]
        assert "11 Nov 2026, 10:00 IST" in turn["answer"]
        assert source_keys(turn) == {("case", practice[k].id) for k in ("rao", "mehta", "old")}

    def test_overview_with_no_cases(self, api):
        turn = ask(api, CHIP_OVERVIEW).json()
        assert turn["status"] == "answer"
        assert "no cases are recorded in Case Intel" in turn["answer"]
        assert turn["sources"] == []

    def test_calendar_week(self, api, anil, practice):
        turn = ask(api, CHIP_CALENDAR).json()
        assert (turn["intent"], turn["status"]) == ("calendar", "answer")
        assert turn["summary"] == as_json(
            reads.calendar_window(owner=anil, date_from=TODAY, date_to=date(2026, 11, 17), now=NOW)
        )
        assert turn["summary"]["total"] == 4
        assert "From 11 Nov 2026 to 17 Nov 2026 (India dates)" in turn["answer"]
        assert "Case Intel has **1 hearing, 2 tasks and 1 event**." in turn["answer"]
        assert "12 Nov 2026: Hearing, Arguments, Rao vs State (scheduled)" in turn["answer"]
        assert ("hearing", practice["hearing"].id) in source_keys(turn)
        assert ("event", practice["event"].id) in source_keys(turn)
        assert ("task", practice["loose"].id) in source_keys(turn)
        assert ("task", practice["overdue"].id) not in source_keys(turn)  # due the 10th

    @pytest.mark.parametrize(
        "query, date_from, date_to",
        [
            ("Any hearings today?", "2026-11-11", "2026-11-11"),
            ("what is my schedule tomorrow", "2026-11-12", "2026-11-12"),
            ("Show the calendar for next week", "2026-11-18", "2026-11-24"),
            ("calendar from 2026-11-20 to 2026-11-22", "2026-11-20", "2026-11-22"),
            ("my agenda", "2026-11-11", "2026-11-17"),
        ],
    )
    def test_calendar_keyword_ranges(self, api, query, date_from, date_to):
        turn = ask(api, query).json()
        assert turn["intent"] == "calendar"
        assert (turn["summary"]["date_from"], turn["summary"]["date_to"]) == (date_from, date_to)

    def test_empty_calendar_says_none_recorded(self, api):
        turn = ask(api, "Any hearings today?").json()
        assert turn["status"] == "answer"
        assert turn["answer"].startswith(
            "No hearings, tasks or events are recorded in Case Intel for 11 Nov 2026"
        )
        assert turn["sources"] == []

    def test_a_typed_range_over_31_days_asks_for_a_shorter_one(self, api):
        turn = ask(api, "calendar from 2026-11-01 to 2026-12-31").json()
        assert (turn["intent"], turn["status"]) == ("calendar", "needs_clarification")
        assert turn["answer"] == answers.RANGE_TOO_LONG
        assert turn["summary"] is None

    def test_selected_day_turn_is_the_calendar_read_for_that_day(self, api, anil, practice):
        turn = ask(api, "What is on Thursday, 12 November 2026?", selected_day="2026-11-12").json()
        assert (turn["intent"], turn["status"]) == ("calendar", "answer")
        day = date(2026, 11, 12)
        assert turn["summary"] == as_json(reads.calendar_window(owner=anil, date_from=day, date_to=day, now=NOW))
        assert turn["summary"]["total"] == 3
        assert "On 12 Nov 2026 (India dates)" in turn["answer"]
        # ...and it is what the overview shows for that day.
        overview = api.get(OVERVIEW_URL, {"from": "2026-11-12", "to": "2026-11-12"}).json()
        assert overview["calendar"]["entries"] == turn["summary"]["entries"]

    def test_selected_day_does_not_capture_an_unrelated_question(self, api, practice):
        turn = ask(api, CHIP_DEADLINES, selected_day="2026-11-12").json()
        assert turn["intent"] == "open_deadlines"

    def test_open_deadlines(self, api, anil, practice):
        turn = ask(api, CHIP_DEADLINES).json()
        assert (turn["intent"], turn["status"]) == ("open_deadlines", "answer")
        assert turn["summary"] == as_json(reads.open_deadlines(owner=anil, now=NOW))
        assert turn["summary"]["total"] == 3
        assert "**3 open tasks** recorded, **1 overdue**" in turn["answer"]
        assert "Due 10 Nov 2026 (overdue): File counter, Rao vs State" in turn["answer"]
        assert "No due date recorded: Call client, Mehta vs Union" in turn["answer"]
        assert source_keys(turn) == {("task", practice[k].id) for k in ("overdue", "loose", "undated")}

    def test_open_deadlines_empty(self, api):
        turn = ask(api, "anything overdue?").json()
        assert turn["intent"] == "open_deadlines"
        assert turn["answer"] == "No open tasks or deadlines are recorded in Case Intel."

    def test_missing_next_date(self, api, practice):
        turn = ask(api, CHIP_MISSING).json()
        assert (turn["intent"], turn["status"]) == ("missing_next_date", "answer")
        assert turn["summary"]["active_cases"] == 2
        assert turn["summary"]["active_without_next_date"] == 1
        assert [row["id"] for row in turn["summary"]["cases"]] == [practice["mehta"].id]
        assert turn["summary"]["truncated"] is False
        assert "1 of your 2 active cases has no scheduled next hearing recorded in Case Intel" in turn["answer"]
        assert "Mehta vs Union" in turn["answer"] and "Old Matter" not in turn["answer"]
        assert source_keys(turn) == {("case", practice["mehta"].id)}

    def test_missing_next_date_keyword_variants(self, api, practice):
        for query in ("cases without a next hearing date", "which matters are missing dates"):
            assert ask(api, query).json()["intent"] == "missing_next_date"

    def test_case_facts_with_a_verified_case_id(self, api, anil, practice):
        rao = practice["rao"]
        turn = ask(api, "Rao vs State", case_id=rao.id).json()
        assert (turn["intent"], turn["status"]) == ("case_facts", "answer")
        assert turn["summary"] == as_json(reads.case_facts(owner=anil, case_id=rao.id, now=NOW))
        assert "Next hearing recorded: 12 Nov 2026 (Arguments)." in turn["answer"]
        assert "Open tasks recorded: 1." in turn["answer"]
        assert "No upcoming events are recorded in Case Intel for this case." in turn["answer"]
        assert source_keys(turn) == {
            ("case", rao.id), ("hearing", practice["hearing"].id), ("task", practice["overdue"].id)
        }

    def test_case_facts_never_invents_a_next_date(self, api, practice):
        turn = ask(api, "Mehta vs Union", case_id=practice["mehta"].id).json()
        assert "No scheduled next hearing is recorded in Case Intel for this case." in turn["answer"]
        assert "Next hearing recorded" not in turn["answer"]

    @pytest.mark.parametrize(
        "query, intent",
        [
            ("How much is unpaid across my cases?", "billing_summary"),
            ("Send the invoice for Rao", "propose_invoice_send"),
        ],
    )
    def test_billing_is_not_available_yet_and_has_no_action_card(self, api, practice, settings, query, intent):
        settings.PRACTICE_INVOICE_ACTIONS_ENABLED = False
        turn = ask(api, query).json()
        assert (turn["intent"], turn["status"]) == (intent, "needs_clarification")
        assert turn["answer"] == answers.BILLING_NOT_AVAILABLE
        assert turn["action_card"] is None
        assert turn["summary"] is None and turn["sources"] == []


# ---------------------------------------------------------------------------
# The classifier path (a fake model)
# ---------------------------------------------------------------------------


class TestClassifier:
    QUESTION = "how are things looking"

    def test_valid_json_routes_to_the_intent(self, api, anil, practice):
        patcher, llm = fake_llm(returns='{"intent": "open_deadlines"}')
        with patcher:
            turn = ask(api, self.QUESTION).json()
        assert (turn["intent"], turn["status"]) == ("open_deadlines", "answer")
        assert turn["summary"]["total"] == 3
        assert llm.generate.call_count == 1
        assert llm.generate.call_args.kwargs["timeout"] == 6

    def test_fenced_json_with_dates(self, api, practice):
        raw = '```json\n{"intent": "calendar", "date_from": "2026-11-12", "date_to": "2026-11-13"}\n```'
        patcher, _ = fake_llm(returns=raw)
        with patcher:
            turn = ask(api, self.QUESTION).json()
        assert turn["intent"] == "calendar"
        assert (turn["summary"]["date_from"], turn["summary"]["date_to"]) == ("2026-11-12", "2026-11-13")

    @pytest.mark.parametrize(
        "raw",
        [
            "not json at all",
            "[1, 2]",
            '{"intent": "delete_everything"}',
            '{"intent": "none"}',
            '{"intent": "calendar", "date_from": "next tuesday"}',
            "",
        ],
    )
    def test_unusable_output_asks_for_clarification(self, api, practice, raw):
        patcher, llm = fake_llm(returns=raw)
        with patcher:
            resp = ask(api, self.QUESTION)
        assert resp.status_code == 200
        turn = resp.json()
        assert (turn["intent"], turn["status"]) == (None, "needs_clarification")
        assert turn["answer"] == answers.FALLBACK_CLARIFICATION
        assert turn["summary"] is None and turn["sources"] == []
        assert llm.generate.call_count == 1  # never retried

    def test_a_timeout_asks_for_clarification(self, api, practice):
        patcher, llm = fake_llm(raises=TimeoutError("provider hung"))
        with patcher:
            resp = ask(api, self.QUESTION)
        assert resp.status_code == 200
        assert resp.json()["status"] == "needs_clarification"
        assert llm.generate.call_count == 1
        assert Message.objects.count() == 2  # the clarification is a stored turn

    def test_a_client_that_cannot_be_built_asks_for_clarification(self, api, no_llm):
        no_llm.side_effect = ConnectionError("ollama is down")
        resp = ask(api, self.QUESTION)
        assert resp.status_code == 200
        assert resp.json()["answer"] == answers.FALLBACK_CLARIFICATION

    def test_a_range_over_31_days_from_the_model_is_refused(self, api, practice):
        raw = '{"intent": "calendar", "date_from": "2026-11-01", "date_to": "2026-12-31"}'
        patcher, _ = fake_llm(returns=raw)
        with patcher:
            turn = ask(api, self.QUESTION).json()
        assert turn["status"] == "needs_clarification"
        assert turn["answer"] == answers.RANGE_TOO_LONG

    def test_billing_from_the_model_gets_no_action_card(self, api, practice, settings):
        settings.PRACTICE_INVOICE_ACTIONS_ENABLED = False
        raw = json.dumps(
            {"intent": "propose_invoice_send", "action_card": {"kind": "send_invoice", "fee_id": 1}}
        )
        patcher, _ = fake_llm(returns=raw)
        with patcher:
            turn = ask(api, self.QUESTION).json()
        assert turn["answer"] == answers.BILLING_NOT_AVAILABLE
        assert turn["action_card"] is None

    def test_ids_and_owners_in_model_output_are_ignored(self, api, practice):
        other = User.objects.create_user(username="practice-other", password="pw-12345")
        theirs = Case.objects.create(owner=other, title="Secret vs Hidden", case_number="OS/7/2026")
        raw = json.dumps(
            {"intent": "case_facts", "case_id": theirs.id, "owner": other.id, "case_text": "Secret vs Hidden"}
        )
        patcher, _ = fake_llm(returns=raw)
        with patcher:
            turn = ask(api, self.QUESTION).json()
        assert (turn["intent"], turn["status"]) == ("case_facts", "needs_clarification")
        assert turn["answer"] == answers.CASE_NOT_FOUND
        assert turn["case_candidates"] == [] and turn["summary"] is None


# ---------------------------------------------------------------------------
# The case chooser
# ---------------------------------------------------------------------------


class TestCaseChooser:
    def test_text_then_candidates_then_case_id_then_facts(self, api, anil, practice):
        patcher, _ = fake_llm(returns='{"intent": "case_facts", "case_text": "Rao"}')
        with patcher:
            first = ask(api, "what is happening in Rao vs State").json()
        assert (first["intent"], first["status"]) == ("case_facts", "needs_clarification")
        assert first["answer"] == answers.CHOOSE_CASE
        assert [c["id"] for c in first["case_candidates"]] == [practice["rao"].id]
        assert first["summary"] is None and first["sources"] == []

        picked = first["case_candidates"][0]
        second = ask(
            api,
            f"{picked['title']} {picked['case_number']}",
            case_id=picked["id"],
            conversation_id=first["conversation_id"],
        ).json()
        assert (second["intent"], second["status"]) == ("case_facts", "answer")
        assert second["conversation_id"] == first["conversation_id"]
        assert second["summary"]["case"]["id"] == practice["rao"].id

    def test_a_single_title_match_is_still_a_chooser(self, api, practice):
        patcher, _ = fake_llm(returns='{"intent": "case_facts", "case_text": "Rao vs State"}')
        with patcher:
            turn = ask(api, "tell me about Rao vs State").json()
        assert turn["status"] == "needs_clarification"
        assert len(turn["case_candidates"]) == 1

    def test_an_exact_case_number_typed_by_the_advocate_answers_directly(self, api, practice):
        number = practice["rao"].case_number
        turn = ask(api, f"Status of {number}").json()
        assert (turn["intent"], turn["status"]) == ("case_facts", "answer")
        assert turn["summary"]["case"]["id"] == practice["rao"].id
        assert turn["case_candidates"] == []

    def test_an_exact_cnr_typed_by_the_advocate_answers_directly(self, api, practice):
        Case.objects.filter(id=practice["mehta"].id).update(cnr_number="TSHC010012342026")
        turn = ask(api, "where does TSHC010012342026 stand").json()
        assert (turn["intent"], turn["status"]) == ("case_facts", "answer")
        assert turn["summary"]["case"]["id"] == practice["mehta"].id

    def test_a_case_number_only_the_model_produced_is_a_chooser(self, api, practice):
        number = practice["rao"].case_number
        patcher, _ = fake_llm(returns=json.dumps({"intent": "case_facts", "case_text": number}))
        with patcher:
            turn = ask(api, "that matter from last month").json()
        assert turn["status"] == "needs_clarification"
        assert [c["id"] for c in turn["case_candidates"]] == [practice["rao"].id]

    def test_no_match_says_so(self, api, practice):
        turn = ask(api, "Status of WP/555/2020").json()
        assert (turn["intent"], turn["status"]) == ("case_facts", "needs_clarification")
        assert turn["answer"] == answers.CASE_NOT_FOUND

    def test_an_unknown_case_id_is_404_and_stores_nothing(self, api, practice):
        resp = ask(api, "x", case_id=practice["rao"].id + 10_000)
        assert resp.status_code == 404
        assert not Message.objects.exists()


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


class TestConversations:
    def test_a_practice_conversation_continues(self, api, practice):
        first = ask(api, CHIP_OVERVIEW).json()
        second = ask(api, CHIP_DEADLINES, conversation_id=first["conversation_id"]).json()
        assert second["conversation_id"] == first["conversation_id"]
        assert Conversation.objects.count() == 1
        assert Message.objects.filter(conversation_id=first["conversation_id"]).count() == 4
        assert Conversation.objects.get().title == "Give me an overview of my practice."

    def test_case_legacy_and_missing_conversations_are_the_same_404(self, api, anil, practice):
        case_chat = Conversation.objects.create(owner=anil, case=practice["rao"], title="case")
        legacy = Conversation.objects.create(owner=anil, title="legacy")
        details = set()
        for conversation_id in (case_chat.id, legacy.id, legacy.id + 10_000):
            resp = ask(api, CHIP_OVERVIEW, conversation_id=conversation_id)
            assert resp.status_code == 404
            details.add(resp.json()["detail"].replace(str(conversation_id), "N"))
        assert details == {"Conversation with id N does not exist."}
        assert not Message.objects.exists()

    def test_the_old_chat_endpoint_refuses_a_practice_conversation(self, api, practice):
        turn = ask(api, CHIP_OVERVIEW).json()
        graph = MagicMock()
        with patch.object(chat_view._ai_service, "_graph", graph):
            resp = api.post(
                "/api/chat/", {"query": "q", "conversation_id": turn["conversation_id"]}, format="json"
            )
        assert resp.status_code == 404
        graph.invoke.assert_not_called()
        assert Message.objects.filter(conversation_id=turn["conversation_id"]).count() == 2

    def test_the_old_pipeline_itself_refuses_a_practice_conversation(self, anil):
        practice_chat = Conversation.objects.create(owner=anil, scope=Conversation.SCOPE_PRACTICE)
        legacy = Conversation.objects.create(owner=anil, title="legacy")
        with pytest.raises(Conversation.DoesNotExist):
            AIWorkflowService._get_or_create_conversation(practice_chat.id, None, "q", anil)
        service = AIWorkflowService(llm=MagicMock(), search_service=MagicMock())
        service._graph = MagicMock()
        with pytest.raises(Conversation.DoesNotExist):
            service.process_query("q", anil, conversation_id=practice_chat.id)
        service._graph.invoke.assert_not_called()
        assert not Message.objects.filter(conversation=practice_chat).exists()
        assert AIWorkflowService._get_or_create_conversation(legacy.id, None, "q", anil) == legacy

    def test_history_returns_the_practice_messages_with_references(self, api, practice):
        turn = ask(api, CHIP_DEADLINES).json()
        resp = api.get(f"/api/conversations/{turn['conversation_id']}/messages/")
        assert resp.status_code == 200
        rows = resp.json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        assert [row["role"] for row in rows] == ["user", "assistant"]
        assert [row["id"] for row in rows] == [turn["user_message_id"], turn["assistant_message_id"]]
        assert rows[1]["content"] == turn["answer"]
        assert rows[1]["references"] == turn["sources"] and len(rows[1]["references"]) == 3
        assert [item["kind"] for item in rows[0]["references"]] == ["practice_request"]

        listed = api.get("/api/conversations/?scope=practice").json()
        listed = listed["results"] if isinstance(listed, dict) else listed
        assert [row["id"] for row in listed] == [turn["conversation_id"]]


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


class TestReplay:
    def test_the_same_request_id_returns_the_stored_turn_and_writes_nothing(self, api, anil, practice):
        body = {"query": CHIP_CALENDAR, "client_request_id": rid()}
        first = api.post(CHAT_URL, body, format="json").json()
        # The data changes; a replay still returns what was stored.
        Task.objects.create(owner=anil, title="New since", due_date=date(2026, 11, 12))
        again = api.post(CHAT_URL, body, format="json")
        assert again.status_code == 200
        assert again.json() == first
        assert Conversation.objects.count() == 1
        assert Message.objects.count() == 2

        continued = api.post(
            CHAT_URL, {**body, "conversation_id": first["conversation_id"]}, format="json"
        ).json()
        assert continued == first
        assert Message.objects.count() == 2

    def test_a_clarification_replays_without_calling_the_model_again(self, api, practice):
        body = {"query": "how are things looking", "client_request_id": rid()}
        patcher, llm = fake_llm(returns='{"intent": "case_facts", "case_text": "Rao"}')
        with patcher:
            first = api.post(CHAT_URL, body, format="json").json()
            again = api.post(CHAT_URL, body, format="json").json()
        assert again == first
        assert first["case_candidates"]
        assert llm.generate.call_count == 1

    def test_a_new_request_id_is_a_new_turn(self, api, practice):
        first = ask(api, CHIP_OVERVIEW).json()
        second = ask(api, CHIP_OVERVIEW).json()
        assert second["conversation_id"] != first["conversation_id"]
        assert Message.objects.count() == 4

    def test_a_turn_that_raises_stores_nothing_and_can_be_resent(self, anil, practice):
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(user=anil)
        body = {"query": CHIP_OVERVIEW, "client_request_id": rid()}
        with patch.object(reads, "portfolio_snapshot", side_effect=RuntimeError("database went away")):
            failed = client.post(CHAT_URL, body, format="json")
        assert failed.status_code == 500
        assert not Conversation.objects.exists() and not Message.objects.exists()

        resent = client.post(CHAT_URL, body, format="json")
        assert resent.status_code == 200
        assert resent.json()["intent"] == "overview"
        assert Message.objects.count() == 2


# ---------------------------------------------------------------------------
# Request validation, references, logging
# ---------------------------------------------------------------------------


class TestRequestValidation:
    @pytest.mark.parametrize(
        "body",
        [
            {"client_request_id": "abc"},
            {"query": "", "client_request_id": "abc"},
            {"query": "x" * 2001, "client_request_id": "abc"},
            {"query": "q"},
            {"query": "q", "client_request_id": "x" * 65},
            {"query": "q", "client_request_id": "has spaces"},
            {"query": "q", "client_request_id": "abc", "selected_day": "12/11/2026"},
            {"query": "q", "client_request_id": "abc", "conversation_id": "five"},
            {"query": "q", "client_request_id": "abc", "case_id": 0},
        ],
    )
    def test_bad_bodies_are_400_and_store_nothing(self, api, body):
        assert api.post(CHAT_URL, body, format="json").status_code == 400
        assert not Message.objects.exists()

    def test_scope_owner_and_as_of_in_the_body_are_ignored(self, api, anil, practice):
        other = User.objects.create_user(username="practice-other", password="pw-12345")
        turn = ask(
            api, CHIP_OVERVIEW, scope="firm", owner=other.id, as_of="2020-01-01T00:00:00+05:30"
        ).json()
        assert turn["as_of"] == NOW.isoformat()
        assert turn["summary"]["total_cases"] == 3
        assert Conversation.objects.get().owner == anil


class TestValidateReferences:
    def test_sources_outside_the_read_result_are_dropped(self, anil, practice):
        summary = reads.open_deadlines(owner=anil, now=NOW)
        real = summary["entries"][0]["ref"]
        state = {
            "summary": summary,
            "sources": [
                real,
                {"kind": "task", "id": 999_999, "case_id": None, "label": "made up", "recorded_at": None},
                {**real, "label": "relabelled"},
                {"kind": "fee", "id": real["id"], "case_id": None, "label": "x", "recorded_at": None},
                "not a reference",
            ],
        }
        assert practice_nodes.validate_references(state) == {"sources": [real]}

    def test_sources_are_capped(self, api, anil):
        for index in range(answers.MAX_SOURCES + 5):
            Task.objects.create(owner=anil, title=f"Task {index}", due_date=date(2026, 11, 20))
        turn = ask(api, CHIP_DEADLINES).json()
        assert turn["summary"]["total"] == answers.MAX_SOURCES + 5
        assert len(turn["sources"]) == answers.MAX_SOURCES
        assert "...and 5 more." in turn["answer"]


class TestLogging:
    def test_logs_carry_no_question_or_answer_text(self, api, practice):
        records = []

        class Collect(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = Collect(level=logging.DEBUG)
        core_logger = logging.getLogger("core")  # does not propagate: attach here
        previous = core_logger.level
        core_logger.addHandler(handler)
        core_logger.setLevel(logging.DEBUG)
        try:
            patcher, _ = fake_llm(returns="zebra-output-not-json")
            with patcher:
                turn = ask(api, "zebra-question about my quokka matter").json()
            ask(api, CHIP_DEADLINES)
        finally:
            core_logger.removeHandler(handler)
            core_logger.setLevel(previous)

        text = "\n".join(records)
        assert "Practice turn:" in text and "intent=open_deadlines" in text
        assert "zebra" not in text and "quokka" not in text
        assert "File counter" not in text
        assert turn["answer"] not in text
