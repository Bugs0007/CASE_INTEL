"""Tests for the `setup_demo_account` management command.

The properties that actually matter for a public-facing portfolio account:
no credential is ever written by the command, re-running is safe, and it
never fabricates case data (which is the whole point of this account --
its caseload comes from a real eCourts import, not a seeder).
"""

from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import AdvocateProfile, Case


def run(*args) -> str:
    out = StringIO()
    call_command("setup_demo_account", *args, stdout=out, stderr=out)
    return out.getvalue()


@pytest.mark.django_db
class TestSetup:
    def test_creates_user_with_unusable_password(self):
        run()

        user = User.objects.get(username="recruiter")
        assert not user.has_usable_password()

    def test_creates_no_cases(self):
        run()

        user = User.objects.get(username="recruiter")
        assert Case.objects.filter(owner=user).count() == 0

    def test_creates_the_billing_profile_row(self):
        run()

        user = User.objects.get(username="recruiter")
        assert AdvocateProfile.objects.filter(owner=user).exists()

    def test_warns_when_letterhead_is_blank(self):
        output = run()
        assert "Letterhead name is blank" in output

    def test_letterhead_flags_are_applied(self):
        run(
            "--letterhead-name", "S. Bhagath, Advocate",
            "--address", "12 Court Road\\nHyderabad 500001",
            "--bar-number", "AP/1234/2015",
            "--default-fee", "15000",
            "--invoice-prefix", "CI",
        )

        profile = AdvocateProfile.objects.get(owner__username="recruiter")
        assert profile.letterhead_name == "S. Bhagath, Advocate"
        # The literal "\n" from argparse becomes a real line break, so the
        # address renders as a multi-line block on the invoice.
        assert profile.address == "12 Court Road\nHyderabad 500001"
        assert profile.bar_registration_number == "AP/1234/2015"
        assert str(profile.default_fee_amount) == "15000.00"
        assert profile.invoice_prefix == "CI"

    def test_rejects_a_non_numeric_fee(self):
        with pytest.raises(CommandError):
            run("--default-fee", "lots")

    def test_custom_username(self):
        run("--username", "portfolio-demo")
        assert User.objects.filter(username="portfolio-demo").exists()


@pytest.mark.django_db
class TestIdempotency:
    def test_rerun_does_not_clobber_a_real_password(self):
        """The operator sets a password with `changepassword` after the
        first run; a later re-run (to re-read the next-step notes, say)
        must not silently lock them back out."""
        run()
        user = User.objects.get(username="recruiter")
        user.set_password("a-real-password-set-by-the-operator")
        user.save()

        run()

        user.refresh_from_db()
        assert user.has_usable_password()
        assert user.check_password("a-real-password-set-by-the-operator")

    def test_rerun_does_not_blank_existing_letterhead(self):
        run("--letterhead-name", "S. Bhagath, Advocate")
        run()  # no flags this time

        profile = AdvocateProfile.objects.get(owner__username="recruiter")
        assert profile.letterhead_name == "S. Bhagath, Advocate"

    def test_rerun_against_a_populated_account_creates_nothing(self):
        run()
        user = User.objects.get(username="recruiter")
        Case.objects.create(
            owner=user, case_number="REAL-1", title="An imported case", client_name="",
        )

        output = run()

        assert Case.objects.filter(owner=user).count() == 1
        assert "already holds 1 case" in output


@pytest.mark.django_db
class TestVerify:
    def test_errors_when_the_account_does_not_exist(self):
        with pytest.raises(CommandError):
            run("--verify")

    def test_reports_an_empty_account_as_todo(self):
        run()
        output = run("--verify")

        assert "Cases: 0" in output
        assert "TODO" in output

    def test_reports_a_populated_account(self):
        run()
        user = User.objects.get(username="recruiter")
        Case.objects.create(
            owner=user,
            case_number="REAL-1",
            title="An imported case",
            client_name="",
            court_type="high_court",
            cnr_number="TSHC010051622026",
            tracking_enabled=True,
        )

        output = run("--verify")

        assert "Cases: 1" in output
        assert "High Court cases: 1" in output

    def test_verify_creates_nothing(self):
        run()
        before = Case.objects.count()

        run("--verify")

        assert Case.objects.count() == before
