import logging
from typing import Dict, List

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

    def generate(self, messages: List[Dict[str, str]]) -> str:
        cached_response = self.cache.get(messages)
        if cached_response is not None:
            logger.info("llm_call outcome=cache_hit provider=none")
            return cached_response

        try:
            logger.info("llm_call provider=primary")
            response = self.primary.generate(messages)

        except LLMProviderError as primary_error:
            logger.warning("llm_failure provider=primary error_type=%s", type(primary_error).__name__)
            try:
                logger.info("llm_call provider=fallback")
                response = self.fallback.generate(messages)

            except LLMProviderError as fallback_error:
                logger.error("llm_failure provider=fallback error_type=%s", type(fallback_error).__name__)
                raise LLMProviderError(
                    "Both primary and fallback LLM providers failed."
                ) from fallback_error

        self.cache.put(messages, response)
        logger.info("llm_success outcome=generated response_chars=%d", len(response))
        return response