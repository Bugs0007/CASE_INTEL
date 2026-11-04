"""Hearing reminder digests: who is emailed, when, how often, and with what.

The run date is always passed explicitly (TODAY = Thursday 5 Nov 2026, India),
so nothing here depends on the clock of the machine running the tests.
"""

from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.core.mail import EmailMessage
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import (
    AdvocateProfile,
    Case,
    CaseEvent,
    Hearing,
    HearingReminder,
    Task,
)
from core.services.india_time import INDIA_TZ
from core.services.notifications import hearing_reminders

pytestmark = pytest.mark.django_db

TODAY = date(2026, 11, 5)  # Thursday
TOMORROW = date(2026, 11, 6)  # Friday
IN_TWO_DAYS = date(2026, 11, 7)  # Saturday


@pytest.fixture(autouse=True)
def configured_mail(settings):
    settings.INVOICE_EMAIL_CONFIGURED = True
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "reminders@example.test"
    settings.FRONTEND_URL = "https://app.example.test"


def make_user(username="alice", email=None):
    return User.objects.create_user(
        username=username,
        password="pw-12345",
        email=f"{username}@example.test" if email is None else email,
    )


def make_case(owner, title="Rao vs State", number="WP/1/2026", **extra):
    return Case.objects.create(owner=owner, title=title, case_number=number, **extra)


def ecourts_hearing(owner, case, day, **extra):
    """eCourts stores the portal date as 00:00 UTC."""
    extra.setdefault("source", "ecourts")
    return Hearing.objects.create(
        owner=owner,
        case=case,
        hearing_date=datetime(day.year, day.month, day.day, tzinfo=dt_timezone.utc),
        hearing_type="other",
        **extra,
    )


def manual_hearing(owner, case, day, hour, minute=0, **extra):
    return Hearing.objects.create(
        owner=owner,
        case=case,
        hearing_date=datetime(day.year, day.month, day.day, hour, minute, tzinfo=INDIA_TZ),
        hearing_type="other",
        **extra,
    )


def run(**kwargs):
    return hearing_reminders.run(today=kwargs.pop("today", TODAY), **kwargs)


@pytest.fixture
def alice(db):
    return make_user("alice")


@pytest.fixture
def alice_case(alice):
    return make_case(alice)


# ---------------------------------------------------------------------------
# The two leads, and once-only
# ---------------------------------------------------------------------------


