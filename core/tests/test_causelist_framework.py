"""The framework's invariants: when a hearing may be told 'not listed', and
every way it may NOT be.

The Telangana fixtures are the document set (8 real PDFs, 58 listed on the
portal's index that day); `StaticAdapter` plays the portal.
"""

import datetime
import pathlib
import re

import pytest
from django.contrib.auth.models import User

from core.models import CauseListFetch, CauseListMatch, Hearing
from core.services.causelists import base, clock, service
from core.services.causelists.adapters.telangana_hc import get_adapter, parse_cause_list_pdf
from core.services.causelists.exceptions import CauseListParseError
from core.services.causelists.service import Decision, decide_outcome
from core.tests.causelist_support import StaticAdapter, make_case, make_doc, make_hearing, target_of

FIX = pathlib.Path(__file__).parent / "fixtures" / "causelists" / "live_2026-08-03"
DAY = datetime.date(2026, 8, 3)
L = Hearing


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="framework-advocate", password="pw-123456")


def tele_case(owner, number):
    return make_case(owner, number, tracking_config={"hc_court_code": "telangana", "cnr": "HBHC010051622026"})


def absent_hearing(owner, number="WP/99999/2099", day=DAY):
    return make_hearing(owner, tele_case(owner, number), day)


def docs():
    names = {
        "ADJOURNED MOTION LIST": "ADJOURNED_MOTION_LIST__B_Vijaysen_Reddy.pdf",
        "BAIL PETITIONS": "BAIL_PETITIONS__N_TUKARAMJI.pdf",
        "DAILY LIST-1": "DAILY_LIST_1__B_Vijaysen_Reddy.pdf",
        "DAILY LIST": "DAILY_LIST__APARESH_KUMAR_SINGH__G_M__MOHIUDDIN.pdf",
    }
    return [make_doc(FIX / n, doc_key=k, list_type=k) for k, n in names.items()]


def go(hearings, *, documents=None, parse_fn=None, params=None, day=DAY, **adapter_kw):
    adapter = StaticAdapter(
        "telangana_hc", docs() if documents is None else documents, parse_fn or get_adapter().parse, **adapter_kw
    )
    return service.process_group(adapter, target_of(adapter, "telangana_hc/1", params), day, hearings)


def status(hearing):
    hearing.refresh_from_db()
    return hearing.cause_list_status


# ---------------------------------------------------------------------------
# The decision function, in isolation
# ---------------------------------------------------------------------------


def decide(**over):
    base_args = dict(
        current_status=L.CAUSE_LIST_NOT_CHECKED, identity_empty=False, n_matches=0, index_status="ok",
        complete=True, n_unavailable=0, n_failed=0, n_total=3,
    )
    return decide_outcome(**{**base_args, **over})


