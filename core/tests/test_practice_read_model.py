"""The practice read model (core/services/practice_assistant/reads.py):
owner isolation on every read, India-day windows, calendar inclusion and
marker rules, exact totals against pages and caps, and a fixed query count
per read."""

from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone

import pytest
from django.contrib.auth.models import User

from core.models import Case, CaseEvent, Hearing, Task
from core.services.india_time import INDIA_TZ
from core.services.practice_assistant import reads
from core.services.practice_assistant.contracts import HARD_ROW_CAP, MAX_RANGE_DAYS, PAGE_SIZE

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 11, 11, 10, 0, tzinfo=INDIA_TZ)
TODAY = date(2026, 11, 11)


def ist(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=INDIA_TZ)


@pytest.fixture
def anil():
    return User.objects.create_user(username="read-anil", password="pw-12345")


@pytest.fixture
def bina():
    return User.objects.create_user(username="read-bina", password="pw-12345")


_seq = iter(range(1, 100000))


def make_case(owner, title="Rao vs State", **extra):
    values = {"owner": owner, "title": title, "case_number": f"OS/{next(_seq)}/2026"}
    values.update(extra)
    return Case.objects.create(**values)


def make_hearing(case, when, **extra):
    values = {"owner": case.owner, "case": case, "hearing_date": when, "hearing_type": "other"}
    values.update(extra)
    return Hearing.objects.create(**values)


def make_task(owner, case=None, **extra):
    values = {"owner": owner, "case": case, "title": "File counter"}
    values.update(extra)
    return Task.objects.create(**values)


def make_event(case, day, **extra):
    values = {"owner": case.owner, "case": case, "title": "Mediation", "date": day}
    values.update(extra)
    return CaseEvent.objects.create(**values)


def ids(entries, kind=None):
    return [e["id"] for e in entries if kind is None or e["kind"] == kind]


# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------


class TestArguments:
    def test_owner_is_keyword_only_and_required(self):
        for read in (
            reads.portfolio_snapshot,
            reads.open_deadlines,
        ):
            with pytest.raises(TypeError):
                read()
        with pytest.raises(TypeError):
            reads.calendar_window(date_from=TODAY, date_to=TODAY)
        with pytest.raises(TypeError):
            reads.case_facts(case_id=1)
        with pytest.raises(TypeError):
            reads.resolve_case_candidates(text="x")

    def test_only_personal_scope(self, anil):
        with pytest.raises(ValueError):
            reads.portfolio_snapshot(owner=anil, scope="firm")
        with pytest.raises(ValueError):
            reads.calendar_window(owner=anil, scope="firm", date_from=TODAY, date_to=TODAY)
        with pytest.raises(ValueError):
            reads.open_deadlines(owner=anil, scope="firm")
        with pytest.raises(ValueError):
            reads.case_facts(owner=anil, scope="firm", case_id=1)
        with pytest.raises(ValueError):
            reads.resolve_case_candidates(owner=anil, scope="firm", text="x")

    def test_range_limits(self, anil):
        longest = TODAY + timedelta(days=MAX_RANGE_DAYS - 1)
        assert reads.calendar_window(owner=anil, date_from=TODAY, date_to=longest, now=NOW)["total"] == 0
        with pytest.raises(ValueError):
            reads.calendar_window(owner=anil, date_from=TODAY, date_to=longest + timedelta(days=1))
        with pytest.raises(ValueError):
            reads.calendar_window(owner=anil, date_from=TODAY, date_to=TODAY - timedelta(days=1))
        with pytest.raises(ValueError):
            reads.calendar_window(owner=anil, date_from=TODAY, date_to=TODAY, kinds=["fee"])

    def test_bad_paging(self, anil):
        with pytest.raises(ValueError):
            reads.portfolio_snapshot(owner=anil, page=0)
        with pytest.raises(ValueError):
            reads.open_deadlines(owner=anil, limit=0)

    def test_as_of_and_timezone(self, anil):
        for result in (
            reads.portfolio_snapshot(owner=anil, now=NOW),
            reads.calendar_window(owner=anil, date_from=TODAY, date_to=TODAY, now=NOW),
            reads.open_deadlines(owner=anil, now=NOW),
        ):
            assert result["as_of"] == "2026-11-11T10:00:00+05:30"
            assert result["timezone"] == "Asia/Kolkata"

    def test_default_clock_is_india_time(self, anil):
        assert reads.open_deadlines(owner=anil)["as_of"].endswith("+05:30")


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


