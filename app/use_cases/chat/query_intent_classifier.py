"""
Query Intent Disambiguation, Topic Extraction & Semantic Routing Engine.

Classifies user queries into distinct semantic intents and topics to resolve context
collapsing and control caching behavior:
- 10 Intent Categories: GREETING, GENERAL_QA, POLICY_LOOKUP, LIST_REQUEST, PROCEDURE_HOW_TO,
  CONTACT_LOOKUP, ROLE_OR_RESPONSIBILITY, CHANGE_REQUEST, PERSONAL_STATUS, OUT_OF_SCOPE.
- Orthogonal Topic extraction (LEAVE, PROJECT_ROLES, COMPENSATION, etc.).
- Contextual FOLLOW_UP detection.
- CachePolicy enforcement (NO_SHARED_CACHE for PERSONAL_STATUS, SEMANTIC_RESTRICTED for CHANGE_REQUEST).
- Deterministic execution (<0.05ms, zero LLM overhead).
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """Semantic intent classification categories for company bot queries."""
    GREETING = "greeting"
    PERSONAL_STATUS = "personal_status"
    CONTACT_LOOKUP = "contact_lookup"
    CHANGE_REQUEST = "change_request"
    LIST_REQUEST = "list_request"
    PROCEDURE_HOW_TO = "procedure_how_to"
    ROLE_OR_RESPONSIBILITY = "role_or_responsibility"
    POLICY_LOOKUP = "policy_lookup"
    OUT_OF_SCOPE = "out_of_scope"
    GENERAL_QA = "general_qa"

    # Aliases for backward compatibility
    PROCEDURAL = "procedure_how_to"
    PERSONAL_BALANCE = "personal_status"
    POLICY_ENTITLEMENT = "policy_lookup"
    POLICY_GENERAL = "policy_lookup"
    DIRECTORY_LOOKUP = "contact_lookup"
    GENERAL_FAQ = "general_qa"


class QueryTopic(Enum):
    """Subject matter topic extraction for queries."""
    LEAVE = "leave"
    PROJECT_ROLES = "project_roles"
    COMPENSATION = "compensation"
    CONDUCT_AND_CULTURE = "conduct_and_culture"
    ONBOARDING_AND_EXIT = "onboarding_and_exit"
    IT_SUPPORT = "it_support"
    GENERAL = "general"


class DataRequirement(Enum):
    """Data sensitivity and authorization requirement for query fulfillment."""
    PUBLIC_KNOWLEDGE = "public_knowledge"
    USER_SPECIFIC = "user_specific"
    ACTION_REQUIRED = "action_required"


class CachePolicy(Enum):
    """Caching policy dictated by the query's intent and privacy requirement."""
    EXACT_AND_SEMANTIC = "exact_and_semantic"
    SEMANTIC_RESTRICTED = "semantic_restricted"
    NO_SHARED_CACHE = "no_shared_cache"
    NO_CACHE = "no_cache"