class TestDecideOutcome:
    def test_a_match_is_always_listed(self):
        for index_status in ("ok", "none_available", "captcha_failed", "fetch_error"):
            for complete in (True, False):
                assert decide(n_matches=1, index_status=index_status, complete=complete).status == L.CAUSE_LIST_LISTED

    def test_only_a_complete_read_with_no_match_is_not_listed(self):
        assert decide(complete=True).status == L.CAUSE_LIST_NOT_LISTED

    @pytest.mark.parametrize(
        "kw,expected",
        [
            (dict(complete=False, n_unavailable=2), L.CAUSE_LIST_NOT_PUBLISHED),
            (dict(complete=False, n_failed=1), L.CAUSE_LIST_FETCH_FAILED),
            (dict(complete=False, n_failed=1, n_unavailable=2), L.CAUSE_LIST_FETCH_FAILED),
            (dict(complete=False), L.CAUSE_LIST_FETCH_FAILED),
            (dict(index_status="none_available"), L.CAUSE_LIST_NOT_PUBLISHED),
            (dict(index_status="captcha_failed"), L.CAUSE_LIST_FETCH_FAILED),
            (dict(index_status="fetch_error"), L.CAUSE_LIST_FETCH_FAILED),
            (dict(index_status="captcha_failed", complete=True), L.CAUSE_LIST_FETCH_FAILED),
        ],
    )
    def test_everything_short_of_a_complete_read_is_never_not_listed(self, kw, expected):
        assert decide(**kw).status == expected

    def test_without_an_identity_absence_proves_nothing(self):
        assert decide(identity_empty=True) is None

    def test_a_known_listing_is_never_downgraded_by_anything(self):
        for kw in (dict(complete=True), dict(complete=False, n_failed=1), dict(index_status="none_available"),
                   dict(index_status="captcha_failed")):
            assert decide(current_status=L.CAUSE_LIST_LISTED, **kw) is None

    def test_an_established_not_listed_survives_a_later_failure_but_not_a_later_match(self):
        assert decide(current_status=L.CAUSE_LIST_NOT_LISTED, index_status="captcha_failed") is None
        assert decide(current_status=L.CAUSE_LIST_NOT_LISTED, complete=False, n_failed=1) is None
        assert decide(current_status=L.CAUSE_LIST_NOT_LISTED, n_matches=1).status == L.CAUSE_LIST_LISTED

    def test_a_failure_overwrites_the_soft_states(self):
        for current in (L.CAUSE_LIST_NOT_CHECKED, L.CAUSE_LIST_NOT_PUBLISHED, L.CAUSE_LIST_FETCH_FAILED, L.CAUSE_LIST_UNSUPPORTED):
            assert decide(current_status=current, index_status="captcha_failed").status == L.CAUSE_LIST_FETCH_FAILED

    def test_notes_say_how_much_was_missing(self):
        assert decide(complete=False, n_unavailable=3, n_total=58).note == "3 of 58 lists not uploaded yet"
        assert decide(complete=False, n_failed=2, n_total=58).note == "2 of 58 lists could not be read"


class TestNotListedHasOneSource:
    def test_only_decide_outcome_ever_assigns_not_listed(self):
        """A grep over the code base: the constant appears in the model
        definition, in decide_outcome (once, as a Decision) and in the
        report counters -- and nowhere else."""
        root = pathlib.Path(service.__file__).resolve().parents[2]
        offenders = []
        for path in root.rglob("*.py"):
            rel = path.relative_to(root.parent).as_posix()
            if "/tests/" in rel or "/migrations/" in rel or path.name == "hearing.py":
                continue
            text = path.read_text(encoding="utf-8")
            if "CAUSE_LIST_NOT_LISTED" in text and not rel.endswith("causelists/service.py"):
                offenders.append(rel)
            if re.search(r"cause_list_status\s*=\s*['\"]not_listed['\"]", text):
                offenders.append(rel + " (literal)")
        assert offenders == []

        text = pathlib.Path(service.__file__).read_text(encoding="utf-8")
        assert text.count("Decision(L.CAUSE_LIST_NOT_LISTED") == 1


