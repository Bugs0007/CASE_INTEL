"""Limitation deadlines (roadmap 1.2a): the rules table, the conservative
computation, recording a deadline as a Task, and the API."""

from datetime import date

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import Case, CourtOrder, Task
from core.services.limitation import (
    LIMITATION_RULES,
    InvalidSourceOrderError,
    UnknownLimitationRuleError,
    add_limitation_deadline,
    compute_deadline,
    get_rule,
    rules_for_court,
)
from core.services.limitation.rules import LimitationRule
from core.services.tasks import OUTCOME_CREATED, OUTCOME_SKIPPED, OUTCOME_UNCHANGED

# ---------------------------------------------------------------------------
# Rules table
# ---------------------------------------------------------------------------


def test_rule_keys_are_unique():
    keys = [rule.key for rule in LIMITATION_RULES]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("rule", LIMITATION_RULES, ids=lambda rule: rule.key)
def test_every_rule_cites_its_source(rule):
    assert rule.citation and rule.label and rule.runs_from
    assert rule.court_types


@pytest.mark.parametrize(
    "key, period, unit",
    [
        ("appeal_to_high_court", 90, "days"),
        ("appeal_to_other_court", 30, "days"),
        ("appeal_within_high_court", 30, "days"),
        ("criminal_appeal_to_high_court", 60, "days"),
        ("criminal_appeal_to_other_court", 30, "days"),
        ("review", 30, "days"),
        ("revision", 90, "days"),
        ("slp_supreme_court", 90, "days"),
        ("execution_of_decree", 12, "years"),
    ],
)
def test_periods_match_the_schedule(key, period, unit):
    """Pinned so that changing a statutory period is a visible, reviewed diff."""
    rule = get_rule(key)
    assert (rule.period, rule.period_unit) == (period, unit)


def test_execution_is_not_condonable_and_has_no_copy_exclusion():
    rule = get_rule("execution_of_decree")
    assert rule.condonable is False  # Section 5 excludes Order XXI applications
    assert rule.copy_time_excluded is False


def test_invalid_rules_are_rejected_at_definition():
    with pytest.raises(ValueError):
        LimitationRule("Bad Key", "x", "x", 30, "days", "x", ("district",), True, True)
    with pytest.raises(ValueError):
        LimitationRule("zero", "x", "x", 0, "days", "x", ("district",), True, True)


def test_unknown_rule():
    with pytest.raises(UnknownLimitationRuleError):
        get_rule("appeal_to_the_moon")


def test_rules_are_filtered_by_court():
    high_court = {rule.key for rule in rules_for_court("high_court")}
    assert "slp_supreme_court" in high_court
    assert "appeal_to_high_court" not in high_court
    assert len(rules_for_court(None)) == len(LIMITATION_RULES)


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key, trigger, expected",
    [
        # The starting day is excluded: 30 days from 1 Jan ends 31 Jan.
        ("review", date(2026, 1, 1), date(2026, 1, 31)),
        # Across a leap-year February.
        ("appeal_to_high_court", date(2027, 12, 15), date(2028, 3, 14)),
        ("criminal_appeal_to_high_court", date(2026, 11, 30), date(2027, 1, 29)),
        # Years land on the anniversary, 29 Feb included.
        ("execution_of_decree", date(2028, 2, 29), date(2040, 2, 29)),
        ("execution_of_decree", date(2026, 9, 15), date(2038, 9, 15)),
    ],
)
def test_last_day(key, trigger, expected):
    assert compute_deadline(get_rule(key), trigger).last_day == expected


def test_notes_are_honest_about_what_is_not_counted():
    notes = compute_deadline(get_rule("review"), date(2026, 1, 1)).notes
    joined = " ".join(notes)
    assert "Section 12(1)" in joined
    assert "Section 12(2)" in joined and "may be later" in joined
    assert "Section 5" in joined
    assert notes[-1].startswith("Computed from the limitation schedule as a guide")


def test_sunday_is_noted_but_not_extended():
    computation = compute_deadline(get_rule("review"), date(2026, 1, 2))
    assert computation.last_day == date(2026, 2, 1)  # a Sunday -- kept, the earlier date
    assert any("Section 4" in note for note in computation.notes)


def test_no_sunday_note_on_a_weekday():
    notes = compute_deadline(get_rule("review"), date(2026, 1, 1)).notes
    assert not any("Section 4" in note for note in notes)


# ---------------------------------------------------------------------------
# Recording a deadline
# ---------------------------------------------------------------------------


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="limitation-advocate", password="pw-12345")


@pytest.fixture
def case(advocate):
    return Case.objects.create(
        owner=advocate, case_number="WP/100/2026", title="Rao vs State", court_type="high_court"
    )


@pytest.fixture
def order(advocate, case):
    return CourtOrder.objects.create(
        owner=advocate,
        case=case,
        order_number="5",
        order_date=date(2026, 9, 1),
        dedup_key="CNR:5:2026-09-01",
    )


