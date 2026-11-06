"""Serializer for an advocate's search profile (who a search is looking for)."""

import re

from django.conf import settings
from rest_framework import serializers

from core.models import AdvocateSearchProfile
from core.services.name_matching import (
    MAX_RECOMMENDED_QUERIES,
    advocate_name_tokens,
    advocate_names_equal,
    minimize_queries,
    normalize_advocate_name,
    suggest_name_forms,
)

BAR_CODE_RE = re.compile(r"^[A-Za-z]{2,3}/\d+/\d{4}$")
MAX_BAR_CODES = 5
MAX_NAME_FORMS = 40
MAX_EXCLUDED = 200
MAX_NAME_LENGTH = 100


def same_name(a: str, b: str) -> bool:
    """The matching rule itself: equal ignoring spaces and, up to three words,
    word order. "S Rambabu" and "Rambabu S" are one name, so the two lists never
    hold either of them at once -- exactly what classification would do."""
    return advocate_names_equal(advocate_name_tokens(a), advocate_name_tokens(b))


def clean_name_list(value, *, label: str, limit: int) -> list[str]:
    if not isinstance(value, list):
        raise serializers.ValidationError(f"{label} must be a list of names.")
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise serializers.ValidationError(f"{label} must be a list of names.")
        name = re.sub(r"\s+", " ", item).strip()
        if not name:
            continue
        if len(name) > MAX_NAME_LENGTH:
            raise serializers.ValidationError(f"A name in {label} is longer than {MAX_NAME_LENGTH} characters.")
        # Spaces are KEPT in the duplicate check: "Rambabu" and "Ram babu" are two
        # spellings the portal searches differently, so both stay. Only case,
        # honorifics, dots and repeated spaces make two entries the same.
        key = normalize_advocate_name(name)
        if not key:
            raise serializers.ValidationError(f"{name!r} has no letters to match on.")
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(name)
    if len(cleaned) > limit:
        raise serializers.ValidationError(f"{label} can hold at most {limit} names.")
    return cleaned


def query_plan(profile) -> dict:
    """What would go to eCourts for this profile. The ONE place the minimized
    queries are built: the serializer (the profile card's "What goes to
    eCourts" box) and the search start both read it, so what the advocate is
    shown is what is sent."""
    queries = minimize_queries(list(profile.name_forms or []))
    warning = ""
    if len(queries) > MAX_RECOMMENDED_QUERIES:
        warning = (
            f"{len(queries)} different searches would go to eCourts for every court complex, "
            f"and each one scans the whole complex, so this takes {len(queries)} times as long as one "
            "name. Drop the spellings you do not need, or keep them if you want the wider net."
        )
    return {
        "queries": queries,
        "query_count": len(queries),
        "warning": warning,
        "seconds_per_call": settings.ADVOCATE_SEARCH_ESTIMATE_SECONDS_PER_CALL,
    }


class AdvocateSearchProfileSerializer(serializers.ModelSerializer):
    # Read-only and computed from the lists above, so the card never has to
    # re-implement them.
    queries = serializers.SerializerMethodField()
    query_count = serializers.SerializerMethodField()
    query_warning = serializers.SerializerMethodField()
    suggestions = serializers.SerializerMethodField()

    class Meta:
        model = AdvocateSearchProfile
        fields = [
            "id",
            "display_name",
            "bar_codes",
            "name_forms",
            "excluded_names",
            "queries",
            "query_count",
            "query_warning",
            "suggestions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_queries(self, obj):
        return query_plan(obj)["queries"]

    def get_query_count(self, obj):
        return query_plan(obj)["query_count"]

    def get_query_warning(self, obj):
        return query_plan(obj)["warning"]

    def get_suggestions(self, obj):
        return suggest_name_forms(obj.display_name, obj.name_forms, obj.excluded_names)

    def validate_display_name(self, value):
        value = re.sub(r"\s+", " ", value or "").strip()
        if not value:
            raise serializers.ValidationError("Enter the advocate's name.")
        return value

    def validate_bar_codes(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("bar_codes must be a list.")
        codes: list[str] = []
        for item in value:
            code = str(item).strip()
            if not code:
                continue
            if not BAR_CODE_RE.match(code):
                raise serializers.ValidationError(
                    f"{code!r} is not a bar code in STATE/NUMBER/YEAR form (for example TS/1234/2009)."
                )
            code = code.upper()
            if code not in codes:
                codes.append(code)
        if len(codes) > MAX_BAR_CODES:
            raise serializers.ValidationError(f"At most {MAX_BAR_CODES} bar codes.")
        return codes

    def validate_name_forms(self, value):
        return clean_name_list(value, label="name_forms", limit=MAX_NAME_FORMS)

    def validate_excluded_names(self, value):
        return clean_name_list(value, label="excluded_names", limit=MAX_EXCLUDED)

    def validate(self, attrs):
        # A name cannot be both "me" and "not me". The lists are edited whole,
        # so judge the result: what is sent, else what is already stored.
        forms = attrs.get("name_forms", getattr(self.instance, "name_forms", []) or [])
        excluded = attrs.get("excluded_names", getattr(self.instance, "excluded_names", []) or [])
        clashing = sorted({n for n in forms if any(same_name(n, e) for e in excluded)})
        if clashing:
            raise serializers.ValidationError(
                {"name_forms": [f"{', '.join(clashing)}: a name cannot be both one of yours and on the Not me list."]}
            )
        return attrs
