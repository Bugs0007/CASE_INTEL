"""The practice assistant's fee action cards: add, change, invoice, delete.

The graph never writes. Each test asks a question, reads the card, and checks
that no fee row changed. `get_llm_client` is patched so any model call fails
the test unless a test asks for a fake one.
"""

import json
import uuid
from datetime import datetime
from datetime import timezone as dt_timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import AdvocateProfile, AppearanceFee, Case, Hearing
from core.services.graph import practice_nodes
from core.services.india_time import INDIA_TZ

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 11, 11, 10, 0, tzinfo=INDIA_TZ)
CHAT_URL = "/api/practice-assistant/chat/"


def rid():
    return str(uuid.uuid4())


@pytest.fixture(autouse=True)
def flags(settings):
    settings.PRACTICE_ASSISTANT_ENABLED = True
    settings.PRACTICE_INVOICE_ACTIONS_ENABLED = True
    settings.CASE_DRAFTING_ENABLED = True


@pytest.fixture(autouse=True)
def clock():
    with patch("core.views.practice_assistant.india_now", return_value=NOW):
        yield


@pytest.fixture(autouse=True)
def no_llm():
    with patch.object(
        practice_nodes, "get_llm_client", side_effect=AssertionError("the model was reached")
    ) as factory:
        yield factory


@pytest.fixture
def anil(db):
    return User.objects.create_user(username="act-anil", password="pw-12345")


@pytest.fixture
def other(db):
    return User.objects.create_user(username="act-other", password="pw-12345")


@pytest.fixture
def api(anil):
    client = APIClient()
    client.force_authenticate(user=anil)
    return client


def day(y, m, d):
    return datetime(y, m, d, tzinfo=dt_timezone.utc)


def make_case(owner, title, number):
    return Case.objects.create(owner=owner, title=title, case_number=number)


def make_hearing(owner, case, when, **extra):
    return Hearing.objects.create(owner=owner, case=case, hearing_date=when, hearing_type="other", **extra)


def make_fee(owner, hearing, *, status="pending", number="", sent="not_sent", amount="15000", category="appearance"):
    return AppearanceFee.objects.create(
        owner=owner,
        hearing=hearing,
        category=category,
        amount=Decimal(amount),
        status=status,
        invoice_number=number,
        invoice_pdf_path=f"invoices/{number}.pdf" if number else "",
        send_status=sent,
    )


@pytest.fixture
def rao(anil):
    case = make_case(anil, "Rao vs State", "OS/12/2026")
    past = make_hearing(anil, case, day(2026, 11, 5))
    older = make_hearing(anil, case, day(2026, 10, 1))
    upcoming = make_hearing(anil, case, day(2026, 12, 1))
    return {"case": case, "past": past, "older": older, "upcoming": upcoming}


def ask(api, query, **extra):
    resp = api.post(CHAT_URL, {"query": query, "client_request_id": rid(), **extra}, format="json")
    assert resp.status_code == 200, resp.content
    return resp.json()


def snapshot():
    return list(AppearanceFee.objects.order_by("id").values())


# ---------------------------------------------------------------------------
# propose_fee_create
# ---------------------------------------------------------------------------


