"""The rest of the 32 hard questions: comparisons, today's focus, attention,
follow-ups, finding a case by its client's name, festivals and a few Hindi
time words, the hearing brief, and the task / mark-paid / bulk cards.

Every turn goes through the real chat endpoint with the model factory
patched to fail, so each answer here is built from the owner's rows alone.
Another advocate's rows are created alongside to prove none of them leak.
"""
import uuid
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import AppearanceFee, Case, ClientContact, Hearing, Task
from core.services import invoice_service
from core.services.graph import practice_nodes
from core.services.india_time import INDIA_TZ
from core.services.practice_assistant import boundaries, cards, report_render, reports

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 11, 13, 10, 0, tzinfo=INDIA_TZ)  # a Friday
TODAY = NOW.date()
CHAT_URL = "/api/practice-assistant/chat/"


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
    with patch.object(practice_nodes, "get_llm_client", side_effect=AssertionError("the model was reached")):
        yield


@pytest.fixture(autouse=True)
def no_mail():
    with patch.object(invoice_service, "send_invoice", side_effect=AssertionError("an invoice was sent")):
        yield


@pytest.fixture
def anil(db):
    return User.objects.create_user(username="p1-anil", password="pw-12345")


@pytest.fixture
def other(db):
    return User.objects.create_user(username="p1-other", password="pw-12345")


@pytest.fixture
def api(anil):
    client = APIClient()
    client.force_authenticate(user=anil)
    return client


def at(day: date, hour: int = 10) -> datetime:
    return datetime(day.year, day.month, day.day, hour, 30, tzinfo=INDIA_TZ)


def case(owner, title, number, *, client="", contact=None, email="c@example.com"):
    row = Case.objects.create(owner=owner, title=title, case_number=number, client_name=client)
    if contact:
        ClientContact.objects.create(owner=owner, case=row, name=contact, email=email, is_billing_contact=True)
    return row


def hearing(owner, row, when, **extra):
    return Hearing.objects.create(owner=owner, case=row, hearing_date=when, hearing_type="other", **extra)


def fee(owner, row, amount, *, status="pending", number="", sent="not_sent", category="appearance", when=None, invoiced_days=0):
    h = hearing(owner, row, when or at(TODAY - timedelta(days=20 + Hearing.objects.count())))
    return AppearanceFee.objects.create(
        owner=owner, hearing=h, category=category, amount=Decimal(amount), status=status,
        invoice_number=number, invoice_pdf_path=f"invoices/{number}.pdf" if number else "",
        invoiced_at=NOW - timedelta(days=invoiced_days) if number else None, send_status=sent,
    )


def ask(api, query, **extra):
    resp = api.post(CHAT_URL, {"query": query, "client_request_id": str(uuid.uuid4()), **extra}, format="json")
    assert resp.status_code == 200, resp.content
    return resp.json()


@pytest.fixture
def practice(anil, other):
    rao = case(anil, "Rao vs State", "WP/1/2026", client="K. Rao", contact="K. Rao")
    sita = case(anil, "Sita vs Ram", "OS/2/2026", contact="Sita Devi")
    mehta = case(anil, "Mehta vs Union", "OS/3/2026", client="Mehta Industries")
    theirs = case(other, "Rao vs Other State", "WP/9/2026", client="K. Rao", contact="K. Rao")
    hearing(other, theirs, at(TODAY))
    fee(other, theirs, "99999.00", status="invoiced", number="OTH-1", invoiced_days=90)
    return {"rao": rao, "sita": sita, "mehta": mehta, "theirs": theirs}


class TestComparisons:
    def test_who_owes_the_most_is_summed_per_client_and_owner_only(self, api, anil, practice):
        fee(anil, practice["rao"], "15000.00", status="invoiced", number="INV-1")
        fee(anil, practice["rao"], "5000.00", status="invoiced", number="INV-2")
        fee(anil, practice["sita"], "14000.00", status="invoiced", number="INV-3")
        fee(anil, practice["mehta"], "90000.00", status="paid", number="INV-4")
        turn = ask(api, "which client owes me the most?")
        assert turn["intent"] == "compare"
        assert turn["answer"].startswith("**K. Rao** owes the most: **Rs. 20,000** across 2 unpaid invoices.")
        assert "Sita Devi: Rs. 14,000" in turn["answer"]
        assert "99,999" not in turn["answer"] and "Mehta" not in turn["answer"]
        assert {ref["kind"] for ref in turn["sources"]} == {"fee"}

    def test_low_fees_are_judged_against_the_category_median(self, api, anil, practice):
        for amount in ("10000.00", "11000.00", "12000.00", "3000.00"):
            fee(anil, practice["rao"], amount)
        turn = ask(api, "what billings are quite low compared to others?")
        assert "median Rs. 10,500" in turn["answer"]
        assert "1 fee is well below it" in turn["answer"] and "Rs. 3,000 (28% of the median)" in turn["answer"]

    def test_too_few_fees_says_so(self, api, anil, practice):
        fee(anil, practice["rao"], "15000.00")
        assert "too few to say" in ask(api, "which fees are the lowest?")["answer"]

    def test_oldest_case_by_filing_date(self, api, practice):
        Case.objects.filter(pk=practice["sita"].pk).update(filing_date=date(2019, 3, 1))
        Case.objects.filter(pk=practice["mehta"].pk).update(filing_date=date(2021, 6, 1))
        turn = ask(api, "which of my cases is the oldest pending one?")
        assert "**Sita vs Ram** (OS/2/2026), filed 01 Mar 2019, 7 years 8 months ago" in turn["answer"]

    def test_busier_week(self, api, anil, practice):
        hearing(anil, practice["rao"], at(TODAY + timedelta(days=8)))
        hearing(anil, practice["sita"], at(TODAY + timedelta(days=9)))
        hearing(anil, practice["mehta"], at(TODAY + timedelta(days=1)))
        turn = ask(api, "am I busier this week or next week?")
        assert turn["answer"].startswith("**Next week is busier** than this week.")
        assert "This week (13 Nov 2026 to 19 Nov 2026): 1 hearing" in turn["answer"]


