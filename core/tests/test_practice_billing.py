"""Billing answers and the invoice send card of the practice assistant.

The assistant only reads and proposes. Every card field comes from the
owner's rows, a model can never change one, and a chat turn sends nothing.
`get_llm_client` is patched so any model call fails the test unless a test
asks for a fake one.
"""

import json
import re
import uuid
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from django.core import mail
from rest_framework.test import APIClient

from core.models import AppearanceFee, Case, ClientContact, Hearing, Message
from core.services import invoice_service
from core.services.graph import practice_nodes
from core.services.india_time import INDIA_TZ
from core.services.practice_assistant import answers, billing

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 11, 11, 10, 0, tzinfo=INDIA_TZ)
CHAT_URL = "/api/practice-assistant/chat/"
SUMMARY_Q = "How much is unpaid across my cases?"
SEND_Q = "Send the invoice INV-0042 by email"


def rid():
    return str(uuid.uuid4())


@pytest.fixture(autouse=True)
def flags(settings):
    settings.PRACTICE_ASSISTANT_ENABLED = True
    settings.PRACTICE_INVOICE_ACTIONS_ENABLED = True


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


@pytest.fixture(autouse=True)
def no_mail():
    """Any send during a test is a failure of its own."""
    with patch.object(
        invoice_service, "send_invoice", side_effect=AssertionError("an invoice was sent")
    ) as sender:
        yield sender


@pytest.fixture
def anil(db):
    return User.objects.create_user(username="billing-anil", password="pw-12345")


@pytest.fixture
def other(db):
    return User.objects.create_user(username="billing-other", password="pw-12345")


@pytest.fixture
def api(anil):
    client = APIClient()
    client.force_authenticate(user=anil)
    return client


def make_fee(owner, case, *, status="pending", number="", sent="not_sent", amount="15000.00",
             paid_at=None, pdf=None, category="appearance"):
    hearing = Hearing.objects.create(
        owner=owner,
        case=case,
        hearing_date=datetime(2026, 11, 20, tzinfo=dt_timezone.utc) + timedelta(days=Hearing.objects.count()),
        hearing_type="other",
    )
    return AppearanceFee.objects.create(
        owner=owner,
        hearing=hearing,
        category=category,
        amount=Decimal(amount),
        status=status,
        invoice_number=number,
        invoice_pdf_path=(f"invoices/{number}.pdf" if number else "") if pdf is None else pdf,
        invoiced_at=NOW if number else None,
        send_status=sent,
        paid_at=paid_at,
    )


def make_case(owner, title, *, email="client@example.com", name="A. Rao", billing_contact=True):
    case = Case.objects.create(owner=owner, title=title, case_number=f"OS/{abs(hash(title)) % 900}/2026")
    if billing_contact:
        ClientContact.objects.create(
            owner=owner, case=case, name=name, email=email, is_billing_contact=True
        )
    return case


def ask(api, query, **extra):
    return api.post(CHAT_URL, {"query": query, "client_request_id": rid(), **extra}, format="json")


@pytest.fixture
def ledger(anil, other):
    rao = make_case(anil, "Rao vs State")
    mehta = make_case(anil, "Mehta vs Union", name="B. Mehta", email="mehta@example.com")
    theirs = make_case(other, "Secret vs Hidden", name="Z", email="z@example.com")
    return {
        "rao": rao,
        "mehta": mehta,
        "theirs": theirs,
        "pending": make_fee(anil, rao, amount="1000"),
        "unsent": make_fee(anil, rao, status="invoiced", number="INV-0042", amount="15000"),
        "sent": make_fee(anil, mehta, status="invoiced", number="INV-0043", sent="sent", amount="2500.50"),
        "paid_recent": make_fee(
            anil, mehta, status="paid", number="INV-0040", sent="sent", amount="700",
            paid_at=NOW - timedelta(days=5),
        ),
        "paid_old": make_fee(
            anil, mehta, status="paid", number="INV-0001", sent="sent", amount="99",
            paid_at=NOW - timedelta(days=45),
        ),
        # The other advocate reuses the same invoice number.
        "their_fee": make_fee(other, theirs, status="invoiced", number="INV-0042", amount="777"),
    }


