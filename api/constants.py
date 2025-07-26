from django.conf import settings

EMBEDDING_MODEL="text-embedding-3-small"
TRANSCRIPTION_MODEL="whisper-1"
AI_MODELS=[
        "mistralai/mistral-small-3.2-24b-instruct:free",
        "qwen/qwen3-235b-a22b:free",
        "sarvamai/sarvam-m:free",
        "google/gemma-3-12b-it:free",
        "deepseek/deepseek-r1-0528:free"
    ]

OPENAI_API_KEY = settings.OPENAI_API_KEY
OPENROUTER_API_KEY = settings.OPENROUTER_API_KEY

SUPABASE_JWT_SECRET = settings.SUPABASE_JWT_SECRET
SUPABASE_URL = settings.SUPABASE_URL
SUPABASE_KEY = settings.SUPABASE_KEY
SUPABASE_ANON_KEY = settings.SUPABASE_ANON_KEY
SUPBASE_ISSUER    = f"{SUPABASE_URL}/auth/v1"
COOKIE_LOCAL_PATH = settings.COOKIE_LOCAL_PATH
COOKIE_STORAGE_PATH = settings.COOKIE_STORAGE_PATH