"""Tasks from court-order directions.

  - parse_direction_due_date: the regex table, case by case (no DB).
  - generate_tasks_for_order: gates, idempotency, pruning.
  - The three entry points: the process_jobs hook, a party-role change on
    PATCH /api/cases/<id>/, and manage.py generate_order_tasks.
"""

from datetime import date, datetime, timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from core.management.commands.process_jobs import Command as ProcessJobsCommand
from core.models import Case, CourtOrder, Document, Hearing, Task
from core.services.tasks.direction_deadlines import parse_direction_due_date
from core.services.tasks.from_orders import (
    LATER_START_NOTE,
    REASON_NOT_SUMMARIZED,
    REASON_OUTSIDE_WINDOW,
    REASON_ROLE_UNKNOWN,
    REASON_SUPERSEDED,
    REASON_UNDATED,
    generate_tasks_for_order,
)

ORDER_DATE = date(2026, 9, 1)
NEXT_HEARING = date(2026, 10, 15)


# ---------------------------------------------------------------------------
# parse_direction_due_date
# ---------------------------------------------------------------------------

EXPLICIT = Task.BASIS_EXPLICIT_DATE
RELATIVE = Task.BASIS_RELATIVE_TO_ORDER
NEXT = Task.BASIS_NEXT_HEARING_FALLBACK


@pytest.mark.parametrize(
    "text, expected_date, expected_basis, approximate",
    [
        # Periods counted from the order date
        ("Respondent to file counter affidavit within 4 weeks.", date(2026, 9, 29), RELATIVE, False),
        ("File counter within four (4) weeks", date(2026, 9, 29), RELATIVE, False),
        ("File counter within 4 (four) weeks", date(2026, 9, 29), RELATIVE, False),
        ("Deposit within a period of 30 days", date(2026, 10, 1), RELATIVE, False),
        ("Comply within ten days", date(2026, 9, 11), RELATIVE, False),
        ("Pay within two months", date(2026, 11, 1), RELATIVE, False),
        ("Pay within a month", date(2026, 10, 1), RELATIVE, False),
        ("Comply within a fortnight", date(2026, 9, 15), RELATIVE, False),
        ("Comply within one year", date(2027, 9, 1), RELATIVE, False),
        ("WITHIN 6 WEEKS file reply", date(2026, 10, 13), RELATIVE, False),
        ("File reply within\n   two\n weeks", date(2026, 9, 15), RELATIVE, False),
        # Periods that start from a later event -> approximate
        (
            "Deposit within 30 days from the date of receipt of a copy of this order",
            date(2026, 10, 1),
            RELATIVE,
            True,
        ),
        ("File rejoinder within 2 weeks thereafter", date(2026, 9, 15), RELATIVE, True),
        ("Pay within 4 weeks after service of notice", date(2026, 9, 29), RELATIVE, True),
        # Explicit dates, day first
        ("Pay costs by 12.10.2026", date(2026, 10, 12), EXPLICIT, False),
        ("File reply on or before 12-10-2026", date(2026, 10, 12), EXPLICIT, False),
        ("File reply before 5/1/27", date(2027, 1, 5), EXPLICIT, False),
        ("Produce records on or before 12th October 2026", date(2026, 10, 12), EXPLICIT, False),
        ("Produce records by 3rd of Nov, 2026", date(2026, 11, 3), EXPLICIT, False),
        ("Submit report by October 20, 2026", date(2026, 10, 20), EXPLICIT, False),
        ("Submit report not later than 1.12.2026", date(2026, 12, 1), EXPLICIT, False),
        # An explicit date beats a period in the same direction
        ("File within 4 weeks, i.e. by 25.09.2026", date(2026, 9, 25), EXPLICIT, False),
        # Next hearing
        ("File status report before the next date of hearing", NEXT_HEARING, NEXT, False),
        ("Produce the file by the next date", NEXT_HEARING, NEXT, False),
        # Immediately
        ("Release the vehicle forthwith", ORDER_DATE, RELATIVE, False),
        # No period stated -> next hearing
        ("Petitioner shall serve notice on the respondents", NEXT_HEARING, NEXT, False),
        # Not a real date -> not an explicit date
        ("File reply by 31.02.2026", NEXT_HEARING, NEXT, False),
        # A near-miss word must not count as a later start
        ("Pay within 2 weeks after servicemen's dues are settled", date(2026, 9, 15), RELATIVE, False),
    ],
)
def test_parse_direction_due_date(text, expected_date, expected_basis, approximate):
    due = parse_direction_due_date(text, order_date=ORDER_DATE, next_hearing_date=NEXT_HEARING)
    assert (due.due_date, due.basis, due.approximate) == (expected_date, expected_basis, approximate)


