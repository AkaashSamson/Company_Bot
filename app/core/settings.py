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