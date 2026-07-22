"""
Folder views — list folders for document organization.
"""

from rest_framework import generics

from core.models import Folder
from core.serializers.folder import FolderSerializer
from core.views.mixins import OwnerScopedMixin


class FolderListView(OwnerScopedMixin, generics.ListAPIView):
    """List all folders belonging to request.user.

    GET /api/folders/
    """

    serializer_class = FolderSerializer
    queryset = Folder.objects.all().order_by('name')