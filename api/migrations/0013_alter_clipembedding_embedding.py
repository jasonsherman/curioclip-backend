# Generated by Django 5.2.3 on 2025-06-18 11:12

import pgvector.django.vector
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0012_clipembedding'),
    ]

    operations = [
        migrations.AlterField(
            model_name='clipembedding',
            name='embedding',
            field=pgvector.django.vector.VectorField(dimensions=1536),
        ),
    ]