class TestLeadsAndDedup:
    def test_two_days_then_one_day_for_the_same_hearing(self, alice, alice_case):
        hearing = ecourts_hearing(alice, alice_case, IN_TWO_DAYS)

        report = run(today=TODAY)
        assert report.sent == 1
        assert len(mail.outbox) == 1
        assert mail.outbox[0].subject == "Hearing in 2 days: Rao vs State"
        assert "Sat 7 Nov, in 2 days" in mail.outbox[0].body

        # A second run on the same day sends nothing.
        assert run(today=TODAY).sent == 0
        assert len(mail.outbox) == 1

        # The next day (Fri 6 Nov) the same hearing is "tomorrow".
        run(today=TOMORROW)
        assert len(mail.outbox) == 2
        assert mail.outbox[1].subject == "Hearing tomorrow: Rao vs State"
        assert "Tomorrow, Sat 7 Nov" in mail.outbox[1].body

        run(today=TOMORROW)
        assert len(mail.outbox) == 2

        leads = sorted(
            HearingReminder.objects.filter(hearing=hearing).values_list("lead_days", "delivery")
        )
        assert leads == [(1, "sent"), (2, "sent")]

    def test_evening_catch_up_sends_only_the_hearing_found_since_the_morning(self, alice, alice_case):
        ecourts_hearing(alice, alice_case, TOMORROW)
        run(today=TODAY)  # the 09:00 run
        assert len(mail.outbox) == 1

        # A case refresh at 14:00 finds a hearing tomorrow on another case.
        late_case = make_case(alice, title="Iyer vs Iyer", number="OS/2/2026")
        late = ecourts_hearing(alice, late_case, TOMORROW)
        Hearing.objects.filter(pk=late.pk).update(
            created_at=datetime(2026, 11, 5, 14, 0, tzinfo=INDIA_TZ)
        )

        run(today=TODAY)  # the 19:45 run
        assert len(mail.outbox) == 2
        evening = mail.outbox[1]
        assert evening.subject == "Hearing tomorrow: Iyer vs Iyer"
        assert "Iyer vs Iyer (OS/2/2026) -- added today" in evening.body
        assert "Rao vs State" not in evening.body

    def test_a_hearing_created_before_today_is_not_marked_added_today(self, alice, alice_case):
        hearing = ecourts_hearing(alice, alice_case, TOMORROW)
        Hearing.objects.filter(pk=hearing.pk).update(
            created_at=datetime(2026, 11, 1, 10, 0, tzinfo=INDIA_TZ)
        )
        run()
        assert "added today" not in mail.outbox[0].body

    def test_editing_a_hearing_date_reminds_again_for_the_new_date(self, alice, alice_case):
        hearing = ecourts_hearing(alice, alice_case, TOMORROW)
        run()
        assert len(mail.outbox) == 1

        hearing.hearing_date = datetime(2026, 11, 7, tzinfo=dt_timezone.utc)
        hearing.save()

        run()
        assert len(mail.outbox) == 2
        assert mail.outbox[1].subject == "Hearing in 2 days: Rao vs State"
        assert HearingReminder.objects.filter(hearing=hearing).count() == 2

        run()
        assert len(mail.outbox) == 2

    def test_hearings_further_out_or_already_past_are_left_alone(self, alice):
        for offset, title in ((0, "today"), (3, "in three days"), (-1, "yesterday")):
            ecourts_hearing(alice, make_case(alice, title=title, number=f"X/{offset}"), TODAY + timedelta(days=offset))
        assert run().sent == 0
        assert mail.outbox == []


# ---------------------------------------------------------------------------
# India days
# ---------------------------------------------------------------------------


class TestIndiaDayBoundaries:
    def test_ecourts_utc_midnight_lands_on_the_same_india_day(self, alice, alice_case):
        # 2026-11-06 00:00 UTC is 05:30 IST on the 6th.
        ecourts_hearing(alice, alice_case, TOMORROW)
        run()
        assert mail.outbox[0].subject == "Hearing tomorrow: Rao vs State"

    def test_late_evening_manual_hearing_stays_on_its_own_day(self, alice):
        late = make_case(alice, title="Late evening", number="L/1")
        # 23:30 IST on the 6th is 18:00 UTC on the 6th: tomorrow, not the day after.
        manual_hearing(alice, late, TOMORROW, 23, 30)
        run()
        assert mail.outbox[0].subject == "Hearing tomorrow: Late evening"

    def test_just_after_midnight_manual_hearing_is_not_the_previous_day(self, alice):
        early = make_case(alice, title="After midnight", number="E/1")
        # 00:30 IST on the 7th is 19:00 UTC on the 6th -- a UTC-date filter
        # would wrongly call this "tomorrow".
        manual_hearing(alice, early, IN_TWO_DAYS, 0, 30)
        run()
        assert mail.outbox[0].subject == "Hearing in 2 days: After midnight"

    def test_window_edges(self, alice):
        edge = make_case(alice, title="Edge", number="G/1")
        # Last minute of today and first minute of three days out: both outside.
        manual_hearing(alice, edge, TODAY, 23, 59)
        manual_hearing(alice, make_case(alice, title="Edge 2", number="G/2"), TODAY + timedelta(days=3), 0, 0)
        assert run().sent == 0


# ---------------------------------------------------------------------------
# Which hearings count
# ---------------------------------------------------------------------------