@pytest.mark.django_db
class TestAddLimitationDeadline:
    def test_records_a_limitation_task(self, case, order):
        task, outcome, computation = add_limitation_deadline(
            case, rule_key="appeal_within_high_court", trigger_date=date(2026, 9, 1), source_order=order
        )

        assert outcome == OUTCOME_CREATED
        assert task.kind == Task.KIND_LIMITATION
        assert task.due_date == date(2026, 10, 1) == computation.last_day
        assert task.due_date_basis == Task.BASIS_LIMITATION_RULE
        assert (task.rule_key, task.trigger_date, task.source_order) == (
            "appeal_within_high_court",
            date(2026, 9, 1),
            order,
        )
        assert task.needs_review is False  # the advocate chose it
        assert "Section 12(2)" in task.description

    def test_same_rule_and_date_is_idempotent(self, case):
        add_limitation_deadline(case, rule_key="review", trigger_date=date(2026, 9, 1))
        _, outcome, _ = add_limitation_deadline(case, rule_key="review", trigger_date=date(2026, 9, 1))

        assert outcome == OUTCOME_UNCHANGED
        assert Task.objects.count() == 1

    def test_an_edited_deadline_is_left_alone(self, case):
        task, _, _ = add_limitation_deadline(case, rule_key="review", trigger_date=date(2026, 9, 1))
        Task.objects.filter(id=task.id).update(user_modified=True, due_date=date(2026, 9, 20))

        _, outcome, _ = add_limitation_deadline(case, rule_key="review", trigger_date=date(2026, 9, 1))

        assert outcome == OUTCOME_SKIPPED
        task.refresh_from_db()
        assert task.due_date == date(2026, 9, 20)

    def test_source_order_must_be_on_the_case(self, advocate, case):
        other_case = Case.objects.create(owner=advocate, case_number="WP/200/2026", title="x")
        foreign_order = CourtOrder.objects.create(
            owner=advocate, case=other_case, order_number="1", order_date=date(2026, 9, 1), dedup_key="k"
        )
        with pytest.raises(InvalidSourceOrderError):
            add_limitation_deadline(
                case, rule_key="review", trigger_date=date(2026, 9, 1), source_order=foreign_order
            )


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@pytest.fixture
def api(advocate):
    client = APIClient()
    client.force_authenticate(user=advocate)
    return client


@pytest.mark.django_db
class TestLimitationApi:
    def test_rules_endpoint_filters_by_court(self, api):
        resp = api.get("/api/limitation/rules/", {"court_type": "district"})
        assert resp.status_code == 200
        keys = {rule["key"] for rule in resp.data}
        assert "appeal_to_high_court" in keys and "slp_supreme_court" not in keys

    def test_compute_endpoint(self, api):
        resp = api.get("/api/limitation/compute/", {"rule_key": "review", "trigger_date": "2026-01-01"})
        assert resp.status_code == 200
        assert resp.data["last_day"] == date(2026, 1, 31)
        assert resp.data["rule"]["citation"].endswith("Article 124")

    @pytest.mark.parametrize(
        "params, field",
        [
            ({"rule_key": "nope", "trigger_date": "2026-01-01"}, "rule_key"),
            ({"rule_key": "review", "trigger_date": "yesterday"}, "trigger_date"),
        ],
    )
    def test_compute_rejects_bad_input(self, api, params, field):
        resp = api.get("/api/limitation/compute/", params)
        assert resp.status_code == 400
        assert field in resp.data

    def test_add_deadline_201_then_200(self, api, case, order):
        body = {"rule_key": "slp_supreme_court", "trigger_date": "2026-09-01", "source_order": order.id}

        first = api.post(f"/api/cases/{case.id}/limitation-deadlines/", body, format="json")
        second = api.post(f"/api/cases/{case.id}/limitation-deadlines/", body, format="json")

        assert first.status_code == 201
        assert first.data["task"]["kind"] == "limitation"
        assert first.data["task"]["due_date"] == "2026-11-30"
        assert first.data["computation"]["notes"]
        assert second.status_code == 200
        # And it shows up in the one task list.
        listed = api.get("/api/tasks/", {"kind": "limitation"}).data
        assert [t["id"] for t in listed] == [first.data["task"]["id"]]

    def test_order_from_another_case_is_rejected(self, api, advocate, case):
        other_case = Case.objects.create(owner=advocate, case_number="WP/200/2026", title="x")
        foreign = CourtOrder.objects.create(
            owner=advocate, case=other_case, order_number="1", order_date=date(2026, 9, 1), dedup_key="k"
        )
        resp = api.post(
            f"/api/cases/{case.id}/limitation-deadlines/",
            {"rule_key": "review", "trigger_date": "2026-09-01", "source_order": foreign.id},
            format="json",
        )
        assert resp.status_code == 400
        assert not Task.objects.exists()

    def test_another_advocates_case_is_404(self, case):
        intruder = APIClient()
        intruder.force_authenticate(user=User.objects.create_user(username="intruder", password="pw-12345"))

        resp = intruder.post(
            f"/api/cases/{case.id}/limitation-deadlines/",
            {"rule_key": "review", "trigger_date": "2026-09-01"},
            format="json",
        )

        assert resp.status_code == 404
        assert not Task.objects.exists()
