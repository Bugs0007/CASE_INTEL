"""Practice reports: the Case Bot's downloadable billing, hearings, cases and
deadlines reports (PDF and DOCX), built from the caller's own rows only.
"""

import io
import json
import uuid
import zipfile
from datetime import date, datetime
from datetime import timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from pdfminer.high_level import extract_text
from rest_framework.test import APIClient

from core.models import AppearanceFee, Case, ClientContact, Hearing, Task
from core.services.graph import practice_nodes
from core.services.india_time import INDIA_TZ
from core.services.practice_assistant import parsing, reports

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 11, 11, 10, 0, tzinfo=INDIA_TZ)
CHAT_URL = "/api/practice-assistant/chat/"
TODAY = date(2026, 11, 11)


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
    with patch.object(practice_nodes, "get_llm_client", side_effect=AssertionError("the model was reached")):
        yield


@pytest.fixture
def anil(db):
    return User.objects.create_user(username="rep-anil", password="pw-12345")


@pytest.fixture
def other(db):
    return User.objects.create_user(username="rep-other", password="pw-12345")


@pytest.fixture
def api(anil):
    client = APIClient()
    client.force_authenticate(user=anil)
    return client


def day(y, m, d):
    return datetime(y, m, d, tzinfo=dt_timezone.utc)


def seed(owner, title, number, *, tag):
    """One case with a past and an upcoming hearing, two fees, an open task."""
    case = Case.objects.create(owner=owner, title=title, case_number=number, client_name=f"Client {tag}")
    past = Hearing.objects.create(owner=owner, case=case, hearing_date=day(2026, 10, 20), hearing_type="other")
    billed = Hearing.objects.create(owner=owner, case=case, hearing_date=day(2026, 10, 25), hearing_type="other")
    upcoming = Hearing.objects.create(owner=owner, case=case, hearing_date=day(2026, 11, 25), hearing_type="other")
    AppearanceFee.objects.create(
        owner=owner, hearing=billed, amount=Decimal("15000"), status="invoiced", invoice_number=f"INV-{tag}1",
        invoiced_at=NOW, send_status="sent",
    )
    AppearanceFee.objects.create(
        owner=owner, hearing=billed, category="hotel", amount=Decimal("5000"), status="paid",
        invoice_number=f"INV-{tag}2", invoiced_at=NOW, paid_at=NOW,
    )
    Task.objects.create(owner=owner, case=case, title=f"File reply {tag}", due_date=date(2026, 11, 1))
    return {"case": case, "past": past, "upcoming": upcoming}


@pytest.fixture
def data(anil, other):
    mine = seed(anil, "Rao vs State", "OS/12/2026", tag="A")
    Case.objects.create(owner=anil, title="Undated vs Crown", case_number="OS/50/2026", client_name="Client U")
    theirs = seed(other, "Secret vs Crown", "OS/777/2026", tag="Z")
    return {"mine": mine, "theirs": theirs}


def fetch(api, kind, fmt, **params):
    return api.get(f"/api/practice-assistant/reports/{kind}/{fmt}/", params)


def pdf_text(response) -> str:
    return extract_text(io.BytesIO(response.content))


def docx_text(response) -> str:
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        return archive.read("word/document.xml").decode("utf-8")


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------


