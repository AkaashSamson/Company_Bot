import logging
import os
import warnings
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DOCUMENTS_DIR = os.getenv("DOCUMENTS_DIR", str(BASE_DIR / "input"))
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "hr_policy_docs")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
DOCLING_ENABLED = os.getenv("DOCLING_ENABLED", "false").lower() == "true"
DOCLING_VISUAL_ENRICHMENT_ENABLED = os.getenv(
    "DOCLING_VISUAL_ENRICHMENT_ENABLED", "false"
).lower() == "true"
DOCLING_VLM_MODEL = os.getenv(
    "DOCLING_VLM_MODEL", "HuggingFaceTB/SmolVLM-256M-Instruct"
)
DOCLING_VLM_MAX_NEW_TOKENS = int(os.getenv("DOCLING_VLM_MAX_NEW_TOKENS", "180"))
DOCLING_OCR_MIN_CONFIDENCE = float(os.getenv("DOCLING_OCR_MIN_CONFIDENCE", "0.35"))
DOCLING_SKIP_DECORATIVE_OCR = os.getenv(
    "DOCLING_SKIP_DECORATIVE_OCR", "true"
).lower() == "true"
DOCLING_CITATION_PDF_ENABLED = os.getenv(
    "DOCLING_CITATION_PDF_ENABLED", "false"
).lower() == "true"
DOCLING_CITATION_PDF_DIR = os.getenv(
    "DOCLING_CITATION_PDF_DIR", str(BASE_DIR / "data" / "citation_pdfs")
)
DOCLING_LIBREOFFICE_PATH = os.getenv("DOCLING_LIBREOFFICE_PATH", "")
# Chunk budget in tokens. Kept at the embedding model's sequence limit
# (sentence-transformers/all-MiniLM-L6-v2 truncates beyond 256) so chunks are
# never silently truncated at embedding time.
DOCLING_MAX_TOKENS = int(os.getenv("DOCLING_MAX_TOKENS", "256"))
RAG_DISTANCE_THRESHOLD = float(os.getenv("RAG_DISTANCE_THRESHOLD", "0.60"))
RAG_DISTANCE_RELAXATION = float(os.getenv("RAG_DISTANCE_RELAXATION", "0.05"))
RAG_MIN_DISTANCE_GAP = float(os.getenv("RAG_MIN_DISTANCE_GAP", "0.10"))
RAG_CANDIDATE_COUNT = int(os.getenv("RAG_CANDIDATE_COUNT", "13"))
RAG_MAX_EVIDENCE = int(os.getenv("RAG_MAX_EVIDENCE", "4"))
RAG_FINAL_K = int(os.getenv("RAG_FINAL_K", "4"))
RERANKER_PROVIDER = os.getenv("RERANKER_PROVIDER", "bge").lower()
RAG_RERANKER_MODEL = os.getenv("RAG_RERANKER_MODEL", "BAAI/bge-reranker-base")
RAG_MAX_CONTEXT_CHARS = int(os.getenv("RAG_MAX_CONTEXT_CHARS", "12000"))
# Master Cache Switch: when false, all cache layers are completely disabled
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "false").lower() == "true"
LLM_CACHE_ENABLED = CACHE_ENABLED and (os.getenv("LLM_CACHE_ENABLED", "true" if CACHE_ENABLED else "false").lower() == "true")
LLM_CACHE_SIZE = int(os.getenv("LLM_CACHE_SIZE", "128")) if LLM_CACHE_ENABLED else 0
FAQ_SIMILARITY_CACHE_ENABLED = CACHE_ENABLED and (os.getenv("FAQ_SIMILARITY_CACHE_ENABLED", "true" if CACHE_ENABLED else "false").lower() == "true")
FAQ_SIMILARITY_THRESHOLD = float(os.getenv("FAQ_SIMILARITY_THRESHOLD", "0.92"))
FAQ_JSON_PATH = os.getenv("FAQ_JSON_PATH", str(BASE_DIR / "data" / "faqs.json"))
LLM_CACHE_SIMILARITY_THRESHOLD = float(
    os.getenv("LLM_CACHE_SIMILARITY_THRESHOLD", "0.85")
)
SEMANTIC_CACHE_SIMILARITY_THRESHOLD = float(
    os.getenv("SEMANTIC_CACHE_SIMILARITY_THRESHOLD", "0.89")
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
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./instance/knowlayer.db")
STREAMLIT_API_BASE_URL = os.getenv("STREAMLIT_API_BASE_URL", "http://127.0.0.1:8000")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_INITIAL_PASSWORD = os.getenv("ADMIN_INITIAL_PASSWORD", "")
DEFAULT_USER_PASSWORD = os.getenv("DEFAULT_USER_PASSWORD", "ChangeMe123!")
AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "change-this-development-secret")
AUTH_TOKEN_EXPIRE_MINUTES = int(os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", "480"))
AUTH_REFRESH_TOKEN_EXPIRE_MINUTES = int(os.getenv("AUTH_REFRESH_TOKEN_EXPIRE_MINUTES", "10080"))

# Session memory configuration (Task AK-1.2)
SESSION_INACTIVITY_TIMEOUT_HOURS = float(os.getenv("SESSION_INACTIVITY_TIMEOUT_HOURS", "12.0"))
SESSION_MAX_HISTORY_TURNS = int(os.getenv("SESSION_MAX_HISTORY_TURNS", "6"))

# Vendor-neutral observability configuration (Task AK-3.2)
OBSERVABILITY_PROVIDER = os.getenv("OBSERVABILITY_PROVIDER", "null").lower()

# Langfuse settings
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", os.getenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com"))

