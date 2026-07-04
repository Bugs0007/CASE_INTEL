"""
Migration: add content_hash to Document and search_vector (tsvector) to DocumentChunk.

Name this file according to your migration numbering, e.g.:
    core/migrations/0005_add_hash_and_tsvector.py

How to apply:
    python manage.py migrate
"""

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        # Replace with your actual last migration name
        ("core", "0004_alter_activitylog_id_alter_case_id_alter_casetag_id_and_more"),
    ]

    operations = [
        # --- Document: SHA-256 content hash for deduplication ---
        migrations.AddField(
            model_name="document",
            name="content_hash",
            field=models.CharField(
                max_length=64,
                blank=True,
                null=True,
                db_index=True,
                help_text="SHA-256 hex digest of the uploaded file.",
            ),
        ),

        # --- DocumentChunk: tsvector column for full-text / BM25 search ---
        migrations.AddField(
            model_name="documentchunk",
            name="search_vector",
            field=SearchVectorField(null=True, blank=True),
        ),

        # --- GIN index on search_vector for fast full-text queries ---
        migrations.AddIndex(
            model_name="documentchunk",
            index=GinIndex(
                fields=["search_vector"],
                name="document_chunks_search_vector_gin",
            ),
        ),

        # --- Backfill search_vector for all existing chunks ---
        # This runs a single SQL UPDATE so it's fast even with many rows.
        migrations.RunSQL(
            sql="""
                UPDATE document_chunks
                SET search_vector = to_tsvector('english', chunk_text)
                WHERE chunk_text IS NOT NULL AND chunk_text != '';
            """,
            reverse_sql="""
                UPDATE document_chunks SET search_vector = NULL;
            """,
        ),
    ]
