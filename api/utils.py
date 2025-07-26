import re
import jwt
import os
import tempfile
import openai
import requests
from supabase import create_client
from PIL import Image
from django.db import connection
from yt_dlp import YoutubeDL
import json_repair
from datetime import datetime, timedelta
from .models import Clip, Tag, ClipTag, Curio, ClipEmbedding, Profile
from .constants import (
    EMBEDDING_MODEL, TRANSCRIPTION_MODEL, AI_MODELS,
    SUPABASE_JWT_SECRET, COOKIE_STORAGE_PATH, COOKIE_LOCAL_PATH,
    SUPABASE_URL, SUPABASE_KEY
)
import logging

logger = logging.getLogger(__name__)

def generate_test_jwt_token(user_id, email=None):
    """
    Generate a test JWT token for local development.
    This mimics the structure of Supabase JWT tokens.
    """
    payload = {
        'sub': str(user_id),  # Supabase uses 'sub' for user ID
        'email': email,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=1),  # Token expires in 1 hour
    }
    token = jwt.encode(
        payload,
        SUPABASE_JWT_SECRET,
        algorithm='HS256'
    )
    return token


def detect_platform(url):
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    elif "tiktok.com" in url:
        return "tiktok"
    elif "instagram.com" in url:
        return "instagram"
    else:
        return "unknown"


def get_platform_video_id(info, url, platform):
    if platform == "youtube":
        return info.get("id")
    elif platform == "instagram":
        return info.get("id") or (
            url.rstrip("/").split("/")[-1].split("?")[0]
        )
    elif platform == "tiktok":
        return info.get("id") or (
            url.rstrip("/").split("/")[-1].split("?")[0]
        )
    else:
        return info.get("id")

def fetch_audio_and_metadata(url):
    platform = detect_platform(url)
    cookiefile = ensure_cookie_file()
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': tempfile.mktemp(suffix='.%(ext)s'),
        'quiet': True,
        'nocheckcertificate': True,
        'noplaylist': True,
        'ignoreerrors': False,
        'restrictfilenames': True,
        'cookiefile': cookiefile,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info is None:
            raise ValueError("Could not extract info from URL.")

        # The downloaded file is stored in 'filepath'
        if 'requested_downloads' in info and len(info['requested_downloads']) > 0:
            filepath = info['requested_downloads'][0]['filepath']
        else:
            # Fallback (works for most YouTube videos)
            filepath = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')
        
        # Download thumbnail image locally for further upload
        thumbnail_url = info.get('thumbnail')
        thumbnail_path = None
        if thumbnail_url:
            _, ext = os.path.splitext(thumbnail_url.split("?")[0])
            ext = ext if ext in [".jpg", ".jpeg", ".png"] else ".jpg"
            thumbnail_path = tempfile.mktemp(suffix=ext)
            try:
                download_image(thumbnail_url, thumbnail_path)
            except Exception as e:
                thumbnail_path = None

        # ----> Extract native video ID for supported platforms
        platform_video_id = get_platform_video_id(info, url, platform)

        metadata = {
            'title': info.get('title'),
            'duration': info.get('duration'),
            'uploader': info.get('uploader'),
            'thumbnail': thumbnail_url,
            'thumbnail_path': thumbnail_path,
            'platform': platform,
            'filepath': filepath,
            'platform_video_id': platform_video_id,
        }
        return metadata
    
def transcribe_audio_with_openai(audio_path, openai_api_key):
    openai.api_key = openai_api_key
    with open(audio_path, "rb") as audio_file:
        transcript = openai.audio.transcriptions.create(
            model=TRANSCRIPTION_MODEL,
            file=audio_file,
            response_format="text" 
        )
    return transcript


def summarize_transcript(transcript, openai_api_key):
    openai.api_key = openai_api_key
    prompt = (
        "You are a smart assistant helping someone organize a video they just saved. "
        "Here's the transcript of the video:\n"
        f"{transcript}\n\n"
        "Please return:\n"
        "- A 1-line summary of the video\n"
        "- The main hack, product, or tip\n"
        "- A list of 3–5 tags or categories\n"
        "- A short description (2–3 sentences)\n"
    )
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300
    )
    summary = response.choices[0].message.content.strip()
    return summary


