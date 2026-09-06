from abc import ABC, abstractmethod
from typing import Dict, List


class LLMProviderError(Exception):
    """Raised when an LLM provider cannot generate a response."""


class LLMProvider(ABC):
    """Provider-independent contract for generating LLM responses."""

    @abstractmethod
    def generate(self, messages: List[Dict[str, str]]) -> str:
        """
        Generate an LLM response from chat messages.

        Args:
            messages: Chat messages using roles such as system, user,
                      and assistant.

        Returns:
            Generated assistant response.
        """
        raise NotImplementedError