# ---------------------------------------------------------------------------
# Every failure mode, through the real pipeline: never 'not listed'
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEveryFailureModeIsNeverNotListed:
    def test_the_control_a_complete_read_does_say_not_listed(self, advocate):
        hearing = absent_hearing(advocate)
        report = go([hearing])
        assert report.complete and status(hearing) == L.CAUSE_LIST_NOT_LISTED

    def test_a_document_the_court_has_not_uploaded(self, advocate):
        hearing = absent_hearing(advocate)
        d = docs()
        d[1] = make_doc(None, doc_key="BAIL", list_type="BAIL PETITIONS", status="not_uploaded")
        report = go([hearing], documents=d)
        assert not report.complete and report.docs_unavailable == 1
        assert status(hearing) == L.CAUSE_LIST_NOT_PUBLISHED
        assert hearing.cause_list_note == "1 of 4 lists not uploaded yet"

    def test_a_document_that_could_not_be_downloaded(self, advocate):
        hearing = absent_hearing(advocate)
        d = docs()
        d[0] = make_doc(None, doc_key="X", list_type="X", status="fetch_error", error="timeout")
        report = go([hearing], documents=d)
        assert report.docs_failed == 1 and status(hearing) == L.CAUSE_LIST_FETCH_FAILED

    def test_a_document_the_parser_cannot_read(self, advocate):
        hearing = absent_hearing(advocate)
        real = get_adapter().parse
        calls = {"n": 0}

        def flaky(doc):
            calls["n"] += 1
            if calls["n"] == 2:
                raise CauseListParseError("layout changed")
            return real(doc)

        report = go([hearing], parse_fn=flaky)
        assert report.docs_failed == 1 and status(hearing) == L.CAUSE_LIST_FETCH_FAILED
        assert CauseListFetch.objects.get(status="parse_failed").error == "layout changed"

    def test_fewer_documents_than_the_index_lists(self, advocate):
        hearing = absent_hearing(advocate)
        report = go([hearing], doc_total=58)
        assert not report.complete and status(hearing) != L.CAUSE_LIST_NOT_LISTED

    def test_an_empty_index_that_claims_success(self, advocate):
        hearing = absent_hearing(advocate)
        report = go([hearing], documents=[], doc_total=0)
        assert not report.complete and status(hearing) != L.CAUSE_LIST_NOT_LISTED

    @pytest.mark.parametrize("index_status", ["captcha_failed", "fetch_error"])
    def test_an_index_that_could_not_be_fetched(self, advocate, index_status):
        hearing = absent_hearing(advocate)
        go([hearing], documents=[], status=index_status, doc_total=0, error="CAPTCHA budget exhausted")
        assert status(hearing) == L.CAUSE_LIST_FETCH_FAILED
        assert "CAPTCHA" in hearing.cause_list_note

    def test_an_early_exit_that_did_not_actually_find_everyone(self, advocate):
        hearing = absent_hearing(advocate)
        report = go([hearing], early_exit=True)
        assert not report.complete and status(hearing) != L.CAUSE_LIST_NOT_LISTED

    def test_a_target_that_only_covers_part_of_the_court(self, advocate):
        """E.g. Madras with the bench unknown: the Madurai lists are not served."""
        hearing = absent_hearing(advocate)
        report = go([hearing], params={"incomplete_scope": "bench not recorded and Madurai lists are not available"})
        assert not report.complete and status(hearing) != L.CAUSE_LIST_NOT_LISTED
        assert "Madurai" in hearing.cause_list_note

    def test_a_document_for_another_date(self, advocate):
        hearing = absent_hearing(advocate, day=datetime.date(2026, 8, 10))
        report = go([hearing], day=datetime.date(2026, 8, 10))
        assert report.docs_ok == 0 and status(hearing) == L.CAUSE_LIST_FETCH_FAILED

    def test_a_case_in_a_skipped_document_is_not_reported_absent(self, advocate):
        """THE latent bug of the old code: the one document that holds the
        case failed, the others were read, and the case read 'not listed'."""
        hearing = make_hearing(advocate, tele_case(advocate, "WA/102/2026"), DAY)  # is in DAILY LIST
        d = docs()
        d = [x for x in d if x.doc_key != "DAILY LIST"] + [
            make_doc(None, doc_key="DAILY LIST", list_type="DAILY LIST", status="not_uploaded")
        ]
        report = go([hearing], documents=d)
        assert not report.complete
        assert status(hearing) == L.CAUSE_LIST_NOT_PUBLISHED


