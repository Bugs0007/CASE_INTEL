"""Unit tests for core.services.party_role.detect_party_role.

Pure function, no DB -- see core/services/advocate_import.py for how this
is wired into the import flow (best-effort, one-shot, at import time only).
"""

from core.services.party_role import detect_party_role


class TestDetectPartyRole:
    def test_clean_petitioner_match(self):
        data = {"petitioner_advocates": ["A. Sharma"], "respondent_advocates": []}
        assert detect_party_role("A. Sharma", "", data) == "petitioner"

    def test_clean_respondent_match(self):
        data = {"petitioner_advocates": [], "respondent_advocates": ["R. Iyer"]}
        assert detect_party_role("R. Iyer", "", data) == "respondent"

    def test_no_match_is_unknown(self):
        data = {"petitioner_advocates": ["A. Sharma"], "respondent_advocates": ["R. Iyer"]}
        assert detect_party_role("Someone Else", "", data) == "unknown"

    def test_match_on_both_sides_is_ambiguous_unknown(self):
        data = {"petitioner_advocates": ["A. Sharma"], "respondent_advocates": ["A. Sharma"]}
        assert detect_party_role("A. Sharma", "", data) == "unknown"

    def test_bar_code_search_is_always_unknown(self):
        # party_advocate_data never carries bar codes -- nothing to
        # compare a bar code against, regardless of what's recorded.
        data = {"petitioner_advocates": ["A. Sharma"], "respondent_advocates": []}
        assert detect_party_role("", "MAH/1234/2015", data) == "unknown"

    def test_empty_party_advocate_data_is_unknown(self):
        assert detect_party_role("A. Sharma", "", {}) == "unknown"
        assert detect_party_role("A. Sharma", "", None) == "unknown"

    def test_honorifics_and_case_are_normalized(self):
        data = {"petitioner_advocates": ["Advocate- A. Sharma"], "respondent_advocates": []}
        assert detect_party_role("a sharma", "", data) == "petitioner"

    def test_substring_match_on_fuller_recorded_name(self):
        data = {"petitioner_advocates": ["Anil Kumar Sharma"], "respondent_advocates": []}
        assert detect_party_role("Sharma", "", data) == "petitioner"

    def test_no_advocate_name_is_unknown(self):
        data = {"petitioner_advocates": ["A. Sharma"], "respondent_advocates": []}
        assert detect_party_role("", "", data) == "unknown"
