"""Advocate search profiles: who a search is looking for.

CRUD under /api/advocate-profiles/ (separate from /api/advocate-profile/, the
billing letterhead), plus two one-click actions used from a result row:

    POST /api/advocate-profiles/<id>/exclude/        {"name": "T Rambabu"}   ("Not me")
    POST /api/advocate-profiles/<id>/add-name-form/  {"name": "Rambabu S"}   ("That's me")

Each MOVES the name: marking a name "Not me" takes it off the name forms, and
"That's me" takes it off the Not me list, because a name is never in both.
Nothing is searched again: result rows are classified when they are read.
"""

from __future__ import annotations

from django.conf import settings
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import AdvocateSearchProfile
from core.serializers.advocate_search_profile import (
    MAX_EXCLUDED,
    MAX_NAME_FORMS,
    AdvocateSearchProfileSerializer,
    clean_name_list,
    same_name,
)
from core.views.mixins import OwnerScopedMixin


class AdvocateSearchProfileListCreateView(OwnerScopedMixin, generics.ListCreateAPIView):
    """GET/POST /api/advocate-profiles/ -- the caller's own search profiles."""

    serializer_class = AdvocateSearchProfileSerializer
    queryset = AdvocateSearchProfile.objects.all()


class AdvocateSearchProfileDetailView(OwnerScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/advocate-profiles/<id>/ -- owner-scoped by the mixin."""

    serializer_class = AdvocateSearchProfileSerializer
    queryset = AdvocateSearchProfile.objects.all()


class _NameActionView(OwnerScopedMixin, generics.GenericAPIView):
    """Base for the two row actions: owner-scoped lookup of the profile (the
    mixin's get_queryset, so another advocate's id is a 404), one `name`."""

    serializer_class = AdvocateSearchProfileSerializer
    queryset = AdvocateSearchProfile.objects.all()

    def _name(self, request) -> str:
        names = clean_name_list([request.data.get("name", "")], label="name", limit=1)
        if not names:
            raise serializers.ValidationError({"name": ["Give the name as the court lists it."]})
        return names[0]

    def _respond(self, profile) -> Response:
        profile.save(update_fields=["name_forms", "excluded_names", "updated_at"])
        return Response(self.get_serializer(profile).data, status=status.HTTP_200_OK)


class AdvocateSearchProfileExcludeView(_NameActionView):
    """"Not me": reject this name from every search, now and later."""

    def post(self, request, pk):
        profile = self.get_object()
        name = self._name(request)
        profile.name_forms = [n for n in profile.name_forms if not same_name(n, name)]
        if not any(same_name(n, name) for n in profile.excluded_names):
            if len(profile.excluded_names) >= MAX_EXCLUDED:
                raise serializers.ValidationError({"name": [f"The Not me list holds at most {MAX_EXCLUDED} names."]})
            profile.excluded_names = [*profile.excluded_names, name]
        return self._respond(profile)


class AdvocateSearchProfileAddNameFormView(_NameActionView):
    """"That's me": this spelling is the advocate's own."""

    def post(self, request, pk):
        profile = self.get_object()
        name = self._name(request)
        profile.excluded_names = [n for n in profile.excluded_names if not same_name(n, name)]
        if not any(same_name(n, name) for n in profile.name_forms):
            if len(profile.name_forms) >= MAX_NAME_FORMS:
                raise serializers.ValidationError({"name": [f"A profile holds at most {MAX_NAME_FORMS} name forms."]})
            profile.name_forms = [*profile.name_forms, name]
        return self._respond(profile)


class AdvocateSearchFeaturesView(APIView):
    """GET /api/advocate-search/features/ -- whether the redesigned search is
    switched on (ADVOCATE_SEARCH_V2), so the page can pick the old or the new flow."""

    def get(self, request):
        return Response(
            {
                "v2": bool(settings.ADVOCATE_SEARCH_V2),
                # What the page tells the advocate to expect per portal request
                # (display only; see the setting's comment).
                "seconds_per_call": settings.ADVOCATE_SEARCH_ESTIMATE_SECONDS_PER_CALL,
            }
        )
