from django.db import migrations
from pgvector.django import HnswIndex


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_alter_activitylog_id_alter_case_id_alter_casetag_id_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="documentchunk",
            index=HnswIndex(
                fields=["embedding"],
                name="document_chunks_embedding_hnsw",
                opclasses=["vector_cosine_ops"],
            ),
        ),
    ]