class TestReportFiles:
    @pytest.mark.parametrize("kind", ["billing", "hearings", "cases", "deadlines"])
    def test_every_kind_gives_a_pdf_and_a_docx(self, api, data, kind):
        params = {"date_from": "2026-10-01", "date_to": "2026-12-31"}
        pdf = fetch(api, kind, "pdf", **params)
        assert pdf.status_code == 200
        assert pdf["Content-Type"] == "application/pdf"
        assert pdf.content.startswith(b"%PDF")
        assert f"{kind}-report" in pdf["Content-Disposition"] and ".pdf" in pdf["Content-Disposition"]
        docx = fetch(api, kind, "docx", **params)
        assert docx.status_code == 200
        assert docx["Content-Type"].endswith("wordprocessingml.document")
        assert docx.content.startswith(b"PK")

    @pytest.mark.parametrize("kind", ["billing", "hearings", "cases", "deadlines"])
    def test_files_carry_only_the_callers_rows(self, api, data, kind):
        params = {"date_from": "2026-10-01", "date_to": "2026-12-31"}
        pdf, docx = pdf_text(fetch(api, kind, "pdf", **params)), docx_text(fetch(api, kind, "docx", **params))
        for text in (pdf, docx):
            assert "Secret" not in text and "OS/777/2026" not in text
            assert "INV-Z" not in text and "File reply Z" not in text and "Client Z" not in text
        if kind != "deadlines":
            assert "Rao vs State" in pdf and "Rao vs State" in docx
        else:
            assert "File reply A" in pdf and "File reply A" in docx

    def test_billing_content(self, api, data):
        report = reports.build_report(
            owner=User.objects.get(username="rep-anil"), kind="billing",
            date_from=date(2026, 10, 1), date_to=date(2026, 10, 31), now=NOW,
        )
        by_label = dict(report["blocks"][0]["items"])
        assert by_label["Invoiced (including paid)"] == "Rs. 20,000"
        assert by_label["Paid"] == "Rs. 5,000"
        assert by_label["Outstanding (invoiced, not paid)"] == "Rs. 15,000"
        assert report["row_count"] == 2
        fee_rows = report["blocks"][1]["rows"]
        assert [r[6] for r in fee_rows] == ["INV-A1", "INV-A2"]
        assert fee_rows[0][0] == "Client A" and fee_rows[0][5] == "Invoiced, sent"
        # the past hearing with no invoice is listed; the invoiced one is not
        assert [(r[2], r[3]) for r in report["blocks"][2]["rows"]] == [("20 Oct 2026", "No fee recorded")]

    def test_billing_names_the_billing_contact_when_the_case_has_no_client(self, api, data):
        owner = User.objects.get(username="rep-anil")
        case = data["mine"]["case"]
        Case.objects.filter(id=case.id).update(client_name="")
        ClientContact.objects.create(owner=owner, case=case, name="K. Rao", is_billing_contact=True)
        report = reports.build_report(
            owner=owner, kind="billing", date_from=date(2026, 10, 1), date_to=date(2026, 10, 31), now=NOW,
        )
        assert {r[0] for r in report["blocks"][1]["rows"]} == {"K. Rao"}

    def test_cases_report_flags_cases_with_no_next_date(self, api, data):
        report = reports.build_report(owner=User.objects.get(username="rep-anil"), kind="cases", now=NOW)
        rows = report["blocks"][1]["rows"]
        assert rows[0][0] == "Undated vs Crown" and rows[0][3] == "No next date recorded"
        assert rows[1][0] == "Rao vs State" and rows[1][3] == "25 Nov 2026" and rows[1][5] == "1"
        assert dict(report["blocks"][0]["items"])["With no next date recorded"] == "1"
        assert (report["date_from"], report["date_to"]) == (None, None)

    def test_deadlines_put_overdue_first_and_say_so(self, api, anil, data):
        Task.objects.create(owner=anil, case=data["mine"]["case"], title="Later task", due_date=date(2026, 12, 20))
        Task.objects.create(owner=anil, case=data["mine"]["case"], title="No date task")
        rows = reports.build_report(owner=anil, kind="deadlines", now=NOW)["blocks"][1]["rows"]
        assert [r[2] for r in rows] == ["File reply A", "Later task", "No date task"]
        assert rows[0][1] == "Overdue" and rows[1][1] == ""

    def test_default_periods(self, anil, data):
        billing = reports.build_report(owner=anil, kind="billing", now=NOW)
        assert (billing["date_from"], billing["date_to"]) == ("2026-04-01", "2027-03-31")
        hearings = reports.build_report(owner=anil, kind="hearings", now=NOW)
        assert (hearings["date_from"], hearings["date_to"]) == ("2026-11-11", "2026-12-11")

    def test_requires_login(self, db):
        assert fetch(APIClient(), "billing", "pdf").status_code in (401, 403)

    def test_off_means_404(self, api, data, settings):
        settings.PRACTICE_ASSISTANT_ENABLED = False
        assert fetch(api, "billing", "pdf").status_code == 404

    @pytest.mark.parametrize("kind,fmt", [("nope", "pdf"), ("billing", "xlsx"), ("billing", "")])
    def test_unknown_kind_or_format_is_404(self, api, data, kind, fmt):
        assert api.get(f"/api/practice-assistant/reports/{kind}/{fmt or 'x'}/").status_code == 404

    @pytest.mark.parametrize(
        "params",
        [
            {"date_from": "2026-10-01"},
            {"date_from": "2026-10-31", "date_to": "2026-10-01"},
            {"date_from": "2020-01-01", "date_to": "2026-10-01"},
            {"date_from": "yesterday", "date_to": "2026-10-01"},
        ],
    )
    def test_bad_period_is_400(self, api, data, params):
        assert fetch(api, "billing", "pdf", **params).status_code == 400


