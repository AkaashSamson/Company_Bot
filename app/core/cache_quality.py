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
