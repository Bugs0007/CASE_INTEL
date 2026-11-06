"""Telling an advocate's own name forms from other people the court lists.

Pure functions (no database): classify_advocate_name, query minimisation and
name-form suggestions. The names are the ones the redesigned search was specified
with: an advocate "Rambabu Samalla" whom courts list as Rambabu, Ram babu,
S Rambabu, S Ram babu and Rambabu S, and who is NOT T Rambabu, K Rambabu or
Rambabu Reddy.
"""

from types import SimpleNamespace

import pytest

from core.services.name_matching import (
    CHECK,
    EXCLUDED,
    MATCHED,
    OTHER,
    advocate_name_tokens,
    advocate_names_equal,
    classify_advocate_name,
    classify_listed_advocates,
    minimize_queries,
    normalize_advocate_name,
    suggest_name_forms,
)

FORMS = ["Rambabu", "Ram babu", "S Rambabu", "S Ram babu", "Rambabu S"]
NOT_ME = ["T Rambabu", "K Rambabu", "Rambabu Reddy"]
PROFILE = SimpleNamespace(name_forms=FORMS, excluded_names=NOT_ME)


class TestNormalize:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("S. Rambabu", "s rambabu"),
            ("Adv. S Rambabu", "s rambabu"),
            ("Advocate Rambabu S.", "rambabu s"),
            ("Sri S. Rambabu", "s rambabu"),
            ("Smt. Lakshmi Devi", "lakshmi devi"),
            ("SHRI  RAMBABU,  S", "rambabu s"),
            ("G.Ramesh kumar", "g ramesh kumar"),
            ("", ""),
        ],
    )
    def test_normalize(self, raw, expected):
        assert normalize_advocate_name(raw) == expected


class TestNamesEqual:
    @pytest.mark.parametrize(
        "a, b",
        [
            ("Ram babu", "Rambabu"),  # spaces do not matter
            ("S Rambabu", "Rambabu S"),  # up to three words, order does not matter
            ("S Ram babu", "Rambabu S"),
            ("Ram babu S", "S Rambabu"),
            ("RAMBABU S", "s rambabu"),
        ],
    )
    def test_equal(self, a, b):
        assert advocate_names_equal(advocate_name_tokens(a), advocate_name_tokens(b))

    @pytest.mark.parametrize(
        "a, b",
        [
            ("T Rambabu", "S Rambabu"),
            ("Rambabu Reddy", "Rambabu S"),
            ("Ramesh", "Rambabu"),
            ("A B C D", "D C B A"),  # four words: order matters again
        ],
    )
    def test_not_equal(self, a, b):
        assert not advocate_names_equal(advocate_name_tokens(a), advocate_name_tokens(b))

    def test_empty_never_equal(self):
        assert not advocate_names_equal((), ())
        assert not advocate_names_equal(("a",), ())


# (name as the court lists it, expected class) against FORMS / NOT_ME above.
CLASSIFY_TABLE = [
    # The advocate's own spellings: an initial or a split name backs them up.
    ("S Rambabu", MATCHED),
    ("Rambabu S", MATCHED),
    ("S Ram babu", MATCHED),
    ("Ram babu", MATCHED),
    ("S. Rambabu", MATCHED),
    ("Adv. S Rambabu", MATCHED),
    ("Sri S Rambabu", MATCHED),
    ("RAMBABU S", MATCHED),
    ("Babu Ram", MATCHED),  # word order is ignored up to three words
    # One word only: could be anyone with the name, never auto-verified.
    ("Rambabu", CHECK),
    ("RAMBABU.", CHECK),
    ("Adv Rambabu", CHECK),
    # The Not me list wins, honorifics and case aside.
    ("T Rambabu", EXCLUDED),
    ("K Rambabu", EXCLUDED),
    ("Rambabu Reddy", EXCLUDED),
    ("Reddy Rambabu", EXCLUDED),
    ("Adv. T. Rambabu", EXCLUDED),
    # The portal's loose matching returns all sorts of names.
    ("G Rambabu", OTHER),
    ("Samalla Rambabu", OTHER),
    ("Rambabu Naidu", OTHER),
    ("APP G.Ramesh Kumar", OTHER),
    ("", OTHER),
]


@pytest.mark.parametrize("listed, expected", CLASSIFY_TABLE)
def test_classify_advocate_name_table(listed, expected):
    assert classify_advocate_name(listed, PROFILE) == expected


