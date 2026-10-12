"""
Unit Tests for Query Intent Disambiguation & Semantic Routing (Task AB-3.4)

Validates:
- Disambiguation between "How many leaves do I have" (PERSONAL_BALANCE) and
  "How to apply for leaves" (PROCEDURAL).
- Cache key namespace isolation (e.g. 'bal:...' vs 'proc:...').
- Policy entitlement vs general policy rule differentiation.
- Prompt directives guidance for HRMS balance clarification.
- Retrieval keyword booster population.
- Edge cases (empty query, case insensitivity, singleton behavior).
"""

import pytest
from app.use_cases.chat.query_intent_classifier import (
    IntentClassificationResult,
    QueryIntent,
    QueryIntentClassifier,
    get_query_intent_classifier,
)


class TestQueryIntentClassifier:
    """Test suite for QueryIntentClassifier."""

    @pytest.fixture
    def classifier(self):
        """Create fresh classifier instance."""
        return QueryIntentClassifier()

    def test_how_many_leaves_do_i_have_is_personal_balance(self, classifier):
        """'How many leaves do I have' is strictly classified as PERSONAL_BALANCE."""
        result = classifier.classify("How many leaves do I have?")

        assert result.intent == QueryIntent.PERSONAL_BALANCE
        assert result.is_personal_query is True
        assert result.cache_prefix == "bal"
        assert result.confidence >= 0.90
        assert "entitlement" in result.retrieval_boost_keywords
        assert "HRMS" in (result.prompt_directive or "")

    def test_how_to_apply_for_leaves_is_procedural(self, classifier):
        """'How to apply for leaves' is strictly classified as PROCEDURAL."""
        result = classifier.classify("How to apply for leaves?")

        assert result.intent == QueryIntent.PROCEDURAL
        assert result.is_personal_query is False
        assert result.cache_prefix == "proc"
        assert result.confidence >= 0.90
        assert "apply" in result.retrieval_boost_keywords
        assert "workflow" in (result.prompt_directive or "").lower()

    def test_cache_keys_are_strictly_isolated(self, classifier):
        """Cache keys for 'how many' and 'how to apply' do not collide."""
        key_balance = classifier.generate_intent_aware_cache_key(
            base_cache_key="leaves",
            query="How many leaves do I have?",
        )
        key_procedural = classifier.generate_intent_aware_cache_key(
            base_cache_key="leaves",
            query="How to apply for leaves?",
        )

        assert key_balance == "bal:leaves"
        assert key_procedural == "proc:leaves"
        assert key_balance != key_procedural

    @pytest.mark.parametrize(
        "query,expected_intent,is_personal",
        [
            ("how many leaves do i have", QueryIntent.PERSONAL_BALANCE, True),
            ("check my leave balance", QueryIntent.PERSONAL_BALANCE, True),
            ("what is my remaining leaves count?", QueryIntent.PERSONAL_BALANCE, True),
            ("how many sick leaves do i have left", QueryIntent.PERSONAL_BALANCE, True),
            ("how to apply for leave", QueryIntent.PROCEDURAL, False),
            ("where do i submit my leave request", QueryIntent.PROCEDURAL, False),
            ("steps to apply for annual vacation", QueryIntent.PROCEDURAL, False),
            ("is manager approval required for leave?", QueryIntent.PROCEDURAL, False),
            ("how many annual leave days are provided per calendar year?", QueryIntent.POLICY_ENTITLEMENT, False),
            ("statutory leave days for regular employees", QueryIntent.POLICY_ENTITLEMENT, False),
            ("can i carry forward unused annual leaves?", QueryIntent.POLICY_GENERAL, False),
            ("what is the work from home policy?", QueryIntent.POLICY_GENERAL, False),
            ("code of conduct and dress code rules", QueryIntent.POLICY_GENERAL, False),
            ("who is the manager of engineering?", QueryIntent.DIRECTORY_LOOKUP, False),
            ("contact for HR support team", QueryIntent.DIRECTORY_LOOKUP, False),
        ],
    )
    def test_intent_categorization_matrix(self, classifier, query, expected_intent, is_personal):
        """Verify intent categorization across diverse employee questions."""
        result = classifier.classify(query)
        assert result.intent == expected_intent
        assert result.is_personal_query == is_personal

    def test_empty_query_fallback(self, classifier):
        """Empty or whitespace queries return GENERAL_FAQ fallback."""
        result = classifier.classify("   ")
        assert result.intent == QueryIntent.GENERAL_FAQ
        assert result.confidence == 0.0
        assert result.cache_prefix == "faq"

    def test_prompt_directive_for_personal_balance_clarification(self, classifier):
        """Personal balance queries contain specific HRMS clarification prompt directives."""
        result = classifier.classify("What is my casual leave balance?")
        assert result.prompt_directive is not None
        assert "HRMS portal" in result.prompt_directive
        assert "standard annual" in result.prompt_directive.lower()

    def test_to_dict_serialization(self, classifier):
        """to_dict produces clean serializable dictionary."""
        result = classifier.classify("How to apply for sick leave")
        data = result.to_dict()

        assert data["intent"] in ("procedure_how_to", "procedural")
        assert data["cache_prefix"] == "proc"
        assert isinstance(data["confidence"], float)
        assert isinstance(data["retrieval_boost_keywords"], list)

    def test_singleton_accessor(self):
        """get_query_intent_classifier returns persistent singleton."""
        inst1 = get_query_intent_classifier()
        inst2 = get_query_intent_classifier()
        assert inst1 is inst2
        assert isinstance(inst1, QueryIntentClassifier)
