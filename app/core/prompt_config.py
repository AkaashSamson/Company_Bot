import logging
from pathlib import Path
from functools import lru_cache

import yaml

from app.core.settings import BASE_DIR

logger = logging.getLogger(__name__)

_PROMPTS_PATH = BASE_DIR / "config" / "prompts.yaml"

_FALLBACK_PROMPTS = {
    "conversation_query_rewrite": (
        "Rewrite a dependent follow-up as one standalone search query. "
        "Use only context in the conversation. Do not answer, add facts, "
        "or change an independent question. Return only the query."
    ),
}


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """Load a prompt template from config/prompts.yaml by section name."""
    try:
        if _PROMPTS_PATH.exists():
            with _PROMPTS_PATH.open("r", encoding="utf-8") as prompts_file:
                prompts = yaml.safe_load(prompts_file) or {}
            entry = prompts.get("prompts", {}).get(name, {})
            if isinstance(entry, dict):
                prompt_text = entry.get("system_prompt") or entry.get("system") or ""
                if prompt_text:
                    return prompt_text.strip()
            elif isinstance(entry, str):
                return entry.strip()
    except Exception as exc:
        logger.warning("Failed to load prompt '%s' from %s: %s", name, _PROMPTS_PATH, exc)

    return _FALLBACK_PROMPTS.get(name, "")
