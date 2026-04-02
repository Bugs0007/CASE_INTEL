"""
Serializers for folders.
"""

from rest_framework import serializers
from core.models import Folder


class FolderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Folder
        fields = ["id", "name", "parent_folder", "created_at"]
        read_only_fields = ["id", "created_at"]