def parse_openai_response(response_content):
    """
    Extract and parse the JSON object that follows the last `prefix` in the model output.
    Handles common noise like markdown fences or trailing commentary.
    """
    try:
        candidate = re.sub(r"```(?:json)?|```", "", response_content).strip()

        start = candidate.find("{")
        end   = candidate.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("No JSON braces found after prefix")

        json_str = candidate[start:end + 1]

        def _escaper(match):
            return match.group(0).replace("\n", "\\n")
        json_str = re.sub(r'"(?:[^"\\]|\\.)*"', _escaper, json_str, flags=re.DOTALL)

        return json_repair.loads(json_str)

    except Exception as e:
        raise ValueError(f"JSON parsing error: {e}\n model_response: {response_content}")
    

def summarize_and_categorize_clip(transcript, curio_names, openai_api_key):
    prompt = f"""
You are an AI assistant helping users organize and summarize social video clips.

Below is the transcript of a video:

--- BEGIN TRANSCRIPT ---
{transcript}
--- END TRANSCRIPT ---

Here is a list of allowed Curio names (categories):
{curio_names}

Please analyze the transcript and respond ONLY with valid JSON in the following format:

{{
  "one_line_summary": "<A concise one-sentence summary of the video>",
  "main_tip_or_product": "<The main hack, tip, or product featured in the video>",
  "tags": ["tag1", "tag2", "tag3"],
  "assigned_curio": "<The best matching Curio from the allowed list, or 'Other'>",
  "suggested_curio": "<Suggest a new Curio name if none from the allowed list fit, otherwise null>",
  "description": "<A short (2-3 sentences) description of the video's content>"
}}

Rules:
- Use ONLY the provided Curio names for "assigned_curio". If none fit, set "assigned_curio" to "Other" and provide a value for "suggested_curio".
- If a Curio from the list fits, set "suggested_curio" to null.
- "tags" should be 3 to 5 relevant words or short phrases.
- Only output valid JSON.
"""
    client = openai.OpenAI(
         base_url="https://openrouter.ai/api/v1",
         api_key=openai_api_key
    )
    last_exception = None
    for model in AI_MODELS:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            ai_content = response.choices[0].message.content.strip()
            logging.info(f"ai content:  {ai_content}")
            summary_data = parse_openai_response(ai_content)
            return summary_data
        except Exception as e:
            logger.info(f"{model} is busy.. {e}")
            last_exception = e
            continue
    raise last_exception if last_exception else RuntimeError("All model calls failed.")


def handle_thumbnail_upload(source_url, clip_id, supabase_url, supabase_key, max_size=(320,320), quality=60, bucket="thumbnails"):
    """
    Downloads an image from source_url, compresses it, uploads to Supabase, and returns the new public URL.
    Cleans up all temp files.
    Returns public_url or None.
    """
    ext = ".jpg"
    tmp_original = tempfile.mktemp(suffix=ext)
    tmp_compressed = tempfile.mktemp(suffix=f"_compressed{ext}")
    try:
        download_image(source_url, tmp_original)
        compress_image(tmp_original, tmp_compressed, max_size=max_size, quality=quality)
        storage_path = f"{clip_id}.jpg"
        public_url = upload_image_to_supabase(
            tmp_compressed, storage_path, supabase_url, supabase_key, bucket=bucket
        )
        return public_url
    except Exception as e:
        logger.info(f"Error during uploading to supabase: {e}")
        return None
    finally:
        for p in [tmp_original, tmp_compressed]:
            if os.path.exists(p):
                os.remove(p)

