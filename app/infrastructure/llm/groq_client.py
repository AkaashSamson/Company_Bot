import re
from typing import Dict, List

import httpx

from app.core.settings import GROQ_API_KEY, GROQ_MODEL
from app.domain.services.llm_provider import (
    LLMProvider,
    LLMProviderError,
)


def _sanitize_response_body(body: str, max_length: int = 1000) -> str:
    sanitized = body[:max_length]
    sanitized = re.sub(
        r"(?i)bearer\s+[a-z0-9._-]+",
        "Bearer [REDACTED]",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)(?:gsk_|sk-)[a-z0-9_-]+",
        "[REDACTED_KEY]",
        sanitized,
    )
    return sanitized


class GroqClient(LLMProvider):
    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(
        self,
        api_key: str = GROQ_API_KEY,
        model: str = GROQ_MODEL,
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
                "GROQ_API_KEY is not configured."
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
                    "Groq returned HTTP "
                    f"{response.status_code}: "
                    f"{_sanitize_response_body(response.text)}"
                )

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            if not content:
                raise LLMProviderError(
                    "Groq returned an empty response."
                )

            return content

        except LLMProviderError:
            raise

        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            raise LLMProviderError(
                f"Groq request failed: {error}"
            ) from error