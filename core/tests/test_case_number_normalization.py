"""
Regression coverage for case-number formatting inconsistency (UI/UX pass,
item 6): the eCourts portal's own HTML occasionally puts a stray space
between a case-type prefix and the slash that follows it, e.g.
"WP /26147/2026" instead of "WP/26147/2026" -- confirmed by comparing
against sibling cases from the same source that don't have it. _clean()
deliberately doesn't strip single internal spaces (shared with fields like
party names where that spacing is meaningful), so a dedicated
normalize_case_number() collapses it specifically for case numbers, at
both places raw eCourts values become Case.case_number:
parse_case_history_html's registration_number and
parse_advocate_search_html's case_number.
"""

from core.services.court_data.ecourts_parsing import (
    normalize_case_number,
    parse_advocate_search_html,
    parse_case_history_html,
)


class TestNormalizeCaseNumber:
    def test_collapses_space_before_prefix_slash(self):
        assert normalize_case_number("WP /26147/2026") == "WP/26147/2026"

    def test_leaves_already_clean_value_unchanged(self):
        assert normalize_case_number("WP/23998/2026") == "WP/23998/2026"

    def test_leaves_other_internal_spacing_untouched(self):
        # Only the prefix/slash boundary is collapsed -- this helper isn't
        # a general whitespace stripper.
        assert normalize_case_number("OS 138 / 2008") == "OS 138 / 2008"

    def test_blank_input(self):
        assert normalize_case_number("") == ""
        assert normalize_case_number(None) == ""

    def test_collapses_whitespace_runs_too(self):
        assert normalize_case_number("WP   /26147/2026") == "WP/26147/2026"


class TestRegistrationNumberNormalizedOnParse:
    def test_stray_space_after_prefix_is_collapsed(self):
        html = """
        <table>
          <tr>
            <td>Registration Number</td><td>WP /26147/2026</td>
            <td>Registration Date</td><td>06-08-2026</td>
          </tr>
        </table>
        """
        data = parse_case_history_html(html)

        assert data is not None
        assert data.registration_number == "WP/26147/2026"


class TestAdvocateSearchCaseNumberNormalizedOnParse:
    def test_stray_space_after_prefix_is_collapsed(self):
        html = """<table id='dispTable'><tbody>
            <tr><td>1</td>
            <td>WP /26147/2026</td>
            <td>T. Srivani<br>Vs</br>Jillala Varamma</td>
            <td><a onClick="viewHistory(1,'TSRA110027752023',1,'','CScaseNumber',29,9,1290106,'CSAdvName')">View</a></td>
            </tr>
        </tbody></table>"""

        hits = parse_advocate_search_html(html, advocate_name="")

        assert len(hits) == 1
        assert hits[0].case_number == "WP/26147/2026"


# ---------------------------------------------------------------------------
# Every intake path, and the stored rows (P2: "WP /26147/2026" in production)
# ---------------------------------------------------------------------------

import importlib  # noqa: E402

import pytest  # noqa: E402
from django.apps import apps as global_apps  # noqa: E402
from django.contrib.auth.models import User  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from core.models import Case  # noqa: E402

_tidy = importlib.import_module("core.migrations.0039_normalize_case_numbers")


@pytest.fixture
def owner(db):
    return User.objects.create_user(username="numbers-advocate", password="pw-12345")


@pytest.mark.django_db
class TestIntakeKeepsTheRawValue:
    def test_saving_tidies_and_keeps_the_original(self, owner):
        case = Case.objects.create(owner=owner, case_number="WP /26147/2026", title="t", client_name="")
        case.refresh_from_db()
        assert case.case_number == "WP/26147/2026"
        assert case.case_number_raw == "WP /26147/2026"

    def test_a_clean_number_has_no_raw_copy(self, owner):
        case = Case.objects.create(owner=owner, case_number="WP/23998/2026", title="t", client_name="")
        assert case.case_number_raw == ""

    def test_manual_entry_is_tidied_too(self, owner):
        api = APIClient()
        api.force_authenticate(user=owner)
        resp = api.post("/api/cases/", {"case_number": "OS  /740/2015", "title": "K vs P"}, format="json")
        assert resp.status_code == 201, resp.data
        assert resp.data["case_number"] == "OS/740/2015"
        assert resp.data["case_number_raw"] == "OS  /740/2015"


@pytest.mark.django_db
class TestOneOffMigration:
    def _stored_untidy(self, owner, number):
        case = Case.objects.create(owner=owner, case_number="placeholder", title="t", client_name="")
        Case.objects.filter(pk=case.pk).update(case_number=number)  # as rows imported before the fix
        return case

    def test_tidies_every_owners_rows(self, owner):
        other = User.objects.create_user(username="numbers-other", password="pw-12345")
        mine, theirs = self._stored_untidy(owner, "WP /26147/2026"), self._stored_untidy(other, "WP /1/2026")

        _tidy.forwards(global_apps, None)

        mine.refresh_from_db()
        theirs.refresh_from_db()
        assert (mine.case_number, mine.case_number_raw) == ("WP/26147/2026", "WP /26147/2026")
        assert theirs.case_number == "WP/1/2026"

    def test_a_collision_is_left_for_a_person(self, owner):
        Case.objects.create(owner=owner, case_number="WP/5/2026", title="t", client_name="")
        dup = self._stored_untidy(owner, "WP /5/2026")

        _tidy.forwards(global_apps, None)

        dup.refresh_from_db()
        assert dup.case_number == "WP /5/2026"

    def test_reverse_restores_the_original(self, owner):
        case = self._stored_untidy(owner, "WP /7/2026")
        _tidy.forwards(global_apps, None)
        _tidy.backwards(global_apps, None)
        case.refresh_from_db()
        assert case.case_number == "WP /7/2026"
