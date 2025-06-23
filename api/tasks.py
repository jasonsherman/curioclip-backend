from celery import shared_task
from .models import Clip, Curio, ClipProcessingTask
from .utils import (
    fetch_audio_and_metadata,
    transcribe_audio_with_openai,
    summarize_and_categorize_clip,
    reuse_clip_if_exists,
    process_clip_embeddings,
    upload_image_to_supabase,
    compress_image,
    handle_thumbnail_upload
)
from .constants import (
    OPENAI_API_KEY,
    OPENROUTER_API_KEY,
    SUPABASE_URL,
    SUPABASE_KEY
)
import os
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def process_clip_task(self, clip_id):
    task_entry = ClipProcessingTask.objects.get(celery_task_id=self.request.id)
    audio_path = None  # Initialize audio_path as None
    try:
        task_entry.status = 'processing'
        task_entry.save()
        clip = Clip.objects.get(id=clip_id)

        reused = reuse_clip_if_exists(clip, OPENAI_API_KEY, SUPABASE_URL, SUPABASE_KEY)
        if reused:
            logger.info("Clip already exists, skipping processing!")
            task_entry.status = 'completed'
            task_entry.save()
            return

        # 1. Fetch audio + metadata
        data = fetch_audio_and_metadata(clip.url)
        logger.info(f"Fetched data for clip {clip_id}: {data}")
        audio_path = data['filepath']
        thumbnail_path = data.get('thumbnail_path')
        public_url = None

        if thumbnail_path and os.path.exists(thumbnail_path):
            compressed_path = thumbnail_path.replace(".jpg", "_compressed.jpg")
            try:
                compress_image(thumbnail_path, compressed_path, max_size=(320, 320), quality=60)
                storage_path = f"{clip.id}.jpg"
                public_url = upload_image_to_supabase(
                    compressed_path, storage_path, SUPABASE_URL, SUPABASE_KEY, bucket="thumbnails"
                )
                clip.thumbnail_url = public_url
                clip.save()
            finally:
                if os.path.exists(thumbnail_path):
                    os.remove(thumbnail_path)
                if os.path.exists(compressed_path):
                    os.remove(compressed_path)
        else:
            if data.get('thumbnail'):
                public_url = handle_thumbnail_upload(
                    data['thumbnail'],
                    clip.id,
                    SUPABASE_URL,
                    SUPABASE_KEY,
                    max_size=(320, 320),
                    quality=60,
                    bucket="thumbnails"
                )
            clip.thumbnail_url = public_url
            clip.save()

        clip.title = data['title']
        clip.platform = data['platform']
        clip.platform_video_id = data.get('platform_video_id')
        clip.save()


        # 2. Transcribe audio
        transcript = transcribe_audio_with_openai(audio_path, OPENAI_API_KEY)
        logger.info(f"Transcript for {clip_id}: {transcript}")
        clip.transcript = transcript
        clip.save()


        # 3. Fetch only the user's Curios for categorization
        curio_names = list(
            Curio.objects.filter(user_id=clip.user_id).values_list('name', flat=True)
        )
        logger.info(f"Existing curios: {curio_names}")

        # 4. Summarize & categorize
        summary_data = summarize_and_categorize_clip(transcript, curio_names, OPENROUTER_API_KEY)
        logger.info(f"AI response: {summary_data}")
        clip.summary = summary_data.get("one_line_summary", "")
        clip.save()

        # Tags: Save as Tag and ClipTag relationships
        from .models import Tag, ClipTag
        tags = summary_data.get("tags", [])
        for tag_name in tags:
            tag, _ = Tag.objects.get_or_create(name=tag_name)
            ClipTag.objects.get_or_create(clip=clip, tag=tag)

        # Assign or suggest Curio (category)
        assigned_curio_name = summary_data.get("assigned_curio")
        suggested_curio_name = summary_data.get("suggested_curio")

        if suggested_curio_name:
            new_curio, created = Curio.objects.get_or_create(
                 name=suggested_curio_name,
                 user_id=clip.user_id,
                 defaults={
                    "description": f"Created by AI suggestion based on video content.",
                    "is_public": False,
                 }
            )
            clip.curio = new_curio
            clip.save()
        elif assigned_curio_name and assigned_curio_name != "Other":
            try:
                assigned_curio = Curio.objects.get(name=assigned_curio_name)
                clip.curio = assigned_curio
                clip.save()
            except Curio.DoesNotExist as e:
                logger.info(f"Error during fetching curio: {e}")
                pass
        
        # 5. Save full description as well
        clip.description = summary_data.get("description", "")
        clip.save()

        process_clip_embeddings(clip, OPENAI_API_KEY)

        task_entry.status = 'completed'
        task_entry.save()
    except Exception as e:
        logger.error(f"Error processing clip {clip_id}: {str(e)}")
        task_entry.status = 'failed'
        task_entry.error = str(e)
        task_entry.save()
    finally:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
        