# Arize Phoenix settings
PHOENIX_COLLECTOR_ENDPOINT = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces")
PHOENIX_PROJECT_NAME = os.getenv("PHOENIX_PROJECT_NAME", "company-bot")

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

EMPLOYEE_ID_PREFIX = os.getenv("EMPLOYEE_ID_PREFIX", "MSS")
DEPARTMENT_ID_PREFIX = os.getenv("DEPARTMENT_ID_PREFIX", "DEPT")
PROJECT_ID_PREFIX = os.getenv("PROJECT_ID_PREFIX", "PROJ")
DOCUMENT_ID_PREFIX = os.getenv("DOCUMENT_ID_PREFIX", "DOC")

# Conversation Logging & Retention Settings
DEFAULT_CONVERSATION_LOG_DIR = "conversation_logs"
DEFAULT_CONVERSATION_LOG_RETENTION_DAYS = 30

raw_log_dir = os.getenv("CONVERSATION_LOG_DIR", DEFAULT_CONVERSATION_LOG_DIR)
_log_dir_path = Path(raw_log_dir)
CONVERSATION_LOG_DIR = _log_dir_path if _log_dir_path.is_absolute() else BASE_DIR / _log_dir_path


def parse_retention_days(raw_value: Optional[str]) -> int:
    """
    Parse retention days with safe fallback to 30 days and developer-visible warnings.
    """
    if raw_value is None or raw_value.strip() == "":
        return DEFAULT_CONVERSATION_LOG_RETENTION_DAYS

    try:
        val = int(raw_value.strip())
        if val <= 0:
            msg = (
                f"Invalid CONVERSATION_LOG_RETENTION_DAYS='{raw_value}': must be a positive integer. "
                f"Falling back to default of {DEFAULT_CONVERSATION_LOG_RETENTION_DAYS} days."
            )
            logger.warning(msg)
            warnings.warn(msg, UserWarning, stacklevel=2)
            return DEFAULT_CONVERSATION_LOG_RETENTION_DAYS
        return val
    except ValueError:
        msg = (
            f"Invalid CONVERSATION_LOG_RETENTION_DAYS='{raw_value}': not a valid integer. "
            f"Falling back to default of {DEFAULT_CONVERSATION_LOG_RETENTION_DAYS} days."
        )
        logger.warning(msg)
        warnings.warn(msg, UserWarning, stacklevel=2)
        return DEFAULT_CONVERSATION_LOG_RETENTION_DAYS


CONVERSATION_LOG_RETENTION_DAYS = parse_retention_days(
    os.getenv("CONVERSATION_LOG_RETENTION_DAYS")
)

LOG_CLEANUP_INTERVAL_SECONDS = int(os.getenv("LOG_CLEANUP_INTERVAL_SECONDS", "86400"))

# ============================================
# AB-13: Query Normalization & Quality Settings
# ============================================

# Query Normalization (AB-3)
ENABLE_QUERY_NORMALIZATION = os.getenv("ENABLE_QUERY_NORMALIZATION", "true").lower() == "true"
QUERY_NORMALIZER_TYPO_CORRECTION = os.getenv("QUERY_NORMALIZER_TYPO_CORRECTION", "true").lower() == "true"
QUERY_NORMALIZER_VOCABULARY = os.getenv("QUERY_NORMALIZER_VOCABULARY", "true").lower() == "true"
QUERY_NORMALIZER_EXPANSION = os.getenv("QUERY_NORMALIZER_EXPANSION", "false").lower() == "true"