class TestEligibility:
    @pytest.mark.parametrize("status", ["cancelled", "completed", "postponed"])
    def test_non_scheduled_hearings_are_skipped(self, alice, alice_case, status):
        ecourts_hearing(alice, alice_case, TOMORROW, status=status)
        assert run().sent == 0
        assert mail.outbox == []

    @pytest.mark.parametrize("case_status", ["closed", "archived"])
    def test_closed_and_archived_cases_are_skipped(self, alice, case_status):
        ecourts_hearing(alice, make_case(alice, status=case_status), TOMORROW)
        assert run().sent == 0

    @pytest.mark.parametrize("case_status", ["open", "pending"])
    def test_open_and_pending_cases_are_reminded(self, alice, case_status):
        ecourts_hearing(alice, make_case(alice, status=case_status), TOMORROW)
        assert run().sent == 1

    def test_inactive_users_are_skipped(self, alice, alice_case):
        ecourts_hearing(alice, alice_case, TOMORROW)
        alice.is_active = False
        alice.save()
        assert run().sent == 0

    def test_manual_and_ecourts_hearing_for_the_same_sitting_list_the_case_once(self, alice, alice_case):
        ecourts_hearing(alice, alice_case, TOMORROW, purpose="FOR ADMISSION")
        manual_hearing(alice, alice_case, TOMORROW, 10, 30, source="manual")

        run()
        assert len(mail.outbox) == 1
        assert mail.outbox[0].subject == "Hearing tomorrow: Rao vs State"
        assert mail.outbox[0].body.count("Rao vs State (WP/1/2026)") == 1
        assert "FOR ADMISSION" in mail.outbox[0].body  # the eCourts record wins
        assert HearingReminder.objects.count() == 2  # both are marked reminded
        run()
        assert len(mail.outbox) == 1


# ---------------------------------------------------------------------------
# Opt-outs, recipient, demo account
# ---------------------------------------------------------------------------


class TestOptOutsAndRecipient:
    def test_master_switch_off(self, alice, alice_case):
        AdvocateProfile.objects.create(owner=alice, hearing_reminders_enabled=False)
        ecourts_hearing(alice, alice_case, TOMORROW)
        report = run()
        assert report.sent == 0
        assert report.opted_out == 1
        assert mail.outbox == []

    def test_two_day_switch_only_silences_the_two_day_reminder(self, alice):
        AdvocateProfile.objects.create(owner=alice, hearing_reminder_two_days=False)
        ecourts_hearing(alice, make_case(alice, title="Soon", number="S/1"), TOMORROW)
        ecourts_hearing(alice, make_case(alice, title="Later", number="S/2"), IN_TWO_DAYS)
        run()
        assert len(mail.outbox) == 1
        assert mail.outbox[0].subject == "Hearing tomorrow: Soon"

    def test_one_day_switch_only_silences_the_one_day_reminder(self, alice):
        AdvocateProfile.objects.create(owner=alice, hearing_reminder_one_day=False)
        ecourts_hearing(alice, make_case(alice, title="Soon", number="S/1"), TOMORROW)
        ecourts_hearing(alice, make_case(alice, title="Later", number="S/2"), IN_TWO_DAYS)
        run()
        assert len(mail.outbox) == 1
        assert mail.outbox[0].subject == "Hearing in 2 days: Later"

    def test_turning_a_switch_back_on_sends_what_was_held_back(self, alice, alice_case):
        profile = AdvocateProfile.objects.create(owner=alice, hearing_reminders_enabled=False)
        ecourts_hearing(alice, alice_case, TOMORROW)
        run()
        assert mail.outbox == []
        profile.hearing_reminders_enabled = True
        profile.save()
        run()
        assert len(mail.outbox) == 1

    def test_no_profile_means_reminders_are_on(self, alice, alice_case):
        assert not AdvocateProfile.objects.filter(owner=alice).exists()
        ecourts_hearing(alice, alice_case, TOMORROW)
        assert run().sent == 1
        # The run did not create a profile as a side effect.
        assert not AdvocateProfile.objects.filter(owner=alice).exists()

    def test_contact_email_beats_login_email(self, alice, alice_case):
        AdvocateProfile.objects.create(owner=alice, contact_email="chambers@example.test")
        ecourts_hearing(alice, alice_case, TOMORROW)
        run()
        assert mail.outbox[0].to == ["chambers@example.test"]
        assert HearingReminder.objects.get().recipient == "chambers@example.test"

    def test_login_email_is_the_fallback(self, alice, alice_case):
        ecourts_hearing(alice, alice_case, TOMORROW)
        run()
        assert mail.outbox[0].to == ["alice@example.test"]

    def test_blank_recipient_is_skipped_and_reported(self):
        nobody = make_user("nobody", email="")
        ecourts_hearing(nobody, make_case(nobody), TOMORROW)
        report = run()
        assert report.sent == 0
        assert report.no_recipient == ["nobody"]
        assert mail.outbox == []
        assert HearingReminder.objects.count() == 0

    def test_demo_account_gets_no_reminders_and_stays_that_way(self):
        call_command("setup_demo_account", stdout=StringIO())
        recruiter = User.objects.get(username="recruiter")
        recruiter.email = "recruiter@example.test"
        recruiter.save()
        profile = AdvocateProfile.objects.get(owner=recruiter)
        assert profile.hearing_reminders_enabled is False

        ecourts_hearing(recruiter, make_case(recruiter), TOMORROW)
        assert run().sent == 0
        assert mail.outbox == []

        # Re-running the setup is idempotent, and re-disables it if someone turned it on.
        profile.hearing_reminders_enabled = True
        profile.save()
        call_command("setup_demo_account", stdout=StringIO())
        call_command("setup_demo_account", stdout=StringIO())
        profile.refresh_from_db()
        assert profile.hearing_reminders_enabled is False


