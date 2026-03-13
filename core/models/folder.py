from django.db import models


class Folder(models.Model):
    name = models.CharField(max_length=255)
    parent_folder = models.ForeignKey(
        "self", on_delete=models.CASCADE, blank=True, null=True, related_name="subfolders"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "folders"

    def __str__(self):
        return self.name
