"""Starting a draft from the practice Case Bot: the `propose_draft` card, and
the two new draft kinds (client letter, list of dates).

The turn only proposes. The advocate's confirmation calls the existing draft
create endpoint with the card's fields.
"""

import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import AssistantDraft, Case
from core.services.drafting import prompt, schema
from core.services.graph import practice_nodes
from core.services.india_time import INDIA_TZ

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 11, 11, 10, 0, tzinfo=INDIA_TZ)
CHAT_URL = "/api/practice-assistant/chat/"
DRAFTS_URL = "/api/case-assistant/drafts/"


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
    with patch.object(practice_nodes, "get_llm_client", side_effect=AssertionError("the model was reached")) as f:
        yield f


@pytest.fixture
def anil(db):
    return User.objects.create_user(username="drf-anil", password="pw-12345")


@pytest.fixture
def other(db):
    return User.objects.create_user(username="drf-other", password="pw-12345")


@pytest.fixture
def api(anil):
    client = APIClient()
    client.force_authenticate(user=anil)
    return client


@pytest.fixture
def rao(anil):
    return Case.objects.create(owner=anil, title="Rao vs State", case_number="OS/12/2026")


def ask(api, query, **extra):
    resp = api.post(CHAT_URL, {"query": query, "client_request_id": rid(), **extra}, format="json")
    assert resp.status_code == 200, resp.content
    return resp.json()


class TestDraftCard:
    @pytest.mark.parametrize(
        "query,subtype,label",
        [
            ("Draft a client letter for OS/12/2026", "client_letter", "Client letter"),
            ("Write a list of dates for OS/12/2026", "list_of_dates", "List of dates"),
            ("Prepare a status memo for OS/12/2026", "status_memo", "Case status memo"),
            ("Draft a personal note on OS/12/2026", "personal_note", "Personal note"),
        ],
    )
    def test_each_subtype_gets_a_card(self, api, rao, query, subtype, label):
        before = AssistantDraft.objects.count()
        turn = ask(api, query)
        assert (turn["intent"], turn["status"]) == ("propose_draft", "answer")
        assert turn["action_card"] == {
            "kind": "start_draft",
            "case_id": rao.id,
            "case_title": "Rao vs State",
            "subtype": subtype,
            "subtype_label": label,
            "instructions": query,
            "blockers": [],
        }
        assert f"Ready to start a {label.lower()} draft for Rao vs State" in turn["answer"]
        assert [(s["kind"], s["id"]) for s in turn["sources"]] == [("case", rao.id)]
        assert AssistantDraft.objects.count() == before  # nothing was created

    def test_chooser_for_a_party_name_then_the_picked_case_completes_it(self, api, rao):
        turn = ask(api, "Draft a client letter for Rao vs State")
        assert turn["status"] == "needs_clarification" and turn["action_card"] is None
        assert [c["id"] for c in turn["case_candidates"]] == [rao.id]
        picked = ask(api, "Draft a client letter for Rao vs State", case_id=rao.id)
        assert picked["action_card"]["case_id"] == rao.id

    def test_no_case_named_is_a_question(self, api, rao):
        turn = ask(api, "Write a client letter")
        assert turn["status"] == "needs_clarification" and turn["action_card"] is None
        assert "Which case do you mean?" in turn["answer"]

    def test_gate_off_answers_in_words_with_no_card(self, api, rao, settings):
        settings.CASE_DRAFTING_ENABLED = False
        turn = ask(api, "Draft a client letter for OS/12/2026")
        assert turn["action_card"] is None
        assert "turned off" in turn["answer"]

    def test_unknown_subtype_from_the_model_falls_back_to_a_question(self, api, rao):
        fake = MagicMock()
        fake.generate.return_value = json.dumps(
            {"intent": "propose_draft", "subtype": "affidavit", "case_text": "OS/12/2026"}
        )
        with patch.object(practice_nodes, "get_llm_client", return_value=fake):
            turn = ask(api, "Can you put together something formal for Rao")
        assert turn["status"] == "needs_clarification" and turn["action_card"] is None
        assert "status memo, a personal note, a client letter or a list of dates" in turn["answer"]

    def test_another_owners_case_is_never_offered(self, api, other):
        Case.objects.create(owner=other, title="Secret vs Crown", case_number="OS/777/2026")
        turn = ask(api, "Draft a client letter for OS/777/2026")
        assert turn["action_card"] is None and turn["case_candidates"] == []
        assert "Secret" not in json.dumps(turn)

    def test_replay_returns_the_same_card_and_creates_nothing(self, api, rao):
        body = {"query": "Draft a client letter for OS/12/2026", "client_request_id": rid()}
        first = api.post(CHAT_URL, body, format="json").json()
        again = api.post(CHAT_URL, body, format="json").json()
        assert again["action_card"] == first["action_card"]
        assert AssistantDraft.objects.count() == 0


class TestNewSubtypes:
    def body(self, subtype):
        return {
            "schema_version": 1,
            "title": "T",
            "subtype": subtype,
            "sections": [{"heading": "H", "blocks": [{"type": "paragraph", "text": "x", "evidence": []}]}],
        }

    @pytest.mark.parametrize("subtype", ["client_letter", "list_of_dates"])
    def test_new_subtypes_validate(self, subtype):
        assert subtype in schema.SUBTYPES
        assert schema.validate_body(self.body(subtype), allowed_evidence=[])["subtype"] == subtype

    def test_unknown_subtype_does_not(self):
        with pytest.raises(schema.DraftValidationError):
            schema.validate_body(self.body("affidavit"), allowed_evidence=[])

    @pytest.mark.parametrize("subtype", ["client_letter", "list_of_dates"])
    def test_every_subtype_has_guidance_and_a_document_kind(self, subtype):
        assert prompt.SUBTYPE_GUIDANCE[subtype]
        assert AssistantDraft.KIND_FOR_SUBTYPE[subtype] == AssistantDraft.KIND_DOCUMENT
        assert subtype in prompt.SYSTEM_PROMPT
        assert set(prompt.SUBTYPE_GUIDANCE) == set(schema.SUBTYPES) == set(AssistantDraft.KIND_FOR_SUBTYPE)

    @pytest.mark.parametrize("subtype", ["client_letter", "list_of_dates"])
    def test_the_existing_create_endpoint_accepts_the_card_payload(self, api, rao, subtype):
        resp = api.post(
            DRAFTS_URL,
            {"case_id": rao.id, "subtype": subtype, "client_request_id": rid(), "instructions": "Draft it"},
            format="json",
        )
        assert resp.status_code == 202, resp.content
        draft = AssistantDraft.objects.get(owner=rao.owner)
        assert (draft.subtype, draft.kind) == (subtype, "document")

    def test_the_create_endpoint_still_rejects_an_unknown_subtype(self, api, rao):
        resp = api.post(
            DRAFTS_URL, {"case_id": rao.id, "subtype": "affidavit", "client_request_id": rid()}, format="json"
        )
        assert resp.status_code == 400
