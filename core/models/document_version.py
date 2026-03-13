from django.db import models


class DocumentVersion(models.Model):
    document = models.ForeignKey(
        "core.Document", on_delete=models.CASCADE, related_name="versions"
    )
    version_number = models.IntegerField()
    file_path = models.CharField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "document_versions"
        ordering = ["-version_number"]

    def __str__(self):
        return f"{self.document.filename} v{self.version_number}"