def reuse_clip_if_exists(clip, OPENAI_API_KEY, SUPABASE_URL, SUPABASE_KEY):
    """
    Checks if the given clip's URL was already processed for any other user.
    If so, clones the results (title, transcript, summary, tags) into this clip.
    Only copies the curio if one wasn't specified in the original request.
    Returns True if reused, False if not.
    """
    existing_clip = (
        Clip.objects
        .filter(
            url=clip.url
        )
        # must have summary *and* transcript
        .exclude(summary__in=[None, ""])
        .exclude(transcript__in=[None, ""])
        .order_by('-created_at')
        .first()
    )
    logger.info(f"Existing clip: {existing_clip}")
    if not existing_clip:
        return False
    
    # 1.  Ensure the source clip itself already has embeddings
    if not ClipEmbedding.objects.filter(clip=existing_clip).exists():
        process_clip_embeddings(existing_clip, OPENAI_API_KEY)

    # 2.  Copy meta, tags and **embeddings** to the new user's clip
    clip.title        = existing_clip.title
    clip.platform     = existing_clip.platform
    clip.transcript   = existing_clip.transcript
    clip.summary      = existing_clip.summary
    clip.platform_video_id = existing_clip.platform_video_id
    clip.description  = getattr(existing_clip, "description", "")
    clip.save()

    # --- Thumbnail Handling ---
    public_url = None
    if existing_clip.thumbnail_url:
        public_url = handle_thumbnail_upload(
            existing_clip.thumbnail_url, clip.id, SUPABASE_URL, SUPABASE_KEY
        )
    
    if not public_url:
        data = fetch_audio_and_metadata(clip.url)
        if data.get('thumbnail'):
            public_url = handle_thumbnail_upload(
                data['thumbnail'], clip.id, SUPABASE_URL, SUPABASE_KEY
            )
    clip.thumbnail_url = public_url
    clip.save()

    # -- tags
    tags = Tag.objects.filter(cliptag__clip=existing_clip)
    ClipTag.objects.bulk_create(
        [ClipTag(clip=clip, tag=t) for t in tags],
        ignore_conflicts=True
    )

    # -- embeddings
    src_vecs = ClipEmbedding.objects.filter(clip=existing_clip)
    ClipEmbedding.objects.bulk_create([
        ClipEmbedding(
            clip        = clip,
            field       = v.field,
            chunk_index = v.chunk_index,
            text_chunk  = v.text_chunk,
            embedding   = v.embedding
        ) for v in src_vecs
    ])

    # -- Curio (category) assignment if one wasn't specified in the original request
    logger.info(f"Existing clip Curio: {existing_clip.curio.name}")
    if existing_clip.curio and not clip.curio:
        user_curio = Curio.objects.filter(
            name=existing_clip.curio.name,
            user_id=clip.user_id
        ).first()
        if not user_curio:
            logger.info("Creating new curio")
            user_curio, _ = Curio.objects.get_or_create(
                name=existing_clip.curio.name,
                user_id=clip.user_id,
                defaults={
                    "description": existing_clip.curio.description or "Created automatically for reused clip.",
                    "is_public": False,
                }
            )
        clip.curio = user_curio
        clip.save()
    return True


def chunk_text(text, chunk_size=300, overlap_ratio=0.2):
    words = text.split()
    n = len(words)
    step = int(chunk_size * (1 - overlap_ratio))
    if step <= 0:
        raise ValueError("chunk_size and overlap_ratio combination not valid.")

    chunks = []
    i = 0
    while i < n:
        chunk = words[i:i + chunk_size]
        if not chunk:
            break
        chunks.append(" ".join(chunk))
        i += step
    return chunks


def embed_texts(text_list, openai_api_key):
    openai.api_key = openai_api_key
    logger.info(f"Creating embedding for: {text_list}")
    response = openai.embeddings.create(
        input=text_list,
        model=EMBEDDING_MODEL
    )
    return [item.embedding for item in response.data]


def process_clip_embeddings(clip, openai_api_key):
    transcript = clip.transcript or ""
    transcript_chunks = chunk_text(transcript, chunk_size=300, overlap_ratio=0.2)
    fields = [
        ("title", [clip.title] if clip.title else []),
        ("summary", [clip.summary] if clip.summary else []),
        ("description", [clip.description] if getattr(clip, "description", None) else []),
        ("transcript", transcript_chunks)
    ]

    all_texts = []
    all_fields = []
    all_indices = []
    for field_name, chunks in fields:
        for idx, chunk in enumerate(chunks):
            all_texts.append(chunk)
            all_fields.append(field_name)
            all_indices.append(idx)
    
    # Generate embeddings
    vectors = embed_texts(all_texts, openai_api_key)
    # Save each embedding to DB
    for chunk, field, idx, vector in zip(all_texts, all_fields, all_indices, vectors):
        ClipEmbedding.objects.create(
            clip=clip,
            field=field,
            chunk_index=idx,
            text_chunk=chunk,
            embedding=vector
        )