class TestPortfolio:
    def test_empty(self, anil):
        snap = reads.portfolio_snapshot(owner=anil, now=NOW)
        assert snap["status_counts"] == {}
        assert snap["total_cases"] == snap["active_cases"] == snap["total"] == 0
        assert snap["active_with_next_hearing"] == snap["active_without_next_date"] == 0
        assert snap["cases"] == []

    def test_counts_and_next_hearing(self, anil):
        two_future = make_case(anil, "Two future")
        make_hearing(two_future, ist(2026, 11, 20, 10, 30))
        make_hearing(two_future, ist(2026, 11, 14, 10, 30))
        make_case(anil, "No hearing at all")
        past_only = make_case(anil, "Past only", status="pending")
        make_hearing(past_only, ist(2026, 11, 1, 10, 30))
        cancelled_future = make_case(anil, "Cancelled future")
        make_hearing(cancelled_future, ist(2026, 11, 15, 10, 30), status="cancelled")
        closed = make_case(anil, "Closed with future", status="closed")
        make_hearing(closed, ist(2026, 11, 15, 10, 30))
        make_case(anil, "Archived", status="archived")

        snap = reads.portfolio_snapshot(owner=anil, now=NOW)
        assert snap["status_counts"] == {"open": 3, "pending": 1, "closed": 1, "archived": 1}
        assert snap["total_cases"] == 6
        assert snap["active_cases"] == 4
        assert snap["active_with_next_hearing"] == 1  # two future hearings, one case
        assert snap["active_without_next_date"] == 3
        rows = {row["title"]: row for row in snap["cases"]}
        assert rows["Two future"]["next_hearing_at"] == "2026-11-14T10:30:00+05:30"
        assert rows["No hearing at all"]["next_hearing_at"] is None
        assert rows["Past only"]["next_hearing_at"] is None
        assert rows["Cancelled future"]["next_hearing_at"] is None
        assert rows["Closed with future"]["next_hearing_at"] == "2026-11-15T10:30:00+05:30"
        assert set(rows["Two future"]) == {"id", "title", "case_number", "court", "status", "next_hearing_at"}

    def test_court_comes_from_recorded_hearing_location(self, anil):
        case = make_case(anil)
        make_hearing(case, ist(2026, 11, 14), location="City Civil Court, Hyderabad")
        bare = make_case(anil, "Bare")
        rows = {r["id"]: r for r in reads.portfolio_snapshot(owner=anil, now=NOW)["cases"]}
        assert rows[case.id]["court"] == "City Civil Court, Hyderabad"
        assert rows[bare.id]["court"] is None

    def test_totals_are_independent_of_the_page(self, anil):
        for index in range(7):
            make_case(anil, f"Open {index}")
        for index in range(3):
            make_case(anil, f"Closed {index}", status="closed")

        first = reads.portfolio_snapshot(owner=anil, page=1, page_size=3, now=NOW)
        assert (len(first["cases"]), first["total"], first["total_cases"]) == (3, 10, 10)
        last = reads.portfolio_snapshot(owner=anil, page=4, page_size=3, now=NOW)
        assert (len(last["cases"]), last["total"]) == (1, 10)
        beyond = reads.portfolio_snapshot(owner=anil, page=9, page_size=3, now=NOW)
        assert (beyond["cases"], beyond["total"]) == ([], 10)

        seen = []
        for page in range(1, 5):
            seen += [r["id"] for r in reads.portfolio_snapshot(owner=anil, page=page, page_size=3, now=NOW)["cases"]]
        assert len(seen) == len(set(seen)) == 10

        closed = reads.portfolio_snapshot(owner=anil, status="closed", page_size=2, now=NOW)
        assert (len(closed["cases"]), closed["total"], closed["total_cases"]) == (2, 3, 10)
        assert closed["status_counts"] == {"open": 7, "closed": 3}
        assert reads.portfolio_snapshot(owner=anil, status="archived", now=NOW)["total"] == 0

    def test_page_size_is_capped(self, anil):
        snap = reads.portfolio_snapshot(owner=anil, page_size=5000, now=NOW)
        assert snap["page_size"] == HARD_ROW_CAP

    def test_isolation(self, anil, bina):
        mine = make_case(anil, "Rao vs State")
        theirs = make_case(bina, "Rao vs State")
        make_hearing(theirs, ist(2026, 11, 14))
        make_case(bina, "Other", status="closed")

        snap = reads.portfolio_snapshot(owner=anil, now=NOW)
        assert snap["status_counts"] == {"open": 1}
        assert snap["active_with_next_hearing"] == 0
        assert [r["id"] for r in snap["cases"]] == [mine.id]
        assert snap["cases"][0]["next_hearing_at"] is None

    def test_another_owners_hearing_on_my_case_is_ignored(self, anil, bina):
        """Rows are filtered by their own owner as well as the case's."""
        mine = make_case(anil)
        Hearing.objects.create(owner=bina, case=mine, hearing_date=ist(2026, 11, 14), hearing_type="other")
        snap = reads.portfolio_snapshot(owner=anil, now=NOW)
        assert snap["active_with_next_hearing"] == 0
        assert snap["cases"][0]["next_hearing_at"] is None
        window = reads.calendar_window(owner=anil, date_from=TODAY, date_to=date(2026, 11, 20), now=NOW)
        assert window["total"] == 0
        assert reads.case_facts(owner=anil, case_id=mine.id, now=NOW)["next_hearing"] is None


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


