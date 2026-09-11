from typing import Dict, List, Optional
import logging

from app.domain.services.llm_provider import (
    LLMProvider,
    LLMProviderError,
)
from app.core.settings import LLM_CACHE_SIZE
from app.infrastructure.llm.prompt_cache import PromptLRUCache

logger = logging.getLogger(__name__)


class FallbackLLMProvider(LLMProvider):
    """
    Uses the primary provider first and falls back to the secondary
    provider when the primary provider fails.
    """

    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider,
        cache: PromptLRUCache | None = None,
    ):
        self.primary = primary
        self.fallback = fallback
        self.cache = cache or PromptLRUCache(maxsize=LLM_CACHE_SIZE)
        self._last_tokens: Optional[dict] = None

    def generate(self, messages: List[Dict[str, str]]) -> str:
        cached_response = self.cache.get(messages)
        if cached_response is not None:
            # For cached responses, set zero tokens
            self._last_tokens = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cache_hit": True,
            }
            return cached_response

        try:
            response = self.primary.generate(messages)
            # Get tokens from primary provider
            if hasattr(self.primary, 'get_last_tokens'):
                self._last_tokens = self.primary.get_last_tokens()

        except LLMProviderError as primary_error:
            logger.warning("Primary LLM provider failed, trying fallback: %s", primary_error)
            try:
                response = self.fallback.generate(messages)
                # Get tokens from fallback provider
                if hasattr(self.fallback, 'get_last_tokens'):
                    self._last_tokens = self.fallback.get_last_tokens()

            except LLMProviderError as fallback_error:
                raise LLMProviderError(
                    "Both primary and fallback LLM providers failed."
                ) from fallback_error

        self.cache.put(messages, response)
        return response

    def get_last_tokens(self) -> Optional[dict]:
        """Get the token usage from the last generate() call."""
        return self._last_tokens