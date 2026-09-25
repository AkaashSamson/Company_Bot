from fastapi.testclient import TestClient
from unittest.mock import Mock

from app.api.dependencies import get_authorization_service, get_chat_principal
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationScope
from app.main import app
from app.api.routes import chat as chat_route
from app.infrastructure.llm.fallback_llm_provider import FallbackLLMProvider
from app.infrastructure.llm.prompt_cache import PromptLRUCache
from app.infrastructure.faq.json_faq_cache import JsonFAQCache


class AdminAuthorization:
    def is_admin(self, principal):
        return True

    def authorization_scope(self, principal, selected_project_id=None):
        return AuthorizationScope(is_admin=True, project_ids=None, document_ids=None, include_unassigned=True)


client = TestClient(app)


def test_chat_endpoint_returns_chat_response(monkeypatch):
    app.dependency_overrides[get_chat_principal] = lambda: AuthenticatedPrincipal("admin")
    app.dependency_overrides[get_authorization_service] = lambda: AdminAuthorization()
    llm = Mock()
    llm.generate.return_value = "Employees receive annual leave according to company policy."
    retrieval = Mock()
    retrieval.retrieve.return_value = [
        {
            "text": "Employees receive annual leave according to company policy.",
            "metadata": {"source": "HR_Policy.pdf", "section": "Leave"},
        }
    ]
    mock_orchestrator = chat_route.QueryOrchestrator(
        llm=FallbackLLMProvider(primary=llm, fallback=Mock()),
        retrieval=retrieval,
        response_cache=PromptLRUCache(maxsize=2),
    )
    monkeypatch.setattr(chat_route, "orchestrator", mock_orchestrator)
    try:
        payload = {
            "question": "What is the annual leave policy?",
            "session_id": "session-123",
            "defer_citations": False,
            "conversation_history": [
                {"role": "user", "content": "What is the annual leave policy?"},
                {"role": "assistant", "content": "It is described in the HR policy."},
            ],
        }
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["session_id"] == "session-123"
        assert "answer" in body
        assert len(body["citations"]) >= 1
    finally:
        app.dependency_overrides.clear()


def test_chat_endpoint_reuses_cached_answer(monkeypatch):
    llm = Mock()
    llm.generate.return_value = "cached answer"
    retrieval = Mock()
    retrieval.retrieve.return_value = [
        {
            "text": "Employees receive annual leave according to company policy.",
            "metadata": {"source": "policy.docx"},
        }
    ]
    cached_orchestrator = chat_route.QueryOrchestrator(
        llm=FallbackLLMProvider(
            primary=llm,
            fallback=Mock(),
            cache=PromptLRUCache(maxsize=2),
        ),
        retrieval=retrieval,
        response_cache=PromptLRUCache(maxsize=2),
        faq_cache=None,
    )
    monkeypatch.setattr(chat_route, "orchestrator", cached_orchestrator)
    payload = {
        "question": "What is the annual leave policy?",
        "session_id": "cache-session",
        "conversation_history": [],
    }

    first_response = client.post("/api/chat", json=payload)
    second_response = client.post("/api/chat", json=payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["answer"] == "cached answer"
    assert second_response.json()["answer"] == "cached answer"
    assert second_response.json()["answer"] == first_response.json()["answer"]
    assert second_response.json()["citations"] == first_response.json()["citations"]
    assert llm.generate.call_count == 1


def test_faq_endpoint_caches_generated_document_faqs(monkeypatch, tmp_path):
    llm = Mock()
    llm.generate.return_value = "1. What is leave entitlement? Employees receive annual leave."
    retrieval = Mock()
    retrieval.retrieve.return_value = [
        {
            "text": "Eligible regular employees receive 18 days of Annual Leave per calendar year.",
            "metadata": {"source": "policy.docx"},
        }
    ]
    cached_orchestrator = chat_route.QueryOrchestrator(
        llm=FallbackLLMProvider(
            primary=llm,
            fallback=Mock(),
            cache=PromptLRUCache(maxsize=2),
        ),
        retrieval=retrieval,
        faq_cache=JsonFAQCache(tmp_path / "faqs_cache.json"),
    )
    monkeypatch.setattr(chat_route, "orchestrator", cached_orchestrator)

    first_response = client.get("/api/faqs")
    second_response = client.get("/api/faqs")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json() == first_response.json()
    assert llm.generate.call_count == 1


def test_similar_questions_return_the_exact_previous_response(monkeypatch):
    llm = Mock()
    llm.generate.return_value = "Eligible employees receive 18 days of Annual Leave."
    retrieval = Mock()
    retrieval.retrieve.return_value = [
        {
            "text": "Eligible regular employees receive 18 days of Annual Leave.",
            "metadata": {"source": "policy.docx"},
        }
    ]

    def embed_question(key):
        return [1.0, 0.0] if "annual leave" in key or "vacation days" in key else [0.0, 1.0]

    response_cache = PromptLRUCache(
        maxsize=4,
        similarity_threshold=0.95,
        embedder=embed_question,
    )
    cached_orchestrator = chat_route.QueryOrchestrator(
        llm=FallbackLLMProvider(primary=llm, fallback=Mock()),
        retrieval=retrieval,
        response_cache=response_cache,
        faq_cache=None,
    )
    monkeypatch.setattr(chat_route, "orchestrator", cached_orchestrator)

    first = client.post(
        "/api/chat",
        json={"question": "How many annual leave days do I get?", "session_id": "similar-1"},
    )
    second = client.post(
        "/api/chat",
        json={"question": "How many vacation days do I receive?", "session_id": "similar-2"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["answer"] == first.json()["answer"]
    assert second.json()["citations"] == first.json()["citations"]
    assert llm.generate.call_count == 1


def test_faq_endpoint_reads_json_cache_without_llm(monkeypatch, tmp_path):
    llm = Mock()
    retrieval = Mock()
    faq_cache = JsonFAQCache(tmp_path / "faqs_cache.json")
    faq_cache.save({
        "faqs": "1. What is the leave entitlement?",
        "citations": [],
    })
    cached_orchestrator = chat_route.QueryOrchestrator(
        llm=llm,
        retrieval=retrieval,
        faq_cache=faq_cache,
    )
    monkeypatch.setattr(chat_route, "orchestrator", cached_orchestrator)

    response = client.get("/api/faqs")

    assert response.status_code == 200
    assert response.json()["faqs"] == "1. What is the leave entitlement?"
    retrieval.retrieve.assert_not_called()
    llm.generate.assert_not_called()


def test_clear_cache_endpoint(monkeypatch):
    mock_response_cache = Mock()
    mock_llm_cache = Mock()
    mock_llm = Mock()
    mock_llm.cache = mock_llm_cache
    orchestrator = Mock()
    orchestrator.response_cache = mock_response_cache
    orchestrator.llm = mock_llm
    orchestrator.faq_cache = None

    monkeypatch.setattr(chat_route, "orchestrator", orchestrator)

    response = client.post("/api/chat/cache/clear")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "response_cache" in body["cleared"]
    assert "llm_prompt_cache" in body["cleared"]
    mock_response_cache.clear.assert_called_once()
    mock_llm_cache.clear.assert_called_once()