# ---------------------------------------------------------------------------
# Periods
# ---------------------------------------------------------------------------


class TestPeriodParsing:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("billing report this month", (date(2026, 11, 1), date(2026, 11, 30))),
            ("report for last month", (date(2026, 10, 1), date(2026, 10, 31))),
            ("billing report for last quarter", (date(2026, 7, 1), date(2026, 9, 30))),
            ("report for this quarter", (date(2026, 10, 1), date(2026, 12, 31))),
            ("billing this financial year", (date(2026, 4, 1), date(2027, 3, 31))),
            ("billing last financial year", (date(2025, 4, 1), date(2026, 3, 31))),
            ("report from 1 Oct to 31 Oct", (date(2026, 10, 1), date(2026, 10, 31))),
            ("hearings from 2026-12-01 to 2026-12-15", (date(2026, 12, 1), date(2026, 12, 15))),
            ("hearings report for the next 30 days", (date(2026, 11, 11), date(2026, 12, 11))),
            ("hearings between 3 November 2026 and 9 November 2026", (date(2026, 11, 3), date(2026, 11, 9))),
        ],
    )
    def test_periods(self, text, expected):
        assert parsing.parse_period(text, today=TODAY) == expected

    def test_a_question_with_no_period(self):
        assert parsing.parse_period("billing report", today=TODAY) is None

    def test_january_wraps_to_last_december(self):
        assert parsing.parse_period("report last month", today=date(2027, 1, 5)) == (
            date(2026, 12, 1), date(2026, 12, 31)
        )

    def test_financial_year_before_april_belongs_to_the_previous_year(self):
        assert parsing.financial_year_start(date(2027, 2, 1)) == date(2026, 4, 1)


# ---------------------------------------------------------------------------
# The chat turn
# ---------------------------------------------------------------------------


def ask(api, query, **extra):
    resp = api.post(CHAT_URL, {"query": query, "client_request_id": rid(), **extra}, format="json")
    assert resp.status_code == 200, resp.content
    return resp.json()


class TestReportTurn:
    def test_billing_report_card_with_period(self, api, data):
        turn = ask(api, "Give me a billing report for this month")
        assert (turn["intent"], turn["status"], turn["action_card"]) == ("practice_report", "answer", None)
        assert turn["report"] == {
            "kind": "billing",
            "title": "Billing report",
            "date_from": "2026-11-01",
            "date_to": "2026-11-30",
            "row_count": 0,
            "formats": ["pdf", "docx"],
        }
        assert "PDF or a Word file" in turn["answer"]

    def test_default_billing_period_is_this_financial_year(self, api, data):
        card = ask(api, "billing report")["report"]
        assert (card["date_from"], card["date_to"], card["row_count"]) == ("2026-04-01", "2027-03-31", 2)

    def test_hearings_deadlines_and_cases_reports(self, api, data):
        hearings = ask(api, "Hearings report from 1 Oct to 31 Oct")["report"]
        assert (hearings["kind"], hearings["row_count"]) == ("hearings", 2)
        deadlines = ask(api, "export my deadlines")["report"]
        assert (deadlines["kind"], deadlines["row_count"], deadlines["date_from"]) == ("deadlines", 1, None)
        cases = ask(api, "report on my cases")["report"]
        assert (cases["kind"], cases["row_count"]) == ("cases", 2)

    def test_report_word_with_no_kind_is_a_question(self, api, data):
        turn = ask(api, "Make me a report")
        assert (turn["status"], turn["report"]) == ("needs_clarification", None)
        assert "billing, hearings, cases or deadlines" in turn["answer"]

    def test_the_card_never_carries_another_owners_figures(self, api, data):
        turn = ask(api, "billing report")
        assert "Secret" not in json.dumps(turn) and "INV-Z" not in json.dumps(turn)

    def test_replay_rebuilds_the_report_card(self, api, data):
        body = {"query": "billing report for this month", "client_request_id": rid()}
        first = api.post(CHAT_URL, body, format="json").json()
        again = api.post(CHAT_URL, body, format="json").json()
        assert again["report"] == first["report"] and first["report"] is not None

    def test_the_report_rule_beats_the_billing_rule_but_not_a_selected_case(self, api, data):
        assert ask(api, "How much is unpaid?")["intent"] == "billing_summary"
        assert ask(api, "unpaid fees report")["intent"] == "practice_report"
        scoped = ask(api, "billing report", case_id=data["mine"]["case"].id)
        assert scoped["intent"] == "billing_summary" and scoped["report"] is None
