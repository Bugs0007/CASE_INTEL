"""The advocate's own invoice letterhead / billing profile.

A singleton per user, so this is a plain APIView on /api/advocate-profile/
rather than a list+detail pair -- the caller never needs (or is allowed)
an id, which removes the whole class of "fetch another advocate's
profile by id" mistakes.
"""

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.serializers import AdvocateProfileSerializer
from core.services.invoice_service import get_or_create_profile


class AdvocateProfileView(APIView):
    """Read or update the requesting advocate's billing profile.

    GET   /api/advocate-profile/
    PATCH /api/advocate-profile/

    Scoped by construction: the profile is always looked up by
    request.user, never by a client-supplied id.
    """

    def get(self, request: Request) -> Response:
        profile = get_or_create_profile(request.user)
        return Response(AdvocateProfileSerializer(profile).data)

    def patch(self, request: Request) -> Response:
        profile = get_or_create_profile(request.user)
        serializer = AdvocateProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