class TestFocusAndAttention:
    def test_today_in_order(self, api, anil, practice):
        hearing(anil, practice["rao"], at(TODAY, 11))
        hearing(anil, practice["sita"], at(TODAY - timedelta(days=3)))  # past, no fee
        Task.objects.create(owner=anil, case=practice["mehta"], title="File reply", due_date=TODAY - timedelta(days=2))
        turn = ask(api, "what should I focus on today?")
        lines = turn["answer"].splitlines()
        assert lines[1] == "1. **Court today: 1 hearing**"
        assert "2. **Overdue: 1 task**" in lines
        assert "3. **Billing: 1 past hearing in the last 30 days has no fee recorded**" in lines

    def test_attention_gives_reasons_most_pressing_first(self, api, anil, practice):
        Task.objects.create(owner=anil, case=practice["sita"], title="File reply", due_date=TODAY - timedelta(days=2))
        hearing(
            anil, practice["mehta"], at(TODAY + timedelta(days=1)),
            cause_list_status=Hearing.CAUSE_LIST_NOT_LISTED,
        )
        fee(anil, practice["rao"], "15000.00", status="invoiced", number="INV-9", invoiced_days=45)
        turn = ask(api, "which cases need my attention and why?")
        assert turn["intent"] == "attention"
        assert "**Mehta vs Union**: hearing on 14 Nov 2026 is not on the court's cause list" in turn["answer"]
        assert "**Sita vs Ram**: task overdue since 11 Nov 2026: File reply" in turn["answer"]
        assert "INV-9 (Rs. 15,000) unpaid for 45 days" in turn["answer"]
        assert "Rao vs Other State" not in turn["answer"]


class TestFollowUps:
    def test_the_one_on_a_weekday_and_then_that(self, api, anil, practice):
        hearing(anil, practice["rao"], at(TODAY + timedelta(days=4)))  # Tuesday
        hearing(anil, practice["sita"], at(TODAY + timedelta(days=5)))  # Wednesday
        first = ask(api, "what hearings do I have this week?")
        second = ask(api, "and the one on tuesday, what's it about?", conversation_id=first["conversation_id"])
        assert second["intent"] == "case_facts"
        assert second["answer"].startswith("Taking that to mean **Rao vs State**")
        third = ask(api, "add a fee of 5000 for that", conversation_id=first["conversation_id"])
        assert third["intent"] == "propose_fee_create"
        assert third["action_card"]["case_id"] == practice["rao"].id
        assert third["action_card"]["amount"] == "5000.00"

    def test_several_matches_give_a_chooser(self, api, anil, practice):
        hearing(anil, practice["rao"], at(TODAY + timedelta(days=4)))
        hearing(anil, practice["sita"], at(TODAY + timedelta(days=4), 12))
        first = ask(api, "hearings this week")
        turn = ask(api, "the one on tuesday?", conversation_id=first["conversation_id"])
        assert turn["status"] == "needs_clarification"
        assert {c["id"] for c in turn["case_candidates"]} == {practice["rao"].id, practice["sita"].id}

    def test_no_previous_turn_means_no_follow_up(self, api, practice):
        assert ask(api, "add a fee of 5000 for that")["status"] == "needs_clarification"


class TestFindingCases:
    def test_a_client_contact_name_finds_the_case(self, api, practice):
        turn = ask(api, "write a letter to K. Rao telling him the next date")
        assert turn["action_card"]["kind"] == "start_draft"
        assert turn["action_card"]["case_id"] == practice["rao"].id

    def test_a_shared_name_across_owners_never_leaks(self, api, practice):
        turn = ask(api, "rao case next date")
        ids = {c["id"] for c in turn["case_candidates"]} or {turn["summary"]["case"]["id"]}
        assert practice["theirs"].id not in ids


