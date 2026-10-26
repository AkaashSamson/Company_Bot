import logging
import re
import time
from typing import Any, Dict, List, Optional

import openai
from openai import AzureOpenAI, OpenAI, OpenAIError, RateLimitError, APITimeoutError

from app.core.settings import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
    LLM_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
)
from app.domain.services.llm_provider import LLMProvider, LLMProviderError
from app.infrastructure.llm.provider_health import get_provider_health_monitor, ProviderType
from app.infrastructure.llm.llm_response import (
    LLMResponse,
    LLMResponseBuilder,
    LLMProviderName,
    LLMResponseStatus,
    LLMTokenUsage,
)
from app.infrastructure.observability.token_tracker import get_token_tracker

logger = logging.getLogger(__name__)

# Matches reasoning/analysis section headers emitted by thinking models.
_THINKING_HEADER = re.compile(
    r"^(#+\s*)?"
    r"(\d+[\.\)]\s*)?"
    r"(\*{1,2})?"
    r"("
    r"analyze|analysis|thinking process|reasoning process|"
    r"scan (context|document)|check (if|whether)|"
    r"formulate|determine (if|whether)|examine|"
    r"user (request|input)|document context|"
    r"here.?s (a |my )?(thinking|reasoning|plan|analysis)|"
    r"(let me|i need to|i will|i must|i should|i'll)\s+(look|check|find|search|examine|scroll|scan|now)"
    r")",
    re.IGNORECASE,
)

_INSTRUCTION_ECHO = re.compile(
    r"^\s*[-*]\s*(question|instructions?|answer using|write \d|no analysis|end (exactly|with)|if (answer|info))",
    re.IGNORECASE,
)


