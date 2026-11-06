from django.db import models

from .mixins import OwnedModel


class AdvocateSearchProfile(OwnedModel):
    """Who an advocate search is looking for: the name forms the advocate
    appears under at the courts, the names that are NOT them, and their bar
    enrolment numbers.

    Separate from AdvocateProfile, which is the advocate's billing identity
    (letterhead, invoice counter) and is one row per user. An advocate may keep
    several search profiles (say, themself and a partner they appear for), so
    this is a list with its own CRUD under /api/advocate-profiles/.

    The lists are JSON arrays of strings, edited whole by the API:
      bar_codes       -- "STATE/NUMBER/YEAR", e.g. "TS/1234/2009"
      name_forms      -- spellings that ARE this advocate ("S Rambabu")
      excluded_names  -- spellings that are NOT ("T Rambabu"), hidden from
                         every search. A name is never in both lists.

    Search results store the advocate name exactly as the court listed it; which
    rows are "yours" is decided from these lists when results are read
    (core/services/advocate_results.py), so changing a list re-labels a finished
    search without a new portal call.
    """

    display_name = models.CharField(max_length=120, help_text="The advocate's full name, e.g. 'Rambabu Samalla'.")
    bar_codes = models.JSONField(default=list, blank=True)
    name_forms = models.JSONField(default=list, blank=True)
    excluded_names = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "advocate_search_profiles"
        ordering = ["id"]

    def __str__(self):
        return f"Advocate search profile {self.display_name!r} for user {self.owner_id}"