# ---------------------------------------------------------------------------
# The email itself
# ---------------------------------------------------------------------------


class TestDigestContent:
    def test_one_digest_per_advocate_with_both_dates(self, alice):
        for i in range(3):
            ecourts_hearing(alice, make_case(alice, title=f"Tomorrow {i}", number=f"T/{i}"), TOMORROW)
        for i in range(2):
            ecourts_hearing(alice, make_case(alice, title=f"Later {i}", number=f"L/{i}"), IN_TWO_DAYS)

        report = run()
        assert report.sent == 1
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.subject == "Hearings tomorrow (3) · Sat 7 Nov (2)"
        assert email.body.index("Tomorrow, Fri 6 Nov") < email.body.index("Sat 7 Nov, in 2 days")
        for title in ("Tomorrow 0", "Tomorrow 2", "Later 1"):
            assert title in email.body
        assert HearingReminder.objects.count() == 5

    def test_subject_when_only_the_day_after_has_several(self, alice):
        for i in range(2):
            ecourts_hearing(alice, make_case(alice, title=f"Later {i}", number=f"L/{i}"), IN_TWO_DAYS)
        run()
        assert mail.outbox[0].subject == "Hearings Sat 7 Nov (2)"

    def test_hearing_details_and_links(self, alice):
        case = make_case(alice, court_type="high_court")
        ecourts_hearing(
            alice, case, TOMORROW,
            location="Court Hall 4, Hyderabad",
            purpose="FOR ADMISSION",
            cause_list_status=Hearing.CAUSE_LIST_LISTED,
            cause_list_item_number="12",
            cause_list_court_hall="3",
        )
        run()
        body = mail.outbox[0].body
        assert "Rao vs State (WP/1/2026)" in body
        assert "Court: Court Hall 4, Hyderabad" in body
        assert "Purpose: FOR ADMISSION" in body
        assert "Cause list: Item 12, court hall 3" in body
        assert f"https://app.example.test/cases/{case.id}" in body
        assert "Change it in Settings: https://app.example.test/settings" in body
        assert mail.outbox[0].from_email == "Case Intel <reminders@example.test>"

    def test_cause_list_state_is_named_when_not_listed(self, alice, alice_case):
        ecourts_hearing(alice, alice_case, TOMORROW, cause_list_status=Hearing.CAUSE_LIST_NOT_PUBLISHED)
        run()
        assert "Cause list: Not yet listed" in mail.outbox[0].body

    def test_court_falls_back_to_the_courts_type(self, alice):
        case = make_case(alice, court_type="district")
        ecourts_hearing(alice, case, TOMORROW)
        run()
        assert "Court: District Court" in mail.outbox[0].body