class TestCalendarWindow:
    def test_hearing_at_0030_ist_is_on_its_india_day(self, anil):
        case = make_case(anil)
        # 00:30 IST on the 7th is 19:00 UTC on the 6th.
        hearing = make_hearing(case, ist(2026, 11, 7, 0, 30), source="manual")

        on_7th = reads.calendar_window(owner=anil, date_from=date(2026, 11, 7), date_to=date(2026, 11, 7), now=NOW)
        assert ids(on_7th["entries"]) == [hearing.id]
        entry = on_7th["entries"][0]
        assert entry["day"] == "2026-11-07"
        assert entry["start_time"] == "00:30"
        assert entry["ref"]["recorded_at"] == "2026-11-07T00:30:00+05:30"
        assert on_7th["day_markers"] == {"2026-11-07": {"hearing": 1, "task": 0, "event": 0}}

        on_6th = reads.calendar_window(owner=anil, date_from=date(2026, 11, 6), date_to=date(2026, 11, 6), now=NOW)
        assert on_6th["entries"] == [] and on_6th["day_markers"] == {}

    def test_portal_date_hearing_is_untimed(self, anil):
        case = make_case(anil)
        # eCourts stores the portal's date as 00:00 UTC.
        hearing = make_hearing(
            case, datetime(2026, 11, 12, tzinfo=dt_timezone.utc), source="ecourts", purpose="FOR ORDERS",
        )
        window = reads.calendar_window(owner=anil, date_from=date(2026, 11, 12), date_to=date(2026, 11, 12), now=NOW)
        entry = window["entries"][0]
        assert (entry["id"], entry["day"], entry["start_time"]) == (hearing.id, "2026-11-12", None)
        assert entry["label"] == "FOR ORDERS"
        assert entry["provenance"] == "ecourts"
        assert entry["ref"] == {
            "kind": "hearing",
            "id": hearing.id,
            "case_id": case.id,
            "label": "FOR ORDERS",
            "recorded_at": "2026-11-12",
        }

    def test_range_end_day_included_and_next_day_excluded(self, anil):
        case = make_case(anil)
        last_minute = make_hearing(case, ist(2026, 11, 15, 23, 59))
        make_hearing(case, ist(2026, 11, 16, 0, 0))  # first instant of the next day
        make_hearing(case, ist(2026, 11, 9, 23, 59))  # last minute before the range
        first_minute = make_hearing(case, ist(2026, 11, 10, 0, 0))
        end_task = make_task(anil, case, due_date=date(2026, 11, 15))
        make_task(anil, case, due_date=date(2026, 11, 16))
        end_event = make_event(case, date(2026, 11, 15))
        make_event(case, date(2026, 11, 16))

        window = reads.calendar_window(owner=anil, date_from=date(2026, 11, 10), date_to=date(2026, 11, 15), now=NOW)
        assert ids(window["entries"], "hearing") == [first_minute.id, last_minute.id]
        assert ids(window["entries"], "task") == [end_task.id]
        assert ids(window["entries"], "event") == [end_event.id]
        assert window["total"] == 4
        assert set(window["day_markers"]) == {"2026-11-10", "2026-11-15"}
        assert (window["date_from"], window["date_to"]) == ("2026-11-10", "2026-11-15")

    def test_task_rules(self, anil):
        case = make_case(anil)
        day = date(2026, 11, 12)
        open_task = make_task(anil, case, due_date=day, kind="order_direction", needs_review=True)
        done = make_task(anil, case, due_date=day, status="completed")
        make_task(anil, case, due_date=day, status="cancelled")  # dismissed
        make_task(anil, case, due_date=None)  # undated
        no_case = make_task(anil, None, due_date=day, status="in_progress")

        window = reads.calendar_window(owner=anil, date_from=day, date_to=day, now=NOW)
        assert ids(window["entries"]) == [open_task.id, done.id, no_case.id]
        by_id = {e["id"]: e for e in window["entries"]}
        assert by_id[done.id]["status"] == "completed"
        assert by_id[open_task.id]["provenance"] == "order_direction"
        assert by_id[open_task.id]["needs_review"] is True
        assert by_id[no_case.id]["case_id"] is None and by_id[no_case.id]["case_title"] is None
        assert window["total"] == 3
        # Markers count open tasks only.
        assert window["day_markers"] == {"2026-11-12": {"hearing": 0, "task": 2, "event": 0}}

    def test_cancelled_event_and_hearing_stay_but_only_the_event_leaves_the_markers(self, anil):
        case = make_case(anil)
        day = date(2026, 11, 12)
        live = make_event(case, day, start_time=time(10, 30), end_time=time(12, 0))
        cancelled = make_event(case, day, status="cancelled")
        done = make_event(case, day, status="completed", start_time=time(9, 0))
        cancelled_hearing = make_hearing(case, ist(2026, 11, 12, 11, 0), status="cancelled")

        window = reads.calendar_window(owner=anil, date_from=day, date_to=day, now=NOW)
        # hearing first; then events: all-day, 09:00, 10:30.
        assert ids(window["entries"]) == [cancelled_hearing.id, cancelled.id, done.id, live.id]
        by_key = {(e["kind"], e["id"]): e for e in window["entries"]}
        assert by_key[("event", cancelled.id)]["status"] == "cancelled"
        assert by_key[("hearing", cancelled_hearing.id)]["status"] == "cancelled"
        assert by_key[("event", live.id)]["start_time"] == "10:30"
        assert by_key[("event", live.id)]["end_time"] == "12:00"
        assert by_key[("event", cancelled.id)]["start_time"] is None
        assert window["total"] == 4
        assert window["day_markers"] == {"2026-11-12": {"hearing": 1, "task": 0, "event": 2}}

    def test_order_is_day_then_hearing_event_task_then_time_then_id(self, anil):
        case = make_case(anil)
        d1, d2 = date(2026, 11, 12), date(2026, 11, 13)
        task_d1 = make_task(anil, case, due_date=d1)
        event_d1 = make_event(case, d1)
        late = make_hearing(case, ist(2026, 11, 12, 15, 0))
        early = make_hearing(case, ist(2026, 11, 12, 10, 0))
        task_d2_a = make_task(anil, case, due_date=d2)
        task_d2_b = make_task(anil, case, due_date=d2)
        hearing_d2 = make_hearing(case, ist(2026, 11, 13, 9, 0))

        window = reads.calendar_window(owner=anil, date_from=d1, date_to=d2, now=NOW)
        assert [(e["kind"], e["id"]) for e in window["entries"]] == [
            ("hearing", early.id),
            ("hearing", late.id),
            ("event", event_d1.id),
            ("task", task_d1.id),
            ("hearing", hearing_d2.id),
            ("task", task_d2_a.id),
            ("task", task_d2_b.id),
        ]

    def test_kinds_and_case_filters(self, anil):
        case, other = make_case(anil, "A"), make_case(anil, "B")
        day = date(2026, 11, 12)
        hearing = make_hearing(case, ist(2026, 11, 12, 10, 0))
        make_hearing(other, ist(2026, 11, 12, 10, 0))
        task = make_task(anil, case, due_date=day)
        make_task(anil, None, due_date=day)
        make_event(other, day)

        only_tasks = reads.calendar_window(owner=anil, date_from=day, date_to=day, kinds=["task"], now=NOW)
        assert {e["kind"] for e in only_tasks["entries"]} == {"task"}
        assert only_tasks["total"] == 2
        assert only_tasks["day_markers"] == {"2026-11-12": {"hearing": 0, "task": 2, "event": 0}}

        one_case = reads.calendar_window(owner=anil, date_from=day, date_to=day, case_id=case.id, now=NOW)
        assert [(e["kind"], e["id"]) for e in one_case["entries"]] == [("hearing", hearing.id), ("task", task.id)]
        assert one_case["entries"][0]["case_title"] == "A"

    def test_hard_cap_sets_truncated_and_keeps_exact_totals(self, anil):
        case = make_case(anil)
        d1, d2 = date(2026, 11, 12), date(2026, 11, 13)
        Task.objects.bulk_create(
            [Task(owner=anil, case=case, title=f"T{i}", due_date=d2) for i in range(HARD_ROW_CAP + 20)]
        )
        events = [make_event(case, d1) for _ in range(3)]

        window = reads.calendar_window(owner=anil, date_from=d1, date_to=d2, now=NOW)
        assert len(window["entries"]) == HARD_ROW_CAP
        assert window["truncated"] is True
        assert window["total"] == HARD_ROW_CAP + 23
        # The earliest rows survive the cut, whatever their kind.
        assert ids(window["entries"][:3], "event") == [e.id for e in events]
        assert window["day_markers"] == {
            "2026-11-12": {"hearing": 0, "task": 0, "event": 3},
            "2026-11-13": {"hearing": 0, "task": HARD_ROW_CAP + 20, "event": 0},
        }

        small = reads.calendar_window(owner=anil, date_from=d1, date_to=d1, now=NOW)
        assert small["truncated"] is False and small["total"] == 3

    def test_isolation(self, anil, bina):
        mine, theirs = make_case(anil, "Rao vs State"), make_case(bina, "Rao vs State")
        day = date(2026, 11, 12)
        my_hearing = make_hearing(mine, ist(2026, 11, 12, 10, 0))
        make_hearing(theirs, ist(2026, 11, 12, 10, 0))
        make_task(bina, theirs, due_date=day)
        make_task(bina, None, due_date=day)
        make_event(theirs, day)

        window = reads.calendar_window(owner=anil, date_from=day, date_to=day, now=NOW)
        assert [(e["kind"], e["id"]) for e in window["entries"]] == [("hearing", my_hearing.id)]
        assert window["total"] == 1
        assert window["day_markers"] == {"2026-11-12": {"hearing": 1, "task": 0, "event": 0}}

        # Asking for the other owner's case by id finds nothing.
        foreign = reads.calendar_window(owner=anil, date_from=day, date_to=day, case_id=theirs.id, now=NOW)
        assert foreign["entries"] == [] and foreign["total"] == 0 and foreign["day_markers"] == {}