def test_no_period_and_no_next_hearing_means_no_date():
    due = parse_direction_due_date(
        "Petitioner shall serve notice", order_date=ORDER_DATE, next_hearing_date=None
    )
    assert (due.due_date, due.basis) == (None, "")


def test_month_arithmetic_clamps_to_month_end():
    due = parse_direction_due_date(
        "Pay within one month", order_date=date(2026, 1, 31), next_hearing_date=None
    )
    assert due.due_date == date(2026, 2, 28)


# ---------------------------------------------------------------------------
# generate_tasks_for_order
# ---------------------------------------------------------------------------

PETITIONER_DIRECTIONS = ["Petitioner to file rejoinder within 2 weeks."]
RESPONDENT_DIRECTIONS = [
    "Respondent to file counter affidavit within 4 weeks.",
    "Respondent to produce the original file before the next date of hearing.",
]


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="directions-advocate", password="pw-12345")


@pytest.fixture
def today():
    return timezone.localdate()


def _case(owner, role="respondent", number="WP/500/2026"):
    return Case.objects.create(
        owner=owner, case_number=number, title=f"{number} Rao vs State", user_party_role=role
    )


def _order(owner, case, order_date, *, number="1", status=CourtOrder.SUMMARY_SUMMARIZED, **summary):
    return CourtOrder.objects.create(
        owner=owner,
        case=case,
        order_number=number,
        order_date=order_date,
        dedup_key=f"CNR:{number}:{order_date}",
        summary_status=status,
        summary_what_happened="Notice issued.",
        summary_petitioner_directions=summary.get("petitioner", PETITIONER_DIRECTIONS),
        summary_respondent_directions=summary.get("respondent", RESPONDENT_DIRECTIONS),
        summary_next_date=summary.get("next_date"),
    )


