from django.db import models


class DocumentTag(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = "document_tags"

    def __str__(self):
        return self.name


class DocumentTagMap(models.Model):
    document = models.ForeignKey(
        "core.Document", on_delete=models.CASCADE, related_name="tag_mappings"
    )
    tag = models.ForeignKey(
        DocumentTag, on_delete=models.CASCADE, related_name="document_mappings"
    )

    class Meta:
        db_table = "document_tag_map"
        unique_together = ("document", "tag")

    def __str__(self):
        return f"{self.document} - {self.tag}"
