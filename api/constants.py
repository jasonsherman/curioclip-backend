from django.conf import settings

EMBEDDING_MODEL="text-embedding-3-small"
TRANSCRIPTION_MODEL="whisper-1"
# AI_MODEL="qwen/qwen3-235b-a22b:free"
AI_MODELS=["qwen/qwen3-235b-a22b:free", "sarvamai/sarvam-m:free"]
SUPABASE_JWT_SECRET = settings.SUPABASE_JWT_SECRET
OPENAI_API_KEY = settings.OPENAI_API_KEY
OPENROUTER_API_KEY = settings.OPENROUTER_API_KEY
