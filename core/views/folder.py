"""
Folder views — list folders for document organization.
"""

from rest_framework import generics

from core.models import Folder
from core.serializers.folder import FolderSerializer


class FolderListView(generics.ListAPIView):
    """List all folders.
    
    GET /api/folders/
    """
    
    serializer_class = FolderSerializer
    queryset = Folder.objects.all().order_by('name')