"""
Laya Guardrail Port — Domain abstraction for the TypeSafe Laya System-One decision model.

This port (interface) belongs to the domain layer. No infrastructure details
(HTTP clients, API URLs, SDK imports) may appear here.

Adapters live in app.infrastructure.llm.laya_client and must implement this protocol.
"""

from __future__ import annotations

from typing import List, Protocol, TypedDict, runtime_checkable


# ── Typed Result Contracts ─────────────────────────────────────────────────────


class InputSafetyResult(TypedDict):
    """Structured result from the input-safety guardrail decision."""

    is_safe: bool
    threat_type: str          # "none" | "prompt_injection" | "jailbreak" | "system_prompt_extraction" | "script_injection" | "social_engineering" | "malicious_query"
    confidence: float         # 0.0 – 1.0
    reason: str
    provider: str             # "laya" | "local" | "local_fallback"


class OutputSafetyResult(TypedDict):
    """Structured result from the output-safety guardrail decision."""

    is_safe: bool
    has_leak: bool
    leak_type: str            # "none" | "credential" | "system_prompt" | "toxic_content" | "malicious_leak"
    reason: str
    provider: str


class QueryIntentResult(TypedDict):
    """Structured result from the query-intent routing decision."""

    category: str             # "document_query" | "conversational" | "unrelated"
    confidence: float
    provider: str


class FollowupIntentResult(TypedDict):
    """Structured result from the follow-up intent disambiguation decision."""

    intent: str               # "feedback_positive" | "feedback_negative" | "followup_query"
    provider: str


# ── Port Protocol ─────────────────────────────────────────────────────────────


@runtime_checkable
class LayaGuardrailPort(Protocol):
    """
    Port for the TypeSafe Laya System-One decision guardrail model.

    Laya is a non-autoregressive classifier, not a text generator. Implementations
    use the TypeSafe / Ollama native Decision API (/v1/systemone) with state + questions.

    All methods return typed dictionaries matching the contracts above.
    All methods must be synchronous and never raise on API failure —
    they fall back to local heuristics and set provider = "local_fallback".
    """

    def is_available(self) -> bool:
        """Return True iff the underlying API/service is configured and the circuit breaker is not open."""
        ...

    def check_input_safety(self, question: str) -> InputSafetyResult:
        """
        Evaluate an incoming user query for security threats.
        Only the sanitized user query is evaluated.
        ZERO company documents or Chroma chunks are sent.
        """
        ...

    def check_output_safety(self, answer: str) -> OutputSafetyResult:
        """
        Evaluate a generated assistant answer for leaks or unsafe content.
        Secrets are pre-redacted locally before transmission.
        """
        ...

    def classify_query_intent(self, question: str) -> QueryIntentResult:
        """Classify the user query intent before retrieval routing."""
        ...

    def classify_followup_intent(
        self,
        current_input: str,
        last_bot_prompt_type: str = "relevance",
        previous_assistant_message: str = "",
    ) -> FollowupIntentResult:
        """Disambiguate follow-up queries from yes/no feedback signals."""
        ...


# Type aliases
DecisionGuardrailPort = LayaGuardrailPort
