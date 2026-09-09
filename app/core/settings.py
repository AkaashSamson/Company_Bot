import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DOCUMENTS_DIR = os.getenv("DOCUMENTS_DIR", str(BASE_DIR / "input"))
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "hr_policy_docs")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
RAG_DISTANCE_THRESHOLD = float(os.getenv("RAG_DISTANCE_THRESHOLD", "0.65"))
RAG_DISTANCE_RELAXATION = float(os.getenv("RAG_DISTANCE_RELAXATION", "0.05"))
RAG_MIN_DISTANCE_GAP = float(os.getenv("RAG_MIN_DISTANCE_GAP", "0.10"))
RAG_CANDIDATE_COUNT = int(os.getenv("RAG_CANDIDATE_COUNT", "8"))
RAG_MAX_EVIDENCE = int(os.getenv("RAG_MAX_EVIDENCE", "4"))
RAG_MAX_CONTEXT_CHARS = int(os.getenv("RAG_MAX_CONTEXT_CHARS", "12000"))
LLM_CACHE_SIZE = int(os.getenv("LLM_CACHE_SIZE", "128"))
LLM_CACHE_SIMILARITY_THRESHOLD = float(
    os.getenv("LLM_CACHE_SIMILARITY_THRESHOLD", "0.70")
)
RESPONSE_CACHE_FILE = os.getenv(
    "RESPONSE_CACHE_FILE",
    str(BASE_DIR / "data" / "response_cache.json"),
)
MONGODB_URI = os.getenv("MONGODB_URI", "")
FAQ_DATABASE_NAME = os.getenv("FAQ_DATABASE_NAME", "knowlayer")
FAQ_COLLECTION_NAME = os.getenv("FAQ_COLLECTION_NAME", "faqs")
FAQ_CACHE_FILE = os.getenv(
    "FAQ_CACHE_FILE",
    str(BASE_DIR / "data" / "faqs_cache.json"),
)
MONGODB_SERVER_SELECTION_TIMEOUT_MS = int(
    os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "2000")
)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


LLM_MODEL = os.getenv(
    "LLM_MODEL",
    "openrouter/anthropic/claude-3.5-sonnet",
)

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "llama-3.1-8b-instant",
)