@pytest.mark.django_db
class TestGenerateTasksForOrder:
    def test_one_task_per_direction_on_your_side(self, advocate, today):
        case = _case(advocate, role="respondent")
        order = _order(advocate, case, today - timedelta(days=3), next_date=today + timedelta(days=40))

        result = generate_tasks_for_order(order, today=today)

        assert result.created == 2
        tasks = Task.objects.filter(case=case).order_by("due_date")
        assert [t.source_text for t in tasks] == RESPONDENT_DIRECTIONS
        counter, produce = tasks
        assert counter.kind == Task.KIND_ORDER_DIRECTION
        assert counter.source_order == order
        assert counter.title == RESPONDENT_DIRECTIONS[0]
        assert counter.due_date == order.order_date + timedelta(weeks=4)
        assert counter.due_date_basis == Task.BASIS_RELATIVE_TO_ORDER
        # "before the next date of hearing" uses the date the order set.
        assert produce.due_date == order.summary_next_date
        assert produce.due_date_basis == Task.BASIS_NEXT_HEARING_FALLBACK
        assert not Task.objects.filter(source_text__in=PETITIONER_DIRECTIONS).exists()

    def test_petitioner_role_takes_petitioner_directions(self, advocate, today):
        case = _case(advocate, role="petitioner")
        order = _order(advocate, case, today - timedelta(days=3))

        generate_tasks_for_order(order, today=today)

        assert list(Task.objects.values_list("source_text", flat=True)) == PETITIONER_DIRECTIONS

    def test_regeneration_is_idempotent(self, advocate, today):
        case = _case(advocate)
        order = _order(advocate, case, today - timedelta(days=3))

        generate_tasks_for_order(order, today=today)
        again = generate_tasks_for_order(order, today=today)

        assert (again.created, again.unchanged) == (0, 2)
        assert Task.objects.count() == 2

    def test_unknown_party_role_creates_nothing(self, advocate, today):
        case = _case(advocate, role="unknown")
        order = _order(advocate, case, today - timedelta(days=3))

        result = generate_tasks_for_order(order, today=today)

        assert result.reason == REASON_ROLE_UNKNOWN
        assert not Task.objects.exists()

    def test_unsummarised_order_creates_nothing(self, advocate, today):
        case = _case(advocate)
        order = _order(advocate, case, today, status=CourtOrder.SUMMARY_PENDING)

        assert generate_tasks_for_order(order, today=today).reason == REASON_NOT_SUMMARIZED
        assert not Task.objects.exists()

    def test_undated_order_creates_nothing(self, advocate, today):
        case = _case(advocate)
        order = _order(advocate, case, None)

        assert generate_tasks_for_order(order, today=today).reason == REASON_UNDATED

    def test_only_the_latest_order_date_gets_tasks(self, advocate, today):
        case = _case(advocate)
        older = _order(advocate, case, today - timedelta(days=20), number="1")
        _order(advocate, case, today - timedelta(days=2), number="2")

        assert generate_tasks_for_order(older, today=today).reason == REASON_SUPERSEDED
        assert not Task.objects.exists()

    def test_old_orders_create_no_overdue_backlog(self, advocate, today):
        case = _case(advocate)
        order = _order(advocate, case, today - timedelta(days=200))

        assert generate_tasks_for_order(order, today=today).reason == REASON_OUTSIDE_WINDOW
        assert not Task.objects.exists()

    def test_period_from_a_later_event_says_so(self, advocate, today):
        case = _case(advocate)
        order = _order(
            advocate,
            case,
            today - timedelta(days=3),
            respondent=["Deposit within 30 days from receipt of a copy of this order."],
        )

        generate_tasks_for_order(order, today=today)

        assert Task.objects.get().description == LATER_START_NOTE

    def test_next_hearing_falls_back_to_the_case_diary(self, advocate, today):
        case = _case(advocate)
        order = _order(advocate, case, today - timedelta(days=3), respondent=["Serve notice."])
        next_hearing = today + timedelta(days=9)
        Hearing.objects.create(
            owner=advocate,
            case=case,
            hearing_date=timezone.make_aware(datetime.combine(next_hearing, datetime.min.time())),
            hearing_type="other",
        )

        generate_tasks_for_order(order, today=today)

        task = Task.objects.get()
        assert (task.due_date, task.due_date_basis) == (next_hearing, Task.BASIS_NEXT_HEARING_FALLBACK)

    def test_reworded_directions_replace_untouched_tasks_only(self, advocate, today):
        case = _case(advocate)
        order = _order(advocate, case, today - timedelta(days=3))
        generate_tasks_for_order(order, today=today)
        edited = Task.objects.get(source_text=RESPONDENT_DIRECTIONS[0])
        Task.objects.filter(id=edited.id).update(user_modified=True)

        # A forced re-summary rewords both directions.
        order.summary_respondent_directions = [
            "Respondent to file counter within four weeks.",
            "Respondent to produce the file before the next hearing.",
        ]
        order.save()
        result = generate_tasks_for_order(order, today=today)

        assert (result.created, result.pruned) == (2, 1)
        remaining = set(Task.objects.values_list("source_text", flat=True))
        assert remaining == {RESPONDENT_DIRECTIONS[0], *order.summary_respondent_directions}


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPartyRoleCorrection:
    @pytest.fixture
    def api(self, advocate):
        client = APIClient()
        client.force_authenticate(user=advocate)
        return client

    def test_flipping_the_role_moves_tasks_to_the_other_side(self, api, advocate, today):
        case = _case(advocate, role="respondent")
        order = _order(advocate, case, today - timedelta(days=3))
        generate_tasks_for_order(order, today=today)
        done = Task.objects.get(source_text=RESPONDENT_DIRECTIONS[0])
        Task.objects.filter(id=done.id).update(status=Task.STATUS_COMPLETED)

        resp = api.patch(f"/api/cases/{case.id}/", {"user_party_role": "petitioner"}, format="json")

        assert resp.status_code == 200, resp.data
        texts = set(Task.objects.values_list("source_text", flat=True))
        # The completed respondent task stays (the advocate did it); the
        # untouched one goes; the petitioner's direction arrives.
        assert texts == {RESPONDENT_DIRECTIONS[0], *PETITIONER_DIRECTIONS}

    def test_setting_the_role_to_unknown_removes_untouched_tasks(self, api, advocate, today):
        case = _case(advocate, role="respondent")
        generate_tasks_for_order(_order(advocate, case, today - timedelta(days=3)), today=today)

        api.patch(f"/api/cases/{case.id}/", {"user_party_role": "unknown"}, format="json")

        assert not Task.objects.exists()

    def test_other_edits_do_not_regenerate(self, api, advocate, today):
        case = _case(advocate, role="respondent")
        _order(advocate, case, today - timedelta(days=3))

        with patch("core.views.case.sync_order_tasks_for_case") as sync:
            api.patch(f"/api/cases/{case.id}/", {"notes": "Brief client"}, format="json")

        sync.assert_not_called()


