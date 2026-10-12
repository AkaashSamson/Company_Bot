"""
Unit Tests for Cache Consistency & 10-Category Intent Disambiguation.

Tests:
1. Exact & canonicalized question matches with zero drift.
2. 10 Intent categories classification (all queries from architecture spec).
3. Intent vs Topic extraction (LEAVE, PROJECT_ROLES, etc.).
4. Contextual follow-up detection.
5. Personal data isolation (PERSONAL_STATUS never enters shared cache).
6. Paraphrase hits for matching intent & topic.
7. Refusal responses are never cached.
8. Invalidation when a document is deleted or updated.
"""

import pytest
from app.core.cache_quality import (
    classify_query_intent,
    check_cache_intent_compatibility,
    calculate_content_token_overlap,
    is_negative_response,
)
from app.infrastructure.cache.quality_aware_cache import QualityAwareCache
from app.use_cases.chat.query_intent_classifier import (
    get_query_intent_classifier,
    QueryIntent,
    QueryTopic,
    CachePolicy,
)
from app.use_cases.chat.query_normalizer import get_query_normalizer


def test_query_normalization_canonical_keys():
    """Verify that conversational rephrasings generate identical deterministic keys."""
    qn = get_query_normalizer()
    q1 = "list the Project Roles"
    q2 = "can u list out the project roles?"
    q3 = "please list the project roles"

    key1 = qn.normalize(q1).cache_key
    key2 = qn.normalize(q2).cache_key
    key3 = qn.normalize(q3).cache_key

    assert key1 == "list_the_project_role"
    assert key2 == "list_the_project_role"
    assert key3 == "list_the_project_role"
    assert key1 == key2 == key3


def test_10_category_intent_and_topic_classification():
    """Verify all 10 intent categories and orthogonal topic extraction from the specification."""
    classifier = get_query_intent_classifier()

    # Query 1: Roles and responsibilities
    r1 = classifier.classify("What are the project roles and responsibilities?")
    assert r1.intent == QueryIntent.ROLE_OR_RESPONSIBILITY
    assert r1.topic == QueryTopic.PROJECT_ROLES
    assert r1.cache_policy == CachePolicy.EXACT_AND_SEMANTIC
    assert r1.is_follow_up is False

    # Query 2: List project roles
    r2 = classifier.classify("Can you list the project roles?")
    assert r2.intent == QueryIntent.LIST_REQUEST
    assert r2.topic == QueryTopic.PROJECT_ROLES

    # Query 3: Change project roles
    r3 = classifier.classify("How do I change project roles?")
    assert r3.intent == QueryIntent.CHANGE_REQUEST
    assert r3.topic == QueryTopic.PROJECT_ROLES
    assert r3.cache_policy == CachePolicy.SEMANTIC_RESTRICTED

    # Query 4: Personal status (leave balance)
    r4 = classifier.classify("How many casual leaves do I have left?")
    assert r4.intent == QueryIntent.PERSONAL_STATUS
    assert r4.topic == QueryTopic.LEAVE
    assert r4.cache_policy == CachePolicy.NO_SHARED_CACHE
    assert r4.is_personal_query is True

    # Query 5: Policy lookup
    r5 = classifier.classify("What is the leave policy?")
    assert r5.intent == QueryIntent.POLICY_LOOKUP
    assert r5.topic == QueryTopic.LEAVE

    # Query 6: Procedure / How-to
    r6 = classifier.classify("How do I apply for leave?")
    assert r6.intent == QueryIntent.PROCEDURE_HOW_TO
    assert r6.topic == QueryTopic.LEAVE

    # Query 7: Contact lookup
    r7 = classifier.classify("Whom should I contact about leave?")
    assert r7.intent == QueryIntent.CONTACT_LOOKUP
    assert r7.topic == QueryTopic.LEAVE

    # Query 8: Greeting
    r8 = classifier.classify("Good morning, how are you?")
    assert r8.intent == QueryIntent.GREETING

    # Query 9: Out of scope
    r9 = classifier.classify("Write a poem about the ocean")
    assert r9.intent == QueryIntent.OUT_OF_SCOPE
    assert r9.cache_policy == CachePolicy.NO_CACHE

    # Query 10: Follow-up detection
    r10 = classifier.classify("What about casual leave?")
    assert r10.is_follow_up is True
    assert r10.topic == QueryTopic.LEAVE


def test_intent_isolation_between_similar_questions():
    """Verify that similar questions with different intents reject semantic cache reuse."""
    q_roles = "What are the project roles and responsibilities?"
    q_list = "Can you list the project roles?"
    q_change = "How do I change project roles?"
    q_personal = "How many casual leaves do I have?"

    # Role responsibilities vs List roles -> MISMATCH
    assert check_cache_intent_compatibility(q_roles, q_list) is False
    # Role responsibilities vs Change roles -> MISMATCH
    assert check_cache_intent_compatibility(q_roles, q_change) is False
    # List roles vs Change roles -> MISMATCH
    assert check_cache_intent_compatibility(q_list, q_change) is False
    # Personal status is NEVER compatible with shared cache
    assert check_cache_intent_compatibility(q_personal, "What is the leave policy?") is False

    # Paraphrased questions with identical intent and topic -> MATCH
    assert check_cache_intent_compatibility(q_list, "Can you list out the project roles?") is True


def test_personal_status_never_stored_or_read_from_shared_cache():
    """Verify that personal status queries (NO_SHARED_CACHE) bypass shared cache entirely."""
    cache = QualityAwareCache(max_entries=10)
    personal_query = "How many casual leaves do I have left?"
    personal_answer = "You have 5 casual leaves remaining in the HR system."

    # Storing personal status must be rejected
    stored = cache.put(
        cache_key="my_leaves_key",
        original_query=personal_query,
        response=personal_answer,
        confidence=0.99,
        citations=[{"source": "hr_portal.docx"}],
    )
    assert stored is False
    # Lookup must also be bypassed (returns None)
    assert cache.get(personal_query) is None


def test_refusal_response_never_cached():
    """Verify that refusal / negative answers are blocked from caching."""
    refusal = "I could not find a list of project roles in the available document context."
    assert is_negative_response(refusal) is True

    cache = QualityAwareCache(max_entries=10)
    stored = cache.put(
        cache_key="test_refusal",
        original_query="list roles",
        response=refusal,
        confidence=0.95,
        citations=[{"source": "test.docx"}],
    )
    assert stored is False
    assert cache.get("test_refusal") is None


def test_document_invalidation():
    """Verify that invalidating a document purges all dependent cache entries."""
    cache = QualityAwareCache(max_entries=10)
    cache.put(
        cache_key="roles_key",
        original_query="what are the project roles",
        response="The roles are developer and manager.",
        confidence=0.95,
        citations=[{"source": "policy.docx", "document_id": "doc_123"}],
        document_ids=["doc_123"],
    )

    # Entry exists
    entry = cache.get("roles_key")
    assert entry is not None
    assert "developer" in entry.response

    # Invalidate document doc_123
    evicted_count = cache.invalidate_document("doc_123")
    assert evicted_count >= 1

    # Entry is gone
    assert cache.get("roles_key") is None
