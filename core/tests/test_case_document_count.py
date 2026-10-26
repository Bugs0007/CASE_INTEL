"""`document_count` on the Cases list (GET /api/cases/).

The Cases page reads each card's "N docs" off this one field. It must be the
number of Document rows linked to the case -- on a fresh request, with no
refresh needed first. (The refresh-then-fresh-request flow and the query
count live in test_order_sync_status.py.)
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Case, Document, Hearing


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="doccount-advocate", password="pw-12345")


@pytest.fixture
def other(db):
    return User.objects.create_user(username="doccount-other", password="pw-12345")


def _api(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _case(owner, number, **extra):
    return Case.objects.create(owner=owner, case_number=number, title=number, client_name="C", **extra)


def _doc(case, n=0, **extra):
    return Document.objects.create(
        owner=case.owner, case=case, filename=f"d{n}.pdf", file_path=f"documents/d{n}.pdf", **extra
    )


def _counts(user, **params):
    response = _api(user).get("/api/cases/", params)
    assert response.status_code == 200
    return {c["case_number"]: c["document_count"] for c in response.json()}


class TestListDocumentCount:
    def test_counts_documents_on_a_fresh_request(self, advocate):
        with_docs = _case(advocate, "A/1")
        empty = _case(advocate, "A/2")
        for i in range(3):
            _doc(with_docs, i)

        assert _counts(advocate) == {"A/1": 3, "A/2": 0}
        assert empty.documents.count() == 0

    def test_every_processing_status_and_type_is_counted(self, advocate):
        case = _case(advocate, "A/1")
        for i, status in enumerate(["pending", "processing", "completed", "failed"]):
            _doc(case, i, processing_status=status)
        _doc(case, 9, document_type="court_order")

        assert _counts(advocate) == {"A/1": 5}

    def test_other_advocates_documents_are_not_counted_or_hidden(self, advocate, other):
        mine = _case(advocate, "A/1")
        theirs = _case(other, "B/1")
        _doc(mine, 1)
        _doc(theirs, 2)
        _doc(theirs, 3)

        assert _counts(advocate) == {"A/1": 1}
        assert _counts(other) == {"B/1": 2}

    def test_counts_survive_the_list_filters_and_the_since_param(self, advocate):
        open_case = _case(advocate, "A/1", status="open")
        closed = _case(advocate, "A/2", status="closed")
        _doc(open_case, 1)
        _doc(closed, 2)
        _doc(closed, 3)
        since = (timezone.now() - timedelta(days=1)).isoformat()

        assert _counts(advocate, status="open") == {"A/1": 1}
        assert _counts(advocate, status="closed") == {"A/2": 2}
        assert _counts(advocate, since=since) == {"A/1": 1, "A/2": 2}

    def test_documents_are_not_multiplied_by_hearings_emails_or_chats(self, advocate):
        case = _case(advocate, "A/1")
        _doc(case, 1)
        _doc(case, 2)
        for day in range(3):
            Hearing.objects.create(
                owner=advocate,
                case=case,
                hearing_date=timezone.now() + timedelta(days=day + 1),
                hearing_type="other",
            )

        body = _api(advocate).get("/api/cases/").json()[0]
        assert body["document_count"] == 2
        assert body["hearing_count"] == 3
