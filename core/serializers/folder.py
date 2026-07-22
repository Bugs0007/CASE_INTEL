"""
Serializers for folders.
"""

from rest_framework import serializers
from core.models import Folder


class FolderSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # No endpoint currently lets a client create/edit folders (only
        # FolderListView, read-only), but scope this defensively so a
        # future write endpoint doesn't inherit a cross-tenant hole.
        request = self.context.get("request")
        if request is not None and "parent_folder" in self.fields:
            self.fields["parent_folder"].queryset = Folder.objects.filter(
                owner=request.user
            )

    class Meta:
        model = Folder
        fields = ["id", "name", "parent_folder", "created_at"]
        read_only_fields = ["id", "created_at"]