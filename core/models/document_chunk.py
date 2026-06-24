from django.db import models
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from pgvector.django import VectorField


class DocumentChunk(models.Model):
    document = models.ForeignKey(
        "core.Document", on_delete=models.CASCADE, related_name="chunks"
    )
    chunk_index = models.IntegerField()
    chunk_text = models.TextField()

    # Vector embedding — 768 dims for nomic-embed-text
    embedding = VectorField(dimensions=768, blank=True, null=True)

    # Full-text search vector for BM25/keyword search.
    # Populated automatically by DocumentProcessor via a raw SQL UPDATE
    # after bulk_create (Django ORM cannot set tsvector directly).
    # The GIN index makes full-text queries fast even with 100k+ chunks.
    search_vector = SearchVectorField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "document_chunks"
        ordering = ["chunk_index"]
        indexes = [
            # GIN index for full-text search — required for fast @@ queries
            GinIndex(fields=["search_vector"], name="document_chunks_svector_gin"),
        ]

    def __str__(self):
        return f"{self.document.filename} - Chunk {self.chunk_index}"