# ---------------------------------------------------------------------------
# Deadlines
# ---------------------------------------------------------------------------


class TestOpenDeadlines:
    def test_rows_order_and_overdue(self, anil):
        case = make_case(anil, "Rao vs State")
        overdue = make_task(
            anil, case, due_date=date(2026, 11, 10), kind="order_direction",
            due_date_basis="relative_to_order", needs_review=True,
        )
        today = make_task(anil, case, due_date=TODAY, status="in_progress")
        later = make_task(anil, None, due_date=date(2026, 12, 1), kind="limitation")
        undated = make_task(anil, case, due_date=None)
        make_task(anil, case, due_date=TODAY, status="completed")
        make_task(anil, case, due_date=TODAY, status="cancelled")

        result = reads.open_deadlines(owner=anil, now=NOW)
        assert [r["id"] for r in result["entries"]] == [overdue.id, today.id, later.id, undated.id]
        assert [r["overdue"] for r in result["entries"]] == [True, False, False, False]
        assert (result["total"], result["truncated"]) == (4, False)
        first = result["entries"][0]
        assert first == {
            "id": overdue.id,
            "case_id": case.id,
            "case_title": "Rao vs State",
            "title": "File counter",
            "due_date": "2026-11-10",
            "status": "pending",
            "kind": "order_direction",
            "needs_review": True,
            "due_date_basis": "relative_to_order",
            "overdue": True,
            "ref": {
                "kind": "task",
                "id": overdue.id,
                "case_id": case.id,
                "label": "File counter",
                "recorded_at": "2026-11-10",
            },
        }
        assert result["entries"][3]["due_date"] is None
        assert result["entries"][1]["due_date_basis"] is None
        assert result["entries"][2]["case_id"] is None

    def test_overdue_uses_the_india_day(self, anil):
        """00:30 IST on the 12th is still the 11th in UTC."""
        task = make_task(anil, None, due_date=date(2026, 11, 11))
        before = reads.open_deadlines(owner=anil, now=ist(2026, 11, 11, 23, 59))
        after = reads.open_deadlines(owner=anil, now=ist(2026, 11, 12, 0, 30))
        assert before["entries"][0]["overdue"] is False
        assert after["entries"][0]["id"] == task.id and after["entries"][0]["overdue"] is True

    def test_limit_cap_and_exact_total(self, anil):
        Task.objects.bulk_create(
            [Task(owner=anil, title=f"T{i}", due_date=TODAY) for i in range(HARD_ROW_CAP + 5)]
        )
        default = reads.open_deadlines(owner=anil, now=NOW)
        assert (len(default["entries"]), default["total"], default["truncated"]) == (
            PAGE_SIZE, HARD_ROW_CAP + 5, True,
        )
        capped = reads.open_deadlines(owner=anil, limit=10_000, now=NOW)
        assert (len(capped["entries"]), capped["total"], capped["truncated"]) == (
            HARD_ROW_CAP, HARD_ROW_CAP + 5, True,
        )

    def test_case_filter_and_isolation(self, anil, bina):
        mine, other, theirs = make_case(anil, "Same"), make_case(anil, "Other"), make_case(bina, "Same")
        task = make_task(anil, mine, due_date=TODAY)
        make_task(anil, other, due_date=TODAY)
        make_task(bina, theirs, due_date=TODAY)
        make_task(bina, None, due_date=TODAY)

        assert reads.open_deadlines(owner=anil, now=NOW)["total"] == 2
        scoped = reads.open_deadlines(owner=anil, case_id=mine.id, now=NOW)
        assert [r["id"] for r in scoped["entries"]] == [task.id]
        foreign = reads.open_deadlines(owner=anil, case_id=theirs.id, now=NOW)
        assert foreign["entries"] == [] and foreign["total"] == 0