# ---------------------------------------------------------------------------
# billing_summary
# ---------------------------------------------------------------------------


class TestBillingSummary:
    def test_counts_and_totals_are_exact_and_owner_scoped(self, anil, ledger):
        summary = billing.billing_summary(owner=anil, scope="personal", now=NOW)
        assert summary["counts"] == {"pending": 1, "invoiced_unsent": 1, "sent_unpaid": 1, "paid_30d": 1}
        assert summary["totals"] == {
            "pending": "1000.00", "invoiced_unsent": "15000.00", "sent_unpaid": "2500.50", "paid_30d": "700.00",
        }
        assert summary["total"] == 3 and summary["truncated"] is False
        assert summary["timezone"] == "Asia/Kolkata"
        assert {row["id"] for row in summary["rows"]} == {
            ledger["pending"].id, ledger["unsent"].id, ledger["sent"].id
        }
        assert json.loads(json.dumps(summary)) == summary  # JSON-safe

    def test_logged_only_counts_as_not_sent(self, anil, ledger):
        AppearanceFee.objects.filter(id=ledger["sent"].id).update(send_status="logged")
        summary = billing.billing_summary(owner=anil, scope="personal", now=NOW)
        assert summary["counts"]["invoiced_unsent"] == 2 and summary["counts"]["sent_unpaid"] == 0

    def test_case_id_narrows(self, anil, ledger):
        summary = billing.billing_summary(owner=anil, scope="personal", case_id=ledger["mehta"].id, now=NOW)
        assert summary["counts"]["pending"] == 0 and summary["counts"]["sent_unpaid"] == 1

    def test_a_foreign_case_id_finds_nothing(self, anil, ledger):
        summary = billing.billing_summary(owner=anil, scope="personal", case_id=ledger["theirs"].id, now=NOW)
        assert summary["total"] == 0 and summary["rows"] == []

    def test_rows_are_capped_and_the_query_count_is_fixed(self, anil, ledger, django_assert_max_num_queries):
        for _ in range(30):
            make_fee(anil, ledger["rao"], amount="1")
        with django_assert_max_num_queries(3):
            summary = billing.billing_summary(owner=anil, scope="personal", now=NOW)
        assert len(summary["rows"]) == 25 and summary["truncated"] is True and summary["total"] == 33

    def test_only_the_personal_scope(self, anil):
        with pytest.raises(ValueError):
            billing.billing_summary(owner=anil, scope="firm")

    def test_chat_answer_and_sources(self, api, ledger):
        turn = ask(api, SUMMARY_Q).json()
        assert (turn["intent"], turn["status"]) == ("billing_summary", "answer")
        assert "**1 fee** with no invoice yet (Rs. 1,000)" in turn["answer"] and "INV-0042" in turn["answer"]
        assert "INV-0001" not in turn["answer"]
        assert turn["action_card"] is None
        kinds = {(r["kind"], r["id"]) for r in turn["sources"]}
        assert ("fee", ledger["unsent"].id) in kinds and ("case", ledger["rao"].id) in kinds
        assert not any(r["id"] == ledger["their_fee"].id for r in turn["sources"] if r["kind"] == "fee")

    def test_empty_ledger(self, api, anil):
        turn = ask(api, SUMMARY_Q).json()
        assert turn["answer"] == "No fees or invoices are recorded in Case Intel."


# ---------------------------------------------------------------------------
# Flag off
# ---------------------------------------------------------------------------


class TestFlagOff:
    @pytest.mark.parametrize("query, intent", [(SUMMARY_Q, "billing_summary"), (SEND_Q, "propose_invoice_send")])
    def test_old_answer_and_no_card(self, api, ledger, settings, query, intent):
        settings.PRACTICE_INVOICE_ACTIONS_ENABLED = False
        turn = ask(api, query).json()
        assert turn["intent"] == intent and turn["status"] == "needs_clarification"
        assert turn["answer"] == answers.BILLING_NOT_AVAILABLE
        assert turn["action_card"] is None and turn["summary"] is None and turn["sources"] == []

    def test_case_id_still_means_case_facts_when_off(self, api, ledger, settings):
        settings.PRACTICE_INVOICE_ACTIONS_ENABLED = False
        turn = ask(api, "Rao vs State fees", case_id=ledger["rao"].id).json()
        assert turn["intent"] == "case_facts"


