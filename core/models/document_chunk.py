from django.db import models
from pgvector.django import VectorField


class DocumentChunk(models.Model):
    document = models.ForeignKey(
        "core.Document", on_delete=models.CASCADE, related_name="chunks"
    )
    chunk_index = models.IntegerField()
    chunk_text = models.TextField()
    embedding = VectorField(dimensions=1536, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "document_chunks"
        ordering = ["chunk_index"]

    def __str__(self):
        return f"{self.document.filename} - Chunk {self.chunk_index}"
