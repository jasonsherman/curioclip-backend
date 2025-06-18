# curioclip-backend/api/models.py

from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.db.models import CompositePrimaryKey
import uuid
from pgvector.django import VectorField


class Profile(models.Model):
    user_id = models.UUIDField(primary_key=True)
    display_name = models.CharField(max_length=255, blank=True)
    avatar_url = models.TextField(blank=True)
    charms_balance = models.IntegerField(default=0)
    created_at = models.DateTimeField()

    class Meta:
        db_table = 'profiles'
        managed = False

class Plan(models.Model):
    id = models.AutoField(primary_key=True)
    slug = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    price_cents = models.IntegerField()
    clip_quota = models.IntegerField(null=True, blank=True)
    charm_bonus = models.IntegerField(default=0)
    created_at = models.DateTimeField()

    class Meta:
        db_table = 'plans'
        managed = False

class UserPlan(models.Model):
    user = models.ForeignKey(Profile, db_column='user_id', on_delete=models.DO_NOTHING)
    plan = models.ForeignKey(Plan, db_column='plan_id', on_delete=models.DO_NOTHING)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default='active')

    class Meta:
        db_table = 'user_plans'
        managed = False
        unique_together = (('user', 'plan', 'starts_at'),)

class Curio(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(Profile, db_column='user_id', on_delete=models.DO_NOTHING)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_public = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'curios'
        managed = False

class Clip(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(Profile, db_column='user_id', on_delete=models.DO_NOTHING)
    curio = models.ForeignKey(Curio, db_column='curio_id', null=True, blank=True, on_delete=models.SET_NULL)
    platform = models.CharField(max_length=20, choices=[
        ('tiktok', 'TikTok'),
        ('instagram', 'Instagram'),
        ('youtube', 'YouTube'),
        ('other', 'Other')
    ], default='other')
    platform_video_id = models.TextField(blank=True, null=True)
    title = models.TextField(blank=True)
    url = models.TextField()
    description = models.TextField(blank=True)
    thumbnail_url = models.TextField(blank=True)
    transcript = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    is_favorite = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'clips'
        managed = False

class Tag(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        db_table = 'tags'
        managed = False

class ClipTag(models.Model):
    clip = models.ForeignKey(Clip, db_column='clip_id', on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, db_column='tag_id', on_delete=models.CASCADE)

    class Meta:
        db_table = 'clip_tags'
        managed = False
        unique_together = (('clip', 'tag'),)

class CurioRating(models.Model):
    curio = models.ForeignKey(Curio, db_column='curio_id', on_delete=models.CASCADE)
    user = models.ForeignKey(Profile, db_column='user_id', on_delete=models.CASCADE)
    rating = models.SmallIntegerField()
    created_at = models.DateTimeField()

    class Meta:
        db_table = 'curio_ratings'
        managed = False
        unique_together = (('curio', 'user'),)

class CurioComment(models.Model):
    id = models.AutoField(primary_key=True)
    curio = models.ForeignKey(Curio, db_column='curio_id', on_delete=models.CASCADE)
    user = models.ForeignKey(Profile, db_column='user_id', on_delete=models.CASCADE)
    comment = models.TextField()
    created_at = models.DateTimeField()

    class Meta:
        db_table = 'curio_comments'
        managed = False

class CharmLedger(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(Profile, db_column='user_id', on_delete=models.CASCADE)
    delta = models.IntegerField()
    reason = models.CharField(max_length=20)
    ref_table = models.TextField(blank=True, null=True)
    ref_id = models.UUIDField(blank=True, null=True)
    created_at = models.DateTimeField()

    class Meta:
        db_table = 'charm_ledger'
        managed = False

class Invitation(models.Model):
    id = models.UUIDField(primary_key=True)
    inviter = models.ForeignKey(Profile, db_column='inviter_id', on_delete=models.CASCADE, related_name='sent_invites')
    invitee_email = models.TextField()
    invitee_user = models.ForeignKey(Profile, db_column='invitee_user_id', on_delete=models.CASCADE, related_name='received_invites', null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField()

    class Meta:
        db_table = 'invitations'
        managed = False

class ClipProcessingTask(models.Model):
    id = models.AutoField(primary_key=True)
    clip = models.ForeignKey(Clip, db_column='clip_id', on_delete=models.CASCADE)
    celery_task_id = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default='pending') # 'pending', 'processing', 'completed', 'failed'
    error = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'clip_processing_task'
        managed = False 

class ClipEmbedding(models.Model):
    id = models.AutoField(primary_key=True)
    clip = models.ForeignKey(Clip, db_column='clip_id', on_delete=models.CASCADE)
    field = models.CharField(max_length=20)  # 'transcript', 'title', 'summary'
    chunk_index = models.IntegerField(null=True)  # 0 for title/summary, or chunk number
    text_chunk = models.TextField()
    embedding = VectorField(dimensions=1536)  # OpenAI output
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'clip_embeddings'
        managed = False
        indexes = [
            models.Index(fields=['clip_id']),
            models.Index(fields=['field']),
        ]