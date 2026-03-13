from django.db import models


class CaseTag(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = "case_tags"

    def __str__(self):
        return self.name


class CaseTagMap(models.Model):
    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, related_name="tag_mappings"
    )
    tag = models.ForeignKey(
        CaseTag, on_delete=models.CASCADE, related_name="case_mappings"
    )

    class Meta:
        db_table = "case_tag_map"
        unique_together = ("case", "tag")

    def __str__(self):
        return f"{self.case} - {self.tag}"
