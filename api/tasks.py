from celery import shared_task
from .models import Clip, Curio, ClipProcessingTask
from .utils import (
    fetch_audio_and_metadata,
    transcribe_audio_with_openai,
    summarize_and_categorize_clip,
    reuse_clip_if_exists,
    process_clip_embeddings
)
from .constants import OPENAI_API_KEY, OPENROUTER_API_KEY
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

        reused = reuse_clip_if_exists(clip, OPENAI_API_KEY)
        if reused:
            logger.info("Clip already exists, skipping processing!")
            task_entry.status = 'completed'
            task_entry.save()
            return

        # 1. Fetch audio + metadata
        data = fetch_audio_and_metadata(clip.url)
        logger.info(f"Fetched data for clip {clip_id}: {data}")
        audio_path = data['filepath']

        clip.title = data['title']
        clip.thumbnail_url = data['thumbnail']
        clip.platform = data['platform']
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