class TestCalendarWords:
    def test_after_diwali(self):
        start, end, note = boundaries.festival_period("whats on after diwali", TODAY)
        assert (start, end) == (date(2026, 11, 9), date(2026, 11, 15))
        assert note == "Taking Diwali as 08 Nov 2026 (it was the nearest one)."

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("kal kya hai court mein", "tomorrow kya hai in court"),
            ("kal court mein kya hua", "yesterday in court kya hua"),
            ("agle hafte ki hearings", "next week ki hearings"),
        ],
    )
    def test_hindi_time_words(self, text, expected):
        assert boundaries.normalise_words(text) == expected

    def test_weekday_due_dates(self):
        assert cards.parse_due("by Monday", TODAY) == date(2026, 11, 16)
        assert cards.parse_due("by friday", TODAY) == date(2026, 11, 20)

    def test_task_wording(self):
        assert cards.parse_task("add a task to file the counter in Rao by Monday", TODAY) == {
            "title": "File the counter", "due_date": date(2026, 11, 16), "case_text": "Rao",
        }


class TestCards:
    def test_task_card_after_choosing_the_case(self, api, practice):
        turn = ask(api, "add a task to file the counter in Rao by Monday", case_id=practice["rao"].id)
        assert turn["action_card"] == {
            "kind": "create_task", "case_id": practice["rao"].id, "case_title": "Rao vs State",
            "title": "File the counter", "due_date": "2026-11-16", "blockers": [],
        }
        assert not Task.objects.exists()

    def test_mark_paid_card_and_its_blocker(self, api, anil, practice):
        fee(anil, practice["rao"], "15000.00", status="invoiced", number="INV-7")
        card = ask(api, "mark INV-7 as paid")["action_card"]
        assert (card["kind"], card["blockers"]) == ("mark_invoice_paid", [])
        fee(anil, practice["sita"], "100.00", status="paid", number="INV-8")
        assert ask(api, "mark INV-8 as paid")["action_card"]["blockers"] == [cards.BLOCKER_ALREADY_PAID]
        turn = ask(api, "mark OTH-1 as paid")
        assert turn["action_card"] is None
        assert turn["answer"] == "No invoice numbered OTH-1 is recorded in your account."

    def test_bulk_fees_lists_only_unbilled_owned_hearings(self, api, anil, practice):
        billed = fee(anil, practice["rao"], "1.00", when=at(TODAY - timedelta(days=3))).hearing
        free = hearing(anil, practice["sita"], at(TODAY - timedelta(days=2)))
        hearing(anil, practice["mehta"], at(TODAY - timedelta(days=20)))  # outside last week
        card = ask(api, "bill all my hearings from last week")["action_card"]
        assert [row["hearing_id"] for row in card["rows"]] == [free.id]
        assert billed.id not in [row["hearing_id"] for row in card["rows"]]
        assert AppearanceFee.objects.filter(owner=anil).count() == 1

    def test_bulk_send_rows_carry_their_blockers(self, api, anil, practice):
        fee(anil, practice["rao"], "15000.00", status="invoiced", number="INV-1")
        fee(anil, practice["mehta"], "100.00", status="invoiced", number="INV-2")  # no billing contact
        fee(anil, practice["sita"], "100.00", status="invoiced", number="INV-3", sent="sent")
        card = ask(api, "send all unpaid invoices")["action_card"]
        rows = {row["invoice_number"]: row for row in card["rows"]}
        assert set(rows) == {"INV-1", "INV-2"}
        assert rows["INV-1"]["blockers"] == [] and rows["INV-2"]["blockers"]

    def test_the_only_hotel_charge_is_found_without_a_case(self, api, anil, practice):
        hotel = fee(anil, practice["sita"], "4000.00", category="hotel")
        card = ask(api, "remove the hotel charge")["action_card"]
        assert (card["kind"], card["fee_id"]) == ("delete_fee", hotel.id)


class TestBrief:
    def test_brief_sections_and_files(self, anil, practice):
        hearing(anil, practice["rao"], at(TODAY + timedelta(days=1)), purpose="Arguments")
        Task.objects.create(owner=anil, case=practice["rao"], title="File reply", due_date=TODAY - timedelta(days=1))
        report = reports.build_report(owner=anil, kind="brief", now=NOW)
        assert report["title"] == "Hearing brief" and report["row_count"] == 1
        section = report["blocks"][0]
        assert section["type"] == "section" and section["heading"] == "Rao vs State (WP/1/2026)"
        assert "Be ready for: Arguments" in section["bullets"]
        assert "Overdue since 12 Nov 2026: File reply" in section["bullets"]
        assert report_render.render(report, "pdf").startswith(b"%PDF")
        assert report_render.render(report, "docx")[:2] == b"PK"

    def test_brief_endpoint_is_owner_scoped(self, api, anil, other, practice):
        hearing(other, practice["theirs"], at(TODAY + timedelta(days=1)))
        resp = api.get("/api/practice-assistant/reports/brief/pdf/")
        assert resp.status_code == 200
        assert b"Other State" not in resp.content
