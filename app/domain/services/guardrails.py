"""
Guardrails Subsystem — Pre-flight Input Security and Post-generation Output Safety.

Powered by:
1. Dynamic TypeSafe Laya System-One Decision Model (Zero-Trust via Ollama):
   - Input evaluation for prompt injections, jailbreaks, system prompt extraction, code/script attacks.
   - Output evaluation for system prompt leakage, secret leakage, and unsafe content.
   - Uses the native Laya Decision API (/v1/systemone).
2. Local Defense-in-Depth Fallback:
   - Fast regex and length caps if API/network is unavailable or in offline mode.
3. Zero-Document Guarantee:
   - ZERO company documents or Chroma chunks are ever evaluated or transmitted for input/output safety.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from app.domain.ports.laya_guardrail import LayaGuardrailPort

logger = logging.getLogger("knowlayer.guardrails")

# ── Local Defense-in-Depth Fallback Patterns ──────────────────────────────────
_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"\b(ignore\s+(?:all\s+)?(?:previous\s+|prior\s+)?(instructions|rules|prompts|directions))\b", re.IGNORECASE),
    re.compile(r"\b(disregard\s+(?:all\s+)?(?:previous\s+|prior\s+)?(instructions|rules|prompts|guidelines))\b", re.IGNORECASE),
    re.compile(r"\b(forget\s+(?:all\s+)?(?:previous\s+|prior\s+)?(instructions|rules|prompts|guidelines))\b", re.IGNORECASE),
    re.compile(r"\b(you\s+are\s+now\s+(dan|uncensored|jailbroken|unrestricted|godmode|chaos))\b", re.IGNORECASE),
    re.compile(r"\b(act\s+as\s+(an?\s+)?(dan|uncensored|unrestricted|jailbroken|evil)\s*(ai|bot|assistant)?)\b", re.IGNORECASE),
    re.compile(r"\b(reveal|show|print|display|dump|leak)\s+(?:all\s+|your\s+|the\s+)*(system\s+prompt|initial\s+prompt|hidden\s+instructions|developer\s+mode)\b", re.IGNORECASE),
    re.compile(r"\b(repeat\s+(?:everything|all)\s+above(?!\s+(?:points|steps|recommendations|options|items|rows|sections|table|in\s+a\s+summary))|repeat\s+(?:all|everything)\s+(?:prior|previous)\s*(?:instructions|prompts)|what\s+are\s+your\s+system\s+instructions)\b", re.IGNORECASE),
    re.compile(r"\b(bypass\s+(content\s+filters?|safety\s+filters?|guardrails?))\b", re.IGNORECASE),
]

_SCRIPT_INJECTION_PATTERNS = [
    re.compile(r"<\s*script\b[^>]*>[\s\S]*?<\s*/\s*script\s*>", re.IGNORECASE),
    re.compile(r"<\s*script\b[^>]*src\s*=\s*", re.IGNORECASE),
    re.compile(r"javascript\s*:\s*", re.IGNORECASE),
    re.compile(r"\bonerror\s*=\s*['\"]?[^'\">\s]+", re.IGNORECASE),
    re.compile(r"\bonload\s*=\s*['\"]?[^'\">\s]+", re.IGNORECASE),
]

_SQL_ARTIFACT_PATTERNS = [
    re.compile(r";\s*(?:drop\s+table|delete\s+from|insert\s+into)\b", re.IGNORECASE),
    re.compile(r"\bunion\s+(?:all\s+)?select\b", re.IGNORECASE),
]

_API_KEY_PATTERNS = [
    re.compile(r"\bsk-[a-zA-Z0-9_-]{20,}\b"),                               # OpenAI / OpenRouter
    re.compile(r"\bgsk_[a-zA-Z0-9_-]{20,}\b"),                              # Groq API key
    re.compile(r"\bBearer\s+[a-zA-Z0-9_\-\.]{25,}\b"),                       # Bearer JWT / Tokens
    re.compile(r"\b[ps]k-lf-[a-zA-Z0-9_-]{20,}\b"),                          # Langfuse keys
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                                    # AWS Access Key ID
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,255}\b"),                      # GitHub PATs
    re.compile(r"\bAIza[0-9A-Za-z-_]{30,40}\b"),                            # Google Cloud API Key
    re.compile(r"\bxox[baprs]-[0-9a-zA-Z-]{10,}\b"),                        # Slack Tokens
    re.compile(r"-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z ]+)?PRIVATE KEY-----"), # PEM Keys
    re.compile(r"(?:mongodb(?:\+srv)?|postgres(?:ql)?|sqlite)://[^\s\"']+", re.IGNORECASE), # Connection strings
]

_SYSTEM_PROMPT_SIGNATURES = [
    "You are a helpful company knowledge assistant. Your role is to provide accurate answers",
    "<user_question>",
    "</user_question>",
    "rag_answer_generation",
]

MAX_INPUT_CHAR_LIMIT = 2000


@dataclass
class GuardrailResult:
    is_safe: bool
    sanitized_text: str
    rejection_reason: Optional[str] = None
    violation_type: Optional[str] = None  # "prompt_injection", "jailbreak", "script_injection", "secret_leak", "length_limit"
    provider: str = "laya"                # "laya", "local", or "local_fallback"



def _get_default_laya_client() -> Optional["LayaGuardrailPort"]:
    """Lazily instantiate the LayaClient infrastructure adapter.
    
    This factory keeps the domain layer decoupled from infrastructure at
    module-import time while still enabling zero-configuration usage.
    """
    try:
        from app.infrastructure.llm.laya_client import LayaClient
        return LayaClient()
    except Exception:
        return None



class SecurityGuardrails:
    """Enterprise Input and Output Guardrail Engine powered by Laya System-One Decisions."""

    @classmethod
    def validate_input(
        cls,
        text: str,
        laya_client: Optional[LayaGuardrailPort] = None,
    ) -> GuardrailResult:
        """Evaluate incoming user message for malicious injection, jailbreaks, and floods.

        Uses Laya System-1 decision routing dynamically to detect threats without hardcoding,
        with local defense-in-depth fallback.
        """
        if not text:
            return GuardrailResult(is_safe=True, sanitized_text="", provider="local")

        # Normalize Unicode (NFKC) and strip zero-width stealth characters to eliminate homoglyph evasion
        normalized = unicodedata.normalize("NFKC", text)
        cleaned_text = re.sub(r"[\u200B-\u200D\uFEFF]", "", normalized)

        # 1. DoS / Overflow Guard (Immediate local sanity check)
        if len(cleaned_text) > MAX_INPUT_CHAR_LIMIT:
            logger.warning("Input rejected: Length %d exceeds %d limit", len(cleaned_text), MAX_INPUT_CHAR_LIMIT)
            return GuardrailResult(
                is_safe=False,
                sanitized_text=cleaned_text[:MAX_INPUT_CHAR_LIMIT],
                rejection_reason="Your message exceeds the maximum allowed length of 2,000 characters. Please shorten your question.",
                violation_type="length_limit",
                provider="local",
            )

        # 2. Dynamic Evaluation via Laya System-One Decision API
        client = laya_client
        if client is None:
            client = _get_default_laya_client()

        if client is not None and getattr(client, "is_available", lambda: False)():
            try:
                laya_res = client.check_input_safety(cleaned_text)
                is_safe = laya_res.get("is_safe", True)
                threat = laya_res.get("threat_type", "none")
                actual_provider = str(laya_res.get("provider", "laya"))

                if not is_safe:
                    logger.warning("Input blocked dynamically by Laya: threat=%s, reason=%s", threat, laya_res.get("reason"))
                    v_type = threat
                    if threat in ("system_prompt_extraction", "system_prompt_leak_attempt"):
                        v_type = "prompt_injection"
                    elif threat == "malicious_query":
                        if any(p.search(cleaned_text) for p in _SCRIPT_INJECTION_PATTERNS):
                            v_type = "script_injection"
                        elif any(p.search(cleaned_text) for p in _SQL_ARTIFACT_PATTERNS):
                            v_type = "sql_artifact"
                        else:
                            v_type = "prompt_injection"
                    elif threat == "none":
                        v_type = "prompt_injection"

                    rejection = "I am designed to assist exclusively with company documentation, policies, and workplace inquiries. I cannot process instructions to bypass safety guidelines or reveal system prompts."
                    if v_type == "script_injection":
                        rejection = "Invalid query format: Script tags and embedded code execution are not permitted."
                    elif v_type == "sql_artifact":
                        rejection = "Invalid query format: Database commands cannot be processed."

                    return GuardrailResult(
                        is_safe=False,
                        sanitized_text="",
                        rejection_reason=rejection,
                        violation_type=v_type,
                        provider=actual_provider,
                    )

                # Defense-in-depth: Even if Laya considered input safe, verify local defense patterns (SQL, script, prompt injection)
                local_check = cls._local_validate_input(cleaned_text, provider=actual_provider)
                if not local_check.is_safe:
                    return local_check

                return GuardrailResult(is_safe=True, sanitized_text=cleaned_text.strip(), provider=actual_provider)
            except Exception as e:
                logger.warning("Laya input safety check failed, falling back to local defense-in-depth: %s", e)
                return cls._local_validate_input(cleaned_text, provider="local_fallback")

        # 3. Local defense-in-depth fallback (if Laya is unavailable or offline)
        return cls._local_validate_input(cleaned_text, provider="local")

    @classmethod
    def validate_output(
        cls,
        answer: str,
        laya_client: Optional[LayaGuardrailPort] = None,
    ) -> GuardrailResult:
        """Inspect generated answer before delivery to prevent credential leakage or prompt dumping."""
        if not answer:
            return GuardrailResult(is_safe=True, sanitized_text="", provider="local")

        sanitized = answer
        leaked_secret = False

        # 1. Immediate Secret / API Key Redaction (Never let secrets leak to output or external API)
        for pattern in _API_KEY_PATTERNS:
            if pattern.search(sanitized):
                leaked_secret = True
                logger.error("CRITICAL: Detected and redacted leaked secret in LLM output!")
                sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)

        # 2. Dynamic Output Safety & Leak Check via Laya System-One Decision API
        client = laya_client
        if client is None:
            client = _get_default_laya_client()

        output_provider = "local"
        if client is not None and getattr(client, "is_available", lambda: False)():
            try:
                laya_res = client.check_output_safety(sanitized)
                output_provider = str(laya_res.get("provider", "laya"))
                if not laya_res.get("is_safe", True) or laya_res.get("has_leak", False):
                    leak_type = laya_res.get("leak_type", "system_prompt")
                    logger.warning("Output flagged dynamically by Laya: leak_type=%s, reason=%s", leak_type, laya_res.get("reason"))
                    if leak_type == "system_prompt":
                        for sig in _SYSTEM_PROMPT_SIGNATURES:
                            sanitized = sanitized.replace(sig, "").strip()
                    elif leak_type == "credential":
                        leaked_secret = True
            except Exception as e:
                logger.warning("Laya output safety check failed, falling back to local heuristic: %s", e)
                output_provider = "local_fallback"

        # 3. Local System Prompt Echo Scrubbing (Secondary defense)
        for sig in _SYSTEM_PROMPT_SIGNATURES:
            if sig in sanitized:
                logger.warning("Detected system prompt echo signature in LLM output. Scrubbing...")
                sanitized = sanitized.replace(sig, "").strip()

        if leaked_secret:
            return GuardrailResult(
                is_safe=True,
                sanitized_text=sanitized,
                rejection_reason=None,
                violation_type="secret_leak_redacted",
                provider=output_provider,
            )

        return GuardrailResult(
            is_safe=True,
            sanitized_text=sanitized,
            provider=output_provider,
        )

    @classmethod
    def _local_validate_input(cls, text: str, provider: str = "local") -> GuardrailResult:
        """Local regex-based fallback for input safety."""
        for pattern in _PROMPT_INJECTION_PATTERNS:
            if pattern.search(text):
                logger.warning("Input blocked by local Prompt Injection fallback: %r", text[:80])
                return GuardrailResult(
                    is_safe=False,
                    sanitized_text="",
                    rejection_reason="I am designed to assist exclusively with company documentation, policies, and workplace inquiries. I cannot process instructions to bypass safety guidelines or reveal system prompts.",
                    violation_type="prompt_injection",
                    provider=provider,
                )

        for pattern in _SCRIPT_INJECTION_PATTERNS:
            if pattern.search(text):
                logger.warning("Input blocked by local Script Injection fallback: %r", text[:80])
                return GuardrailResult(
                    is_safe=False,
                    sanitized_text="",
                    rejection_reason="Invalid query format: Script tags and embedded code execution are not permitted.",
                    violation_type="script_injection",
                    provider=provider,
                )

        for pattern in _SQL_ARTIFACT_PATTERNS:
            if pattern.search(text):
                logger.warning("Input blocked by local SQL Artifact fallback: %r", text[:80])
                return GuardrailResult(
                    is_safe=False,
                    sanitized_text="",
                    rejection_reason="Invalid query format: Database commands cannot be processed.",
                    violation_type="sql_artifact",
                    provider=provider,
                )

        return GuardrailResult(is_safe=True, sanitized_text=text.strip(), provider=provider)

