"""
Tests for Quality-Aware Cache (AB-4, AB-7)

Tests the quality-aware semantic cache with LRU eviction,
TTL support, and confidence-based caching.
"""

import time
import pytest
from app.infrastructure.cache.quality_aware_cache import (
    QualityAwareCache,
    CacheEntrySource,
)


class TestQualityAwareCache:
    """Test suite for QualityAwareCache."""
    
    @pytest.fixture
    def cache(self):
        """Create a test cache instance."""
        return QualityAwareCache(
            max_entries=10,
            ttl_seconds=2,  # Short TTL for testing
            min_confidence_threshold=0.6,
        )
    
    def test_cache_miss(self, cache):
        """Test cache miss returns None."""
        result = cache.get("nonexistent_key")
        assert result is None
    
    def test_cache_put_rejects_low_confidence(self, cache):
        """Test that low confidence entries are rejected."""
        result = cache.put(
            cache_key="test_key",
            original_query="test query",
            response="test response",
            confidence=0.3,  # Below threshold
            source=CacheEntrySource.RAG_GENERATED,
        )
        assert result is False
        
        # Verify nothing was cached
        assert cache.get("test_key") is None
    
    def test_cache_put_accepts_high_confidence(self, cache):
        """Test that high confidence entries are cached."""
        result = cache.put(
            cache_key="test_key",
            original_query="test query",
            response="test response",
            confidence=0.8,  # Above threshold
            source=CacheEntrySource.RAG_GENERATED,
            evidence_count=3,
        )
        assert result is True
        
        # Verify entry was cached
        entry = cache.get("test_key")
        assert entry is not None
        assert entry.response == "test response"
        assert entry.confidence == 0.8
    
    def test_cache_lru_eviction(self, cache):
        """Test LRU eviction when max entries reached."""
        # Fill cache to max (10 entries)
        for i in range(10):
            cache.put(
                cache_key=f"key_{i}",
                original_query=f"query_{i}",
                response=f"response_{i}",
                confidence=0.9,
                source=CacheEntrySource.RAG_GENERATED,
            )
        
        # Verify all entries exist
        for i in range(10):
            assert cache.get(f"key_{i}") is not None
        
        # Add one more - should evict oldest (key_0)
        cache.put(
            cache_key="key_10",
            original_query="query_10",
            response="response_10",
            confidence=0.9,
            source=CacheEntrySource.RAG_GENERATED,
        )
        
        # key_0 should be evicted
        assert cache.get("key_0") is None
        # key_1 through key_10 should exist
        for i in range(1, 11):
            assert cache.get(f"key_{i}") is not None
    
    def test_cache_ttl_expiry(self, cache):
        """Test TTL-based expiration."""
        cache.put(
            cache_key="expiring_key",
            original_query="test query",
            response="test response",
            confidence=0.9,
            source=CacheEntrySource.RAG_GENERATED,
        )
        
        # Should exist immediately
        assert cache.get("expiring_key") is not None
        
        # Wait for TTL to expire
        time.sleep(2.5)
        
        # Should be expired now
        assert cache.get("expiring_key") is None
    
    def test_cache_stats(self, cache):
        """Test cache statistics tracking."""
        # Add entries
        cache.put(
            cache_key="key1",
            original_query="query1",
            response="response1",
            confidence=0.9,
            source=CacheEntrySource.RAG_GENERATED,
        )
        
        cache.put(
            cache_key="key2",
            original_query="query2",
            response="response2",
            confidence=0.3,  # Rejected
            source=CacheEntrySource.RAG_GENERATED,
        )
        
        # Hit and miss
        cache.get("key1")  # Hit
        cache.get("nonexistent")  # Miss
        
        stats = cache.get_stats()
        
        assert stats["writes"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["rejected_low_confidence"] == 1
        assert stats["current_entries"] == 1
    
    def test_cache_invalidation(self, cache):
        """Test cache entry invalidation."""
        cache.put(
            cache_key="key1",
            original_query="query1",
            response="response1",
            confidence=0.9,
            source=CacheEntrySource.RAG_GENERATED,
        )
        
        assert cache.get("key1") is not None
        
        # Invalidate
        result = cache.invalidate("key1")
        assert result is True
        
        assert cache.get("key1") is None
    
    def test_cache_clear(self, cache):
        """Test clearing all cache entries."""
        # Add entries
        for i in range(5):
            cache.put(
                cache_key=f"key_{i}",
                original_query=f"query_{i}",
                response=f"response_{i}",
                confidence=0.9,
                source=CacheEntrySource.RAG_GENERATED,
            )
        
        assert len(cache.get_all_entries()) == 5
        
        # Clear
        cache.clear()
        
        assert len(cache.get_all_entries()) == 0
    
    def test_cache_metadata(self, cache):
        """Test storing metadata with cache entries."""
        metadata = {"model": "claude-3.5-sonnet", "temperature": 0.7}
        
        cache.put(
            cache_key="key1",
            original_query="query1",
            response="response1",
            confidence=0.9,
            source=CacheEntrySource.RAG_GENERATED,
            model="claude-3.5-sonnet",
            citations=[{"source": "doc1", "text": "..."}],
            metadata=metadata,
        )
        
        entry = cache.get("key1")
        assert entry is not None
        assert entry.model == "claude-3.5-sonnet"
        assert len(entry.citations) == 1
        assert entry.metadata["temperature"] == 0.7


class TestCacheEntrySource:
    """Test CacheEntrySource enum."""
    
    def test_all_sources_defined(self):
        """Verify all cache sources are defined."""
        sources = [
            CacheEntrySource.RAG_GENERATED,
            CacheEntrySource.FAQ_MATCHED,
            CacheEntrySource.LLM_CACHED,
            CacheEntrySource.SEMANTIC_CACHE,
            CacheEntrySource.QUALITY_GATED,
        ]
        
        assert len(sources) == 5
    
    def test_source_values(self):
        """Verify source enum values."""
        assert CacheEntrySource.RAG_GENERATED.value == "rag_generated"
        assert CacheEntrySource.FAQ_MATCHED.value == "faq_matched"
        assert CacheEntrySource.LLM_CACHED.value == "llm_cached"
        assert CacheEntrySource.SEMANTIC_CACHE.value == "semantic_cache"


class TestQualityAwareCacheComponents:
    """Test suite for Task AB-4 specific components."""

    def test_cache_entry_metadata(self):
        """Test CacheEntryMetadata creation and dictionary conversion."""
        from app.infrastructure.cache.quality_aware_cache import (
            CacheEntryMetadata,
            QualityGateDecision,
        )

        meta = CacheEntryMetadata(
            source=CacheEntrySource.QUALITY_GATED,
            confidence=0.88,
            evidence_count=2,
            evidence_distances=[0.42, 0.55],
            model="gpt-4o",
            evaluation_decision=QualityGateDecision.PASS,
            quality_metrics={"accuracy": 5, "grounding": 5},
            extra={"session_id": "sess_123"},
        )

        assert meta.confidence == 0.88
        assert meta["session_id"] == "sess_123"
        assert meta.get("model") == "gpt-4o"
        assert "accuracy" not in meta  # In quality_metrics

        d = meta.to_dict()
        assert d["confidence"] == 0.88
        assert d["source"] == "quality_gated"
        assert d["evaluation_decision"] == "PASS"

        restored = CacheEntryMetadata.from_dict(d)
        assert restored.confidence == 0.88
        assert restored.source == CacheEntrySource.QUALITY_GATED
        assert restored.evaluation_decision == QualityGateDecision.PASS

    def test_quality_aware_cache_entry(self):
        """Test QualityAwareCacheEntry initialization and property delegation."""
        from app.infrastructure.cache.quality_aware_cache import (
            QualityAwareCacheEntry,
            CacheEntryMetadata,
        )

        entry = QualityAwareCacheEntry(
            cache_key="hash_abc",
            original_query="What is the leave policy?",
            response="You get 18 annual leaves.",
            confidence=0.92,
            source=CacheEntrySource.QUALITY_GATED,
            evidence_count=2,
            evidence_distances=[0.35, 0.48],
            model="claude-3-5-sonnet",
            citations=[{"document": "handbook.docx", "section": "Leaves"}],
        )

        assert entry.cache_key == "hash_abc"
        assert entry.confidence == 0.92
        assert entry.source == CacheEntrySource.QUALITY_GATED
        assert entry.evidence_count == 2
        assert entry.model == "claude-3-5-sonnet"
        assert not entry.is_expired(ttl_seconds=100)

        entry.update_access()
        assert entry.access_count == 1

        d = entry.to_dict()
        assert d["cache_key"] == "hash_abc"
        assert d["confidence"] == 0.92

        from_dict_entry = QualityAwareCacheEntry.from_dict(d)
        assert from_dict_entry.original_query == "What is the leave policy?"
        assert from_dict_entry.confidence == 0.92

    def test_in_memory_quality_aware_cache_alias(self):
        """Test InMemoryQualityAwareCache works identically to QualityAwareCache."""
        from app.infrastructure.cache.quality_aware_cache import (
            InMemoryQualityAwareCache,
            QualityAwareCache,
        )

        assert InMemoryQualityAwareCache is QualityAwareCache
        cache = InMemoryQualityAwareCache(max_entries=5, min_confidence_threshold=0.7)
        assert cache.min_confidence_threshold == 0.7


class TestCacheQualityValidator:
    """Test suite for CacheQualityValidator according to C.R.E.A.T.E. rules."""

    def test_validate_empty_response_fails(self):
        from app.infrastructure.cache.quality_aware_cache import (
            CacheQualityValidator,
            QualityGateDecision,
        )

        validator = CacheQualityValidator()
        res = validator.validate(query="test", response="")
        assert res.is_valid is False
        assert res.decision == QualityGateDecision.FAIL
        assert "Empty" in res.reason

    def test_validate_low_confidence_fails(self):
        from app.infrastructure.cache.quality_aware_cache import (
            CacheQualityValidator,
            QualityGateDecision,
        )

        validator = CacheQualityValidator(min_confidence_threshold=0.75)
        res = validator.validate(query="test", response="Some answer", confidence=0.70)
        assert res.is_valid is False
        assert res.decision == QualityGateDecision.FAIL
        assert "Confidence" in res.reason

    def test_validate_create_distance_grading(self):
        """Test C.R.E.A.T.E. distance classification thresholds."""
        from app.infrastructure.cache.quality_aware_cache import (
            CacheQualityValidator,
            EvidenceQualityLevel,
            QualityGateDecision,
        )

        validator = CacheQualityValidator()

        assert validator.classify_distance(0.45) == EvidenceQualityLevel.STRONG
        assert validator.classify_distance(0.65) == EvidenceQualityLevel.BORDERLINE
        assert validator.classify_distance(0.75) == EvidenceQualityLevel.WEAK
        assert validator.classify_distance(0.89) == EvidenceQualityLevel.INVALID

        # Distance >= 0.85 must FAIL the quality gate
        invalid_res = validator.validate(
            query="test",
            response="A valid answer text",
            confidence=0.90,
            evidence_distances=[0.89, 0.92],
        )
        assert invalid_res.is_valid is False
        assert invalid_res.decision == QualityGateDecision.FAIL

        # Distance < 0.60 must PASS
        strong_res = validator.validate(
            query="test",
            response="A valid answer text",
            confidence=0.90,
            evidence_distances=[0.42],
        )
        assert strong_res.is_valid is True
        assert strong_res.decision == QualityGateDecision.PASS

    def test_validate_lexical_grounding_thresholds(self):
        """Test lexical grounding target >= 0.20."""
        from app.infrastructure.cache.quality_aware_cache import (
            CacheQualityValidator,
            QualityGateDecision,
        )

        validator = CacheQualityValidator(allow_review=False)
        fail_res = validator.validate(
            query="test",
            response="answer",
            confidence=0.85,
            lexical_grounding=0.10,  # Below target 0.20
        )
        assert fail_res.is_valid is False
        assert fail_res.decision == QualityGateDecision.FAIL

        # With allow_review=True, it should produce REVIEW and allow caching
        review_validator = CacheQualityValidator(allow_review=True)
        review_res = review_validator.validate(
            query="test",
            response="answer",
            confidence=0.85,
            lexical_grounding=0.15,
        )
        assert review_res.is_valid is True
        assert review_res.decision == QualityGateDecision.REVIEW

    def test_cache_integration_with_validator(self):
        """Test that InMemoryQualityAwareCache rejects entries failing validator."""
        from app.infrastructure.cache.quality_aware_cache import (
            InMemoryQualityAwareCache,
            CacheQualityValidator,
        )

        validator = CacheQualityValidator(min_confidence_threshold=0.70)
        cache = InMemoryQualityAwareCache(validator=validator)

        # Invalid distance (0.90 >= 0.85) rejected
        saved = cache.put(
            cache_key="bad_dist",
            original_query="What?",
            response="An answer",
            confidence=0.85,
            evidence_distances=[0.90],
        )
        assert saved is False
        assert cache.get("bad_dist") is None
        assert cache.get_stats()["rejected_quality_gate"] == 1

        # Valid distance accepted
        saved = cache.put(
            cache_key="good_dist",
            original_query="What?",
            response="An answer",
            confidence=0.85,
            evidence_distances=[0.50],
        )
        assert saved is True
        assert cache.get("good_dist") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])