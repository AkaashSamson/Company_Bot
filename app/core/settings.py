import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DOCUMENTS_DIR = os.getenv("DOCUMENTS_DIR", str(BASE_DIR / "input"))
UPLOADS_DIR = os.getenv("UPLOADS_DIR", str(Path(DOCUMENTS_DIR) / "uploads"))
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "hr_policy_docs")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
RAG_DISTANCE_THRESHOLD = float(os.getenv("RAG_DISTANCE_THRESHOLD", "0.50"))
RAG_DISTANCE_RELAXATION = float(os.getenv("RAG_DISTANCE_RELAXATION", "0.05"))
RAG_MIN_DISTANCE_GAP = float(os.getenv("RAG_MIN_DISTANCE_GAP", "0.10"))
RAG_CANDIDATE_COUNT = int(os.getenv("RAG_CANDIDATE_COUNT", "5"))
RAG_MAX_EVIDENCE = int(os.getenv("RAG_MAX_EVIDENCE", "3"))
RAG_MAX_CONTEXT_CHARS = int(os.getenv("RAG_MAX_CONTEXT_CHARS", "12000"))
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