def _strip_reasoning(raw: str) -> str:
    """Extract the final answer from a reasoning model's output."""
    text = re.sub(r"<think(?:ing)?>.*?</think(?:ing)?>", "", raw, flags=re.DOTALL).strip()
    lines = text.splitlines()
    last_header_idx = -1

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and (_THINKING_HEADER.search(stripped) or _INSTRUCTION_ECHO.search(stripped)):
            last_header_idx = i

    if last_header_idx != -1:
        after = "\n".join(lines[last_header_idx + 1:]).strip()
        if not after:
            paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
            cleaned = paragraphs[-1] if paragraphs else text
        else:
            cleaned = after
    else:
        cleaned = text

    # Clean generic [Document Context] or 【Document Context】 tags while preserving specific citations
    cleaned = re.sub(r"[【\[]\s*Document[\u202f\s]+Context\s*[】\]]", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _extract_usage(usage: Any) -> tuple[int, int, int]:
    """Safely extract prompt, completion, and total tokens from SDK object or dict."""
    if usage is None:
        return 0, 0, 0
    if isinstance(usage, dict):
        p = usage.get("prompt_tokens", 0) or 0
        c = usage.get("completion_tokens", 0) or 0
        t = usage.get("total_tokens", 0) or (p + c)
        return p, c, t
    p = getattr(usage, "prompt_tokens", 0) or 0
    c = getattr(usage, "completion_tokens", 0) or 0
    t = getattr(usage, "total_tokens", 0) or (p + c)
    return p, c, t


class OpenAIClient(LLMProvider):
    """
    OpenAI / Azure OpenAI LLM provider supporting both direct OpenAI API and
    Azure OpenAI Service endpoints with token tracking and health monitoring.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_version: Optional[str] = None,
        deployment: Optional[str] = None,
        timeout: float = 60.0,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        top_p: float = 1.0,
        session_id: Optional[str] = None,
        health_monitor: Optional[Any] = None,
        client: Optional[Any] = None,
        **kwargs,
    ):
        self.api_version = api_version if api_version is not None else AZURE_OPENAI_API_VERSION
        self.deployment = deployment if deployment is not None else AZURE_OPENAI_DEPLOYMENT
        self.model = model if model is not None else (OPENAI_MODEL or LLM_MODEL or "gpt-4o")

        if api_key is None:
            if OPENAI_API_KEY and not AZURE_OPENAI_API_KEY:
                is_azure = False
                self.api_key = OPENAI_API_KEY
                self.endpoint = endpoint if endpoint is not None else OPENAI_BASE_URL
            else:
                self.api_key = AZURE_OPENAI_API_KEY or OPENAI_API_KEY
                self.endpoint = endpoint if endpoint is not None else (AZURE_OPENAI_ENDPOINT or OPENAI_BASE_URL)
                is_azure = bool(
                    self.endpoint and ("azure.com" in self.endpoint.lower() or "azure" in self.endpoint.lower())
                ) or bool(self.api_version and self.endpoint and "azure" in self.endpoint.lower())
        else:
            self.api_key = api_key
            self.endpoint = endpoint if endpoint is not None else (AZURE_OPENAI_ENDPOINT or OPENAI_BASE_URL)
            is_azure = bool(
                self.endpoint and ("azure.com" in self.endpoint.lower() or "azure" in self.endpoint.lower())
            ) or bool(self.api_version and self.endpoint and "azure" in self.endpoint.lower())

        self.effective_model = (self.deployment if is_azure and self.deployment else self.model) or "gpt-4o"
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.session_id = session_id
        self.health_monitor = health_monitor or get_provider_health_monitor()
        self._last_tokens: Optional[dict] = None

        if client is not None:
            self._client = client
        elif not self.api_key:
            self._client = None
        else:
            try:
                if is_azure and self.endpoint:
                    self._client = AzureOpenAI(
                        api_version=self.api_version,
                        azure_endpoint=self.endpoint,
                        api_key=self.api_key,
                        timeout=self.timeout,
                    )
                else:
                    client_kwargs: Dict[str, Any] = {"api_key": self.api_key, "timeout": self.timeout}
                    if self.endpoint:
                        client_kwargs["base_url"] = self.endpoint
                    self._client = OpenAI(**client_kwargs)
            except Exception as exc:
                logger.warning("Failed to initialize OpenAI client: %s", exc)
                self._client = None

    def generate(self, messages: List[Dict[str, str]]) -> str:
        start_time = time.perf_counter()
        if self.health_monitor:
            self.health_monitor.record_request_start(ProviderType.OPENAI.value)

        if not self.api_key or self._client is None:
            if self.health_monitor:
                self.health_monitor.record_request_failure(ProviderType.OPENAI.value)
            raise LLMProviderError("OPENAI_API_KEY / AZURE_OPENAI_API_KEY is not configured.")

        try:
            response = self._client.chat.completions.create(
                model=self.effective_model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                top_p=self.top_p,
            )
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            if not response.choices or not response.choices[0].message:
                if self.health_monitor:
                    self.health_monitor.record_request_failure(ProviderType.OPENAI.value)
                raise LLMProviderError("OpenAI returned an empty response.")

            raw = response.choices[0].message.content or ""
            if not raw:
                if self.health_monitor:
                    self.health_monitor.record_request_failure(ProviderType.OPENAI.value)
                raise LLMProviderError("OpenAI returned empty message content.")

            if self.health_monitor:
                self.health_monitor.record_request_success(ProviderType.OPENAI.value, latency_ms)

            usage = getattr(response, "usage", None)
            self._track_tokens(usage)

            return _strip_reasoning(raw)

        except LLMProviderError:
            raise
        except RateLimitError as error:
            if self.health_monitor:
                self.health_monitor.record_request_failure(ProviderType.OPENAI.value)
            raise LLMProviderError(f"OpenAI rate limited: {error}") from error
        except APITimeoutError as error:
            if self.health_monitor:
                self.health_monitor.record_request_failure(ProviderType.OPENAI.value)
            raise LLMProviderError(f"OpenAI timed out: {error}") from error
        except OpenAIError as error:
            if self.health_monitor:
                self.health_monitor.record_request_failure(ProviderType.OPENAI.value)
            raise LLMProviderError(f"OpenAI request failed: {error}") from error
        except Exception as error:
            if self.health_monitor:
                self.health_monitor.record_request_failure(ProviderType.OPENAI.value)
            raise LLMProviderError(f"OpenAI request failed: {error}") from error

    def generate_with_response(self, messages: List[Dict[str, str]]) -> LLMResponse:
        """Execute chat completion and return structured LLMResponse object."""
        start_time = time.perf_counter()
        if self.health_monitor:
            self.health_monitor.record_request_start(ProviderType.OPENAI.value)

        if not self.api_key or self._client is None:
            if self.health_monitor:
                self.health_monitor.record_request_failure(ProviderType.OPENAI.value)
            return LLMResponseBuilder.error(
                "OPENAI_API_KEY / AZURE_OPENAI_API_KEY is not configured.",
                status=LLMResponseStatus.FAILED,
                provider=LLMProviderName.OPENAI,
            )

        try:
            response = self._client.chat.completions.create(
                model=self.effective_model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                top_p=self.top_p,
            )
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            if not response.choices or not response.choices[0].message:
                if self.health_monitor:
                    self.health_monitor.record_request_failure(ProviderType.OPENAI.value)
                return LLMResponseBuilder.error(
                    "OpenAI returned an empty response.",
                    status=LLMResponseStatus.FAILED,
                    provider=LLMProviderName.OPENAI,
                )

            raw = response.choices[0].message.content or ""
            if not raw:
                if self.health_monitor:
                    self.health_monitor.record_request_failure(ProviderType.OPENAI.value)
                return LLMResponseBuilder.error(
                    "OpenAI returned empty message content.",
                    status=LLMResponseStatus.FAILED,
                    provider=LLMProviderName.OPENAI,
                )

            if self.health_monitor:
                self.health_monitor.record_request_success(ProviderType.OPENAI.value, latency_ms)

            usage = getattr(response, "usage", None)
            self._track_tokens(usage)

            prompt_tokens, completion_tokens, total_tokens = _extract_usage(usage)
            tokens = LLMTokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )
            cleaned = _strip_reasoning(raw)
            return (
                LLMResponseBuilder()
                .with_content(cleaned)
                .with_status(LLMResponseStatus.SUCCESS)
                .with_provider(LLMProviderName.OPENAI)
                .with_model(self.effective_model)
                .with_tokens(tokens=tokens)
                .with_latency(latency_ms)
                .build()
            )

        except RateLimitError as error:
            if self.health_monitor:
                self.health_monitor.record_request_failure(ProviderType.OPENAI.value)
            return LLMResponseBuilder.error(
                f"OpenAI rate limited: {error}",
                status=LLMResponseStatus.RATE_LIMITED,
                provider=LLMProviderName.OPENAI,
            )
        except APITimeoutError as error:
            if self.health_monitor:
                self.health_monitor.record_request_failure(ProviderType.OPENAI.value)
            return LLMResponseBuilder.error(
                f"OpenAI timed out: {error}",
                status=LLMResponseStatus.TIMEOUT,
                provider=LLMProviderName.OPENAI,
            )
        except Exception as error:
            if self.health_monitor:
                self.health_monitor.record_request_failure(ProviderType.OPENAI.value)
            return LLMResponseBuilder.error(
                f"OpenAI request failed: {error}",
                status=LLMResponseStatus.FAILED,
                provider=LLMProviderName.OPENAI,
            )

    def _track_tokens(self, usage: Any) -> None:
        """Extract, store, and track token usage from response."""
        try:
            if usage is None:
                return
            prompt_tokens, completion_tokens, total_tokens = _extract_usage(usage)

            self._last_tokens = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "model": self.effective_model,
            }

            logger.info(
                "Token usage: prompt=%d, completion=%d, total=%d, model=%s",
                prompt_tokens,
                completion_tokens,
                total_tokens,
                self.effective_model,
            )

            tracker = get_token_tracker()
            tracker.track(
                model=self.effective_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                session_id=self.session_id,
                cache_hit=False,
                provider="openai",
            )
        except Exception as e:
            logger.warning("Failed to track token usage: %s", e)

    def get_last_tokens(self) -> Optional[dict]:
        """Get the token usage from the last generate() call."""
        return self._last_tokens
