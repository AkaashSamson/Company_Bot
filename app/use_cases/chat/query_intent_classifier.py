"""
Query Intent Disambiguation & Semantic Routing Engine (Task AB-3.4)

Classifies user queries into distinct semantic intents to resolve context
collapsing (e.g. "How many leaves do I have" vs "How to apply for leaves"):
- Rule-based, sub-millisecond execution (<0.05ms, zero LLM overhead)
- Disambiguates PROCEDURAL, PERSONAL_BALANCE, POLICY_ENTITLEMENT, POLICY_GENERAL, and DIRECTORY_LOOKUP
- Injects intent tags into QualityAwareCache keys to eliminate cache collisions
- Provides intent-specific retrieval keyword boosts and prompt directives for HRMS clarification
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """Semantic intent classification categories for company bot queries."""
    PROCEDURAL = "procedural"                    # Workflow, steps, forms, portal navigation, how-to-apply
    PERSONAL_BALANCE = "personal_balance"        # Employee's individual remaining count/balance ("do I have", "my leaves")
    POLICY_ENTITLEMENT = "policy_entitlement"    # Company-wide standard allowance ("how many annual leave days are provided")
    POLICY_GENERAL = "policy_general"            # Rules, guidelines, carry-forward, probation, conduct
    DIRECTORY_LOOKUP = "directory_lookup"        # People, managers, email addresses, departments
    GENERAL_FAQ = "general_faq"                  # General questions, greetings, miscellaneous


@dataclass
class IntentClassificationResult:
    """Detailed result of query intent classification."""
    intent: QueryIntent
    confidence: float
    matched_patterns: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    cache_prefix: str = ""
    retrieval_boost_keywords: list[str] = field(default_factory=list)
    prompt_directive: Optional[str] = None
    is_personal_query: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert classification result to dictionary."""
        return {
            "intent": self.intent.value,
            "confidence": round(self.confidence, 4),
            "matched_patterns": self.matched_patterns,
            "matched_keywords": self.matched_keywords,
            "cache_prefix": self.cache_prefix,
            "retrieval_boost_keywords": self.retrieval_boost_keywords,
            "prompt_directive": self.prompt_directive,
            "is_personal_query": self.is_personal_query,
        }


