"""What the case page and its dialogs show -- the P1 "wrong data on screen"
fixes from the Phase 1 browser test.

  - staleness: old tracking data says "Outdated", never "None scheduled";
  - parties: petitioner/respondent from the record, else the title, and
    the same answer on the page and in generated documents;
  - billing: nothing is listed as owed at Rs. 0, and a Rs. 0 appearance fee
    can't be recorded by accident;
  - the document dialog: the court from the CNR, and "Save for next time";
  - all of it owner-scoped.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import AdvocateProfile, AppearanceFee, Case, ClientContact, Hearing
from core.services.court_tracking import tracking_freshness
from core.services.doc_templates import engine
from core.services.invoice_service import get_or_create_profile
from core.services.parties import case_parties, court_name_from_cnr


@pytest.fixture
def advocate(db):
    user = User.objects.create_user(username="page-advocate", password="pw-12345")
    get_or_create_profile(user)
    return user


@pytest.fixture
def api(advocate):
    client = APIClient()
    client.force_authenticate(user=advocate)
    return client


def _case(owner, number="WP/26147/2026", **extra):
    defaults = dict(title="S.Sashi Kumar vs The State of Telangana", client_name="")
    defaults.update(extra)
    return Case.objects.create(owner=owner, case_number=number, **defaults)


def _hearing(case, day, **extra):
    return Hearing.objects.create(
        owner=case.owner, case=case, source="ecourts", hearing_type="other",
        hearing_date=timezone.make_aware(datetime.combine(day, datetime.min.time())), **extra,
    )


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTrackingFreshness:
    def test_a_month_old_check_is_stale(self, advocate):
        case = _case(advocate, tracking_enabled=True, last_fetched_at=timezone.now() - timedelta(days=31))
        freshness = tracking_freshness(case)
        assert freshness["stale"] and freshness["reasons"] == ["last_checked"]

    def test_a_past_hearing_still_scheduled_is_stale_even_if_checked_today(self, advocate):
        """Case 38 in production: the 22 Sep hearing under Past, still
        "Scheduled"."""
        case = _case(advocate, tracking_enabled=True, last_fetched_at=timezone.now() - timedelta(hours=2))
        _hearing(case, timezone.localdate() - timedelta(days=1), status="scheduled")
        freshness = tracking_freshness(case)
        assert freshness["stale"]
        assert freshness["reasons"] == ["past_hearing_unconfirmed"]
        assert freshness["awaiting_update_count"] == 1

    def test_a_fresh_check_is_not_stale_and_says_when_refresh_unlocks(self, advocate):
        checked = timezone.now() - timedelta(minutes=7)
        case = _case(advocate, tracking_enabled=True, last_fetched_at=checked)
        freshness = tracking_freshness(case)
        assert not freshness["stale"]
        assert freshness["refresh_available_at"] == checked + timedelta(hours=1)

    def test_the_threshold_is_a_setting(self, advocate, settings):
        settings.TRACKING_STALE_DAYS = 45
        case = _case(advocate, tracking_enabled=True, last_fetched_at=timezone.now() - timedelta(days=31))
        assert not tracking_freshness(case)["stale"]

    def test_an_untracked_case_is_never_stale(self, advocate):
        assert not tracking_freshness(_case(advocate))["stale"]

    def test_case_page_carries_it(self, api, advocate):
        case = _case(advocate, tracking_enabled=True, last_fetched_at=timezone.now() - timedelta(days=31))
        assert api.get(f"/api/cases/{case.id}/").data["tracking_freshness"]["stale"] is True


# ---------------------------------------------------------------------------
# Parties
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestParties:
    def test_the_record_wins(self, advocate):
        case = _case(advocate, petitioner_name="S.Sashi Kumar", respondent_name="The State of Telangana",
                     user_party_role="petitioner", title="something else")
        parties = case_parties(case)
        assert (parties.petitioner, parties.respondent, parties.source) == (
            "S.Sashi Kumar", "The State of Telangana", "record",
        )
        assert parties.ours == "S.Sashi Kumar" and parties.opposing == "The State of Telangana"

    def test_the_title_when_there_is_no_record(self, advocate):
        """Case 38: "No client on file" though the title names both sides."""
        case = _case(advocate, number="OS/740/2015", title="K. Venkat Reddy vs P. Suresh", user_party_role="respondent")
        parties = case_parties(case)
        assert parties.source == "title"
        assert parties.ours == "P. Suresh"
        assert parties.opposing == "K. Venkat Reddy"

    def test_unknown_side_names_no_opposing_party(self, advocate):
        parties = case_parties(_case(advocate))
        assert parties.petitioner == "S.Sashi Kumar" and parties.opposing == ""

    def test_case_page_and_documents_agree(self, api, advocate):
        case = _case(advocate, number="OS/740/2015", title="K. Venkat Reddy vs P. Suresh", user_party_role="respondent")
        body = api.get(f"/api/cases/{case.id}/").data["parties"]
        assert body == {
            "petitioner": "K. Venkat Reddy", "respondent": "P. Suresh", "source": "title",
            "ours": "P. Suresh", "opposing": "K. Venkat Reddy",
        }
        memo = engine.resolve(engine.get_template("memo_of_appearance"), case=case,
                              profile=get_or_create_profile(advocate))
        values = memo.values
        assert values["petitioner"] == "K. Venkat Reddy"
        assert values["respondent"] == "P. Suresh"
        assert values["our_party"] == "P. Suresh"


# ---------------------------------------------------------------------------
# Court from the CNR
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCourtFromCnr:
    def test_high_court_prefixes_name_the_court(self):
        assert court_name_from_cnr("HBHC010536082026") == "High Court for the State of Telangana at Hyderabad"
        assert court_name_from_cnr("APHC010000012026") == "High Court of Andhra Pradesh at Amaravati"
        assert court_name_from_cnr("DLHC010000012026") == "High Court of Delhi"

    def test_district_and_unknown_prefixes_are_not_guessed(self):
        assert court_name_from_cnr("TSRR010007402015") == ""
        assert court_name_from_cnr("") == ""
        assert court_name_from_cnr("ESCR010000012026") == ""

    def test_the_document_dialog_no_longer_asks_for_the_court(self, advocate):
        """Case 28: the dialog asked for "Court" though the CNR is HBHC."""
        case = _case(advocate, cnr_number="HBHC010536082026")
        resolution = engine.resolve(engine.get_template("vakalatnama"), case=case,
                                    profile=get_or_create_profile(advocate))
        court = next(f for f in resolution.fields if f.name == "court")
        assert court.value == "High Court for the State of Telangana at Hyderabad"
        assert not court.missing


# ---------------------------------------------------------------------------
# Save for next time
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSaveForNextTime:
    def _setup(self, advocate):
        case = _case(advocate, cnr_number="HBHC010536082026",
                     petitioner_name="S.Sashi Kumar", respondent_name="The State of Telangana")
        contact = ClientContact.objects.create(owner=advocate, case=case, name="Karthik Bablu", role="primary")
        return case, contact

    def _inputs(self):
        return {
            "user_side": "Petitioner", "executant_relation": "S/o Raghavalu", "executant_age": "45",
            "executant_address": "Miyapur, Hyderabad", "advocate_name": "A. Rao",
            "bar_registration_number": "TS/1234/2010", "place": "Hyderabad",
        }

    def test_ticked_answers_are_written_back_and_the_rest_are_not(self, api, advocate):
        case, contact = self._setup(advocate)

        resp = api.post(
            f"/api/cases/{case.id}/generate-document/",
            {"template": "vakalatnama", "inputs": self._inputs(),
             "save": ["user_side", "executant_relation", "executant_age", "bar_registration_number", "place"]},
            format="json",
        )

        assert resp.status_code == 201, resp.data
        case.refresh_from_db()
        contact.refresh_from_db()
        profile = AdvocateProfile.objects.get(owner=advocate)
        assert case.user_party_role == "petitioner"
        assert (contact.relation_type, contact.relation_name, contact.age) == ("s/o", "Raghavalu", 45)
        assert contact.address == ""  # not ticked
        assert profile.bar_registration_number == "TS/1234/2010"
        assert profile.advocate_name == ""  # not ticked
        # "place" has no home on the record; asking to save it is a no-op.

    def test_the_side_is_a_choice_not_free_text(self, advocate):
        case, _ = self._setup(advocate)
        resolution = engine.resolve(engine.get_template("vakalatnama"), case=case,
                                    profile=get_or_create_profile(advocate), inputs={"user_side": "the plaintiff"})
        side = next(f for f in resolution.fields if f.name == "user_side")
        assert side.choices == ("Petitioner", "Respondent")
        assert side.missing  # "the plaintiff" is not an answer

    def test_an_unsaveable_answer_fails_before_anything_is_written(self, api, advocate):
        case, contact = self._setup(advocate)
        inputs = {**self._inputs(), "executant_relation": "son of Raghavalu"}

        resp = api.post(
            f"/api/cases/{case.id}/generate-document/",
            {"template": "vakalatnama", "inputs": inputs, "save": ["executant_age", "executant_relation"]},
            format="json",
        )

        assert resp.status_code == 400
        assert "S/o Name" in resp.data["detail"]
        contact.refresh_from_db()
        assert contact.age is None  # the earlier save in the same request rolled back
        assert not case.documents.exists()

    def test_another_advocates_case_is_a_404_and_saves_nothing(self, advocate):
        other = User.objects.create_user(username="page-other", password="pw-12345")
        get_or_create_profile(other)
        theirs = _case(other, number="WP/1/2026")
        client = APIClient()
        client.force_authenticate(user=advocate)

        resp = client.post(
            f"/api/cases/{theirs.id}/generate-document/",
            {"template": "vakalatnama", "inputs": {"user_side": "Respondent"}, "save": ["user_side"]},
            format="json",
        )

        assert resp.status_code == 404
        theirs.refresh_from_db()
        assert theirs.user_party_role == "unknown"


# ---------------------------------------------------------------------------
# Billing: nothing owed at Rs. 0
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestNothingOwedAtZero:
    def test_a_zero_charge_is_not_listed_as_owed(self, api, advocate):
        """WP/23998/2026 under "Cases not linked to a client" at Rs. 0.00."""
        zero = _case(advocate, number="WP/23998/2026")
        owed = _case(advocate, number="OS/1/2026")
        AppearanceFee.objects.create(owner=advocate, hearing=_hearing(zero, timezone.localdate()), amount=Decimal("0"))
        AppearanceFee.objects.create(owner=advocate, hearing=_hearing(owed, timezone.localdate()), amount=Decimal("5000"))

        body = api.get("/api/billing/portfolio/").data

        assert [row["case_number"] for row in body["unassigned"]] == ["OS/1/2026"]
        assert body["unassigned_total"] == 1

    def test_a_blank_appearance_fee_with_no_default_is_refused(self, api, advocate):
        case = _case(advocate)
        hearing = _hearing(case, timezone.localdate())

        resp = api.post("/api/appearance-fees/", {"hearing": hearing.id, "category": "appearance"}, format="json")

        assert resp.status_code == 400
        assert "default appearance fee" in str(resp.data["amount"])
        assert not AppearanceFee.objects.exists()


# ---------------------------------------------------------------------------
# Order documents are named for people, not for the file system
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_order_documents_read_as_order_number_and_date(api, advocate):
    from datetime import date

    from core.models import CourtOrder, Document

    case = _case(advocate)
    order_doc = Document.objects.create(
        owner=advocate, case=case, filename="HBHC010536082026_order_4_2026-08-17.pdf",
        file_path="documents/court_orders/x.pdf", file_type="pdf", document_type="court_order",
    )
    CourtOrder.objects.create(
        owner=advocate, case=case, order_number="4", order_date=date(2026, 8, 17),
        dedup_key="HBHC010536082026:4:2026-08-17", document=order_doc,
    )
    Document.objects.create(owner=advocate, case=case, filename="affidavit.pdf", file_path="d/a.pdf", file_type="pdf")

    rows = {d["filename"]: d for d in api.get("/api/documents/", {"case_id": case.id}).data}

    assert rows["HBHC010536082026_order_4_2026-08-17.pdf"]["display_name"] == "Order 4 · 17 Aug 2026"
    assert rows["affidavit.pdf"]["display_name"] == "affidavit.pdf"


@pytest.mark.django_db
def test_a_name_saved_from_the_document_dialog_re_signs_waiting_drafts(api, advocate):
    from core.models import ClientMessage

    AdvocateProfile.objects.filter(owner=advocate).update(letterhead_name="case intel law")
    case = _case(advocate, cnr_number="HBHC010536082026", petitioner_name="P", respondent_name="R",
                 user_party_role="petitioner")
    ClientContact.objects.create(
        owner=advocate, case=case, name="K", role="primary", relation_type="s/o", relation_name="R", age=40,
        address="Hyderabad",
    )
    draft = ClientMessage.objects.create(
        owner=advocate, case=case, kind="case_update", dedup_key="k1", subject="s",
        body="Dear K,\n\nRegards,\ncase intel law\n",
    )

    resp = api.post(
        f"/api/cases/{case.id}/generate-document/",
        {"template": "vakalatnama", "inputs": {"advocate_name": "S. Bhagath", "bar_registration_number": "TS/1/2015",
                                               "place": "Hyderabad"},
         "save": ["advocate_name"]},
        format="json",
    )

    assert resp.status_code == 201, resp.data
    draft.refresh_from_db()
    assert draft.body.endswith("Regards,\nS. Bhagath\ncase intel law\n")
