"""
Tests for Query Normalizer (AB-3, AB-7)

Tests query normalization with domain vocabulary,
typo correction, and cache key generation.
"""

import pytest
from app.use_cases.chat.query_normalizer import (
    QueryNormalizer,
    get_query_normalizer,
    DOMAIN_VOCABULARY,
    TYPO_CORRECTIONS,
)


class TestQueryNormalizer:
    """Test suite for QueryNormalizer."""
    
    @pytest.fixture
    def normalizer(self):
        """Create a normalizer instance."""
        return QueryNormalizer(
            enable_typo_correction=True,
            enable_vocabulary_mapping=True,
            enable_lemmatization=False,
        )
    
    @pytest.fixture
    def normalizer_no_vocab(self):
        """Create a normalizer without vocabulary mapping."""
        return QueryNormalizer(
            enable_typo_correction=False,
            enable_vocabulary_mapping=False,
            enable_lemmatization=False,
        )
    
    def test_empty_query(self, normalizer):
        """Test handling of empty query."""
        result = normalizer.normalize("")
        
        assert result.normalized_query == ""
        assert result.cache_key == "empty_query"
        assert result.was_modified is False
    
    def test_whitespace_normalization(self, normalizer):
        """Test whitespace normalization."""
        result = normalizer.normalize("  multiple   spaces   here  ")
        
        assert result.normalized_query == "multiple spaces here"
        assert result.was_modified is True
    
    def test_case_normalization(self, normalizer):
        """Test case normalization to lowercase."""
        result = normalizer.normalize("HELLO World")
        
        assert result.normalized_query == "hello world"
    
    def test_domain_vocabulary_mapping(self, normalizer):
        """Test domain vocabulary mapping."""
        result = normalizer.normalize("How many vacation days do I have?")
        
        # "vacation days" should map to "annual leave"
        assert "annual leave" in result.normalized_query
        assert len(result.corrections_made) > 0
    
    def test_vocabulary_leave_variations(self, normalizer):
        """Test various leave-related mappings."""
        test_cases = [
            ("casual leave policy", "casual leave"),
            ("sick leave balance", "sick leave"),
        ]
        
        for query, expected in test_cases:
            result = normalizer.normalize(query)
            assert expected in result.normalized_query, f"Failed for: {query}"
    
    def test_vocabulary_compensation(self, normalizer):
        """Test compensation vocabulary mapping."""
        result = normalizer.normalize("what is my salary and bonus?")
        
        assert "salary" in result.normalized_query
        assert "bonus" in result.normalized_query
    
    def test_vocabulary_policy(self, normalizer):
        """Test policy vocabulary mapping."""
        result = normalizer.normalize("company policies and handbook")
        
        assert "policy" in result.normalized_query
        assert "handbook" in result.normalized_query
    
    def test_typo_correction(self, normalizer):
        """Test typo correction."""
        # Test known typos
        result = normalizer.normalize("what is myleve policy?")
        
        # "leeve" should be corrected to "leave"
        assert "leave" in result.normalized_query
    
    def test_typo_correction_salary(self, normalizer):
        """Test typo correction for salary."""
        result = normalizer.normalize("my slary information")
        
        assert "salary" in result.normalized_query
    
    def test_no_changes_for_clean_query(self, normalizer):
        """Test clean queries aren't modified unnecessarily."""
        result = normalizer.normalize("annual leave policy")
        
        # "annual leave policy" is already normalized, so was_modified should be False
        # The vocabulary mapping doesn't change already-correct terms
        assert result.normalized_query == "annual leave policy"
    
    def test_cache_key_generation(self, normalizer):
        """Test deterministic cache key generation."""
        result1 = normalizer.normalize("What is annual leave?")
        result2 = normalizer.normalize("what is annual leave?")
        
        # Same query should generate same key despite case difference
        assert result1.cache_key == result2.cache_key
    
    def test_cache_key_different_queries(self, normalizer):
        """Test different queries generate different keys."""
        result1 = normalizer.normalize("annual leave")
        result2 = normalizer.normalize("sick leave")
        
        assert result1.cache_key != result2.cache_key
    
    def test_semantic_equivalence(self, normalizer):
        """Test semantic equivalence detection."""
        # Two identical queries should be equivalent
        query1 = "annual leave policy"
        query2 = "annual leave policy"
        
        assert normalizer.is_semantically_equivalent(query1, query2)
        
        # Queries with same terms in different order
        query3 = "leave annual"
        query4 = "annual leave"
        assert normalizer.is_semantically_equivalent(query3, query4)
    
    def test_semantic_inequivalence(self, normalizer):
        """Test non-equivalent queries."""
        query1 = "annual leave policy"
        query2 = "sick leave policy"
        
        assert not normalizer.is_semantically_equivalent(query1, query2)
    
    def test_disabled_vocabulary_mapping(self, normalizer_no_vocab):
        """Test with vocabulary mapping disabled."""
        result = normalizer_no_vocab.normalize("vacation days")
        
        # Should NOT map to annual leave when disabled
        assert "annual leave" not in result.normalized_query
    
    def test_special_characters_removed(self, normalizer):
        """Test special characters are removed from cache key."""
        result = normalizer.normalize("What is #annual leave?!")
        
        # Special chars should be removed from cache key
        assert "#" not in result.cache_key
        assert "!" not in result.cache_key
    
    def test_unicode_normalization(self, normalizer):
        """Test Unicode normalization."""
        # Test with accented characters
        result = normalizer.normalize("café")
        
        assert result.normalized_query is not None
    
    def test_cache_key_length_limit(self, normalizer):
        """Test cache key length is limited."""
        long_query = "a " * 150  # Very long query
        result = normalizer.normalize(long_query)
        
        # Cache key should be limited
        assert len(result.cache_key) <= 200


