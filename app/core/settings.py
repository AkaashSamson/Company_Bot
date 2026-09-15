import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DOCUMENTS_DIR = os.getenv("DOCUMENTS_DIR", str(BASE_DIR / "input"))
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "hr_policy_docs")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
RAG_DISTANCE_THRESHOLD = float(os.getenv("RAG_DISTANCE_THRESHOLD", "0.60"))
RAG_DISTANCE_RELAXATION = float(os.getenv("RAG_DISTANCE_RELAXATION", "0.05"))
RAG_MIN_DISTANCE_GAP = float(os.getenv("RAG_MIN_DISTANCE_GAP", "0.10"))
RAG_CANDIDATE_COUNT = int(os.getenv("RAG_CANDIDATE_COUNT", "5"))
RAG_MAX_EVIDENCE = int(os.getenv("RAG_MAX_EVIDENCE", "3"))
RAG_MAX_CONTEXT_CHARS = int(os.getenv("RAG_MAX_CONTEXT_CHARS", "12000"))
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./instance/knowlayer.db")
STREAMLIT_API_BASE_URL = os.getenv("STREAMLIT_API_BASE_URL", "http://127.0.0.1:8000")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_INITIAL_PASSWORD = os.getenv("ADMIN_INITIAL_PASSWORD", "")
DEFAULT_USER_PASSWORD = os.getenv("DEFAULT_USER_PASSWORD", "ChangeMe123!")
AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "change-this-development-secret")
AUTH_TOKEN_EXPIRE_MINUTES = int(os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", "480"))


LLM_MODEL = os.getenv(
    "LLM_MODEL",
    "openrouter/anthropic/claude-3.5-sonnet",
)

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "llama-3.1-8b-instant",
)

EMPLOYEE_ID_PREFIX = os.getenv("EMPLOYEE_ID_PREFIX", "MSS")
DEPARTMENT_ID_PREFIX = os.getenv("DEPARTMENT_ID_PREFIX", "DEPT")
PROJECT_ID_PREFIX = os.getenv("PROJECT_ID_PREFIX", "PROJ")
DOCUMENT_ID_PREFIX = os.getenv("DOCUMENT_ID_PREFIX", "DOC")