# Quality Gate (AB-5)
ENABLE_QUALITY_GATE = os.getenv("ENABLE_QUALITY_GATE", "true").lower() == "true"
QUALITY_GATE_MIN_SCORE = float(os.getenv("QUALITY_GATE_MIN_SCORE", "0.4"))
QUALITY_GATE_MIN_EVIDENCE = int(os.getenv("QUALITY_GATE_MIN_EVIDENCE", "1"))
QUALITY_GATE_DISTANCE_THRESHOLD = float(os.getenv("QUALITY_GATE_DISTANCE_THRESHOLD", "0.60"))
QUALITY_GATE_GROUNDING_THRESHOLD = float(os.getenv("QUALITY_GATE_GROUNDING_THRESHOLD", "0.2"))


# ============================================
# AB-4, AB-14: Semantic Cache Settings
# ============================================

# Quality-Aware Cache (AB-4)
SEMANTIC_CACHE_ENABLED = CACHE_ENABLED and (os.getenv("SEMANTIC_CACHE_ENABLED", "true" if CACHE_ENABLED else "false").lower() == "true")
SEMANTIC_CACHE_MAX_ENTRIES = int(os.getenv("SEMANTIC_CACHE_MAX_ENTRIES", "1000"))
# 30 days = 30 * 24 * 3600 = 2,592,000 seconds
SEMANTIC_CACHE_TTL_SECONDS = float(os.getenv("SEMANTIC_CACHE_TTL_SECONDS", str(30 * 24 * 3600)))
SEMANTIC_CACHE_MIN_CONFIDENCE = float(os.getenv("SEMANTIC_CACHE_MIN_CONFIDENCE", "0.6"))


# ============================================
# AB-1: Provider Health & Circuit Breaker
# ============================================

# Provider Health Monitoring
ENABLE_PROVIDER_HEALTH = os.getenv("ENABLE_PROVIDER_HEALTH", "true").lower() == "true"
CIRCUIT_BREAKER_FAILURE_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
CIRCUIT_BREAKER_SUCCESS_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_SUCCESS_THRESHOLD", "2"))
CIRCUIT_BREAKER_TIMEOUT_SECONDS = float(os.getenv("CIRCUIT_BREAKER_TIMEOUT_SECONDS", "30.0"))


# ============================================
# AB-6: Pipeline Tracing
# ============================================

# Pipeline Tracing
ENABLE_PIPELINE_TRACING = os.getenv("ENABLE_PIPELINE_TRACING", "true").lower() == "true"
PIPELINE_TRACER_MAX_TRACES = int(os.getenv("PIPELINE_TRACER_MAX_TRACES", "1000"))


# ============================================
# AB-14: LangCache Configuration (Dual-Cache)
# ============================================

# LangCache Primary Semantic Cache
LANGCACHE_ENABLED = os.getenv("LANGCACHE_ENABLED", "true").lower() == "true"
LANGCACHE_SERVER_URL = os.getenv("LANGCACHE_SERVER_URL", "https://aws-us-east-1.langcache.redis.io")
LANGCACHE_CACHE_ID = os.getenv("LANGCACHE_CACHE_ID", "")
LANGCACHE_API_KEY = os.getenv("LANGCACHE_API_KEY", "")
LANGCACHE_TIMEOUT_SECONDS = float(os.getenv("LANGCACHE_TIMEOUT_SECONDS", "3.0"))
LANGCACHE_SIMILARITY_THRESHOLD = float(
    os.getenv("LANGCACHE_SIMILARITY_THRESHOLD", str(SEMANTIC_CACHE_SIMILARITY_THRESHOLD))
)

# Dual Cache: Local Fallback when LangCache unavailable
DUAL_CACHE_JSON_FALLBACK_ENABLED = (
    os.getenv("DUAL_CACHE_JSON_FALLBACK_ENABLED", os.getenv("LANGCACHE_FALLBACK_ENABLED", "true")).lower() == "true"
)
_default_cache_dir = os.getenv("LANGCACHE_CACHE_DIR", str(BASE_DIR / "data"))
DUAL_CACHE_JSON_FILE_PATH = os.getenv(
    "DUAL_CACHE_JSON_FILE_PATH",
    str(Path(_default_cache_dir) / "semantic_cache.json")
)

# Cache sync settings
DUAL_CACHE_SYNC_INTERVAL_SECONDS = float(
    os.getenv("DUAL_CACHE_SYNC_INTERVAL_SECONDS", os.getenv("LANGCACHE_SYNC_INTERVAL_SECONDS", "60.0"))
)
DUAL_CACHE_SYNC_ON_WRITE = os.getenv("DUAL_CACHE_SYNC_ON_WRITE", "true").lower() == "true"

