"""Mechanical document generation (core/services/doc_templates/).

  - every shipped template loads and its placeholders all map to declared
    fields (a typo fails here, not on a client's vakalatnama);
  - missing required fields block generation with a list of what and where;
  - stored data first, generation-time inputs only as the fallback;
  - the output is a real PDF saved as a Document on the case.
"""

import io
import json
from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.utils import timezone
from pdfminer.high_level import extract_text
from rest_framework.test import APIClient

from core.models import AdvocateProfile, Case, ClientContact, Document, Hearing
from core.services.doc_templates import engine
from core.services.invoice_service import get_or_create_profile


@pytest.fixture
def advocate(db):
    user = User.objects.create_user(username="docgen-advocate", password="pw-12345")
    get_or_create_profile(user)
    return user


@pytest.fixture
def api(advocate):
    client = APIClient()
    client.force_authenticate(user=advocate)
    return client


def _complete_profile(user):
    AdvocateProfile.objects.filter(owner=user).update(
        advocate_name="A. Rao",
        letterhead_name="Rao & Associates",
        address="12 Court Road\nHyderabad",
        bar_registration_number="TS/1234/2010",
        phone="9800000000",
        contact_email="rao@example.com",
    )


def _case(owner, **extra):
    defaults = dict(
        case_number="OS/42/2026",
        title="OS/42/2026 Ramesh vs Suresh",
        client_name="Ramesh",
        petitioner_name="Ramesh Kumar",
        respondent_name="Suresh Reddy",
        user_party_role="petitioner",
    )
    defaults.update(extra)
    case = Case.objects.create(owner=owner, **defaults)
    # The court name comes from the case's hearings (stamped from the
    # portal's court_name on every fetch).
    Hearing.objects.create(
        owner=owner,
        case=case,
        hearing_date=timezone.now(),
        hearing_type="other",
        location="Court of the Principal Junior Civil Judge, Hyderabad",
    )
    return case


def _executant(case, **extra):
    defaults = dict(
        name="Ramesh Kumar",
        email="ramesh@example.com",
        role="primary",
        relation_type="s/o",
        relation_name="Venkat Rao",
        age=45,
        address="Plot 7, Banjara Hills, Hyderabad",
    )
    defaults.update(extra)
    return ClientContact.objects.create(owner=case.owner, case=case, **defaults)


