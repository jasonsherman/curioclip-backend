# Generated by Django 5.2.3 on 2025-06-17 14:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0007_alter_clip_embeddings'),
    ]

    operations = [
        migrations.AlterField(
            model_name='clip',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True),
        ),
    ]