class TestCreateCard:
    def test_hotel_charge_with_amount_on_a_case_number(self, api, anil, rao):
        before = snapshot()
        turn = ask(api, "Add a hotel fee of Rs 5,000 for OS/12/2026")
        card = turn["action_card"]
        assert (turn["intent"], turn["status"]) == ("propose_fee_create", "answer")
        assert card["kind"] == "create_fee"
        assert (card["case_id"], card["case_title"]) == (rao["case"].id, "Rao vs State")
        assert (card["category"], card["amount"], card["description"]) == ("hotel", "5000.00", "")
        assert card["hearing_id"] == rao["past"].id  # latest past hearing
        assert card["blockers"] == []
        assert [o["id"] for o in card["hearing_options"]] == [
            rao["upcoming"].id, rao["past"].id, rao["older"].id,
        ]
        assert card["hearing_options"][1]["date"] == "2026-11-05"
        assert "Ready to add a hotel charge of Rs. 5,000 on Rao vs State" in turn["answer"]
        assert snapshot() == before  # nothing was written

    def test_amounts_in_every_common_spelling(self, api, anil, rao):
        for text, expected in [
            ("15000", "15000.00"),
            ("Rs. 15,000", "15000.00"),
            ("₹15,000", "15000.00"),
            ("15k", "15000.00"),
            ("1.5 lakh", "150000.00"),
            ("INR 2500", "2500.00"),
        ]:
            turn = ask(api, f"Add a flight charge of {text} for OS/12/2026")
            assert turn["action_card"]["amount"] == expected, text

    def test_date_in_the_question_picks_that_hearing(self, api, anil, rao):
        turn = ask(api, "Add an appearance fee of 12000 for OS/12/2026 for the hearing on 1 Oct 2026")
        assert turn["action_card"]["hearing_id"] == rao["older"].id
        assert turn["action_card"]["blockers"] == []

    def test_date_with_no_hearing_picks_nothing_and_blocks(self, api, anil, rao):
        turn = ask(api, "Add a hotel fee of 3000 for OS/12/2026 on 2026-09-09")
        card = turn["action_card"]
        assert card["hearing_id"] is None
        assert any("No hearing of this case is recorded on 09 Sep 2026" in b for b in card["blockers"])
        assert len(card["hearing_options"]) == 3

    def test_appearance_prefers_a_hearing_with_no_appearance_fee(self, api, anil, rao):
        make_fee(anil, rao["past"])
        turn = ask(api, "Add an appearance fee for OS/12/2026")
        assert turn["action_card"]["hearing_id"] == rao["older"].id

    def test_a_case_with_no_hearing_blocks(self, api, anil):
        make_case(anil, "Empty vs State", "OS/99/2026")
        turn = ask(api, "Add a hotel fee of 4000 for OS/99/2026")
        assert turn["action_card"]["hearing_id"] is None
        assert "This case has no hearing to attach the fee to." in turn["action_card"]["blockers"]
        assert "cannot add" in turn["answer"]

    def test_hotel_without_an_amount_blocks(self, api, anil, rao):
        card = ask(api, "Add a hotel fee for OS/12/2026")["action_card"]
        assert card["amount"] is None
        assert "An amount is needed for this kind of charge." in card["blockers"]

    def test_appearance_without_amount_uses_the_profile_default(self, api, anil, rao):
        blocked = ask(api, "Add an appearance fee for OS/12/2026")["action_card"]
        assert blocked["amount"] is None and blocked["blockers"]
        AdvocateProfile.objects.update_or_create(owner=anil, defaults={"default_fee_amount": Decimal("12000")})
        ok = ask(api, "Add an appearance fee for OS/12/2026")["action_card"]
        assert ok["amount"] is None and ok["blockers"] == []

    def test_party_names_give_a_chooser_then_the_picked_case_completes_the_card(self, api, anil, rao):
        turn = ask(api, "Add a hotel fee of 5000 for Rao vs State")
        assert turn["status"] == "needs_clarification"
        assert turn["action_card"] is None
        assert [c["id"] for c in turn["case_candidates"]] == [rao["case"].id]
        picked = ask(api, "Add a hotel fee of 5000 for Rao vs State", case_id=rao["case"].id)
        assert picked["status"] == "answer"
        assert picked["action_card"]["case_id"] == rao["case"].id
        assert picked["action_card"]["amount"] == "5000.00"

    def test_description_is_read_from_the_words(self, api, anil, rao):
        card = ask(api, "Add a hotel fee of 4000 for OS/12/2026 description: two nights at Hyderabad")["action_card"]
        assert card["description"] == "two nights at Hyderabad"

    def test_another_owners_case_is_never_offered(self, api, anil, other):
        theirs = make_case(other, "Secret vs Crown", "OS/777/2026")
        make_hearing(other, theirs, day(2026, 11, 5))
        turn = ask(api, "Add a hotel fee of 5000 for OS/777/2026")
        assert turn["action_card"] is None
        assert turn["case_candidates"] == []
        assert "Secret" not in json.dumps(turn)

    def test_foreign_case_id_is_a_404(self, api, anil, other):
        theirs = make_case(other, "Secret vs Crown", "OS/777/2026")
        resp = api.post(
            CHAT_URL,
            {"query": "Add a hotel fee of 5000", "client_request_id": rid(), "case_id": theirs.id},
            format="json",
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# propose_fee_update
# ---------------------------------------------------------------------------


class TestUpdateCard:
    def test_invoiced_unsent_fee_by_number_regenerates_the_invoice(self, api, anil, rao):
        fee = make_fee(anil, rao["past"], status="invoiced", number="INV-0042")
        before = snapshot()
        turn = ask(api, "Change INV-0042 to Rs 20,000")
        card = turn["action_card"]
        assert turn["intent"] == "propose_fee_update"
        assert card == {
            "kind": "update_fee",
            "case_id": rao["case"].id,
            "case_title": "Rao vs State",
            "fee_id": fee.id,
            "invoice_number": "INV-0042",
            "fee_status": "invoiced",
            "current": {"amount": "15000.00", "category": "appearance", "description": ""},
            "proposed": {"amount": "20000.00"},
            "regenerates_invoice": True,
            "blockers": [],
        }
        assert "same number, INV-0042" in turn["answer"]
        assert snapshot() == before

    def test_by_case_picks_the_latest_changeable_fee(self, api, anil, rao):
        make_fee(anil, rao["older"], status="paid", number="INV-0001")
        mine = make_fee(anil, rao["past"])
        card = ask(api, "Update the fee for OS/12/2026 to 18k")["action_card"]
        assert (card["fee_id"], card["proposed"]) == (mine.id, {"amount": "18000.00"})
        assert card["regenerates_invoice"] is False

    def test_category_and_description_changes(self, api, anil, rao):
        fee = make_fee(anil, rao["past"])
        card = ask(api, "Change the fee for OS/12/2026 category to hotel")["action_card"]
        assert card["fee_id"] == fee.id and card["proposed"] == {"category": "hotel"}
        card = ask(api, "Edit the fee for OS/12/2026 description: travel")["action_card"]
        assert card["proposed"] == {"description": "travel"}

    @pytest.mark.parametrize("send_status", ["sent", "logged"])
    def test_sent_invoice_carries_a_blocker(self, api, anil, rao, send_status):
        make_fee(anil, rao["past"], status="invoiced", number="INV-0007", sent=send_status)
        card = ask(api, "Change INV-0007 to 9000")["action_card"]
        assert card["blockers"] == ["This invoice has already been sent to the client, so the fee can no longer be changed."]
        assert card["regenerates_invoice"] is False

    def test_paid_fee_carries_a_blocker(self, api, anil, rao):
        make_fee(anil, rao["past"], status="paid", number="INV-0008")
        turn = ask(api, "Change INV-0008 to 9000")
        assert "already paid" in turn["action_card"]["blockers"][0]
        assert "cannot be changed" in turn["answer"]

    def test_no_change_named_is_a_question(self, api, anil, rao):
        make_fee(anil, rao["past"], status="invoiced", number="INV-0042")
        turn = ask(api, "Change INV-0042")
        assert (turn["status"], turn["action_card"]) == ("needs_clarification", None)
        assert "What should change?" in turn["answer"]

    def test_same_value_is_not_a_change(self, api, anil, rao):
        make_fee(anil, rao["past"], status="invoiced", number="INV-0042")
        turn = ask(api, "Change INV-0042 to 15000")
        assert turn["status"] == "needs_clarification"

    def test_no_case_or_number_is_a_question(self, api, anil, rao):
        turn = ask(api, "Change the fee to 20000")
        assert turn["status"] == "needs_clarification"
        assert "invoice number" in turn["answer"]

    def test_another_owners_invoice_number_names_nothing(self, api, anil, other):
        theirs = make_case(other, "Secret vs Crown", "OS/777/2026")
        make_fee(other, make_hearing(other, theirs, day(2026, 11, 5)), status="invoiced", number="INV-0500")
        turn = ask(api, "Change INV-0500 to 1")
        assert turn["action_card"] is None
        assert "Secret" not in json.dumps(turn)

    def test_case_with_no_fee(self, api, anil, rao):
        turn = ask(api, "Change the fee for OS/12/2026 to 5000")
        assert turn["status"] == "needs_clarification"
        assert "No fee is recorded for Rao vs State" in turn["answer"]


# ---------------------------------------------------------------------------
# propose_invoice_generate and propose_fee_delete
# ---------------------------------------------------------------------------


class TestGenerateAndDeleteCards:
    def test_generate_for_a_pending_fee(self, api, anil, rao):
        fee = make_fee(anil, rao["past"], category="hotel", amount="5000")
        before = snapshot()
        turn = ask(api, "Generate invoice for OS/12/2026")
        assert turn["intent"] == "propose_invoice_generate"
        assert turn["action_card"] == {
            "kind": "generate_invoice",
            "case_id": rao["case"].id,
            "case_title": "Rao vs State",
            "fee_id": fee.id,
            "amount": "5000.00",
            "category": "hotel",
            "blockers": [],
        }
        assert "does not send it" in turn["answer"]
        assert snapshot() == before

    def test_generate_on_an_invoiced_fee_is_blocked(self, api, anil, rao):
        make_fee(anil, rao["past"], status="invoiced", number="INV-0042")
        card = ask(api, "Generate the invoice for INV-0042")["action_card"]
        assert card["blockers"] == ["INV-0042 has already been made for this fee."]

    def test_generate_picks_the_pending_fee_over_a_newer_invoiced_one(self, api, anil, rao):
        pending = make_fee(anil, rao["older"])
        make_fee(anil, rao["past"], status="invoiced", number="INV-0002")
        assert ask(api, "Create an invoice for OS/12/2026")["action_card"]["fee_id"] == pending.id

    def test_delete_a_pending_fee(self, api, anil, rao):
        fee = make_fee(anil, rao["past"])
        before = snapshot()
        turn = ask(api, "Delete the pending fee for OS/12/2026")
        assert turn["intent"] == "propose_fee_delete"
        assert turn["action_card"] == {
            "kind": "delete_fee",
            "case_id": rao["case"].id,
            "case_title": "Rao vs State",
            "fee_id": fee.id,
            "amount": "15000.00",
            "category": "appearance",
            "fee_status": "pending",
            "blockers": [],
        }
        assert "cannot be undone" in turn["answer"]
        assert snapshot() == before

    def test_delete_an_invoiced_fee_is_blocked(self, api, anil, rao):
        make_fee(anil, rao["past"], status="invoiced", number="INV-0042")
        card = ask(api, "Delete INV-0042")["action_card"]
        assert card["blockers"] == ["Only a fee with no invoice yet can be deleted. This one has already been invoiced."]

    def test_replay_returns_the_same_card_and_writes_nothing(self, api, anil, rao):
        make_fee(anil, rao["past"])
        request_id = rid()
        body = {"query": "Delete the pending fee for OS/12/2026", "client_request_id": request_id}
        first = api.post(CHAT_URL, body, format="json").json()
        before = snapshot()
        again = api.post(CHAT_URL, body, format="json").json()
        assert again["action_card"] == first["action_card"]
        assert snapshot() == before


# ---------------------------------------------------------------------------
# Gates, ordering of the rules, and the model fallback
# ---------------------------------------------------------------------------


class TestGateAndRouting:
    @pytest.mark.parametrize(
        "query",
        [
            "Add a hotel fee of 5000 for OS/12/2026",
            "Change INV-0042 to 20000",
            "Generate invoice for OS/12/2026",
            "Delete the pending fee for OS/12/2026",
        ],
    )
    def test_gate_off_answers_in_words_with_no_card(self, api, anil, rao, settings, query):
        make_fee(anil, rao["past"], status="invoiced", number="INV-0042")
        settings.PRACTICE_INVOICE_ACTIONS_ENABLED = False
        turn = ask(api, query)
        assert turn["action_card"] is None
        assert "turned off" in turn["answer"]

    def test_questions_that_only_mention_fees_still_read(self, api, anil, rao):
        turn = ask(api, "How much is unpaid across my cases?")
        assert turn["intent"] == "billing_summary"
        turn = ask(api, "Send the invoice INV-0042 by email")
        assert turn["intent"] == "propose_invoice_send"

    def test_model_fallback_may_propose_a_fee_intent(self, api, anil, rao):
        fake = MagicMock()
        fake.generate.return_value = json.dumps(
            {"intent": "propose_fee_create", "case_text": "Rao", "date_from": None, "date_to": None}
        )
        query = "I spent 5000 on lodging for Rao, put it on the books"
        with patch.object(practice_nodes, "get_llm_client", return_value=fake):
            chooser = ask(api, query)
            assert (chooser["intent"], chooser["action_card"]) == ("propose_fee_create", None)
            assert [c["id"] for c in chooser["case_candidates"]] == [rao["case"].id]

    def test_model_text_that_is_not_in_the_question_gives_a_chooser(self, api, anil, rao):
        fake = MagicMock()
        fake.generate.return_value = json.dumps({"intent": "propose_fee_delete", "case_text": "Rao"})
        with patch.object(practice_nodes, "get_llm_client", return_value=fake):
            turn = ask(api, "Scrap that charge please")
        assert turn["action_card"] is None
        assert [c["id"] for c in turn["case_candidates"]] == [rao["case"].id]
