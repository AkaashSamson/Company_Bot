"""
Unit Tests for Cache Factory, Loose Coupling, and Streamlit App Inputs

Tests:
- Creation of DualCache, LangCacheAdapter, InMemoryQualityAwareCache, JSONLocalCache via factory
- Loose coupling: QueryOrchestrator functioning seamlessly with swappable cache adapters
- Streamlit app input representation:
  * Full ChatRequest payload (question, timestamp, session_id, conversation_history, defer_citations, project_id)
  * RBAC and user context scopes (roles, project_ids, document_ids)
  * Streamlit relevance feedback handling ("No, not relevant" evicts from cache)
  * Streamlit sidebar "Clear Cache" button integration
  * End-to-end FastAPI endpoint simulation matching ChatService.ask() payload
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_authorization_service, get_chat_principal
from app.api.routes import chat as chat_route
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.ports.cache import CacheEntryProtocol, SemanticCachePort
from app.domain.services.authorization_engine import AuthorizationScope
from app.infrastructure.cache.dual_cache import DualCache, DualCacheEntry, JSONLocalCache
from app.infrastructure.cache.factory import (
    create_cache,
    get_semantic_cache,
    reset_cache_instance,
)
from app.infrastructure.cache.langcache_adapter import LangCacheAdapter
from app.infrastructure.cache.quality_aware_cache import InMemoryQualityAwareCache
from app.main import app
from app.use_cases.chat.query_orchestrator import QueryOrchestrator


class MockSwappableCache:
    """Mock cache demonstrating loose coupling and protocol adherence."""
    def __init__(self):
        self.store = {}
        self.stats = {"hits": 0, "misses": 0, "writes": 0, "deletions": 0}

    def get(self, cache_key: str, original_query: str = "", **kwargs):
        lookup = original_query or cache_key
        if lookup in self.store:
            self.stats["hits"] += 1
            return self.store[lookup]
        if cache_key in self.store:
            self.stats["hits"] += 1
            return self.store[cache_key]
        self.stats["misses"] += 1
        return None

    def put(self, cache_key: str, original_query: str, response: str, **kwargs):
        entry = {
            "answer": response,
            "response": response,
            "citations": kwargs.get("citations", []),
            "cache_id": kwargs.get("cache_id", "mock_cch_123"),
            "assigned_role": kwargs.get("assigned_role"),
        }
        self.store[cache_key] = entry
        if original_query and original_query != cache_key:
            self.store[original_query] = entry
        self.stats["writes"] += 1
        return True

    def delete(self, cache_key: str) -> bool:
        deleted = False
        if cache_key in self.store:
            del self.store[cache_key]
            deleted = True
        self.stats["deletions"] += 1
        return deleted

    def clear(self) -> None:
        self.store.clear()

    def get_stats(self) -> dict:
        return dict(self.stats)

    def is_healthy(self) -> bool:
        return True


class TestCacheFactory:
    """Test suite for Cache Factory and loosely coupled Streamlit interactions."""

    @pytest.fixture(autouse=True)
    def enable_cache(self, monkeypatch):
        monkeypatch.setattr("app.core.settings.CACHE_ENABLED", True)
        monkeypatch.setattr("app.core.settings.SEMANTIC_CACHE_ENABLED", True)
        monkeypatch.setattr("app.core.settings.FAQ_SIMILARITY_CACHE_ENABLED", True)

    def setup_method(self):
        reset_cache_instance()

    def teardown_method(self):
        reset_cache_instance()

    def test_create_langcache_adapter(self):
        """Test creating LangCache adapter backend."""
        cache = create_cache(backend="langcache", langcache_server_url="", langcache_cache_id="", langcache_api_key="")
        assert isinstance(cache, LangCacheAdapter)
        assert isinstance(cache, SemanticCachePort)

    def test_create_dual_cache(self, tmp_path):
        """Test creating DualCache backend."""
        fallback_file = str(tmp_path / "fallback.json")
        cache = create_cache(
            backend="dual",
            langcache_server_url="",
            langcache_cache_id="",
            langcache_api_key="",
            fallback_path=fallback_file,
            enable_sync=False,
        )
        assert isinstance(cache, DualCache)
        assert isinstance(cache, SemanticCachePort)

    def test_create_json_cache(self, tmp_path):
        """Test creating JSONLocalCache backend."""
        cache_file = str(tmp_path / "test.json")
        cache = create_cache(backend="json", fallback_path=cache_file)
        assert isinstance(cache, JSONLocalCache)

    def test_create_memory_cache(self):
        """Test creating InMemoryQualityAwareCache backend."""
        cache = create_cache(backend="memory", max_entries=50, ttl_seconds=600)
        assert isinstance(cache, InMemoryQualityAwareCache)

    def test_get_semantic_cache_singleton(self, tmp_path):
        """Test get_semantic_cache maintains singleton lifecycle."""
        fallback = str(tmp_path / "cache.json")
        cache1 = get_semantic_cache(backend="dual", fallback_path=fallback, enable_sync=False)
        cache2 = get_semantic_cache()
        assert cache1 is cache2

        reset_cache_instance()
        cache3 = get_semantic_cache(backend="json", fallback_path=fallback)
        assert cache3 is not cache1

    def test_orchestrator_with_full_streamlit_app_inputs(self, tmp_path):
        """
        Verify QueryOrchestrator works with the EXACT inputs constructed by
        the Streamlit app (streamlit_app/app.py & ChatService.ask):
        - question: str
        - question_timestamp: ISO-8601 string
        - session_id: unique session ID
        - conversation_history: list of messages [{"role": ..., "content": ...}]
        - defer_citations: True (Streamlit default)
        - user_context: dict with role, roles, uid
        - authorization_scope: AuthorizationScope
        """
        # Create a loosely-coupled DualCache with local JSON fallback
        cache_file = str(tmp_path / "streamlit_test_cache.json")
        dual_cache = DualCache(
            langcache_config={},  # offline mock mode
            json_fallback_path=cache_file,
            enable_sync=False,
        )

        mock_llm = MagicMock()
        mock_llm.generate.return_value = "Employees are entitled to 20 days of annual leave."

        mock_retrieval = MagicMock()
        mock_retrieval.retrieve.return_value = [
            {"text": "Annual leave entitlement is 20 days.", "metadata": {"source": "HR_Leave_Policy.pdf", "document_id": "doc_leave_01"}}
        ]

        mock_provenance = MagicMock()
        mock_provenance.build_citations.return_value = [
            {"source": "HR_Leave_Policy.pdf", "section": "Leave", "text": "Annual leave entitlement is 20 days."}
        ]

        orchestrator = QueryOrchestrator(
            retrieval=mock_retrieval,
            provenance=mock_provenance,
            llm=mock_llm,
            response_cache=dual_cache,
            faq_cache=None,
        )

        # ── Turn 1: Streamlit asks a question for the first time ──
        streamlit_question = "What is the annual leave policy?"
        streamlit_timestamp = datetime.now(timezone.utc).isoformat()
        streamlit_session_id = "streamlit-sess-999"
        streamlit_history = [
            {"role": "user", "content": "Hello, I have a question."},
            {"role": "assistant", "content": "Hello! How can I assist you with company policies today?"},
        ]
        user_scope = AuthorizationScope(is_admin=False, project_ids=["proj_general"], document_ids=None, include_unassigned=True)
        user_ctx = {
            "uid": "emp_42",
            "role": "employee",
            "roles": ["employee"],
            "is_admin": False,
        }

        turn1_response = orchestrator.answer(
            question=streamlit_question,
            conversation_history=streamlit_history,
            authorization_scope=user_scope,
            session_id=streamlit_session_id,
            defer_citations=True,
            question_timestamp=streamlit_timestamp,
            user_context=user_ctx,
        )

        assert turn1_response["cache_hit"] is False
        assert "20 days" in turn1_response["answer"]
        assert mock_llm.generate.called

        # ── Turn 2: User asks the exact same question in Streamlit ──
        # Streamlit conversation history now contains the first Q&A
        updated_history = list(streamlit_history) + [
            {"role": "user", "content": streamlit_question},
            {"role": "assistant", "content": turn1_response["answer"]},
        ]

        mock_llm.generate.reset_mock()
        turn2_response = orchestrator.answer(
            question=streamlit_question,
            conversation_history=updated_history,
            authorization_scope=user_scope,
            session_id=streamlit_session_id,
            defer_citations=True,
            question_timestamp=datetime.now(timezone.utc).isoformat(),
            user_context=user_ctx,
        )

        # Cache HIT from DualCache!
        assert turn2_response["cache_hit"] is True
        assert "20 days" in turn2_response["answer"]
        # LLM was NOT called on cache hit (saves tokens in Streamlit)
        assert not mock_llm.generate.called
        assert turn2_response.get("cache_id") is not None

    def test_streamlit_feedback_not_relevant_evicts_from_cache(self, tmp_path):
        """
        Verify Streamlit feedback button flow:
        When a user in Streamlit clicks '👎 No, not relevant', Streamlit sends
        'No, not relevant' with the previous question in conversation_history.
        The QueryOrchestrator must evict the stale entry from the loosely coupled cache.
        """
        cache = MockSwappableCache()

        llm = MagicMock()
        llm.generate.return_value = "Submit receipts via the portal."
        retrieval = MagicMock()
        retrieval.retrieve.return_value = [{"text": "Submit receipts via the portal.", "metadata": {"source": "Expenses.pdf"}}]
        provenance = MagicMock()
        provenance.build_citations.return_value = [{"source": "Expenses.pdf", "text": "Submit receipts via the portal."}]

        orchestrator = QueryOrchestrator(
            retrieval=retrieval,
            provenance=provenance,
            llm=llm,
            response_cache=cache,
            faq_cache=None,
        )

        # Turn 1: Initial query from Streamlit
        session_id = "feedback-sess"
        t1 = orchestrator.answer(
            question="how to claim travel expenses",
            session_id=session_id,
        )
        assert t1["answer"] is not None

        # Turn 2: User clicked '👎 No, not relevant' in Streamlit
        feedback_input = "No, not relevant"
        history = [
            {"role": "user", "content": "how to claim travel expenses"},
            {"role": "assistant", "content": t1["answer"]},
        ]

        res = orchestrator.answer(
            question=feedback_input,
            conversation_history=history,
            session_id=session_id,
        )

        # Entry should have been deleted from cache
        assert cache.get_stats()["deletions"] >= 1
        assert cache.get("how to claim travel expenses") is None

    def test_streamlit_clear_cache_clears_loosely_coupled_backend(self, tmp_path):
        """
        Verify the Streamlit sidebar '🧹 Clear Cache' button:
        Calling cache.clear() on the factory-provided cache clears both
        primary and fallback layers.
        """
        fallback_file = str(tmp_path / "clear_test.json")
        cache = DualCache(
            langcache_config={},
            json_fallback_path=fallback_file,
            enable_sync=False,
        )

        # Populate
        cache.put(cache_key="q1", original_query="q1", response="a1")
        cache.put(cache_key="q2", original_query="q2", response="a2")
        assert len(cache._json_cache.get_all()) == 2

        # Simulate Streamlit clear cache button
        cache.clear()
        assert len(cache._json_cache.get_all()) == 0
        assert cache.get("q1") is None

    def test_fastapi_chat_endpoint_with_exact_streamlit_payload(self, monkeypatch):
        """
        Test the end-to-end FastAPI endpoint (/api/chat) using the exact
        JSON request payload sent by ChatService.ask() in the Streamlit app.
        Verifies that get_semantic_cache() intercepts and caches requests.
        """
        custom_cache = MockSwappableCache()

        # Mock dependencies
        class MockAuthService:
            def authorization_scope(self, principal, project_id=None):
                return AuthorizationScope(is_admin=True, project_ids=None, document_ids=None, include_unassigned=True)
            def roles_for_user(self, uid):
                return ["employee"]

        app.dependency_overrides[get_chat_principal] = lambda: AuthenticatedPrincipal("emp_test")
        app.dependency_overrides[get_authorization_service] = lambda: MockAuthService()

        llm = MagicMock()
        llm.generate.return_value = "Sick leave is 10 days per calendar year."

        retrieval = MagicMock()
        retrieval.retrieve.return_value = [
            {"text": "Sick leave is 10 days per calendar year.", "metadata": {"source": "Handbook.pdf"}}
        ]

        test_orchestrator = chat_route.QueryOrchestrator(
            llm=llm,
            retrieval=retrieval,
            response_cache=custom_cache,
            faq_cache=None,
        )
        monkeypatch.setattr(chat_route, "orchestrator", test_orchestrator)

        client = TestClient(app)

        try:
            # Exact payload generated by ChatService.ask() in Streamlit
            streamlit_payload = {
                "question": "How many days of sick leave can I take?",
                "question_timestamp": datetime.now(timezone.utc).isoformat(),
                "session_id": "streamlit-web-session-001",
                "project_id": None,
                "conversation_history": [],
                "defer_citations": True,
            }

            # First call -> Miss -> Generates & Caches
            resp1 = client.post("/api/chat", json=streamlit_payload)
            assert resp1.status_code == 200
            data1 = resp1.json()
            assert data1["session_id"] == "streamlit-web-session-001"
            assert "10 days" in data1["answer"]
            assert data1["cache_hit"] is False

            # Second call with the same Streamlit payload -> Cache HIT!
            resp2 = client.post("/api/chat", json=streamlit_payload)
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2["cache_hit"] is True
            assert "10 days" in data2["answer"]

        finally:
            app.dependency_overrides.clear()