@pytest.mark.django_db
class TestStatePersistence:
    def test_a_listed_hearing_survives_every_failed_run(self, advocate):
        hearing = make_hearing(advocate, tele_case(advocate, "WA/102/2026"), DAY)
        go([hearing])
        assert status(hearing) == L.CAUSE_LIST_LISTED
        for kw in (
            dict(documents=[], status="captcha_failed", doc_total=0),
            dict(documents=[], status="none_available", doc_total=0),
            dict(documents=[], status="fetch_error", doc_total=0),
            dict(doc_total=58),
        ):
            go([hearing], **kw)
            assert status(hearing) == L.CAUSE_LIST_LISTED
            assert hearing.cause_list_item_number == "1"
        assert hearing.cause_list_matches.count() == 1

    def test_an_established_not_listed_is_not_erased_by_a_failed_run(self, advocate):
        hearing = absent_hearing(advocate)
        go([hearing])
        go([hearing], documents=[], status="captcha_failed", doc_total=0)
        assert status(hearing) == L.CAUSE_LIST_NOT_LISTED

    def test_a_later_publication_upgrades_the_soft_states(self, advocate):
        hearing = make_hearing(advocate, tele_case(advocate, "WA/102/2026"), DAY)
        go([hearing], documents=[], status="none_available", doc_total=0)
        assert status(hearing) == L.CAUSE_LIST_NOT_PUBLISHED
        go([hearing], documents=[], status="captcha_failed", doc_total=0)
        assert status(hearing) == L.CAUSE_LIST_FETCH_FAILED
        go([hearing])
        assert status(hearing) == L.CAUSE_LIST_LISTED

    def test_a_not_listed_becomes_listed_when_the_case_appears(self, advocate):
        """A supplementary list adds the matter after the first read."""
        hearing = make_hearing(advocate, tele_case(advocate, "WA/102/2026"), DAY)
        go([hearing], documents=[d for d in docs() if d.doc_key == "BAIL PETITIONS"])
        assert status(hearing) == L.CAUSE_LIST_NOT_LISTED
        go([hearing])
        assert status(hearing) == L.CAUSE_LIST_LISTED

    def test_multiple_hits_are_all_kept_with_the_earliest_primary(self, advocate):
        hearing = make_hearing(advocate, tele_case(advocate, "WA/102/2026"), DAY)
        d = docs()
        go([hearing], documents=[d[3], d[3].__class__(**{**d[3].__dict__, "doc_key": "DUP", "list_type": "SUPPLEMENTARY"})])
        matches = list(hearing.cause_list_matches.order_by("-is_primary", "id"))
        assert len(matches) == 2
        assert matches[0].is_primary and matches[0].list_type == "DAILY LIST"
        assert {m.list_type for m in matches} == {"DAILY LIST", "SUPPLEMENTARY"}

    def test_the_match_table_is_replaced_not_appended_on_rerun(self, advocate):
        hearing = make_hearing(advocate, tele_case(advocate, "WA/102/2026"), DAY)
        go([hearing])
        go([hearing])
        assert CauseListMatch.objects.filter(hearing=hearing).count() == 1