# ---------------------------------------------------------------------------
# propose_invoice_send
# ---------------------------------------------------------------------------


class TestSendCard:
    def test_single_candidate_card_matches_the_rows(self, api, anil, ledger):
        turn = ask(api, SEND_Q).json()
        fee, case = ledger["unsent"], ledger["rao"]
        assert (turn["intent"], turn["status"]) == ("propose_invoice_send", "answer")
        assert turn["action_card"] == {
            "kind": "send_invoice",
            "fee_id": fee.id,
            "case_id": case.id,
            "case_title": case.title,
            "invoice_number": "INV-0042",
            "amount": "15000.00",
            "recipient_name": "A. Rao",
            "recipient_email": "client@example.com",
            "blockers": [],
        }
        assert turn["answer"] == (
            "Invoice INV-0042 for Rs. 15,000 is ready to send to A. Rao. Confirm below to send it."
        )
        assert ("fee", fee.id) in {(r["kind"], r["id"]) for r in turn["sources"]}

    def test_other_owners_invoice_number_finds_nothing(self, api, anil, other, ledger):
        AppearanceFee.objects.filter(id__in=[ledger["unsent"].id, ledger["sent"].id]).delete()
        turn = ask(api, SEND_Q).json()
        assert turn["action_card"] is None
        assert turn["answer"] == answers.NO_INVOICE_TO_SEND
        assert "777" not in turn["answer"] and "Secret" not in json.dumps(turn)

    def test_several_candidates_need_clarification_and_no_card(self, api, ledger):
        turn = ask(api, "Send the invoice").json()
        assert turn["status"] == "needs_clarification" and turn["action_card"] is None
        assert "INV-0042" in turn["answer"] and "INV-0043" in turn["answer"]
        assert "Which one" in turn["answer"]

    def test_a_selected_case_narrows_to_one(self, api, ledger):
        turn = ask(api, "Send the invoice", case_id=ledger["mehta"].id).json()
        assert turn["intent"] == "propose_invoice_send" and turn["status"] == "answer"
        assert turn["action_card"]["fee_id"] == ledger["sent"].id

    def test_a_foreign_case_id_is_404(self, api, ledger):
        resp = ask(api, "Send the invoice", case_id=ledger["theirs"].id)
        assert resp.status_code == 404

    def test_nothing_waiting(self, api, anil):
        make_fee(anil, make_case(anil, "Only pending"))
        turn = ask(api, "Send the invoice").json()
        assert turn["answer"] == answers.NO_INVOICE_TO_SEND and turn["action_card"] is None

    def test_not_invoiced_blocker(self, anil):
        fee = make_fee(anil, make_case(anil, "C1"))
        card = billing.build_send_card(owner=anil, fee=fee)
        assert card["blockers"] == [billing.BLOCKER_NOT_INVOICED]
        assert billing.BLOCKER_NOT_INVOICED == "This fee has no invoice yet. Generate the invoice first."

    def test_paid_blocker_through_chat(self, api, ledger):
        turn = ask(api, "Send the invoice INV-0040").json()
        assert turn["action_card"]["blockers"] == ["This invoice is already paid."]
        assert "cannot be sent yet" in turn["answer"]

    def test_no_email_blocker(self, anil):
        case = make_case(anil, "No email", email="")
        fee = make_fee(anil, case, status="invoiced", number="INV-0100")
        card = billing.build_send_card(owner=anil, fee=fee)
        assert card["blockers"] == ["No billing email is recorded for this client."]
        assert card["recipient_email"] is None

    def test_no_billing_contact_blocker(self, anil):
        case = make_case(anil, "No contact", billing_contact=False)
        fee = make_fee(anil, case, status="invoiced", number="INV-0101")
        assert billing.build_send_card(owner=anil, fee=fee)["blockers"] == [billing.BLOCKER_NO_EMAIL]

    def test_a_foreign_fee_cannot_get_a_card(self, anil, ledger):
        with pytest.raises(AppearanceFee.DoesNotExist):
            billing.build_send_card(owner=anil, fee=ledger["their_fee"])

    def test_replay_returns_the_same_card_and_writes_nothing(self, api, ledger):
        body = {"query": SEND_Q, "client_request_id": rid()}
        first = api.post(CHAT_URL, body, format="json").json()
        count = Message.objects.count()
        second = api.post(CHAT_URL, body, format="json").json()
        assert second == first and second["action_card"] is not None
        assert Message.objects.count() == count

    def test_a_chat_turn_sends_no_email_and_changes_no_fee(self, api, ledger, no_mail):
        before = list(AppearanceFee.objects.order_by("id").values())
        mail.outbox.clear()
        ask(api, SEND_Q)
        ask(api, SUMMARY_Q)
        assert mail.outbox == [] and no_mail.call_count == 0
        assert list(AppearanceFee.objects.order_by("id").values()) == before