class TestAlsoDue:
    def test_open_tasks_and_events_ride_along_across_all_cases(self, alice, alice_case):
        ecourts_hearing(alice, alice_case, TOMORROW)
        other = make_case(alice, title="Iyer vs Iyer", number="OS/2/2026")  # no hearing
        Task.objects.create(owner=alice, case=other, title="File counter", due_date=TOMORROW)
        Task.objects.create(owner=alice, case=other, title="Old chase", due_date=date(2026, 11, 2))
        Task.objects.create(owner=alice, case=other, title="Done already", due_date=TOMORROW, status="completed")
        Task.objects.create(owner=alice, case=other, title="Next month", due_date=date(2026, 12, 1))
        Task.objects.create(owner=alice, case=other, title="Undated")
        CaseEvent.objects.create(
            owner=alice, case=other, title="Mediation sitting", event_type="mediation",
            date=TOMORROW, start_time=time(15, 0), end_time=time(16, 30),
        )
        CaseEvent.objects.create(
            owner=alice, case=other, title="Cancelled call", date=TOMORROW, status="cancelled"
        )
        CaseEvent.objects.create(owner=alice, case=other, title="Far event", date=date(2026, 11, 20))

        run()
        body = mail.outbox[0].body
        assert "Also due" in body
        assert "Due Fri 6 Nov: File counter -- Iyer vs Iyer" in body
        assert "OVERDUE (was Mon 2 Nov): Old chase -- Iyer vs Iyer" in body
        assert "Fri 6 Nov, 15:00-16:30: Mediation - Mediation sitting -- Iyer vs Iyer" in body
        for absent in ("Done already", "Next month", "Undated", "Cancelled call", "Far event"):
            assert absent not in body
        # Overdue first.
        assert body.index("Old chase") < body.index("File counter")

    def test_also_due_is_capped_at_ten_lines(self, alice, alice_case):
        ecourts_hearing(alice, alice_case, TOMORROW)
        for i in range(13):
            Task.objects.create(owner=alice, case=alice_case, title=f"Chore {i:02d}", due_date=TOMORROW)
        run()
        body = mail.outbox[0].body
        assert body.count("Chore ") == 10
        assert "+3 more in Case Intel" in body

    def test_tasks_and_events_alone_never_send_an_email(self, alice, alice_case):
        Task.objects.create(owner=alice, case=alice_case, title="Due tomorrow", due_date=TOMORROW)
        Task.objects.create(owner=alice, case=alice_case, title="Overdue", due_date=date(2026, 10, 1))
        CaseEvent.objects.create(owner=alice, case=alice_case, title="Meeting", date=TOMORROW)
        assert run().sent == 0
        assert mail.outbox == []

    def test_no_also_due_section_when_nothing_is_due(self, alice, alice_case):
        ecourts_hearing(alice, alice_case, TOMORROW)
        run()
        assert "Also due" not in mail.outbox[0].body

    def test_tasks_on_closed_cases_are_left_out(self, alice, alice_case):
        ecourts_hearing(alice, alice_case, TOMORROW)
        closed = make_case(alice, title="Old matter", number="C/1", status="closed")
        Task.objects.create(owner=alice, case=closed, title="Stale chore", due_date=date(2026, 9, 1))
        run()
        assert "Stale chore" not in mail.outbox[0].body

    def test_a_task_without_a_case_is_included(self, alice, alice_case):
        ecourts_hearing(alice, alice_case, TOMORROW)
        Task.objects.create(owner=alice, title="Renew bar membership", due_date=TOMORROW)
        run()
        assert "Due Fri 6 Nov: Renew bar membership" in mail.outbox[0].body


# ---------------------------------------------------------------------------
# Tenancy
# ---------------------------------------------------------------------------