# ---------------------------------------------------------------------------
# Marking unsupported, stale false states, ledger, temp files
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUnsupportedAndLedger:
    def test_unsupported_overrides_a_stale_false_state_and_clears_its_matches(self, advocate):
        hearing = make_hearing(advocate, make_case(advocate, "WP/1/2026", tracking_config={"hc_court_code": "kerala"}), DAY)
        hearing.cause_list_status = L.CAUSE_LIST_NOT_LISTED  # what the old Telangana-only code wrote
        hearing.cause_list_source = "telangana_hc"
        hearing.cause_list_item_number = "7"
        hearing.save()
        CauseListMatch.objects.create(owner=advocate, hearing=hearing, item_number="7")

        report = service.run([DAY])

        hearing.refresh_from_db()
        assert report.unsupported_marked == 1
        assert hearing.cause_list_status == L.CAUSE_LIST_UNSUPPORTED
        assert hearing.cause_list_item_number == ""
        assert "Kerala" in hearing.cause_list_note
        assert not hearing.cause_list_matches.exists()

    def test_completed_and_cancelled_hearings_are_not_checked(self, advocate):
        hearing = make_hearing(advocate, tele_case(advocate, "WA/102/2026"), DAY, status="completed")
        assert service.run([DAY]).groups == []
        assert status(hearing) == L.CAUSE_LIST_NOT_CHECKED

    def test_temp_files_never_outlive_the_group(self, advocate, tmp_path, monkeypatch):
        import tempfile

        made = []
        real = tempfile.mkdtemp
        monkeypatch.setattr(tempfile, "mkdtemp", lambda *a, **k: made.append(real(*a, **{**k, "dir": str(tmp_path)})) or made[-1])
        go([absent_hearing(advocate)])
        assert made and not pathlib.Path(made[0]).exists()

    def test_the_fixtures_themselves_are_never_deleted(self, advocate):
        before = sorted(p.name for p in FIX.glob("*.pdf"))
        go([absent_hearing(advocate)])
        assert sorted(p.name for p in FIX.glob("*.pdf")) == before

    def test_an_unreadable_document_is_recorded_in_the_ledger(self, advocate):
        d = docs()
        d[0] = make_doc(None, doc_key="GONE", list_type="GONE", status="not_uploaded")
        go([absent_hearing(advocate)], documents=d)
        assert CauseListFetch.objects.get(doc_key="GONE").status == "not_uploaded"
        assert CauseListFetch.objects.get(kind="index").doc_total == 4

    def test_an_unchanged_document_is_not_reparsed_when_every_hearing_is_final(self, advocate):
        hearing = absent_hearing(advocate)
        for doc in docs():
            doc.sha256 = doc.doc_key  # StaticAdapter copies; sha256 is what the ledger keys on
        parses = {"n": 0}
        real = get_adapter().parse

        def counting(doc):
            parses["n"] += 1
            return real(doc)

        go([hearing], parse_fn=counting)
        first = parses["n"]
        assert first == 4 and status(hearing) == L.CAUSE_LIST_NOT_LISTED
        go([hearing], parse_fn=counting)
        assert parses["n"] == first  # final hearing + same hashes: nothing re-read
        assert status(hearing) == L.CAUSE_LIST_NOT_LISTED


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRunBudget:
    def test_a_group_cut_by_the_time_budget_is_couldnt_check_never_not_listed(self, advocate, monkeypatch):
        hearing = make_hearing(advocate, tele_case(advocate, "WA/102/2026"), DAY)
        ticks = iter([0, 10_000, 10_000, 10_000, 10_000])
        report = service.run([DAY], max_minutes=1, monotonic=lambda: next(ticks, 10_000))
        assert any("time budget" in line for line in report.skipped)
        assert status(hearing) == L.CAUSE_LIST_FETCH_FAILED
        assert "budget" in hearing.cause_list_note

    def test_the_budget_never_downgrades_a_listing(self, advocate):
        hearing = make_hearing(advocate, tele_case(advocate, "WA/102/2026"), DAY)
        hearing.cause_list_status = L.CAUSE_LIST_LISTED
        hearing.save()
        ticks = iter([0, 10_000])
        service.run([DAY], max_minutes=1, monotonic=lambda: next(ticks, 10_000))
        assert status(hearing) == L.CAUSE_LIST_LISTED


# ---------------------------------------------------------------------------
# IST days, whatever the server clock says
# ---------------------------------------------------------------------------


