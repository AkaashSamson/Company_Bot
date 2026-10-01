import logging
import re
import time
from typing import Any, Dict, List, Optional

import httpx

from app.core.settings import GROQ_API_KEY, GROQ_MODEL
from app.domain.services.llm_provider import LLMProvider, LLMProviderError
from app.infrastructure.llm.provider_health import get_provider_health_monitor, ProviderType
from app.infrastructure.llm.llm_response import (
    LLMResponse,
    LLMResponseBuilder,
    LLMProviderName,
    LLMResponseStatus,
    LLMTokenUsage,
)

logger = logging.getLogger(__name__)


def _sanitize_response_body(body: str, max_length: int = 1000) -> str:
    sanitized = body[:max_length]
    sanitized = re.sub(r"(?i)bearer\s+[a-z0-9._-]+", "Bearer [REDACTED]", sanitized)
    sanitized = re.sub(r"(?i)(?:gsk_|sk-)[a-z0-9_-]+", "[REDACTED_KEY]", sanitized)
    return sanitized


class GroqClient(LLMProvider):
    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(
        self,
        api_key: str = GROQ_API_KEY,
        model: str = GROQ_MODEL,
        timeout: float = 60.0,
        max_tokens: int = 400,
        health_monitor: Optional[Any] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.health_monitor = health_monitor or get_provider_health_monitor()
        self._last_tokens: Optional[dict] = None
        self._last_token_usage: Optional[LLMTokenUsage] = None

        # Persistent client — reuses TCP/TLS connection across calls.
        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

    def generate(self, messages: List[Dict[str, str]]) -> str:
        start_time = time.perf_counter()
        if self.health_monitor:
            self.health_monitor.record_request_start(ProviderType.GROQ.value)

        if not self.api_key:
            if self.health_monitor:
                self.health_monitor.record_request_failure(ProviderType.GROQ.value)
            raise LLMProviderError("GROQ_API_KEY is not configured.")

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }

        try:
            response = self._client.post(self.BASE_URL, json=payload)
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            if response.is_error:
                if self.health_monitor:
                    self.health_monitor.record_request_failure(ProviderType.GROQ.value)
                raise LLMProviderError(
                    f"Groq returned HTTP {response.status_code}: "
                    f"{_sanitize_response_body(response.text)}"
                )

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            if not content:
                if self.health_monitor:
                    self.health_monitor.record_request_failure(ProviderType.GROQ.value)
                raise LLMProviderError("Groq returned an empty response.")

            # Record success metrics
            if self.health_monitor:
                self.health_monitor.record_request_success(ProviderType.GROQ.value, latency_ms)

            # Track tokens if present in response
            usage = data.get("usage", {})
            if usage:
                prompt_tok = usage.get("prompt_tokens", 0)
                comp_tok = usage.get("completion_tokens", 0)
                tot_tok = usage.get("total_tokens", prompt_tok + comp_tok)
                self._last_tokens = {
                    "prompt_tokens": prompt_tok,
                    "completion_tokens": comp_tok,
                    "total_tokens": tot_tok,
                    "model": self.model,
                }
                self._last_token_usage = LLMTokenUsage(
                    prompt_tokens=prompt_tok,
                    completion_tokens=comp_tok,
                    total_tokens=tot_tok,
                )
            else:
                self._last_tokens = None
                self._last_token_usage = None

            return content

        except LLMProviderError:
            self._last_tokens = None
            self._last_token_usage = None
            raise
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            self._last_tokens = None
            self._last_token_usage = None
            if self.health_monitor:
                self.health_monitor.record_request_failure(ProviderType.GROQ.value)
            raise LLMProviderError(f"Groq request failed: {error}") from error

    def generate_with_response(self, messages: List[Dict[str, str]]) -> LLMResponse:
        """Execute chat completion and return structured LLMResponse object (Task AB-1.2)."""
        start_time = time.perf_counter()
        if self.health_monitor:
            self.health_monitor.record_request_start(ProviderType.GROQ.value)

        if not self.api_key:
            self._last_tokens = None
            self._last_token_usage = None
            if self.health_monitor:
                self.health_monitor.record_request_failure(ProviderType.GROQ.value)
            return LLMResponseBuilder.error(
                "GROQ_API_KEY is not configured.",
                status=LLMResponseStatus.FAILED,
                provider=LLMProviderName.GROQ,
            )

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }

        try:
            response = self._client.post(self.BASE_URL, json=payload)
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            if response.status_code == 429:
                self._last_tokens = None
                self._last_token_usage = None
                if self.health_monitor:
                    self.health_monitor.record_request_failure(ProviderType.GROQ.value)
                return LLMResponseBuilder.error(
                    f"Groq rate limited (HTTP 429): {_sanitize_response_body(response.text)}",
                    status=LLMResponseStatus.RATE_LIMITED,
                    provider=LLMProviderName.GROQ,
                )

            if response.is_error:
                self._last_tokens = None
                self._last_token_usage = None
                if self.health_monitor:
                    self.health_monitor.record_request_failure(ProviderType.GROQ.value)
                return LLMResponseBuilder.error(
                    f"Groq returned HTTP {response.status_code}: {_sanitize_response_body(response.text)}",
                    status=LLMResponseStatus.FAILED,
                    provider=LLMProviderName.GROQ,
                )

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            if not content:
                self._last_tokens = None
                self._last_token_usage = None
                if self.health_monitor:
                    self.health_monitor.record_request_failure(ProviderType.GROQ.value)
                return LLMResponseBuilder.error(
                    "Groq returned an empty response.",
                    status=LLMResponseStatus.FAILED,
                    provider=LLMProviderName.GROQ,
                )

            if self.health_monitor:
                self.health_monitor.record_request_success(ProviderType.GROQ.value, latency_ms)

            usage = data.get("usage", {})
            if usage:
                prompt_tok = usage.get("prompt_tokens", 0)
                comp_tok = usage.get("completion_tokens", 0)
                tot_tok = usage.get("total_tokens", prompt_tok + comp_tok)
                tokens = LLMTokenUsage(
                    prompt_tokens=prompt_tok,
                    completion_tokens=comp_tok,
                    total_tokens=tot_tok,
                )
                self._last_token_usage = tokens
                self._last_tokens = {
                    "prompt_tokens": tokens.prompt_tokens,
                    "completion_tokens": tokens.completion_tokens,
                    "total_tokens": tokens.total_tokens,
                    "model": self.model,
                }
            else:
                tokens = None
                self._last_token_usage = None
                self._last_tokens = None

            builder = (
                LLMResponseBuilder()
                .with_content(content)
                .with_status(LLMResponseStatus.SUCCESS)
                .with_provider(LLMProviderName.GROQ)
                .with_model(self.model)
                .with_latency(latency_ms)
            )
            if tokens is not None:
                builder = builder.with_tokens(tokens=tokens)

            return builder.build()

        except Exception as error:
            self._last_tokens = None
            self._last_token_usage = None
            if self.health_monitor:
                self.health_monitor.record_request_failure(ProviderType.GROQ.value)
            return LLMResponseBuilder.error(
                f"Groq request failed: {error}",
                status=LLMResponseStatus.FAILED,
                provider=LLMProviderName.GROQ,
            )

    def get_last_tokens(self) -> Optional[dict]:
        """Get token usage from the last generate call."""
        return self._last_tokens

    def get_last_token_usage(self) -> Optional[LLMTokenUsage]:
        """Get standardized LLMTokenUsage from the last generate call (Task AK-3.3)."""
        return self._last_token_usage