# ---------------------------------------------------------------------------
# One case
# ---------------------------------------------------------------------------


class TestCaseFacts:
    def test_not_the_owners_case_is_none(self, anil, bina):
        theirs = make_case(bina, "Rao vs State")
        make_case(anil, "Rao vs State")
        make_hearing(theirs, ist(2026, 11, 14))
        assert reads.case_facts(owner=anil, case_id=theirs.id, now=NOW) is None
        assert reads.case_facts(owner=anil, case_id=987654321, now=NOW) is None

    def test_empty_case(self, anil):
        case = make_case(anil, "Bare", cnr_number="TSHC010000012026")
        facts = reads.case_facts(owner=anil, case_id=case.id, now=NOW)
        assert facts["case"]["id"] == case.id
        assert facts["case"]["title"] == "Bare"
        assert facts["case"]["case_number"] == case.case_number
        assert facts["case"]["cnr_number"] == "TSHC010000012026"
        assert facts["case"]["status"] == "open"
        assert facts["case"]["ref"] == {
            "kind": "case", "id": case.id, "case_id": case.id, "label": "Bare", "recorded_at": None,
        }
        assert facts["next_hearing"] is None
        assert facts["open_tasks"] == {"entries": [], "total": 0, "truncated": False}
        assert facts["upcoming_events"] == {"entries": [], "total": 0, "truncated": False}
        assert facts["as_of"] == "2026-11-11T10:00:00+05:30"
        assert facts["timezone"] == "Asia/Kolkata"

    def test_facts(self, anil, bina):
        case, sibling = make_case(anil, "Rao vs State"), make_case(anil, "Sibling")
        make_hearing(case, ist(2026, 11, 1, 10, 0))  # past
        make_hearing(case, ist(2026, 11, 25, 10, 0))
        soonest = make_hearing(case, ist(2026, 11, 14, 10, 30), location="Court 3")
        make_hearing(case, ist(2026, 11, 12, 10, 0), status="cancelled")
        make_hearing(sibling, ist(2026, 11, 12, 10, 0))
        task = make_task(anil, case, due_date=date(2026, 11, 9))
        make_task(anil, case, due_date=TODAY, status="completed")
        make_task(anil, sibling, due_date=TODAY)
        event = make_event(case, date(2026, 11, 13), start_time=time(16, 0))
        make_event(case, date(2026, 11, 10))  # past
        make_event(case, date(2026, 11, 13), status="cancelled")
        make_event(sibling, date(2026, 11, 13))
        # Another owner's rows, one of them wrongly attached to this case.
        Task.objects.create(owner=bina, case=case, title="Not mine", due_date=TODAY)

        facts = reads.case_facts(owner=anil, case_id=case.id, now=NOW)
        assert facts["case"]["court"] == "Court 3"
        assert facts["next_hearing"]["id"] == soonest.id
        assert facts["next_hearing"]["start_time"] == "10:30"
        assert facts["next_hearing"]["ref"]["kind"] == "hearing"
        assert facts["next_hearing"]["ref"]["case_id"] == case.id
        assert [r["id"] for r in facts["open_tasks"]["entries"]] == [task.id]
        assert facts["open_tasks"]["entries"][0]["overdue"] is True
        assert facts["open_tasks"]["entries"][0]["ref"]["kind"] == "task"
        assert facts["open_tasks"]["total"] == 1
        assert [e["id"] for e in facts["upcoming_events"]["entries"]] == [event.id]
        assert facts["upcoming_events"]["entries"][0]["ref"]["kind"] == "event"
        assert facts["upcoming_events"]["total"] == 1

    def test_rows_are_bounded_with_exact_totals(self, anil):
        case = make_case(anil)
        Task.objects.bulk_create(
            [Task(owner=anil, case=case, title=f"T{i}", due_date=TODAY) for i in range(reads.CASE_FACTS_ROWS + 4)]
        )
        for _ in range(2):
            make_event(case, TODAY)
        facts = reads.case_facts(owner=anil, case_id=case.id, now=NOW)
        assert len(facts["open_tasks"]["entries"]) == reads.CASE_FACTS_ROWS
        assert facts["open_tasks"]["total"] == reads.CASE_FACTS_ROWS + 4
        assert facts["open_tasks"]["truncated"] is True
        assert facts["upcoming_events"]["total"] == 2  # not multiplied by the task join
        assert facts["upcoming_events"]["truncated"] is False


