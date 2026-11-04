from typing import Dict, List, Optional
import logging
from app.core.cache_quality import is_negative_response, _NO_INFO_PATTERN

from app.domain.services.llm_provider import (
    LLMProvider,
    LLMProviderError,
)
from app.core import settings
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
        if cache is not None:
            self.cache = cache
        else:
            cache_master = getattr(settings, "CACHE_ENABLED", True)
            cache_enabled = cache_master and getattr(settings, "LLM_CACHE_ENABLED", False)
            cache_size = getattr(settings, "LLM_CACHE_SIZE", 0) if cache_enabled else 0
            self.cache = PromptLRUCache(maxsize=cache_size)
        self._last_tokens: Optional[dict] = None

    def generate(self, messages: List[Dict[str, str]]) -> str:
        cached_response = self.cache.get(messages)
        if cached_response is not None:
            if is_negative_response(cached_response):
                logger.info("llm_cache_evict reason=cached_negative_response")
                cached_response = None
            else:
                logger.info("llm_call outcome=cache_hit provider=none")
                # For cached responses, set zero tokens
                self._last_tokens = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cache_hit": True,
                }
                return cached_response

        try:
            logger.info("llm_call provider=primary")
            response = self.primary.generate(messages)
            # Get tokens from primary provider
            if hasattr(self.primary, 'get_last_tokens'):
                self._last_tokens = self.primary.get_last_tokens()

        except LLMProviderError as primary_error:
            logger.warning("llm_failure provider=primary error_type=%s", type(primary_error).__name__)
            try:
                logger.info("llm_call provider=fallback")
                response = self.fallback.generate(messages)
                # Get tokens from fallback provider
                if hasattr(self.fallback, 'get_last_tokens'):
                    self._last_tokens = self.fallback.get_last_tokens()

            except LLMProviderError as fallback_error:
                logger.error("llm_failure provider=fallback error_type=%s", type(fallback_error).__name__)
                raise LLMProviderError(
                    "Both primary and fallback LLM providers failed."
                ) from fallback_error

        if not is_negative_response(response):
            self.cache.put(messages, response)
        else:
            logger.info("llm_cache_skip reason=negative_response")
        logger.info("llm_success outcome=generated response_chars=%d", len(response))
        return response

    def get_last_tokens(self) -> Optional[dict]:
        """Get the token usage from the last generate() call."""
        return self._last_tokens
