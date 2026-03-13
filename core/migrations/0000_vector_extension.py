from pgvector.django import VectorExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = []

    operations = [
        VectorExtension(),
    ]