class TestResolveCaseCandidates:
    def test_matches_title_number_and_cnr(self, anil):
        rao = make_case(anil, "Rao vs State", case_number="WP/26147/2026", cnr_number="TSHC010030082026")
        iyer = make_case(anil, "Iyer vs Iyer", case_number="OS/9/2026")

        def found(text):
            return [c["id"] for c in reads.resolve_case_candidates(owner=anil, text=text)]

        assert found("rao") == [rao.id]
        assert found("  26147 ") == [rao.id]
        assert found("tshc0100300") == [rao.id]
        assert found("vs") == [iyer.id, rao.id]  # title order
        assert found("nothing like this") == []
        assert found("") == [] and found("   ") == []
        candidate = reads.resolve_case_candidates(owner=anil, text="rao")[0]
        assert candidate == {"id": rao.id, "title": "Rao vs State", "case_number": "WP/26147/2026", "court": None}

    def test_duplicate_titles_come_back_as_separate_candidates(self, anil):
        first = make_case(anil, "Rao vs State")
        second = make_case(anil, "Rao vs State")
        make_hearing(second, ist(2026, 11, 14), location="High Court for the State of Telangana")
        found = reads.resolve_case_candidates(owner=anil, text="Rao vs State")
        assert [c["id"] for c in found] == [first.id, second.id]
        assert found[0]["case_number"] != found[1]["case_number"]
        assert found[1]["court"] == "High Court for the State of Telangana"

    def test_limit(self, anil):
        for index in range(8):
            make_case(anil, f"Rao {index}")
        assert len(reads.resolve_case_candidates(owner=anil, text="rao")) == 5
        assert len(reads.resolve_case_candidates(owner=anil, text="rao", limit=2)) == 2

    def test_never_another_owners_case(self, anil, bina):
        mine = make_case(anil, "Rao vs State")
        make_case(bina, "Rao vs State", case_number="CRLP/777/2026", cnr_number="APHC010000772026")
        assert [c["id"] for c in reads.resolve_case_candidates(owner=anil, text="Rao")] == [mine.id]
        assert reads.resolve_case_candidates(owner=anil, text="CRLP/777") == []
        assert reads.resolve_case_candidates(owner=anil, text="APHC010000772026") == []


