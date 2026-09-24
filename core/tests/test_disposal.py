"""Disposed-of detection (core/services/disposal.py), on the real
WP/26147/2026 orders and eCourts page (fixtures/ecourts/README.md).

The case page must offer to close a disposed case, never close it itself,
and must not mistake an interim order for a final one.
"""

from datetime import date
from io import StringIO
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.management.commands.process_jobs import Command as ProcessJobsCommand
from core.models import Case, CourtFetchLog, CourtOrder, Document
from core.services.court_data.ecourts_parsing import parse_case_history_html
from core.services.court_tracking import _build_snapshot
from core.services.disposal import order_text_disposes_case, snapshot_says_disposed

FIXTURES = Path(__file__).parent / "fixtures" / "ecourts"
FINAL_ORDER = (FIXTURES / "order_HBHC010536082026_4_2026-08-17.txt").read_text(encoding="utf-8")
INTERIM_ORDER = (FIXTURES / "order_HBHC010536082026_3_2026-08-14.txt").read_text(encoding="utf-8")
CASE_PAGE = (FIXTURES / "hc_cnr_HBHC010536082026.html").read_text(encoding="utf-8")


class TestOrderText:
    def test_the_real_final_order_disposes_of_the_case(self):
        assert order_text_disposes_case(FINAL_ORDER)

    def test_the_real_interim_order_does_not(self):
        assert not order_text_disposes_case(INTERIM_ORDER)

    @pytest.mark.parametrize(
        "text",
        [
            "I.A. No.1 of 2026 is disposed of.",
            "The interlocutory application is dismissed.",
            "pending disposal of the writ petition, the respondents shall not act",
            "List the matter on 17.08.2026 for pronouncement of orders.",
            "The miscellaneous petition is allowed.",
        ],
    )
    def test_interim_disposals_are_not_the_case_ending(self, text):
        assert not order_text_disposes_case(text)

    @pytest.mark.parametrize(
        "text",
        [
            "In the result, the suit is decreed with costs.",
            "The appeal is accordingly allowed.",
            "Miscellaneous petitions pending, if any, shall stand closed.",
            "Accordingly, the Writ Petition is dismissed. No order as to costs.",
        ],
    )
    def test_final_formulas_are(self, text):
        assert order_text_disposes_case(text)


class TestEcourtsStatus:
    def test_the_real_case_page_reads_as_disposed(self):
        data = parse_case_history_html(CASE_PAGE)
        snapshot = _build_snapshot(data, [])["snapshot"]
        assert snapshot["case_status"] == "Case disposed"
        assert snapshot_says_disposed(snapshot)

    def test_a_pending_case_does_not(self):
        assert not snapshot_says_disposed({"case_status": "Pending", "nature_of_disposal": ""})
        assert not snapshot_says_disposed({"case_status": "", "nature_of_disposal": "--"})
        assert not snapshot_says_disposed(None)


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="disposal-advocate", password="pw-12345")


@pytest.fixture
def api(advocate):
    client = APIClient()
    client.force_authenticate(user=advocate)
    return client


@pytest.fixture
def case(advocate):
    return Case.objects.create(
        owner=advocate, case_number="WP/26147/2026", title="S.Sashi Kumar vs The State of Telangana",
        client_name="", cnr_number="HBHC010536082026", court_type="high_court", tracking_enabled=True,
        tracking_config={"court_type": "high_court", "cnr": "HBHC010536082026"},
    )


def _order(case, number, day, text):
    document = Document.objects.create(
        owner=case.owner, case=case, filename=f"o{number}.pdf", file_path=f"documents/o{number}.pdf",
        file_type="pdf", document_type="court_order", processing_status="completed", extracted_text=text,
    )
    return CourtOrder.objects.create(
        owner=case.owner, case=case, order_number=str(number), order_date=day,
        dedup_key=f"HBHC010536082026:{number}:{day}", document=document,
        summary_status=CourtOrder.SUMMARY_SUMMARIZED, summary_what_happened="x",
    )


@pytest.mark.django_db
class TestWorkerAndCasePage:
    def test_the_worker_flags_a_disposing_order(self, case):
        order = _order(case, 4, date(2026, 8, 17), FINAL_ORDER)
        ProcessJobsCommand(stdout=StringIO())._summarize_order_if_any(order.document_id)
        order.refresh_from_db()
        assert order.disposes_case is True

    def test_case_page_offers_to_close_but_leaves_the_status_alone(self, api, case):
        order = _order(case, 4, date(2026, 8, 17), FINAL_ORDER)
        CourtOrder.objects.filter(id=order.id).update(disposes_case=True)

        data = api.get(f"/api/cases/{case.id}/").data

        assert data["disposal"]["source"] == "order"
        assert data["disposal"]["order_id"] == order.id
        assert data["status"] == "open"
        case.refresh_from_db()
        assert case.status == "open"

    def test_only_the_latest_order_counts(self, api, case):
        old = _order(case, 1, date(2026, 8, 7), FINAL_ORDER)
        CourtOrder.objects.filter(id=old.id).update(disposes_case=True)
        _order(case, 2, date(2026, 8, 13), INTERIM_ORDER)
        assert api.get(f"/api/cases/{case.id}/").data["disposal"] is None

    def test_ecourts_status_alone_is_enough(self, api, case):
        data = parse_case_history_html(CASE_PAGE)
        CourtFetchLog.objects.create(owner=case.owner, case=case, success=True, fields_changed=_build_snapshot(data, []))

        body = api.get(f"/api/cases/{case.id}/").data

        assert body["disposal"] == {
            "source": "ecourts", "detail": "Contested--DISPOSED OF NO COSTS", "order_id": None, "order_date": None,
        }
        assert body["tracking_snapshot"]["case_status"] == "Case disposed"
        assert body["tracking_snapshot"]["court_and_judge"] == "APARESH KUMAR SINGH , G.M. MOHIUDDIN"