class TestTenancy:
    def test_each_advocate_sees_only_their_own_data(self):
        a, b = make_user("alice"), make_user("bob")
        case_a = make_case(a, title="Alice's matter", number="A/1")
        case_b = make_case(b, title="Bob's matter", number="B/1")
        ecourts_hearing(a, case_a, TOMORROW)
        ecourts_hearing(b, case_b, TOMORROW)
        Task.objects.create(owner=a, case=case_a, title="Alice chore", due_date=TOMORROW)
        Task.objects.create(owner=b, case=case_b, title="Bob chore", due_date=TOMORROW)
        CaseEvent.objects.create(owner=a, case=case_a, title="Alice meeting", date=TOMORROW)
        CaseEvent.objects.create(owner=b, case=case_b, title="Bob meeting", date=TOMORROW)

        assert run().sent == 2
        by_recipient = {m.to[0]: m.body for m in mail.outbox}
        alice_body, bob_body = by_recipient["alice@example.test"], by_recipient["bob@example.test"]

        assert "Alice's matter" in alice_body and "Alice chore" in alice_body and "Alice meeting" in alice_body
        assert "Bob" not in alice_body
        assert "Bob's matter" in bob_body and "Bob chore" in bob_body and "Bob meeting" in bob_body
        assert "Alice" not in bob_body
        assert str(case_b.id) not in alice_body.replace(f"/cases/{case_a.id}", "")

    def test_owner_flag_limits_the_run_to_one_user(self):
        a, b = make_user("alice"), make_user("bob")
        ecourts_hearing(a, make_case(a, number="A/1"), TOMORROW)
        ecourts_hearing(b, make_case(b, number="B/1"), TOMORROW)
        assert run(owner_username="bob").sent == 1
        assert [m.to[0] for m in mail.outbox] == ["bob@example.test"]


# ---------------------------------------------------------------------------
# Delivery states
# ---------------------------------------------------------------------------


class TestDelivery:
    def test_not_configured_logs_and_sends_nothing(self, settings, alice, alice_case):
        settings.INVOICE_EMAIL_CONFIGURED = False
        ecourts_hearing(alice, alice_case, TOMORROW)

        report = run()
        assert report.logged == 1 and report.sent == 0
        assert mail.outbox == []
        row = HearingReminder.objects.get()
        assert row.delivery == "logged"
        assert row.sent_at is None

        # "logged" is final: it does not nag the log on every run.
        assert run().logged == 0

    def test_a_send_error_is_recorded_and_retried_on_the_next_run(self, alice, alice_case):
        ecourts_hearing(alice, alice_case, TOMORROW)

        with patch.object(EmailMessage, "send", side_effect=RuntimeError("resend is down\nsecond line")):
            report = run()
        assert report.failed == 1
        row = HearingReminder.objects.get()
        assert row.delivery == "failed"
        assert row.attempts == 1
        assert row.error == "RuntimeError: resend is down second line"
        assert "Traceback" not in row.error
        assert row.sent_at is None
        assert mail.outbox == []

        report = run()  # the 19:45 run: the mail backend works again
        assert report.sent == 1
        row.refresh_from_db()
        assert (row.delivery, row.attempts, row.error) == ("sent", 2, "")
        assert row.sent_at is not None
        assert len(mail.outbox) == 1
        assert HearingReminder.objects.count() == 1  # the same row, not a second one

        assert run().sent == 0

    def test_a_fourth_attempt_is_never_made(self, alice, alice_case):
        ecourts_hearing(alice, alice_case, TOMORROW)
        with patch.object(EmailMessage, "send", side_effect=RuntimeError("down")) as send:
            for _ in range(5):
                run()
        assert send.call_count == hearing_reminders.MAX_ATTEMPTS == 3
        row = HearingReminder.objects.get()
        assert (row.delivery, row.attempts) == ("failed", 3)

    def test_a_backend_that_accepts_nothing_counts_as_failed(self, alice, alice_case):
        ecourts_hearing(alice, alice_case, TOMORROW)
        with patch.object(EmailMessage, "send", return_value=0):
            assert run().failed == 1

    def test_one_advocates_failure_does_not_stop_the_others(self):
        a, b = make_user("alice"), make_user("bob")
        ecourts_hearing(a, make_case(a, number="A/1"), TOMORROW)
        ecourts_hearing(b, make_case(b, number="B/1"), TOMORROW)
        real = hearing_reminders.build_digest

        def flaky(owner, *args, **kwargs):
            if owner.username == "alice":
                raise ValueError("boom")
            return real(owner, *args, **kwargs)

        with patch.object(hearing_reminders, "build_digest", side_effect=flaky):
            report = run()
        assert report.crashed == 1 and report.sent == 1
        assert [m.to[0] for m in mail.outbox] == ["bob@example.test"]
        # Alice has no row, so the next run still tries her.
        assert HearingReminder.objects.filter(owner=a).count() == 0
        assert run().sent == 1

    def test_a_run_that_cannot_take_the_lock_does_nothing(self, alice, alice_case):
        ecourts_hearing(alice, alice_case, TOMORROW)

        class _Held:
            def __enter__(self):
                return False

            def __exit__(self, *exc):
                return False

        with patch.object(hearing_reminders, "_run_lock", return_value=_Held()):
            report = run()
        assert report.not_run_reason
        assert mail.outbox == []
        assert HearingReminder.objects.count() == 0

    def test_the_lock_is_released_after_a_run(self, alice, alice_case):
        from django.db import connection

        ecourts_hearing(alice, alice_case, TOMORROW)
        run()
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [hearing_reminders.ADVISORY_LOCK_KEY])
            assert cursor.fetchone()[0] is True
            cursor.execute("SELECT pg_advisory_unlock(%s)", [hearing_reminders.ADVISORY_LOCK_KEY])


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


