"""
Unit Tests for LangCacheAdapter (Loosely Coupled Semantic Cache)

Tests the LangCacheAdapter against mocked and simulated Redis LangCache SDK responses:
- Initialization and availability flags
- Semantic search result handling and parsing
- Set operations with metadata/attribute extraction
- Attribute fallback resilience for unconfigured caches
- Negative response filtering
- RBAC validation on cached attributes
- Network failure resilience and graceful degradation
"""

from unittest.mock import MagicMock
import pytest

from app.domain.ports.cache import CacheEntryProtocol, SemanticCachePort
from app.infrastructure.cache.langcache_adapter import LangCacheAdapter


class DummyCacheEntry:
    """Mock of LangCache SDK CacheEntry."""
    def __init__(self, entry_id: str, prompt: str, response: str, similarity: float = 1.0, attributes: dict = None):
        self.id = entry_id
        self.prompt = prompt
        self.response = response
        self.similarity = similarity
        self.attributes = attributes or {}


class DummySearchResponse:
    """Mock of LangCache SDK SearchResponse."""
    def __init__(self, data: list):
        self.data = data


class DummySetResponse:
    """Mock of LangCache SDK SetResponse."""
    def __init__(self, entry_id: str):
        self.entry_id = entry_id


class TestLangCacheAdapter:
    """Test suite for LangCacheAdapter."""

    def test_implements_semantic_cache_port(self):
        """Verify LangCacheAdapter implements SemanticCachePort protocol."""
        adapter = LangCacheAdapter(server_url="", cache_id="", api_key="")
        assert isinstance(adapter, SemanticCachePort)

    def test_initialization_with_custom_client(self):
        """Test initializing with pre-configured client."""
        mock_client = MagicMock()
        adapter = LangCacheAdapter(client=mock_client)
        assert adapter.is_available is True
        assert adapter.is_healthy() is True

    def test_initialization_without_credentials_is_unavailable(self):
        """Test adapter safely marks itself unavailable when credentials missing."""
        adapter = LangCacheAdapter(server_url="", cache_id="", api_key="")
        assert adapter.is_available is False
        assert adapter.is_healthy() is False
        assert adapter.get("any_key") is None
        assert adapter.put("any_key", "prompt", "response") is False

    def test_search_hit_parses_sdk_response(self):
        """Test successful semantic search hit with SDK objects."""
        mock_client = MagicMock()
        mock_client.search.return_value = DummySearchResponse(
            data=[
                DummyCacheEntry(
                    entry_id="lc_12345",
                    prompt="What is the leave policy?",
                    response="Leave policy provides 20 days annual leave.",
                    similarity=0.96,
                    attributes={"model": "llama-3", "cache_id": "cch_abc123"},
                )
            ]
        )

        adapter = LangCacheAdapter(client=mock_client)
        entry = adapter.get(
            cache_key="leave_query",
            original_query="What is the leave policy?",
        )

        assert entry is not None
        assert isinstance(entry, CacheEntryProtocol)
        assert entry.response == "Leave policy provides 20 days annual leave."
        assert entry.confidence == 0.96
        assert entry.source == "langcache"
        assert entry.cache_id == "cch_abc123"
        assert adapter.get_stats()["hits"] == 1

    def test_search_miss_returns_none(self):
        """Test search miss returns None and increments miss metric."""
        mock_client = MagicMock()
        mock_client.search.return_value = DummySearchResponse(data=[])

        adapter = LangCacheAdapter(client=mock_client)
        entry = adapter.get(cache_key="unmatched", original_query="Non-existent query")

        assert entry is None
        assert adapter.get_stats()["misses"] == 1

    def test_search_rejects_negative_cached_response(self):
        """Test unhelpful/negative cached response is discarded as a miss."""
        mock_client = MagicMock()
        mock_client.search.return_value = DummySearchResponse(
            data=[
                DummyCacheEntry(
                    entry_id="lc_neg",
                    prompt="What is X?",
                    response="I am sorry, but no information was found in the provided documents.",
                    similarity=0.99,
                )
            ]
        )

        adapter = LangCacheAdapter(client=mock_client)
        entry = adapter.get(cache_key="neg_q", original_query="What is X?")
        assert entry is None

    def test_search_rbac_filtering(self):
        """Test RBAC role enforcement against stored attributes."""
        mock_client = MagicMock()
        mock_client.search.return_value = DummySearchResponse(
            data=[
                DummyCacheEntry(
                    entry_id="lc_hr",
                    prompt="Manager bonus details",
                    response="Manager bonus is 15%.",
                    similarity=0.95,
                    attributes={"assigned_role": "manager"},
                )
            ]
        )

        adapter = LangCacheAdapter(client=mock_client)

        # Employee should be denied
        denied_entry = adapter.get(
            cache_key="bonus_query",
            original_query="Manager bonus details",
            role="employee",
        )
        assert denied_entry is None

        # Manager should be granted
        allowed_entry = adapter.get(
            cache_key="bonus_query",
            original_query="Manager bonus details",
            role="manager",
        )
        assert allowed_entry is not None
        assert allowed_entry.response == "Manager bonus is 15%."

        # Admin should always be granted
        admin_entry = adapter.get(
            cache_key="bonus_query",
            original_query="Manager bonus details",
            is_admin=True,
        )
        assert admin_entry is not None

    def test_put_stores_entry_successfully(self):
        """Test storing prompt and response with SetResponse acknowledgment."""
        mock_client = MagicMock()
        mock_client.set.return_value = DummySetResponse(entry_id="entry_987")

        adapter = LangCacheAdapter(client=mock_client)
        success = adapter.put(
            cache_key="policy_key",
            original_query="What is the policy?",
            response="The policy is standard.",
            confidence=0.9,
            model="gpt-4o",
            assigned_role="employee",
        )

        assert success is True
        assert adapter.get_stats()["writes"] == 1
        assert mock_client.set.called

    def test_put_filters_negative_response(self):
        """Test negative answers are not stored in LangCache."""
        mock_client = MagicMock()
        adapter = LangCacheAdapter(client=mock_client)

        success = adapter.put(
            cache_key="refusal_key",
            original_query="Secret information",
            response="Unable to find any information in the provided documents.",
        )

        assert success is False
        assert not mock_client.set.called
        assert adapter.get_stats()["negative_responses_skipped"] == 1

    def test_put_attribute_fallback_when_attributes_not_configured(self):
        """Test fallback when LangCache cloud instance does not support attributes."""
        mock_client = MagicMock()
        # First call with attributes fails, second call without attributes succeeds
        mock_client.set.side_effect = [
            Exception('{"detail":"attributes: no attributes are configured for this cache."}'),
            DummySetResponse(entry_id="retry_ok"),
        ]

        adapter = LangCacheAdapter(client=mock_client)
        assert adapter._supports_attributes is True

        success = adapter.put(
            cache_key="test_key",
            original_query="test query",
            response="test answer",
            assigned_role="employee",
        )

        assert success is True
        assert adapter._supports_attributes is False  # remembered fallback
        assert mock_client.set.call_count == 2

    def test_network_exception_during_search_degrades_gracefully(self):
        """Test network errors during search do not raise exceptions."""
        mock_client = MagicMock()
        mock_client.search.side_effect = ConnectionError("Remote endpoint unreachable")

        adapter = LangCacheAdapter(client=mock_client)
        entry = adapter.get(cache_key="err_key", original_query="test query")

        assert entry is None
        assert adapter.get_stats()["errors"] == 1

    def test_network_exception_during_set_degrades_gracefully(self):
        """Test network errors during set do not raise exceptions."""
        mock_client = MagicMock()
        mock_client.set.side_effect = TimeoutError("Redis gateway timeout")

        adapter = LangCacheAdapter(client=mock_client)
        success = adapter.put(
            cache_key="err_key",
            original_query="test query",
            response="test answer",
        )

        assert success is False
        assert adapter.get_stats()["errors"] == 1

    def test_clear_flushes_cache(self):
        """Test clear calls client flush."""
        mock_client = MagicMock()
        adapter = LangCacheAdapter(client=mock_client)
        adapter.clear()
        assert mock_client.flush.called
