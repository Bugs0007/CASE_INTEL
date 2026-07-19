"""
Standalone verification for GeminiEmbeddingService -- calls the REAL
Gemini embed_content API once and asserts the response is actually
768-dimensional, since output_dimensionality is set explicitly on every
call and must match DocumentChunk.embedding's fixed VectorField(768)
column. Does not touch the database or any Document/DocumentChunk rows.

Usage:
    python manage.py test_gemini_embedding "some text"
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.services.gemini_embedding_service import GeminiEmbeddingService


class Command(BaseCommand):
    help = "Call the real Gemini embedding API once and verify the response is 768-dim."

    def add_arguments(self, parser):
        parser.add_argument("text", type=str)

    def handle(self, *args, **options):
        text = options["text"]

        if not settings.GEMINI_API_KEY:
            raise CommandError(
                "GEMINI_API_KEY is not set. Add it to .env before running this command."
            )

        service = GeminiEmbeddingService()
        self.stdout.write(
            f"Calling Gemini (model={service.model}, "
            f"output_dimensionality={settings.EMBEDDING_DIMENSIONS}) with: {text!r}"
        )

        embedding = service.embed_text(text)

        self.stdout.write(f"len(embedding) = {len(embedding)}")

        assert len(embedding) == 768, (
            f"Expected a 768-dim embedding to match DocumentChunk.embedding's "
            f"VectorField(dimensions=768), got {len(embedding)}. Gemini did not "
            f"honor output_dimensionality, or the schema has drifted."
        )

        self.stdout.write(
            self.style.SUCCESS(
                "OK: embedding is 768-dim, matches DocumentChunk.embedding schema."
            )
        )