class TestDomainVocabulary:
    """Test domain vocabulary coverage."""
    
    def test_vocabulary_not_empty(self):
        """Verify vocabulary is populated."""
        assert len(DOMAIN_VOCABULARY) > 0
    
    def test_common_hr_terms(self):
        """Test common HR terms are in vocabulary."""
        # Check some expected terms
        assert "leave" in DOMAIN_VOCABULARY.values()
        assert "salary" in DOMAIN_VOCABULARY.values()
        assert "bonus" in DOMAIN_VOCABULARY.values()


class TestTypoCorrections:
    """Test typo corrections."""
    
    def test_typo_dict_not_empty(self):
        """Verify typo corrections are populated."""
        assert len(TYPO_CORRECTIONS) > 0
    
    def test_typo_to_correct_mapping(self):
        """Test typo to correct word mapping."""
        # "leve" should map to "leave"
        assert TYPO_CORRECTIONS.get("leve") == "leave"


class TestSingleton:
    """Test singleton pattern."""
    
    def test_get_query_normalizer(self):
        """Test getting singleton normalizer."""
        n1 = get_query_normalizer()
        n2 = get_query_normalizer()
        
        assert n1 is n2


class TestWordBoundaryFixing:
    """Test suite for word boundary and conjoined word fixing (AB-3.1)."""

    @pytest.fixture
    def normalizer(self):
        return QueryNormalizer(enable_word_boundary=True)

    def test_conjoined_domain_words(self, normalizer):
        """Test splitting conjoined words like 'leavesavailable'."""
        result = normalizer.normalize("what are the leavesavailable?")
        # leavesavailable should be split to leaves available -> leave available
        assert "leave available" in result.normalized_query or "leaves available" in result.normalized_query
        assert any("word_boundary" in c for c in result.corrections_made)

    def test_camel_case_splitting(self, normalizer):
        """Test splitting camelCase like 'leavePolicy'."""
        result = normalizer.normalize("check our leavePolicy")
        assert "leave" in result.normalized_query
        assert "policy" in result.normalized_query

    def test_alphanumeric_boundary(self, normalizer):
        """Test splitting letter-number boundary like 'leave2026'."""
        result = normalizer.normalize("leave2026 guidelines")
        assert "leave 2026" in result.normalized_query

    def test_preserve_unbroken_concepts(self, normalizer):
        """Test that single concepts like 'handbook' are not split into 'hand book'."""
        result = normalizer.normalize("employee handbook")
        assert "handbook" in result.normalized_query

    def test_dp_multi_word_splitting(self, normalizer):
        """Test dynamic programming splitting of multi-word conjoined tokens like 'howareyou'."""
        res1 = normalizer.normalize("howareyou")
        assert "how" in res1.normalized_query
        assert any("word_boundary: howareyou -> how are you" in c for c in res1.corrections_made)

        res2 = normalizer.normalize("whatisleavepolicy")
        assert "leave" in res2.normalized_query
        assert "policy" in res2.normalized_query
        assert any("what is leave policy" in c for c in res2.corrections_made)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])