@pytest.mark.django_db
class TestProcessJobsHook:
    def _order_with_document(self, advocate, today):
        case = _case(advocate)
        order = _order(advocate, case, today - timedelta(days=1))
        order.document = Document.objects.create(
            owner=advocate,
            case=case,
            filename="order.pdf",
            file_path="documents/order.pdf",
            file_type="pdf",
            document_type="court_order",
            processing_status="completed",
            extracted_text="(already summarised)",
        )
        order.save()
        return order

    def test_tasks_are_generated_after_the_summary(self, advocate, today):
        order = self._order_with_document(advocate, today)

        ProcessJobsCommand(stdout=StringIO())._summarize_order_if_any(order.document_id)

        assert Task.objects.filter(source_order=order).count() == 2

    def test_a_task_failure_never_fails_the_document_job(self, advocate, today):
        order = self._order_with_document(advocate, today)

        with patch(
            "core.services.tasks.from_orders.generate_tasks_for_order",
            side_effect=RuntimeError("boom"),
        ):
            ProcessJobsCommand(stdout=StringIO())._summarize_order_if_any(order.document_id)

        assert not Task.objects.exists()


@pytest.mark.django_db
class TestGenerateOrderTasksCommand:
    def test_dry_run_writes_nothing(self, advocate, today):
        case = _case(advocate)
        _order(advocate, case, today - timedelta(days=3))
        out = StringIO()

        call_command("generate_order_tasks", "--dry-run", stdout=out)

        assert "2 created" in out.getvalue()
        assert "rolled back" in out.getvalue()
        assert not Task.objects.exists()

    def test_backfills_and_reports_skipped_orders(self, advocate, today):
        case = _case(advocate)
        _order(advocate, case, today - timedelta(days=3))
        unknown = _case(advocate, role="unknown", number="OS/9/2026")
        _order(advocate, unknown, today - timedelta(days=3))
        out = StringIO()

        call_command("generate_order_tasks", "--owner", advocate.username, stdout=out)

        assert Task.objects.count() == 2
        assert f"{REASON_ROLE_UNKNOWN}=1" in out.getvalue()