class TestIstDays:
    def test_today_is_the_ist_date_even_when_utc_is_still_yesterday(self):
        # 19:00 UTC on 10 Oct is 00:30 IST on 11 Oct: the evening run must already be on the 11th.
        moment = datetime.datetime(2026, 10, 10, 19, 0, tzinfo=datetime.timezone.utc)
        assert clock.today(moment) == datetime.date(2026, 10, 11)
        assert moment.date() == datetime.date(2026, 10, 10)

    def test_day_bounds_are_ist_midnight_to_midnight(self):
        start, end = clock.day_bounds(datetime.date(2026, 10, 12))
        assert start.astimezone(datetime.timezone.utc) == datetime.datetime(2026, 10, 11, 18, 30, tzinfo=datetime.timezone.utc)
        assert end - start == datetime.timedelta(days=1)

    @pytest.mark.django_db
    def test_a_hearing_just_after_ist_midnight_belongs_to_its_ist_day(self, advocate):
        """00:30 IST on the 12th is 19:00 UTC on the 11th: a UTC-date filter
        would put it on the wrong list."""
        case = tele_case(advocate, "WA/102/2026")
        late = Hearing.objects.create(
            owner=advocate, case=case, hearing_type="other", status="scheduled", source="manual",
            hearing_date=datetime.datetime(2026, 10, 11, 19, 0, tzinfo=datetime.timezone.utc),
        )
        selected = service.select_hearings([datetime.date(2026, 10, 12)])
        assert [h.pk for h in selected] == [late.pk]
        assert clock.ist_date_of(late.hearing_date) == datetime.date(2026, 10, 12)
        assert service.select_hearings([datetime.date(2026, 10, 11)]) == []

    @pytest.mark.django_db
    def test_an_ecourts_hearing_stored_at_utc_midnight_is_on_the_same_ist_day(self, advocate):
        h = make_hearing(advocate, tele_case(advocate, "WA/102/2026"), datetime.date(2026, 10, 12))
        assert clock.ist_date_of(h.hearing_date) == datetime.date(2026, 10, 12)
        assert [x.pk for x in service.select_hearings([datetime.date(2026, 10, 12)])] == [h.pk]

    @pytest.mark.django_db
    def test_the_command_defaults_to_today_through_two_days_ahead_in_ist(self, advocate, monkeypatch):
        from django.core.management import call_command

        seen = {}
        monkeypatch.setattr(service, "run", lambda dates, **kw: seen.setdefault("dates", dates) and service.RunReport(dates=dates))
        monkeypatch.setattr(clock, "today", lambda now=None: datetime.date(2026, 10, 11))
        call_command("fetch_cause_lists", "--court", "telangana_hc")
        assert seen["dates"] == [datetime.date(2026, 10, 11), datetime.date(2026, 10, 12), datetime.date(2026, 10, 13)]


# ---------------------------------------------------------------------------
# The doctor command writes nothing
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDoctor:
    def test_it_fetches_parses_and_matches_without_writing(self, advocate, capsys, monkeypatch):
        from django.core.management import call_command

        hearing = make_hearing(advocate, tele_case(advocate, "WA/102/2026"), DAY)
        static = StaticAdapter("telangana_hc", docs(), get_adapter().parse)
        monkeypatch.setattr(type(get_adapter()), "fetch", lambda self, target, d, workdir: static.fetch(target, d, workdir))

        call_command(
            "causelist_doctor", "--adapter", "telangana_hc", "--target", "telangana_hc/1",
            "--date", "2026-08-03", "--number", "WP/99999/2099",
        )
        out = capsys.readouterr().out
        assert "read completely: yes" in out
        assert "hearing" in out and "listed" in out and "ad hoc: not_listed" in out
        assert "item        1  WA/102/2026" in out

        hearing.refresh_from_db()
        assert hearing.cause_list_status == L.CAUSE_LIST_NOT_CHECKED
        assert CauseListFetch.objects.count() == 0 and CauseListMatch.objects.count() == 0

    def test_it_says_when_a_hearing_could_not_be_decided(self, advocate, capsys, monkeypatch):
        from django.core.management import call_command

        static = StaticAdapter("telangana_hc", docs()[:2], get_adapter().parse, doc_total=4)
        monkeypatch.setattr(type(get_adapter()), "fetch", lambda self, target, d, workdir: static.fetch(target, d, workdir))
        call_command(
            "causelist_doctor", "--adapter", "telangana_hc", "--target", "telangana_hc/1",
            "--date", "2026-08-03", "--number", "WP/99999/2099",
        )
        assert "NO -- no hearing can be reported as not listed" in capsys.readouterr().out