class QueryIntentClassifier:
    """
    High-speed deterministic classifier that detects query intent using regex
    patterns and semantic keyword clustering.
    """

    # 1. Procedural Action Patterns (Application workflows, submissions, portal forms)
    PROCEDURAL_PATTERNS = [
        re.compile(r"\b(how\s+to|how\s+do\s+i|how\s+can\s+i|where\s+do\s+i|where\s+to)\s+(apply|submit|request|book|claim|fill|cancel|raise)\b", re.IGNORECASE),
        re.compile(r"\b(process|procedure|steps|workflow|guide|instructions)\s+(to|for|of)\s+(apply|applying|request|submission|avail|claim)\b", re.IGNORECASE),
        re.compile(r"\b(apply|applying|application|submission)\s+(for|of)\s+(leave|pto|vacation|wfh|expense|reimbursement|claim)\b", re.IGNORECASE),
        re.compile(r"\b(approval|approve|permission)\s+(required|process|needed|workflow|from\s+manager)\b", re.IGNORECASE),
        re.compile(r"\b(hr\s+portal|hrms|designated\s+system|login\s+to\s+apply)\b", re.IGNORECASE),
    ]

    # 2. Personal Balance Patterns (Queries asking about individual balance / remaining count)
    PERSONAL_BALANCE_PATTERNS = [
        re.compile(r"\b(how\s+many|how\s+much|what\s+is\s+my|check\s+my)\b.*\b(do\s+i\s+have|i\s+have|i\s+got|left|remaining|balance|available\s+to\s+me)\b", re.IGNORECASE),
        re.compile(r"\b(my\s+leave\s+balance|my\s+remaining\s+leaves|my\s+leaves\s+left|my\s+pto\s+balance|my\s+quota)\b", re.IGNORECASE),
        re.compile(r"\b(how\s+many\s+(days|leaves|hours)\s+(do\s+i|can\s+i\s+take|are\s+left\s+for\s+me))\b", re.IGNORECASE),
        re.compile(r"\b(am\s+i\s+eligible\s+for|how\s+much\s+leave\s+is\s+credited\s+to\s+me)\b", re.IGNORECASE),
    ]

    # 3. Policy Entitlement Patterns (Company-wide statutory/annual quota without personal pronouns)
    ENTITLEMENT_PATTERNS = [
        re.compile(r"\b(how\s+many|what\s+is\s+the|total\s+number\s+of)\b.*\b(annual\s+leave|sick\s+leave|casual\s+leave|maternity\s+leave|paternity\s+leave)\b.*\b(days|entitlement|quota|credited|per\s+year|calendar\s+year)\b", re.IGNORECASE),
        re.compile(r"\b(entitlement|allowance|quota|allotment)\s+(for|of)\s+(annual|sick|casual|maternity|paternity|bereavement)\b", re.IGNORECASE),
        re.compile(r"\b(days\s+of\s+annual\s+leave|days\s+per\s+calendar\s+year|statutory\s+leave\s+days)\b", re.IGNORECASE),
    ]

    # 4. Directory & People Lookup Patterns
    DIRECTORY_PATTERNS = [
        re.compile(r"\b(who\s+is|who\s+are|contact\s+for|email\s+of|reach\s+out\s+to|manager\s+of|head\s+of|reporting\s+to)\b", re.IGNORECASE),
        re.compile(r"\b(people\s+directory|employee\s+directory|staff\s+list|find\s+colleague)\b", re.IGNORECASE),
    ]

    # 5. General Policy Patterns
    POLICY_GENERAL_PATTERNS = [
        re.compile(r"\b(carry\s+forward|encashment|lapse|expire|lapse\s+of\s+leave)\b", re.IGNORECASE),
        re.compile(r"\b(work\s+from\s+home\s+policy|wfh\s+rules|remote\s+work\s+guidelines|working\s+hours|grace\s+period)\b", re.IGNORECASE),
        re.compile(r"\b(code\s+of\s+conduct|dress\s+code|posh|harassment|notice\s+period|probation)\b", re.IGNORECASE),
    ]

    # Intent-specific retrieval keyword boosters
    INTENT_RETRIEVAL_BOOSTS = {
        QueryIntent.PROCEDURAL: [
            "apply", "submission", "portal", "approval", "process", "workflow", "request", "steps"
        ],
        QueryIntent.PERSONAL_BALANCE: [
            "entitlement", "annual leave days", "calendar year", "credited", "balance", "allowance", "hrms"
        ],
        QueryIntent.POLICY_ENTITLEMENT: [
            "entitlement", "eligible", "regular employees receive", "calendar year", "days", "annual leave"
        ],
        QueryIntent.POLICY_GENERAL: [
            "policy", "rules", "guidelines", "handbook", "eligibility", "terms"
        ],
        QueryIntent.DIRECTORY_LOOKUP: [
            "directory", "department", "manager", "email", "team", "organization"
        ],
        QueryIntent.GENERAL_FAQ: [],
    }

    # Intent-specific system prompt directives for LLM generation
    INTENT_PROMPT_DIRECTIVES = {
        QueryIntent.PROCEDURAL: (
            "The user is asking for procedural instructions on how to submit or apply. "
            "Focus strictly on the step-by-step application workflow, approval requirements, "
            "and portal submission steps described in the documentation."
        ),
        QueryIntent.PERSONAL_BALANCE: (
            "The user is asking about their personal leave balance ('How many leaves do I have'). "
            "State the company's standard annual policy entitlement (e.g., 18 Annual Leave days per calendar year), "
            "and explicitly inform the user that live, individualized remaining balances must be viewed "
            "on the internal company HRMS portal."
        ),
        QueryIntent.POLICY_ENTITLEMENT: (
            "The user is asking for standard company-wide leave entitlements or quotas. "
            "State the exact number of days provided per calendar year according to corporate policy."
        ),
        QueryIntent.DIRECTORY_LOOKUP: (
            "The user is asking for employee or department directory information. "
            "Provide accurate contact, department, and role details from the authorized directory."
        ),
        QueryIntent.POLICY_GENERAL: None,
        QueryIntent.GENERAL_FAQ: None,
    }

    def classify(self, query: str) -> IntentClassificationResult:
        """
        Classify incoming user query into semantic intent.
        
        Args:
            query: User's raw or normalized query text
            
        Returns:
            IntentClassificationResult with intent, confidence, cache prefix, and prompt guidance
        """
        if not query or not query.strip():
            return IntentClassificationResult(
                intent=QueryIntent.GENERAL_FAQ,
                confidence=0.0,
                cache_prefix="faq",
                retrieval_boost_keywords=[],
                prompt_directive=None,
                is_personal_query=False,
            )

        clean_query = query.strip()
        matched_patterns: list[str] = []
        matched_keywords: list[str] = []

        # 1. Check Personal Balance FIRST (prevents personal queries from collapsing into general entitlement)
        for idx, pat in enumerate(self.PERSONAL_BALANCE_PATTERNS):
            match = pat.search(clean_query)
            if match:
                matched_patterns.append(f"personal_balance_{idx}")
                matched_keywords.extend(match.group(0).split())
                return IntentClassificationResult(
                    intent=QueryIntent.PERSONAL_BALANCE,
                    confidence=0.95,
                    matched_patterns=matched_patterns,
                    matched_keywords=list(set(matched_keywords)),
                    cache_prefix="bal",
                    retrieval_boost_keywords=self.INTENT_RETRIEVAL_BOOSTS[QueryIntent.PERSONAL_BALANCE],
                    prompt_directive=self.INTENT_PROMPT_DIRECTIVES[QueryIntent.PERSONAL_BALANCE],
                    is_personal_query=True,
                )

        # 2. Check Procedural Actions ("how to apply", "submit", "portal")
        for idx, pat in enumerate(self.PROCEDURAL_PATTERNS):
            match = pat.search(clean_query)
            if match:
                matched_patterns.append(f"procedural_{idx}")
                matched_keywords.extend(match.group(0).split())
                return IntentClassificationResult(
                    intent=QueryIntent.PROCEDURAL,
                    confidence=0.95,
                    matched_patterns=matched_patterns,
                    matched_keywords=list(set(matched_keywords)),
                    cache_prefix="proc",
                    retrieval_boost_keywords=self.INTENT_RETRIEVAL_BOOSTS[QueryIntent.PROCEDURAL],
                    prompt_directive=self.INTENT_PROMPT_DIRECTIVES[QueryIntent.PROCEDURAL],
                    is_personal_query=False,
                )

        # 3. Check Statutory / Policy Entitlement
        for idx, pat in enumerate(self.ENTITLEMENT_PATTERNS):
            match = pat.search(clean_query)
            if match:
                matched_patterns.append(f"entitlement_{idx}")
                matched_keywords.extend(match.group(0).split())
                return IntentClassificationResult(
                    intent=QueryIntent.POLICY_ENTITLEMENT,
                    confidence=0.90,
                    matched_patterns=matched_patterns,
                    matched_keywords=list(set(matched_keywords)),
                    cache_prefix="entitle",
                    retrieval_boost_keywords=self.INTENT_RETRIEVAL_BOOSTS[QueryIntent.POLICY_ENTITLEMENT],
                    prompt_directive=self.INTENT_PROMPT_DIRECTIVES[QueryIntent.POLICY_ENTITLEMENT],
                    is_personal_query=False,
                )

        # 4. Check Directory / People Lookup
        for idx, pat in enumerate(self.DIRECTORY_PATTERNS):
            match = pat.search(clean_query)
            if match:
                matched_patterns.append(f"directory_{idx}")
                matched_keywords.extend(match.group(0).split())
                return IntentClassificationResult(
                    intent=QueryIntent.DIRECTORY_LOOKUP,
                    confidence=0.90,
                    matched_patterns=matched_patterns,
                    matched_keywords=list(set(matched_keywords)),
                    cache_prefix="dir",
                    retrieval_boost_keywords=self.INTENT_RETRIEVAL_BOOSTS[QueryIntent.DIRECTORY_LOOKUP],
                    prompt_directive=self.INTENT_PROMPT_DIRECTIVES[QueryIntent.DIRECTORY_LOOKUP],
                    is_personal_query=False,
                )

        # 5. Check General Policy Rules
        for idx, pat in enumerate(self.POLICY_GENERAL_PATTERNS):
            match = pat.search(clean_query)
            if match:
                matched_patterns.append(f"policy_{idx}")
                matched_keywords.extend(match.group(0).split())
                return IntentClassificationResult(
                    intent=QueryIntent.POLICY_GENERAL,
                    confidence=0.85,
                    matched_patterns=matched_patterns,
                    matched_keywords=list(set(matched_keywords)),
                    cache_prefix="policy",
                    retrieval_boost_keywords=self.INTENT_RETRIEVAL_BOOSTS[QueryIntent.POLICY_GENERAL],
                    prompt_directive=self.INTENT_PROMPT_DIRECTIVES[QueryIntent.POLICY_GENERAL],
                    is_personal_query=False,
                )

        # Default fallback: General FAQ
        return IntentClassificationResult(
            intent=QueryIntent.GENERAL_FAQ,
            confidence=0.60,
            matched_patterns=["default_faq"],
            matched_keywords=[],
            cache_prefix="faq",
            retrieval_boost_keywords=[],
            prompt_directive=None,
            is_personal_query=False,
        )

    def generate_intent_aware_cache_key(self, base_cache_key: str, query: str) -> str:
        """
        Produce a namespace-isolated cache key combining semantic intent and normalized key.
        
        Example:
        - "how to apply for leaves" -> "proc:how_to_apply_for_leaves"
        - "how many leaves do i have" -> "bal:how_many_leaves_do_i_have"
        """
        result = self.classify(query)
        prefix = result.cache_prefix or "faq"
        clean_base = base_cache_key.strip().lower()
        # Avoid duplicate prefixes
        if clean_base.startswith(f"{prefix}:"):
            return clean_base
        return f"{prefix}:{clean_base}"


# Singleton instance
_intent_classifier: Optional[QueryIntentClassifier] = None


def get_query_intent_classifier() -> QueryIntentClassifier:
    """Get or initialize the global QueryIntentClassifier singleton."""
    global _intent_classifier
    if _intent_classifier is None:
        _intent_classifier = QueryIntentClassifier()
    return _intent_classifier
