from typing import Dict, List

from app.domain.services.llm_provider import (
    LLMProvider,
    LLMProviderError,
)


class FallbackLLMProvider(LLMProvider):
    """
    Uses the primary provider first and falls back to the secondary
    provider when the primary provider fails.
    """

    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider,
    ):
        self.primary = primary
        self.fallback = fallback

    def generate(self, messages: List[Dict[str, str]]) -> str:
        try:
            return self.primary.generate(messages)

        except LLMProviderError as primary_error:
            try:
                return self.fallback.generate(messages)

            except LLMProviderError as fallback_error:
                raise LLMProviderError(
                    "Both primary and fallback LLM providers failed."
                ) from fallback_error