# ---------------------------------------------------------------------------
# Query counts: fixed per read, however much data there is
# ---------------------------------------------------------------------------


def _populate(owner, cases):
    made = []
    for index in range(cases):
        case = make_case(owner, f"Matter {index}")
        make_hearing(case, ist(2026, 11, 12, 10, index % 60))
        make_hearing(case, ist(2026, 11, 13, 10, index % 60))
        make_task(owner, case, due_date=date(2026, 11, 12))
        make_event(case, date(2026, 11, 12))
        made.append(case)
    return made


class TestQueryCounts:
    @pytest.mark.parametrize("cases", [2, 15])
    def test_fixed_query_counts(self, anil, bina, django_assert_num_queries, cases):
        mine = _populate(anil, cases)
        _populate(bina, 2)
        window = {"date_from": date(2026, 11, 11), "date_to": date(2026, 11, 17)}

        with django_assert_num_queries(4):
            snap = reads.portfolio_snapshot(owner=anil, now=NOW)
        assert snap["total_cases"] == cases and snap["active_with_next_hearing"] == cases

        with django_assert_num_queries(6):
            result = reads.calendar_window(owner=anil, now=NOW, **window)
        assert result["total"] == cases * 4

        with django_assert_num_queries(2):
            reads.calendar_window(owner=anil, kinds=["hearing"], now=NOW, **window)

        with django_assert_num_queries(2):
            deadlines = reads.open_deadlines(owner=anil, now=NOW)
        assert deadlines["total"] == cases

        with django_assert_num_queries(6):
            facts = reads.case_facts(owner=anil, case_id=mine[0].id, now=NOW)
        assert facts["next_hearing"] is not None

        with django_assert_num_queries(1):
            assert reads.case_facts(owner=bina, case_id=mine[0].id, now=NOW) is None

        with django_assert_num_queries(3):
            found = reads.resolve_case_candidates(owner=anil, text="Matter", limit=50)
        assert len(found) == cases
