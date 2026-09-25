"""Plain-language order summaries for client emails
(core/services/client_updates/plain.py).

The Order Overview is written for the advocate; a client got "the proviso
to Rule 3(a)(iii) be read to include..." in their update. Client emails now
use a lay rewrite when one can be made, and the advocate's text otherwise.
"""

import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from core.models import AdvocateProfile, Case, ClientContact, CourtOrder
from core.services.client_updates import draft_update_for_order
from core.services.client_updates.plain import ensure_plain_summary
from core.services.invoice_service import get_or_create_profile

LAWYER_TEXT = (
    "The court disposed of the writ petition, declaring that the proviso to Rule 3(a)(iii) be read "
    "to include children of Central Government employees, and directed respondent No.2 to treat the "
    "petitioner as a local candidate."
)
PLAIN_TEXT = (
    "The court ruled in your favour. The university must treat you as a local candidate for "
    "admission this year, and the government is to correct its rules."
)


def _llm(reply):
    client = MagicMock()
    if isinstance(reply, Exception):
        client.generate_with_json.side_effect = reply
    else:
        client.generate_with_json.return_value = reply
    return patch("core.services.ai_service_factory.get_llm_client", return_value=client), client


@pytest.fixture
def order(db):
    owner = User.objects.create_user(username="plain-advocate", password="pw-12345")
    get_or_create_profile(owner)
    AdvocateProfile.objects.filter(owner=owner).update(advocate_name="S. Bhagath", contact_email="s@example.com")
    case = Case.objects.create(owner=owner, case_number="WP/26147/2026", title="S.Sashi Kumar vs The State", client_name="")
    ClientContact.objects.create(owner=owner, case=case, name="Karthik", email="k@example.com")
    return CourtOrder.objects.create(
        owner=owner, case=case, order_number="4", order_date=timezone.localdate() - timedelta(days=1),
        dedup_key="HB:4", summary_status=CourtOrder.SUMMARY_SUMMARIZED, summary_what_happened=LAWYER_TEXT,
    )


@pytest.mark.django_db
class TestPlainSummary:
    def test_generated_once_and_used_in_the_client_email(self, order):
        patcher, client = _llm(json.dumps({"plain": PLAIN_TEXT}))
        with patcher:
            assert ensure_plain_summary(order) == PLAIN_TEXT
            assert ensure_plain_summary(order) == PLAIN_TEXT  # cached: no second call
        assert client.generate_with_json.call_count == 1

        message, _ = draft_update_for_order(order)

        assert PLAIN_TEXT in message.body
        assert "proviso to Rule" not in message.body

    def test_no_llm_falls_back_to_the_advocates_text(self, order):
        patcher, _ = _llm(RuntimeError("no LLM configured"))
        with patcher:
            assert ensure_plain_summary(order) == ""
        order.refresh_from_db()
        assert order.summary_plain == ""

        message, _ = draft_update_for_order(order)
        assert LAWYER_TEXT in message.body

    @pytest.mark.parametrize("reply", ["not json", json.dumps({"plain": ""}), json.dumps({"plain": "x" * 800})])
    def test_an_unusable_answer_is_not_stored(self, order, reply):
        patcher, _ = _llm(reply)
        with patcher:
            assert ensure_plain_summary(order) == ""
        order.refresh_from_db()
        assert order.summary_plain == ""

    def test_templated_orders_never_call_the_llm(self, order):
        CourtOrder.objects.filter(id=order.id).update(
            summary_status=CourtOrder.SUMMARY_NO_DIRECTIONS, summary_what_happened="No directions."
        )
        order.refresh_from_db()
        patcher, client = _llm(json.dumps({"plain": PLAIN_TEXT}))
        with patcher:
            assert ensure_plain_summary(order) == ""
        client.generate_with_json.assert_not_called()

    def test_the_worker_makes_it_before_drafting(self, order):
        from io import StringIO

        from core.management.commands.process_jobs import Command
        from core.models import Document

        order.document = Document.objects.create(
            owner=order.owner, case=order.case, filename="o4.pdf", file_path="d/o4.pdf", file_type="pdf",
            document_type="court_order", processing_status="completed", extracted_text="(summarised)",
        )
        order.save()
        patcher, _ = _llm(json.dumps({"plain": PLAIN_TEXT}))
        with patcher:
            Command(stdout=StringIO())._summarize_order_if_any(order.document_id)

        order.refresh_from_db()
        assert order.summary_plain == PLAIN_TEXT
        assert PLAIN_TEXT in order.client_messages.get().body
