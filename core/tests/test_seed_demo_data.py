"""Tests for the `seed_demo_data` management command.

Focused on one regression class: case_number is unique per owner, not
globally (core/models/case.py's (owner, case_number) UniqueConstraint) --
the command's own docstring promises "Only the demo user's own rows are
ever touched -- no other user or case is read or modified", so its
case-creation lookup must be scoped to the demo user being seeded, not to
case_number alone. Before the fix, `Case.objects.get_or_create(case_number=...)`
with no `owner` in the lookup kwargs would match ANY owner's row with that
case_number and silently skip creating the demo user's own case.
"""

from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from core.models import Case

CASE_NUMBER = "DEMO-2026-CV-001"


def run(*args) -> str:
    out = StringIO()
    call_command("seed_demo_data", *args, stdout=out, stderr=out)
    return out.getvalue()


@pytest.mark.django_db
class TestSeedDemoDataOwnerScoping:
    def test_seeding_creates_its_own_row_even_when_another_owner_has_the_same_case_number(self):
        other_user = User.objects.create_user(username="someone-else", password="pass-123")
        Case.objects.create(
            owner=other_user, case_number=CASE_NUMBER, title="Someone else's case", client_name="",
        )

        run("--commit", "--username", "demo-seed-test")

        demo_user = User.objects.get(username="demo-seed-test")
        # The seed must have created ITS OWN row for this demo user, not
        # silently reused/skipped because another owner already holds
        # this case_number.
        seeded_case = Case.objects.get(owner=demo_user, case_number=CASE_NUMBER)
        assert seeded_case.title != "Someone else's case"
        assert Case.objects.filter(case_number=CASE_NUMBER).count() == 2

    def test_rerun_for_the_same_user_does_not_duplicate(self):
        run("--commit", "--username", "demo-seed-test-2")
        run("--commit", "--username", "demo-seed-test-2")

        demo_user = User.objects.get(username="demo-seed-test-2")
        assert Case.objects.filter(owner=demo_user, case_number=CASE_NUMBER).count() == 1
