import re
import time
from typing import Any, Dict, List, Optional

import httpx

from app.core.settings import LLM_MODEL, OPENROUTER_API_KEY
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

# Matches the offer-for-references line we ask the model to append.
_REFERENCES_LINE = re.compile(
    r"would you like to see the references for this\??",
    re.IGNORECASE,
)

# Matches reasoning/analysis section headers emitted by thinking models.
_THINKING_HEADER = re.compile(
    r"^(#+\s*)?"                                  # optional markdown heading
    r"(\d+[\.\)]\s*)?"                            # optional "1." / "1)"
    r"(\*{1,2})?"                                 # optional bold marker
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

# Matches lines that are echoing back the instructions
_INSTRUCTION_ECHO = re.compile(
    r"^\s*[-*]\s*(question|instructions?|answer using|write \d|no analysis|end (exactly|with)|if (answer|info))",
    re.IGNORECASE,
)


def _strip_reasoning(raw: str) -> str:
    """
    Extract the final answer from a reasoning model's output.

    Strategy: find the LAST line matching a thinking/instruction-echo header,
    return everything after it. Falls back to last paragraph if nothing matches.
    """
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


class OpenRouterClient(LLMProvider):
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self,
        api_key: str = OPENROUTER_API_KEY,
        model: str = LLM_MODEL,
        timeout: float = 3.0,
        max_tokens: int = 1024,
        session_id: Optional[str] = None,
        health_monitor: Optional[Any] = None,
        **kwargs
    ):
        self.base_url = kwargs.get("base_url") or "https://openrouter.ai/api/v1/chat/completions"
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.session_id = session_id
        self.health_monitor = health_monitor or get_provider_health_monitor()

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
            self.health_monitor.record_request_start(ProviderType.OPENROUTER.value)

        if not self.api_key:
            if self.health_monitor:
                self.health_monitor.record_request_failure(ProviderType.OPENROUTER.value)
            raise LLMProviderError("OPENROUTER_API_KEY is not configured.")

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }

        try:
            response = self._client.post(self.base_url, json=payload)
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            if response.is_error:
                if self.health_monitor:
                    self.health_monitor.record_request_failure(ProviderType.OPENROUTER.value)
                raise LLMProviderError(
                    f"OpenRouter returned HTTP {response.status_code}: {response.text}"
                )

            data = response.json()

            # Some models return {"error": {...}} with HTTP 200 (upstream errors)
            if "error" in data and "choices" not in data:
                if self.health_monitor:
                    self.health_monitor.record_request_failure(ProviderType.OPENROUTER.value)
                err_msg = data["error"].get("message", str(data["error"]))
                raise LLMProviderError(f"OpenRouter upstream error: {err_msg}")

            raw = data["choices"][0]["message"]["content"]

            if not raw:
                # Retry once with user-only message (some models return null
                # when the system prompt is too long).
                payload["messages"] = [
                    {"role": "user", "content": payload["messages"][-1]["content"]}
                ]
                response = self._client.post(self.base_url, json=payload)
                if response.is_error:
                    if self.health_monitor:
                        self.health_monitor.record_request_failure(ProviderType.OPENROUTER.value)
                    raise LLMProviderError(
                        f"OpenRouter returned HTTP {response.status_code}: {response.text}"
                    )
                data = response.json()
                raw = data["choices"][0]["message"]["content"]

            if not raw:
                if self.health_monitor:
                    self.health_monitor.record_request_failure(ProviderType.OPENROUTER.value)
                raise LLMProviderError("OpenRouter returned an empty response.")

            # Record health success
            if self.health_monitor:
                self.health_monitor.record_request_success(ProviderType.OPENROUTER.value, latency_ms)

            # Track token usage from OpenRouter response
            self._track_tokens(data)
            
            # Update LangSmith trace with token counts (if tracing is enabled)
            self._add_tokens_to_langsmith(data)

            return _strip_reasoning(raw)

        except LLMProviderError:
            raise
        except (httpx.HTTPError, KeyError, IndexError, TypeError) as error:
            if self.health_monitor:
                self.health_monitor.record_request_failure(ProviderType.OPENROUTER.value)
            raise LLMProviderError(f"OpenRouter request failed: {error}") from error

    def generate_with_response(self, messages: List[Dict[str, str]]) -> LLMResponse:
        """Execute chat completion and return structured LLMResponse object (Task AB-1.2)."""
        start_time = time.perf_counter()
        if self.health_monitor:
            self.health_monitor.record_request_start(ProviderType.OPENROUTER.value)

        if not self.api_key:
            if self.health_monitor:
                self.health_monitor.record_request_failure(ProviderType.OPENROUTER.value)
            return LLMResponseBuilder.error(
                "OPENROUTER_API_KEY is not configured.",
                status=LLMResponseStatus.FAILED,
                provider=LLMProviderName.OPENROUTER,
            )

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }

        try:
            response = self._client.post(self.base_url, json=payload)
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            if response.status_code == 429:
                if self.health_monitor:
                    self.health_monitor.record_request_failure(ProviderType.OPENROUTER.value)
                return LLMResponseBuilder.error(
                    f"OpenRouter rate limited (HTTP 429): {response.text}",
                    status=LLMResponseStatus.RATE_LIMITED,
                    provider=LLMProviderName.OPENROUTER,
                )

            if response.is_error:
                if self.health_monitor:
                    self.health_monitor.record_request_failure(ProviderType.OPENROUTER.value)
                return LLMResponseBuilder.error(
                    f"OpenRouter returned HTTP {response.status_code}: {response.text}",
                    status=LLMResponseStatus.FAILED,
                    provider=LLMProviderName.OPENROUTER,
                )

            data = response.json()
            if "error" in data and "choices" not in data:
                if self.health_monitor:
                    self.health_monitor.record_request_failure(ProviderType.OPENROUTER.value)
                err_msg = data["error"].get("message", str(data["error"]))
                return LLMResponseBuilder.error(
                    f"OpenRouter upstream error: {err_msg}",
                    status=LLMResponseStatus.FAILED,
                    provider=LLMProviderName.OPENROUTER,
                )

            raw = data["choices"][0]["message"]["content"]
            if not raw:
                # Retry once with user-only message
                payload["messages"] = [
                    {"role": "user", "content": payload["messages"][-1]["content"]}
                ]
                response = self._client.post(self.base_url, json=payload)
                if response.is_error:
                    if self.health_monitor:
                        self.health_monitor.record_request_failure(ProviderType.OPENROUTER.value)
                    return LLMResponseBuilder.error(
                        f"OpenRouter returned HTTP {response.status_code}: {response.text}",
                        status=LLMResponseStatus.FAILED,
                        provider=LLMProviderName.OPENROUTER,
                    )
                data = response.json()
                raw = data["choices"][0]["message"]["content"]

            if not raw:
                if self.health_monitor:
                    self.health_monitor.record_request_failure(ProviderType.OPENROUTER.value)
                return LLMResponseBuilder.error(
                    "OpenRouter returned an empty response.",
                    status=LLMResponseStatus.FAILED,
                    provider=LLMProviderName.OPENROUTER,
                )

            if self.health_monitor:
                self.health_monitor.record_request_success(ProviderType.OPENROUTER.value, latency_ms)

            self._track_tokens(data)
            self._add_tokens_to_langsmith(data)

            usage = data.get("usage", {})
            tokens = LLMTokenUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            )
            cleaned = _strip_reasoning(raw)
            return (
                LLMResponseBuilder()
                .with_content(cleaned)
                .with_status(LLMResponseStatus.SUCCESS)
                .with_provider(LLMProviderName.OPENROUTER)
                .with_model(self.model)
                .with_tokens(tokens=tokens)
                .with_latency(latency_ms)
                .build()
            )

        except Exception as error:
            if self.health_monitor:
                self.health_monitor.record_request_failure(ProviderType.OPENROUTER.value)
            return LLMResponseBuilder.error(
                f"OpenRouter request failed: {error}",
                status=LLMResponseStatus.FAILED,
                provider=LLMProviderName.OPENROUTER,
            )

    def _track_tokens(self, response_data: dict) -> None:
        """Extract and track token usage from OpenRouter response."""
        try:
            usage = response_data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)

            tracker = get_token_tracker()
            tracker.track(
                model=self.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                session_id=self.session_id,
                cache_hit=False,
                provider="openrouter",
            )
        except Exception as e:
            # Don't let tracking errors break the response
            import logging
            logging.warning(f"Failed to track token usage: {e}")

    def _add_tokens_to_langsmith(self, response_data: dict) -> None:
        """Add token usage metadata to LangSmith trace."""
        try:
            usage = response_data.get("usage", {})
            if not usage:
                return

            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = prompt_tokens + completion_tokens

            # Store tokens as class attribute so they can be accessed later
            self._last_tokens = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "model": self.model,
            }

            # Log for visibility
            import logging
            logger = logging.getLogger(__name__)
            logger.info(
                "Token usage: prompt=%d, completion=%d, total=%d, model=%s",
                prompt_tokens,
                completion_tokens,
                total_tokens,
                self.model,
            )

            # Try to add to LangSmith context
            try:
                from langsmith import get_run_tree
                run = get_run_tree()
                if run:
                    # Add tokens to the current run's metadata
                    if not hasattr(run, '_metadata'):
                        run._metadata = {}
                    run._metadata.update({
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                        "model": self.model,
                    })
                    logger.debug(f"Added token metadata to LangSmith run: {run.id}")
            except Exception as e:
                logger.debug(f"Could not add tokens to LangSmith: {e}")

        except Exception as e:
            import logging
            logging.debug(f"Failed to process token usage: {e}")

    def get_last_tokens(self) -> dict:
        """Get the token usage from the last generate() call."""
        return getattr(self, "_last_tokens", None)
