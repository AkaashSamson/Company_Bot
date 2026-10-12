"""
Cache Quality and Negative Response Detection (Task AB-4, Cache Quality Gate).

Defines quality gating rules ensuring negative/unverified responses
(e.g., "No information regarding this topic was found") are NEVER cached
in any semantic, prompt, or FAQ cache layer.
"""

import re
from typing import Optional

# Standard regex pattern for detecting refusal/no-info output
_NO_INFO_PATTERN = re.compile(
    r"(?:could not find|cannot find|can't find|unable to find|not found in|not mentioned in|no information|does not contain|no relevant information|failed to locate)",
    re.IGNORECASE,
)

# Comprehensive patterns detecting refusals, non-answers, and missing information
_NEGATIVE_RESPONSE_PATTERNS = [
    # 1. Inability to find / locate / determine information
    re.compile(
        r"\b(?:could not|cannot|can't|unable to|failed to)\s+(?:find|locate|retrieve|identify|uncover|determine|(?:provide\s+(?:any\s+|the\s+)?(?:information|details?|answers?|guidance|records?)))\b",
        re.IGNORECASE,
    ),
    # 2. No info / no details / no records found
    re.compile(
        r"\bno\s+(?:relevant\s+|specific\s+|applicable\s+|further\s+|requested\s+)?(?:information|details?|data|documents?|guidance|records?|context)\b",
        re.IGNORECASE,
    ),
    # 3. Not found / not mentioned / not covered in documents/handbook/context/files
    re.compile(
        r"\bnot\s+(?:found|mentioned|covered|specified|stated|addressed|included|provided|detailed|available|discussed|referenced|contained)\s+(?:in|within|across)\s+(?:the\s+)?(?:provided\s+|available\s+|retrieved\s+)?(?:documents?|handbooks?|context|files?|guidelines?|manuals?|records?)\b",
        re.IGNORECASE,
    ),
    # 4. Does not contain / does not provide / does not mention information
    re.compile(
        r"\b(?:does not|doesn't|do not|don't|did not|didn't)\s+(?:contain|mention|provide|specify|cover|include|address|detail|state)\s+(?:any|the|that|this|sufficient)?\s*(?:information|details?|guidance|data|records?)\b",
        re.IGNORECASE,
    ),
    # 5. Access restricted / denied
    re.compile(
        r"\brelevant information exists in a (?:project\s+)?document that you do not\s+(?:currently\s+)?have access to",
        re.IGNORECASE,
    ),
    # 6. Direct refusal phrases
    re.compile(
        r"\bno\s+specific\s+document\s+references\s+are\s+available\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bneither the provided documents nor\b",
        re.IGNORECASE,
    ),
]


def is_negative_response(text: Optional[str]) -> bool:
    """Return True if the text represents a refusal, non-answer, or missing information response.

    Such responses should NEVER be cached in semantic, prompt, or FAQ caches.
    """
    if text is None:
        return True
    if not isinstance(text, str):
        return False
    if not text.strip():
        return True  # Empty/whitespace responses must never be cached

    normalized = re.sub(r"\s+", " ", text).strip()
    return any(pattern.search(normalized) for pattern in _NEGATIVE_RESPONSE_PATTERNS)


# ============================================================
# Query Intent Classification & Cache Compatibility (AB-9)
# ============================================================

def classify_query_intent(query_text: str) -> str:
    """Classify user query into 10-category actionable intent."""
    from app.use_cases.chat.query_intent_classifier import get_query_intent_classifier
    return get_query_intent_classifier().classify(query_text).intent.value.upper()


def check_cache_intent_compatibility(query1: str, query2: str) -> bool:
    """Verify that two queries share compatible intent and topic before reusing a cached answer."""
    from app.use_cases.chat.query_intent_classifier import get_query_intent_classifier, CachePolicy, QueryIntent
    classifier = get_query_intent_classifier()
    res1 = classifier.classify(query1)
    res2 = classifier.classify(query2)

    # 1. Never share personal status answers in shared cache
    if res1.cache_policy == CachePolicy.NO_SHARED_CACHE or res2.cache_policy == CachePolicy.NO_SHARED_CACHE:
        return False
    if res1.cache_policy == CachePolicy.NO_CACHE or res2.cache_policy == CachePolicy.NO_CACHE:
        return False

    # 2. Both intent and topic must match (unless general QA)
    if res1.intent != res2.intent and res1.intent != QueryIntent.GENERAL_QA and res2.intent != QueryIntent.GENERAL_QA:
        return False
    if res1.topic != res2.topic and res1.topic.value != "general" and res2.topic.value != "general":
        return False

    return True


_INTENT_STOPWORDS = {
    "what", "are", "is", "the", "and", "or", "a", "an", "to", "in", "of", "for",
    "can", "u", "you", "out", "do", "i", "my", "how", "about", "regarding", "please",
}


def calculate_content_token_overlap(query1: str, query2: str) -> float:
    """Calculate overlap of significant content words between two queries."""
    clean1 = re.sub(r"[^a-z0-9\s]", " ", (query1 or "").lower())
    clean2 = re.sub(r"[^a-z0-9\s]", " ", (query2 or "").lower())
    toks1 = {w for w in clean1.split() if len(w) > 1 and w not in _INTENT_STOPWORDS}
    toks2 = {w for w in clean2.split() if len(w) > 1 and w not in _INTENT_STOPWORDS}
    if not toks1 or not toks2:
        return 0.0
    return len(toks1 & toks2) / max(1, min(len(toks1), len(toks2)))