class TestHostileModelOutput:
    QUESTION = "could you get that over to my client"  # no rule matches

    def test_model_arguments_cannot_alter_the_card(self, api, ledger, anil):
        # One invoiced fee only, so a card is produced.
        AppearanceFee.objects.filter(id=ledger["sent"].id).update(status="paid")
        raw = json.dumps(
            {
                "intent": "propose_invoice_send",
                "fee_id": ledger["their_fee"].id,
                "case_id": ledger["theirs"].id,
                "recipient_email": "evil@example.com",
                "recipient_name": "Evil",
                "amount": "1",
                "action_card": {"kind": "send_invoice", "fee_id": ledger["their_fee"].id},
            }
        )
        llm = MagicMock()
        llm.generate.return_value = raw
        with patch.object(practice_nodes, "get_llm_client", return_value=llm):
            turn = ask(api, self.QUESTION).json()
        card = turn["action_card"]
        assert card["fee_id"] == ledger["unsent"].id
        assert card["recipient_email"] == "client@example.com"
        assert card["recipient_name"] == "A. Rao" and card["amount"] == "15000.00"
        assert "evil" not in json.dumps(turn).lower()
        assert llm.generate.call_count == 1

    def test_model_billing_with_the_flag_off_gets_no_card(self, api, ledger, settings):
        settings.PRACTICE_INVOICE_ACTIONS_ENABLED = False
        llm = MagicMock()
        llm.generate.return_value = json.dumps({"intent": "propose_invoice_send"})
        with patch.object(practice_nodes, "get_llm_client", return_value=llm):
            turn = ask(api, self.QUESTION).json()
        assert turn["action_card"] is None and turn["answer"] == answers.BILLING_NOT_AVAILABLE


# ---------------------------------------------------------------------------
# Tenancy of the existing send endpoint, and the hard "graph only reads" rule
# ---------------------------------------------------------------------------


def test_existing_send_endpoint_is_404_for_a_foreign_fee(api, ledger):
    resp = api.post(f"/api/appearance-fees/{ledger['their_fee'].id}/send/")
    assert resp.status_code == 404


FORBIDDEN = re.compile(
    r"\bsend_invoice\s*\(|import[^\n]*\bsend_invoice\b|\bgenerate_invoice\s*\(|\bmark_paid\b"
    r"|\bdeliver_email\b|\bsend_mail\b|\bEmailMessage\b|\.status\s*=(?!=)|\.send_status\s*=(?!=)"
)


def test_graph_and_assistant_packages_never_send_generate_or_mark_paid():
    root = Path(__file__).resolve().parents[1] / "services"
    files = list((root / "graph").rglob("*.py")) + list((root / "practice_assistant").rglob("*.py"))
    assert files
    hits = [
        f"{path.name}: {match.group(0)}"
        for path in files
        for match in FORBIDDEN.finditer(path.read_text(encoding="utf-8"))
        if "graph" in path.parts or "practice_assistant" in path.parts
    ]
    assert hits == []
