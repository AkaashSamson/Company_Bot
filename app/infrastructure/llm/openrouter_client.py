from typing import Dict, List

import httpx

from app.core.settings import LLM_MODEL, OPENROUTER_API_KEY
from app.domain.services.llm_provider import (
    LLMProvider,
    LLMProviderError,
)


class OpenRouterClient(LLMProvider):
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self,
        api_key: str = OPENROUTER_API_KEY,
        model: str = LLM_MODEL,
        timeout: float = 30.0,
        max_tokens: int = 512,
    ):


        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens

    def generate(self, messages: List[Dict[str, str]]) -> str:
        if not self.api_key:
            raise LLMProviderError(
                "OPENROUTER_API_KEY is not configured."
            )

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    self.BASE_URL,
                    headers=headers,
                    json=payload,
                )

            if response.is_error:
              raise LLMProviderError(
                   f"OpenRouter returned HTTP {response.status_code}: "
                   f"{response.text}"
    )

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            if not content:
                raise LLMProviderError(
                    "OpenRouter returned an empty response."
                )

            return content

        except LLMProviderError:
            raise

        except (httpx.HTTPError, KeyError, IndexError, TypeError) as error:
            raise LLMProviderError(
                f"OpenRouter request failed: {error}"
            ) from error