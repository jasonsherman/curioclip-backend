# Generated by Django 5.2.3 on 2025-06-17 18:58

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_alter_clip_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClipTag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('clip', models.ForeignKey(db_column='clip_id', on_delete=django.db.models.deletion.CASCADE, to='api.clip')),
                ('tag', models.ForeignKey(db_column='tag_id', on_delete=django.db.models.deletion.CASCADE, to='api.tag')),
            ],
            options={
                'db_table': 'clip_tags',
                'managed': True,
                'unique_together': {('clip', 'tag')},
            },
        ),
    ]
