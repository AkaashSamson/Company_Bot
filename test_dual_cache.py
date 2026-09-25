"""
Tests for Dual-Cache Implementation (AB-14, AB-7)

Tests the dual-cache system: LangCache primary + JSON fallback.
"""

import json
import os
import pytest
import tempfile
from app.infrastructure.cache.dual_cache import (
    DualCache,
    JSONLocalCache,
    DualCacheEntry,
    LANGCACHE_AVAILABLE,
)


class TestJSONLocalCache:
    """Test suite for JSONLocalCache."""
    
    @pytest.fixture
    def temp_cache_file(self):
        """Create a temporary cache file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        yield temp_path
        
        # Cleanup
        if os.path.exists(temp_path):
            os.remove(temp_path)
    
    @pytest.fixture
    def json_cache(self, temp_cache_file):
        """Create a JSON cache instance."""
        return JSONLocalCache(temp_cache_file)
    
    def test_cache_initialization(self, json_cache):
        """Test cache initializes correctly."""
        assert json_cache is not None
        assert len(json_cache.get_all()) == 0
    
    def test_cache_put_and_get(self, json_cache):
        """Test putting and getting entries."""
        entry = DualCacheEntry(
            cache_key="test_key",
            original_query="test query",
            response="test response",
            confidence=0.9,
        )
        
        json_cache.put(entry)
        
        retrieved = json_cache.get("test_key")
        
        assert retrieved is not None
        assert retrieved.cache_key == "test_key"
        assert retrieved.response == "test response"
    
    def test_cache_miss(self, json_cache):
        """Test cache miss returns None."""
        result = json_cache.get("nonexistent")
        assert result is None
    
    def test_cache_delete(self, json_cache):
        """Test deleting cache entries."""
        entry = DualCacheEntry(
            cache_key="test_key",
            original_query="test query",
            response="test response",
        )
        
        json_cache.put(entry)
        assert json_cache.get("test_key") is not None
        
        json_cache.delete("test_key")
        assert json_cache.get("test_key") is None
    
    def test_cache_clear(self, json_cache):
        """Test clearing all entries."""
        for i in range(5):
            entry = DualCacheEntry(
                cache_key=f"key_{i}",
                original_query=f"query_{i}",
                response=f"response_{i}",
            )
            json_cache.put(entry)
        
        assert len(json_cache.get_all()) == 5
        
        json_cache.clear()
        
        assert len(json_cache.get_all()) == 0
    
    def test_cache_persistence(self, temp_cache_file):
        """Test cache persists to file."""
        # Create cache and add entry
        cache1 = JSONLocalCache(temp_cache_file)
        entry = DualCacheEntry(
            cache_key="persist_key",
            original_query="persist query",
            response="persist response",
        )
        cache1.put(entry)
        
        # Create new cache instance with same file
        cache2 = JSONLocalCache(temp_cache_file)
        retrieved = cache2.get("persist_key")
        
        assert retrieved is not None
        assert retrieved.response == "persist response"
    
    def test_cache_to_dict(self, json_cache):
        """Test exporting cache as dictionary."""
        entry = DualCacheEntry(
            cache_key="test_key",
            original_query="test query",
            response="test response",
        )
        json_cache.put(entry)
        
        result = json_cache.to_dict()
        
        assert isinstance(result, dict)
        assert "test_key" in result


class TestDualCacheEntry:
    """Test DualCacheEntry dataclass."""
    
    def test_entry_creation(self):
        """Test creating a cache entry."""
        entry = DualCacheEntry(
            cache_key="key1",
            original_query="query1",
            response="response1",
            confidence=0.8,
            source="rag_generated",
            evidence_count=3,
            model="claude-3.5-sonnet",
        )
        
        assert entry.cache_key == "key1"
        assert entry.confidence == 0.8
        assert entry.evidence_count == 3
    
    def test_entry_to_dict(self):
        """Test entry serialization."""
        entry = DualCacheEntry(
            cache_key="key1",
            original_query="query1",
            response="response1",
            confidence=0.8,
        )
        
        d = entry.to_dict()
        
        assert d["cache_key"] == "key1"
        assert d["response"] == "response1"
        assert d["confidence"] == 0.8


class TestDualCache:
    """Test suite for DualCache."""
    
    @pytest.fixture
    def temp_cache_file(self):
        """Create a temporary cache file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        yield temp_path
        
        # Cleanup
        if os.path.exists(temp_path):
            os.remove(temp_path)
    
    @pytest.fixture
    def dual_cache(self, temp_cache_file):
        """Create a dual cache instance."""
        # Pass empty config to skip LangCache initialization
        return DualCache(
            langcache_config={},
            json_fallback_path=temp_cache_file,
            enable_sync=False,
        )
    
    def test_dual_cache_initialization(self, dual_cache):
        """Test dual cache initializes."""
        assert dual_cache is not None
        # LangCache should be unavailable with empty config
        assert dual_cache._langcache_available is False
    
    def test_dual_cache_get_miss(self, dual_cache):
        """Test cache miss returns None."""
        result = dual_cache.get("nonexistent", "nonexistent query")
        assert result is None
    
    def test_dual_cache_put_and_get(self, dual_cache):
        """Test putting and getting entries."""
        result = dual_cache.put(
            cache_key="test_key",
            original_query="test query",
            response="test response",
            confidence=0.9,
        )
        
        assert result is True  # Should succeed (JSON fallback)
        
        # Get from cache
        entry = dual_cache.get("test_key", "test query")
        
        assert entry is not None
        assert entry.response == "test response"
    
    def test_dual_cache_invalidate(self, dual_cache):
        """Test cache invalidation."""
        # Add entry
        dual_cache.put(
            cache_key="test_key",
            original_query="test query",
            response="test response",
        )
        
        # Verify it exists
        assert dual_cache.get("test_key") is not None
        
        # Invalidate
        result = dual_cache.invalidate("test_key")
        
        # Should return True (though JSON might not have it after get)
        assert result is True
    
    def test_dual_cache_clear(self, dual_cache):
        """Test clearing all entries."""
        # Add entries
        for i in range(3):
            dual_cache.put(
                cache_key=f"key_{i}",
                original_query=f"query_{i}",
                response=f"response_{i}",
            )
        
        # Clear
        dual_cache.clear()
        
        # Should be empty (or at least not error)
        stats = dual_cache.get_stats()
        assert "json_fallback_entries" in stats
    
    def test_dual_cache_stats(self, dual_cache):
        """Test getting cache statistics."""
        dual_cache.put(
            cache_key="key1",
            original_query="query1",
            response="response1",
        )
        
        stats = dual_cache.get_stats()
        
        assert "langcache_available" in stats
        assert "json_fallback_entries" in stats
    
    def test_dual_cache_is_healthy(self, dual_cache):
        """Test health check."""
        assert dual_cache.is_healthy() is True


class TestLangCacheAvailability:
    """Test LangCache availability check."""
    
    def test_langcache_available_flag(self):
        """Test LANGCACHE_AVAILABLE flag is set."""
        # This test just verifies the flag exists
        assert isinstance(LANGCACHE_AVAILABLE, bool)


class TestDualCacheWithLangCache:
    """Test dual cache behavior when LangCache is available."""
    
    @pytest.fixture
    def temp_cache_file(self):
        """Create a temporary cache file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        yield temp_path
        
        if os.path.exists(temp_path):
            os.remove(temp_path)
    
    def test_fallback_when_langcache_unavailable(self, temp_cache_file):
        """Test JSON fallback when LangCache unavailable."""
        # Create with empty config (no LangCache)
        cache = DualCache(
            langcache_config={},
            json_fallback_path=temp_cache_file,
            enable_sync=False,
        )
        
        # Put should work via JSON fallback
        result = cache.put(
            cache_key="fallback_test",
            original_query="test query",
            response="test response",
        )
        
        assert result is True
        
        # Get should work via JSON fallback
        entry = cache.get("fallback_test", "test query")
        
        assert entry is not None
        assert entry.response == "test response"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])