class TestClassifyEdgeCases:
    def test_single_word_form_never_verifies_a_row_on_its_own(self):
        only_single = SimpleNamespace(name_forms=["Rambabu"], excluded_names=[])
        assert classify_advocate_name("Rambabu", only_single) == CHECK
        # "Ram babu" equals "Rambabu" once spaces are ignored, but only through
        # the single-word form: still a check.
        assert classify_advocate_name("Ram babu", only_single) == CHECK
        # Not the same name at all.
        assert classify_advocate_name("S Rambabu", only_single) == OTHER

    def test_single_word_listed_name_never_verifies_even_against_a_split_form(self):
        split_only = SimpleNamespace(name_forms=["Ram babu"], excluded_names=[])
        assert classify_advocate_name("Rambabu", split_only) == CHECK
        assert classify_advocate_name("Ram babu", split_only) == MATCHED

    def test_excluded_is_checked_before_matched(self):
        # Never stored this way (a name is not in both lists), but if it were,
        # the advocate's explicit rejection wins.
        both = SimpleNamespace(name_forms=["S Rambabu"], excluded_names=["Rambabu S"])
        assert classify_advocate_name("S Rambabu", both) == EXCLUDED

    def test_empty_profile_makes_everything_other(self):
        empty = SimpleNamespace(name_forms=[], excluded_names=[])
        assert classify_advocate_name("S Rambabu", empty) == OTHER

    def test_profile_without_the_attributes_is_tolerated(self):
        assert classify_advocate_name("S Rambabu", SimpleNamespace()) == OTHER


class TestClassifyListedAdvocates:
    def test_designation_on_its_own_line_does_not_hide_the_name(self):
        assert classify_listed_advocates(["APP", "S Rambabu"], PROFILE) == MATCHED

    def test_the_advocates_name_beside_a_rejected_one_still_wins(self):
        assert classify_listed_advocates(["T Rambabu", "S Rambabu"], PROFILE) == MATCHED

    def test_check_beats_excluded(self):
        assert classify_listed_advocates(["T Rambabu", "Rambabu"], PROFILE) == CHECK

    def test_excluded_beats_other(self):
        assert classify_listed_advocates(["APP", "T Rambabu"], PROFILE) == EXCLUDED

    def test_a_plain_string_is_one_segment(self):
        assert classify_listed_advocates("S Rambabu", PROFILE) == MATCHED


class TestMinimizeQueries:
    def test_the_five_forms_need_exactly_two_queries(self):
        assert minimize_queries(FORMS) == ["Rambabu", "Ram babu"]

    def test_spaced_spellings_stay_distinct_because_the_portal_is_space_sensitive(self):
        assert minimize_queries(["Rambabu", "Ram babu"]) == ["Rambabu", "Ram babu"]

    def test_initial_only_words_are_dropped(self):
        assert minimize_queries(["S Rambabu"]) == ["Rambabu"]
        assert minimize_queries(["Rambabu S."]) == ["Rambabu"]

    def test_a_query_containing_another_is_dropped(self):
        assert minimize_queries(["Rambabu Samalla", "Rambabu"]) == ["Rambabu"]
        assert minimize_queries(["Rambabu Samalla"]) == ["Rambabu Samalla"]

    def test_under_three_letters_cannot_be_searched(self):
        assert minimize_queries(["Ra", "S R"]) == []

    def test_case_and_duplicates_collapse_keeping_the_first_spelling(self):
        assert minimize_queries(["RAMBABU", "rambabu", "Rambabu S"]) == ["RAMBABU"]

    def test_honorifics_are_dropped(self):
        assert minimize_queries(["Adv. Rambabu Samalla"]) == ["Rambabu Samalla"]

    def test_empty(self):
        assert minimize_queries([]) == []

    def test_unrelated_names_are_all_kept(self):
        assert minimize_queries(["Rambabu", "Suresh Kumar", "Anil"]) == ["Rambabu", "Suresh Kumar", "Anil"]


class TestSuggestNameForms:
    def test_three_suggestions_for_a_two_word_name(self):
        assert suggest_name_forms("Rambabu Samalla", [], []) == ["S Rambabu", "Rambabu S", "Samalla Rambabu"]

    def test_existing_forms_are_left_out(self):
        assert suggest_name_forms("Rambabu Samalla", ["S Rambabu", "Rambabu S"], []) == ["Samalla Rambabu"]

    def test_a_name_on_the_not_me_list_is_not_suggested(self):
        assert suggest_name_forms("Rambabu Samalla", [], ["Samalla Rambabu"]) == ["S Rambabu", "Rambabu S"]

    def test_one_word_name_has_nothing_to_suggest(self):
        assert suggest_name_forms("Rambabu", [], []) == []

    def test_nothing_is_added_on_its_own(self):
        forms: list[str] = []
        suggest_name_forms("Rambabu Samalla", forms, [])
        assert forms == []
