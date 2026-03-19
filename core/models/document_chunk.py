from django.db import models
from pgvector.django import VectorField


class DocumentChunk(models.Model):
    document = models.ForeignKey(
        "core.Document", on_delete=models.CASCADE, related_name="chunks"
    )
    chunk_index = models.IntegerField()
    chunk_text = models.TextField()
    # Embedding dimensions: 768 for Ollama nomic-embed-text (default)
    # Note: For OpenAI text-embedding-3-small (1536), adjust dimensions or use conversion
    embedding = VectorField(dimensions=768, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "document_chunks"
        ordering = ["chunk_index"]

    def __str__(self):
        return f"{self.document.filename} - Chunk {self.chunk_index}"