class TestTemplatesAreValid:
    def test_the_three_shipped_templates_load(self):
        keys = {t.key for t in engine.list_templates()}
        assert keys == {"vakalatnama", "memo_of_appearance", "cover_letter"}

    def test_an_undeclared_placeholder_is_rejected_at_load(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text(
            json.dumps(
                {
                    "key": "bad",
                    "title": "Bad",
                    "fields": [{"name": "a", "label": "A", "sources": []}],
                    "blocks": [{"type": "text", "text": "{a} {typo}"}],
                }
            )
        )
        with pytest.raises(ValueError, match="typo"):
            engine._load(path)

    def test_an_unknown_source_is_rejected_at_load(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text(
            json.dumps(
                {
                    "key": "bad",
                    "title": "Bad",
                    "fields": [{"name": "a", "label": "A", "sources": ["case.nope"]}],
                    "blocks": [{"type": "text", "text": "{a}"}],
                }
            )
        )
        with pytest.raises(ValueError, match="unknown source"):
            engine._load(path)


@pytest.mark.django_db
class TestReadiness:
    def test_lists_templates_without_a_case(self, api):
        resp = api.get("/api/doc-templates/")
        assert resp.status_code == 200
        assert {t["key"] for t in resp.data} == {"vakalatnama", "memo_of_appearance", "cover_letter"}

    def test_shows_what_is_missing_and_where_for_a_case(self, api, advocate):
        case = _case(advocate)
        resp = api.get("/api/doc-templates/", {"case": case.id})
        vakalat = next(t for t in resp.data if t["key"] == "vakalatnama")
        missing = {f["name"]: f["where"] for f in vakalat["fields"] if f["missing"]}
        assert vakalat["ready"] is False
        assert "advocate_name" in missing and missing["advocate_name"].startswith("Settings")
        assert "executant_name" in missing and "client contact" in missing["executant_name"]
        assert "place" in missing  # never stored anywhere -- always typed
        filled = {f["name"]: f for f in vakalat["fields"]}
        assert filled["petitioner"]["value"] == "Ramesh Kumar"
        assert filled["petitioner"]["source"] == "case.petitioner_name"


@pytest.mark.django_db
class TestGeneration:
    def test_missing_fields_block_generation_and_save_nothing(self, api, advocate):
        case = _case(advocate)
        resp = api.post(
            f"/api/cases/{case.id}/generate-document/", {"template": "vakalatnama"}, format="json"
        )
        assert resp.status_code == 400
        assert resp.data["code"] == "missing_fields"
        labels = {m["label"] for m in resp.data["missing"]}
        assert "Your name" in labels and "Place of signing" in labels
        assert not Document.objects.exists()

    def test_generates_a_pdf_document_on_the_case(self, api, advocate):
        _complete_profile(advocate)
        case = _case(advocate)
        _executant(case)

        resp = api.post(
            f"/api/cases/{case.id}/generate-document/",
            {"template": "vakalatnama", "inputs": {"place": "Hyderabad"}},
            format="json",
        )

        assert resp.status_code == 201, resp.data
        document = Document.objects.get(id=resp.data["id"])
        assert document.case == case
        assert document.document_type == "generated"
        assert document.processing_status == "completed"
        with default_storage.open(document.file_path, "rb") as handle:
            data = handle.read()
        assert data.startswith(b"%PDF")
        # Justified lines come back with uneven spacing; compare words.
        text = " ".join(extract_text(io.BytesIO(data)).split())
        assert "VAKALATNAMA" in text
        assert "S/o Venkat Rao" in text
        assert "TS/1234/2010" in text
        assert "PRINCIPAL JUNIOR CIVIL JUDGE" in text
        assert "Ramesh Kumar" in document.extracted_text

    def test_inputs_fill_only_what_isnt_stored(self, advocate):
        _complete_profile(advocate)
        case = _case(advocate)
        contact = _executant(case, relation_type="", relation_name="")
        template = engine.get_template("vakalatnama")

        resolution = engine.resolve(
            template,
            case=case,
            profile=AdvocateProfile.objects.get(owner=advocate),
            contact=contact,
            inputs={"executant_relation": "S/o Venkat Rao", "advocate_name": "SOMEONE ELSE", "place": "Hyd"},
        )

        fields = {f.name: f for f in resolution.fields}
        assert fields["executant_relation"].value == "S/o Venkat Rao"
        assert fields["executant_relation"].source == "input"
        # Stored wins: an input never overrides a value already on record.
        assert fields["advocate_name"].value == "A. Rao"
        assert fields["advocate_name"].source == "profile.advocate_name"
        assert not resolution.missing
        # Nothing typed is saved back.
        contact.refresh_from_db()
        assert contact.relation_name == ""

    def test_unknown_party_role_is_asked_for(self, api, advocate):
        _complete_profile(advocate)
        case = _case(advocate, user_party_role="unknown")
        _executant(case)
        resp = api.post(
            f"/api/cases/{case.id}/generate-document/",
            {"template": "memo_of_appearance", "inputs": {"place": "Hyderabad"}},
            format="json",
        )
        assert resp.status_code == 400
        assert "user_side" in {m["name"] for m in resp.data["missing"]}

        resp = api.post(
            f"/api/cases/{case.id}/generate-document/",
            {"template": "memo_of_appearance", "inputs": {"place": "Hyderabad", "user_side": "Petitioner"}},
            format="json",
        )
        assert resp.status_code == 201, resp.data

    def test_cover_letter_uses_the_letterhead(self, api, advocate):
        _complete_profile(advocate)
        case = _case(advocate)
        _executant(case)
        resp = api.post(
            f"/api/cases/{case.id}/generate-document/",
            {"template": "cover_letter", "inputs": {"subject": "Next date", "body": "Your matter is listed."}},
            format="json",
        )
        assert resp.status_code == 201, resp.data
        with default_storage.open(Document.objects.get(id=resp.data["id"]).file_path, "rb") as handle:
            text = extract_text(io.BytesIO(handle.read()))
        assert "Rao & Associates" in text
        assert "Your matter is listed." in text

    def test_contact_from_another_case_is_refused(self, api, advocate):
        _complete_profile(advocate)
        case = _case(advocate)
        elsewhere = _executant(_case(advocate, case_number="OS/43/2026"))
        resp = api.post(
            f"/api/cases/{case.id}/generate-document/",
            {"template": "vakalatnama", "contact_id": elsewhere.id, "inputs": {"place": "X"}},
            format="json",
        )
        assert resp.status_code == 400

    def test_unknown_template(self, api, advocate):
        case = _case(advocate)
        resp = api.post(f"/api/cases/{case.id}/generate-document/", {"template": "nope"}, format="json")
        assert resp.status_code == 400

    def test_optional_empty_lines_are_dropped(self, advocate):
        template = engine.get_template("memo_of_appearance")
        values = {f.name: f"<{f.name}>" for f in template.fields}
        values["advocate_phone"] = ""
        text = engine.merged_text(template, values)
        assert "<advocate_email>" in text
        assert "\n\n<advocate_email>" not in text  # the empty phone line is gone


@pytest.mark.django_db
def test_date_source_is_today(advocate):
    case = _case(advocate)
    resolution = engine.resolve(
        engine.get_template("cover_letter"),
        case=case,
        profile=AdvocateProfile.objects.get(owner=advocate),
    )
    assert {f.name: f.value for f in resolution.fields}["date"] == date.today().strftime("%d %B %Y")