def vector_search_clip_ids_with_similarity(query_embedding, top_n=30, threshold=0.7):
    """
    Returns a list of (clip_id, percent_match, embedding_id) tuples for best matches above threshold.
    """
    
    if isinstance(query_embedding, (list, tuple)):
        query_embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    else:
        query_embedding_str = str(query_embedding)
    sql = """
        SELECT id, clip_id, field, chunk_index, text_chunk,
               (1 - (embedding <=> %s::vector)) as percent_match
        FROM clip_embeddings
        ORDER BY percent_match DESC
        LIMIT %s;
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [query_embedding_str, top_n])
        results = cursor.fetchall()
    # Results: (embedding_id, clip_id, field, chunk_index, text_chunk, percent_match)
    filtered = [r for r in results if r[5] >= threshold]
    # Return as list of dicts
    return [
        {
            "clip_id": r[1],
            "embedding_id": r[0],
            "percent_match": round(r[5] * 100, 2),  # percent as float
            "field": r[2],
            "chunk_index": r[3],
            "text_chunk": r[4],
        }
        for r in filtered
    ]


def download_image(url, out_path):
    r = requests.get(url, stream=True, timeout=10)
    if r.status_code == 200:
        with open(out_path, 'wb') as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)
        return out_path
    raise Exception(f"Failed to download image: {url}")


def upload_image_to_supabase(local_path, storage_path, supabase_url, supabase_key, bucket="thumbnails"):
    supabase = create_client(supabase_url, supabase_key)
    with open(local_path, "rb") as f:
        resp = supabase.storage.from_(bucket).upload(storage_path, f)
        public_url = f"{supabase_url.replace('/rest/v1', '')}/storage/v1/object/public/{bucket}/{storage_path}"
        return public_url
    

def download_file_from_supabase(storage_path, destination_path, supabase_url, supabase_key, bucket="secrets"):
    """
    Downloads a file from a private Supabase bucket to a local destination.
    Args:
        storage_path (str): Path to the file in the bucket (e.g., 'folder/file.jpg').
        destination_path (str): Local path to save the downloaded file.
        supabase_url (str): Supabase project URL.
        supabase_key (str): Supabase service role or user JWT (must have access).
        bucket (str): Name of the bucket (default: 'secrets').
    Raises:
        Exception: If download fails or file not found.
    Returns:
        str: Path to the downloaded file.
    """
    supabase = create_client(supabase_url, supabase_key)
    try:
        data = supabase.storage.from_(bucket).download(storage_path)
        with open(destination_path, 'wb') as f:
            f.write(data)
        return destination_path
    except Exception as e:
        logger.error(f"Failed to download file from Supabase: {e}")
        raise Exception(f"Failed to download file from Supabase: {e}")

def ensure_cookie_file():
    if not os.path.exists(COOKIE_LOCAL_PATH):
        download_file_from_supabase(
            storage_path=COOKIE_STORAGE_PATH,
            destination_path=COOKIE_LOCAL_PATH,
            supabase_url=SUPABASE_URL,
            supabase_key=SUPABASE_KEY,
            bucket="secrets",
        )
    return COOKIE_LOCAL_PATH

def compress_image(input_path, output_path, max_size=(320, 320), quality=60):
    """
    Compresses and resizes an image to save storage/bandwidth.
    max_size: (width, height) in pixels.
    quality: JPEG quality 1-100 (lower = more compression).
    """
    try:
        img = Image.open(input_path)
        img.thumbnail(max_size, Image.LANCZOS)
        # Always convert to RGB for JPEG
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(output_path, format="JPEG", quality=quality, optimize=True)
        return output_path
    except Exception as e:
        raise Exception(f"Compression failed: {str(e)}")
    
def get_profile_from_request(request):
    supabase_user = request.user
    # Defensive: handle cases where id is missing or invalid
    if not hasattr(supabase_user, "id"):
        raise Exception("Authenticated user missing id")
    return Profile.objects.get(user_id=supabase_user.id)