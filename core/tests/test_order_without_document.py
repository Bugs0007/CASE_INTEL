"""A CourtOrder with no PDF yet (download_status "pending") must be safe
everywhere an order is read.

Order sync now saves the row when the portal lists the order and fetches the
PDF afterwards, so `document` is null for as long as the download is
outstanding. Each reader below was audited for that; these keep it true.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Case, CourtOrder, Hearing
from core.serializers import CourtOrderSerializer, HearingSerializer
from core.services.client_updates.compose import what_happened_line
from core.services.disposal import case_disposal
from core.services.hearing_digest.assemble import assemble_hearing_digest
from core.services.order_summary import summarize_court_order
from core.services.tasks.from_orders import sync_order_tasks_for_case


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="nodoc-advocate", password="pw-12345")


@pytest.fixture
def case(advocate):
    return Case.objects.create(
        owner=advocate, case_number="OS/1/2026", title="A vs B", client_name="A",
        user_party_role="petitioner",
    )


@pytest.fixture
def pending_order(case):
    return CourtOrder.objects.create(
        owner=case.owner, case=case, order_number="1",
        order_date=(timezone.now() - timedelta(days=3)).date(),
        dedup_key="TSHC010030082026:1:x", download_status="pending", description="Interim order 1",
    )


@pytest.fixture
def api(advocate):
    client = APIClient()
    client.force_authenticate(user=advocate)
    return client


def test_order_serializer_says_there_is_no_file(pending_order):
    data = CourtOrderSerializer(pending_order).data
    assert data["has_file"] is False
    assert data["filename"] is None and data["file_size"] is None and data["processing_status"] is None


def test_orders_endpoint_lists_it_without_a_file(api, case, pending_order):
    body = api.get(f"/api/cases/{case.id}/orders/").json()
    assert [(o["order_number"], o["has_file"]) for o in body] == [("1", False)]


def test_file_endpoint_is_a_404_not_a_crash(api, pending_order):
    response = api.get(f"/api/orders/{pending_order.id}/file/")
    assert response.status_code == 404
    assert "no file" in response.json()["detail"].lower()


def test_hearing_serializer_shows_no_overview_for_it(case, pending_order):
    hearing = Hearing.objects.create(
        owner=case.owner, case=case, hearing_date=timezone.now() - timedelta(days=3), hearing_type="other",
    )
    assert HearingSerializer(hearing).data["order_summary"] is None


def test_hearing_digest_ignores_it(case, pending_order):
    hearing = Hearing.objects.create(
        owner=case.owner, case=case, hearing_date=timezone.now() + timedelta(days=2), hearing_type="other",
    )
    digest = assemble_hearing_digest(hearing)
    assert digest.last_order is None


def test_summarising_it_is_unreadable_without_an_llm_call(pending_order):
    summarize_court_order(pending_order)
    pending_order.refresh_from_db()
    assert pending_order.summary_status == CourtOrder.SUMMARY_UNREADABLE
    assert pending_order.summary_llm_calls == 0


def test_tasks_and_disposal_and_client_updates_do_not_choke(case, pending_order):
    assert sync_order_tasks_for_case(case) == []
    assert case_disposal(case, snapshot={}) is None
    assert what_happened_line(pending_order) == ""