class TestCommand:
    def test_dry_run_prints_the_digest_and_writes_and_sends_nothing(self, alice, alice_case):
        ecourts_hearing(alice, alice_case, TOMORROW)
        out = StringIO()
        call_command("send_hearing_reminders", "--dry-run", "--today", "2026-11-05", stdout=out)
        text = out.getvalue()
        assert "To: alice@example.test" in text
        assert "Subject: Hearing tomorrow: Rao vs State" in text
        assert "Tomorrow, Fri 6 Nov" in text
        assert mail.outbox == []
        assert HearingReminder.objects.count() == 0

        # And it did not use up the real send.
        call_command("send_hearing_reminders", "--today", "2026-11-05", stdout=StringIO())
        assert len(mail.outbox) == 1

    def test_real_run_summary(self, alice, alice_case):
        ecourts_hearing(alice, alice_case, TOMORROW)
        out = StringIO()
        call_command("send_hearing_reminders", "--today", "2026-11-05", stdout=out)
        assert "1 digest(s) -> 1 sent, 0 logged" in out.getvalue()

    def test_owner_flag(self):
        a, b = make_user("alice"), make_user("bob")
        ecourts_hearing(a, make_case(a, number="A/1"), TOMORROW)
        ecourts_hearing(b, make_case(b, number="B/1"), TOMORROW)
        call_command("send_hearing_reminders", "--owner", "alice", "--today", "2026-11-05", stdout=StringIO())
        assert [m.to[0] for m in mail.outbox] == ["alice@example.test"]

    def test_bad_arguments(self, alice):
        with pytest.raises(CommandError, match="YYYY-MM-DD"):
            call_command("send_hearing_reminders", "--today", "05-11-2026", stdout=StringIO())
        with pytest.raises(CommandError, match="No user"):
            call_command("send_hearing_reminders", "--owner", "ghost", stdout=StringIO())

    def test_defaults_to_the_real_india_date(self, alice, alice_case):
        from core.services.india_time import india_today

        ecourts_hearing(alice, alice_case, india_today() + timedelta(days=1))
        call_command("send_hearing_reminders", stdout=StringIO())
        assert len(mail.outbox) == 1


class TestProfileApi:
    def test_the_three_switches_are_exposed_and_writable(self, alice):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=alice)

        resp = client.get("/api/advocate-profile/")
        assert resp.status_code == 200
        assert resp.data["hearing_reminders_enabled"] is True
        assert resp.data["hearing_reminder_two_days"] is True
        assert resp.data["hearing_reminder_one_day"] is True

        resp = client.patch(
            "/api/advocate-profile/",
            {"hearing_reminders_enabled": False, "hearing_reminder_two_days": False},
            format="json",
        )
        assert resp.status_code == 200
        profile = AdvocateProfile.objects.get(owner=alice)
        assert profile.hearing_reminders_enabled is False
        assert profile.hearing_reminder_two_days is False
        assert profile.hearing_reminder_one_day is True
