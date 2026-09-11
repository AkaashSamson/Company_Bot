import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DOCUMENTS_DIR = os.getenv("DOCUMENTS_DIR", str(BASE_DIR / "input"))
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "hr_policy_docs")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
RAG_DISTANCE_THRESHOLD = float(os.getenv("RAG_DISTANCE_THRESHOLD", "0.50"))
RAG_DISTANCE_RELAXATION = float(os.getenv("RAG_DISTANCE_RELAXATION", "0.15"))
RAG_MIN_DISTANCE_GAP = float(os.getenv("RAG_MIN_DISTANCE_GAP", "0.10"))
RAG_CANDIDATE_COUNT = int(os.getenv("RAG_CANDIDATE_COUNT", "5"))
RAG_MAX_EVIDENCE = int(os.getenv("RAG_MAX_EVIDENCE", "3"))
RAG_MAX_CONTEXT_CHARS = int(os.getenv("RAG_MAX_CONTEXT_CHARS", "12000"))
LLM_CACHE_SIZE = int(os.getenv("LLM_CACHE_SIZE", "128"))
FAQ_SIMILARITY_CACHE_ENABLED = os.getenv("FAQ_SIMILARITY_CACHE_ENABLED", "true").lower() == "true"
FAQ_SIMILARITY_THRESHOLD = float(os.getenv("FAQ_SIMILARITY_THRESHOLD", "0.92"))
FAQ_JSON_PATH = os.getenv("FAQ_JSON_PATH", str(BASE_DIR / "data" / "faqs.json"))
MONGODB_URI = os.getenv("MONGODB_URI", "")
FAQ_DATABASE_NAME = os.getenv("FAQ_DATABASE_NAME", "knowlayer")
FAQ_COLLECTION_NAME = os.getenv("FAQ_COLLECTION_NAME", "faqs")
MONGODB_SERVER_SELECTION_TIMEOUT_MS = int(
    os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "2000")
)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# LangSmith observability — set LANGCHAIN_TRACING_V2=true to enable
LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY", "")
LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT", "company-bot")
LANGCHAIN_ENDPOINT = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")


LLM_MODEL = os.getenv(
    "LLM_MODEL",
    "openrouter/anthropic/claude-3.5-sonnet",
)

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "llama-3.1-8b-instant",
)