@dataclass
class IntentClassificationResult:
    """Detailed result of query intent classification."""
    intent: QueryIntent
    topic: QueryTopic
    cache_policy: CachePolicy
    data_requirement: DataRequirement = DataRequirement.PUBLIC_KNOWLEDGE
    confidence: float = 1.0
    is_follow_up: bool = False
    is_personal_query: bool = False
    matched_patterns: list[str] = field(default_factory=list)
    cache_prefix: str = ""
    prompt_directive: Optional[str] = None
    retrieval_boost_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert classification result to dictionary."""
        return {
            "intent": self.intent.value,
            "topic": self.topic.value,
            "cache_policy": self.cache_policy.value,
            "data_requirement": self.data_requirement.value,
            "confidence": round(self.confidence, 4),
            "is_follow_up": self.is_follow_up,
            "is_personal_query": self.is_personal_query,
            "matched_patterns": self.matched_patterns,
            "cache_prefix": self.cache_prefix,
            "prompt_directive": self.prompt_directive,
            "retrieval_boost_keywords": self.retrieval_boost_keywords,
        }


class QueryIntentClassifier:
    """
    High-speed deterministic classifier that detects query intent, topic,
    and cache policy using ordered regex patterns.
    """

    INTENT_PATTERNS = [
        (
            QueryIntent.GREETING,
            [re.compile(r"^(hi|hello|hey|good morning|good afternoon|good evening|greetings)\b", re.IGNORECASE)],
            "greet",
        ),
        (
            QueryIntent.PERSONAL_STATUS,
            [
                re.compile(r"\b(my|me|mine|i have|i am entitled to)\b.*(?<!my company s\s)(?<!our company s\s)\b(balance|remaining|used|available|entitlement|status|quota)\b", re.IGNORECASE),
                re.compile(r"\bhow many\b.*\b(do i have|have i got|remain|left|can i take)\b", re.IGNORECASE),
                re.compile(r"\bmy\b.*\b(leave balance|leave status|salary|attendance|quota)\b", re.IGNORECASE),
                re.compile(r"\bcheck my\b.*\b(balance|leaves|leave)\b", re.IGNORECASE),
            ],
            "bal",
        ),
        (
            QueryIntent.CONTACT_LOOKUP,
            [
                re.compile(r"\b(who|whom|where)\b.*\b(contact|reach|ask|approach|talk to|call|email)\b", re.IGNORECASE),
                re.compile(r"\b(contact|email|phone number|spoc|hr point of contact)\b", re.IGNORECASE),
                re.compile(r"\bwho is the\b.*\b(manager|lead|director|head|spoc)\b", re.IGNORECASE),
            ],
            "dir",
        ),
        (
            QueryIntent.CHANGE_REQUEST,
            [
                re.compile(r"\b(how\s+(?:can|do)\s+i|how\s+to)\s+(?:change|modify|update|revise|switch|reassign|alter)\b", re.IGNORECASE),
                re.compile(r"\b(change|modify|update|revise|reassign|replace|switch|alter)\s+(?:in|of|my|the)?\s*(?:role|roles|job|project|assignment|policy|shift)\b", re.IGNORECASE),
            ],
            "change",
        ),
        (
            QueryIntent.LIST_REQUEST,
            [
                re.compile(r"\b(list|enumerate|show me all|give me all)\b", re.IGNORECASE),
                re.compile(r"\b(list out|list down|can u list|can you list|please list|list of|types of)\b", re.IGNORECASE),
            ],
            "list",
        ),
        (
            QueryIntent.PROCEDURE_HOW_TO,
            [
                re.compile(r"\bhow do i\b", re.IGNORECASE),
                re.compile(r"\bhow can i\b", re.IGNORECASE),
                re.compile(r"\bsteps (?:to|for)\b", re.IGNORECASE),
                re.compile(r"\bprocess (?:for|to|of)\b", re.IGNORECASE),
                re.compile(r"\bhow to\b", re.IGNORECASE),
                re.compile(r"\bwhere (?:do|can) i\b", re.IGNORECASE),
                re.compile(r"\b(?:is|are)\b.*\b(?:approval required|permission needed)\b", re.IGNORECASE),
            ],
            "proc",
        ),
        (
            QueryIntent.ROLE_OR_RESPONSIBILITY,
            [
                re.compile(r"\b(role|roles|responsibilities|responsibility|ownership|owner|duties)\b", re.IGNORECASE),
                re.compile(r"\b(who is responsible for|who owns)\b", re.IGNORECASE),
            ],
            "role",
        ),
        (
            QueryIntent.POLICY_LOOKUP,
            [
                re.compile(r"\b(policy|policies|rules|eligibility|entitlement|carry forward|encashment|maternity|paternity|sick leave|annual leave|casual leave|wfh|work from home|code of conduct|dress code|probation|notice period|statutory|statutory leave)\b", re.IGNORECASE),
            ],
            "pol",
        ),
        (
            QueryIntent.OUT_OF_SCOPE,
            [
                re.compile(r"\b(write a poem|weather in|tell me a joke|recipe for|capital of)\b", re.IGNORECASE),
            ],
            "out",
        ),
    ]

    TOPIC_PATTERNS = [
        (QueryTopic.LEAVE, [re.compile(r"\b(leave|leaves|pto|vacation|casual leave|annual leave|sick leave|maternity|paternity|bereavement|time off|holiday)\b", re.IGNORECASE)]),
        (QueryTopic.PROJECT_ROLES, [re.compile(r"\b(project|project role|project roles|task lifecycle|task owner|role|roles)\b", re.IGNORECASE)]),
        (QueryTopic.COMPENSATION, [re.compile(r"\b(salary|pay|wages|bonus|pf|provident fund|gratuity|allowance|insurance|benefit)\b", re.IGNORECASE)]),
        (QueryTopic.CONDUCT_AND_CULTURE, [re.compile(r"\b(conduct|culture|harassment|posh|grievance|ethics|disciplinary|misconduct)\b", re.IGNORECASE)]),
        (QueryTopic.ONBOARDING_AND_EXIT, [re.compile(r"\b(onboarding|orientation|joining|probation|notice period|resignation|exit|termination)\b", re.IGNORECASE)]),
        (QueryTopic.IT_SUPPORT, [re.compile(r"\b(laptop|device|vpn|credentials|software|hardware|it support)\b", re.IGNORECASE)]),
    ]

    FOLLOW_UP_PATTERNS = [
        re.compile(r"^(what about|how about|and for|what of|and the)\b", re.IGNORECASE),
        re.compile(r"^(and|also|what else)\b", re.IGNORECASE),
    ]

    INTENT_PROMPT_DIRECTIVES = {
        QueryIntent.PERSONAL_STATUS: (
            "The user is asking about their personal status or leave balance ('How many leaves do I have'). "
            "State the company's standard annual policy entitlement from the documents, and explicitly inform the user "
            "that the bot does not have access to live personal HR balances — they must check the internal HRMS portal or contact People & Culture."
        ),
        QueryIntent.PROCEDURE_HOW_TO: (
            "The user is asking for procedural instructions on how to perform a task. Focus strictly on the "
            "step-by-step workflow, approval requirements, and submission channels described in the documentation."
        ),
        QueryIntent.ROLE_OR_RESPONSIBILITY: (
            "The user is asking about roles, responsibilities, or ownership. Explain documented duties, "
            "ownership principles, and the task lifecycle accurately from the context."
        ),
        QueryIntent.LIST_REQUEST: (
            "The user is asking for an explicit enumeration or list. Enumerate all distinct roles, "
            "policies, or items explicitly mentioned in the context."
        ),
        QueryIntent.CHANGE_REQUEST: (
            "The user is asking how to change or modify an assignment or status. Explain the official "
            "change procedure and required approvals from company documentation."
        ),
        QueryIntent.CONTACT_LOOKUP: (
            "The user is asking whom to contact. Identify the designated department or point of contact."
        ),
    }

    INTENT_RETRIEVAL_BOOSTS = {
        QueryIntent.PERSONAL_STATUS: ["leave", "entitlement", "balance", "policy"],
        QueryIntent.PROCEDURE_HOW_TO: ["apply", "workflow", "process", "procedure", "steps"],
        QueryIntent.ROLE_OR_RESPONSIBILITY: ["role", "responsibilities", "task lifecycle", "owner"],
        QueryIntent.POLICY_LOOKUP: ["policy", "rules", "eligibility", "entitlement"],
        QueryIntent.CONTACT_LOOKUP: ["contact", "spoc", "email", "hr"],
        QueryIntent.LIST_REQUEST: ["list", "roles", "policies"],
        QueryIntent.CHANGE_REQUEST: ["change", "process", "approval"],
    }

    def classify(self, query: str) -> IntentClassificationResult:
        """
        Classify incoming user query into semantic intent, topic, and cache policy.
        """
        if not query or not query.strip():
            return IntentClassificationResult(
                intent=QueryIntent.GENERAL_QA,
                topic=QueryTopic.GENERAL,
                cache_policy=CachePolicy.EXACT_AND_SEMANTIC,
                data_requirement=DataRequirement.PUBLIC_KNOWLEDGE,
                confidence=0.0,
                cache_prefix="faq",
            )

        clean_query = query.strip()
        matched_patterns: list[str] = []

        # 1. Detect Follow-Up
        is_follow_up = any(p.search(clean_query) for p in self.FOLLOW_UP_PATTERNS)

        # 2. Detect Intent
        detected_intent = QueryIntent.GENERAL_QA
        cache_prefix = "faq"
        for intent, patterns, prefix in self.INTENT_PATTERNS:
            for idx, pat in enumerate(patterns):
                if pat.search(clean_query):
                    detected_intent = intent
                    cache_prefix = prefix
                    matched_patterns.append(f"{intent.value}_{idx}")
                    break
            if detected_intent != QueryIntent.GENERAL_QA:
                break

        # 3. Detect Topic
        detected_topic = QueryTopic.GENERAL
        for topic, patterns in self.TOPIC_PATTERNS:
            for pat in patterns:
                if pat.search(clean_query):
                    detected_topic = topic
                    break
            if detected_topic != QueryTopic.GENERAL:
                break

        # 4. Determine Cache Policy and Data Requirement
        if detected_intent == QueryIntent.PERSONAL_STATUS:
            cache_policy = CachePolicy.NO_SHARED_CACHE
            data_requirement = DataRequirement.USER_SPECIFIC
        elif detected_intent == QueryIntent.CHANGE_REQUEST:
            cache_policy = CachePolicy.SEMANTIC_RESTRICTED
            data_requirement = DataRequirement.ACTION_REQUIRED
        elif detected_intent == QueryIntent.LIST_REQUEST:
            cache_policy = CachePolicy.SEMANTIC_RESTRICTED
            data_requirement = DataRequirement.PUBLIC_KNOWLEDGE
        elif detected_intent == QueryIntent.OUT_OF_SCOPE:
            cache_policy = CachePolicy.NO_CACHE
            data_requirement = DataRequirement.PUBLIC_KNOWLEDGE
        else:
            cache_policy = CachePolicy.EXACT_AND_SEMANTIC
            data_requirement = DataRequirement.PUBLIC_KNOWLEDGE

        is_personal = (detected_intent == QueryIntent.PERSONAL_STATUS)

        return IntentClassificationResult(
            intent=detected_intent,
            topic=detected_topic,
            cache_policy=cache_policy,
            data_requirement=data_requirement,
            confidence=0.95 if detected_intent != QueryIntent.GENERAL_QA else 0.60,
            is_follow_up=is_follow_up,
            is_personal_query=is_personal,
            matched_patterns=matched_patterns,
            cache_prefix=cache_prefix,
            prompt_directive=self.INTENT_PROMPT_DIRECTIVES.get(detected_intent),
            retrieval_boost_keywords=self.INTENT_RETRIEVAL_BOOSTS.get(detected_intent, []),
        )

    def generate_intent_aware_cache_key(self, base_cache_key: str, query: str) -> str:
        """
        Produce a namespace-isolated cache key combining prefix and normalized key.
        """
        result = self.classify(query)
        prefix = result.cache_prefix or "faq"
        clean_base = base_cache_key.strip().lower()
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
