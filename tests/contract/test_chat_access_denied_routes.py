"""Contract tests: the /api/chat route threads the access-request wiring
(project contact lookup + authorized scope) and returns the safe response shape.
"""
from fastapi.testclient import TestClient

import app.api.routes.chat as chat_routes
from app.api.dependencies import get_authorization_service, get_chat_principal
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationScope
from app.main import app


class StubAuthorization:
    def authorization_scope(self, principal, selected_project_id=None):
        if selected_project_id == "p-denied":
            return AuthorizationScope(is_admin=False, project_ids=[], document_ids=None, include_unassigned=False)
        if selected_project_id is None:
            return AuthorizationScope(is_admin=False, project_ids=[], document_ids=None, include_unassigned=False)
        return AuthorizationScope(is_admin=False, project_ids=["p1"], document_ids=None, include_unassigned=False)

    def project_access_contact(self, project_id):
        return {
            "project_id": project_id,
            "project_name": "Project Bravo",
            "manager_name": "Sara Blake",
        }


class OrchestratorSpy:
    received_contact_lookup = None
    received_scope = None
    received_question = None

    def __init__(self, **kwargs):
        OrchestratorSpy.received_contact_lookup = kwargs.get("project_contact_lookup")

    def answer(self, question, conversation_history=None, authorized_project_ids=None, authorization_scope=None):
        OrchestratorSpy.received_scope = authorization_scope
        OrchestratorSpy.received_question = question
        return {
            "answer": (
                "Relevant information exists in a project document that you do "
                "not currently have access to. Please contact Sara Blake, the "
                "manager of Project Bravo, to request access."
            ),
            "citations": [],
        }


def test_chat_route_injects_project_contact_lookup_into_orchestrator(monkeypatch):
    monkeypatch.setattr(chat_routes, "QueryOrchestrator", OrchestratorSpy)
    app.dependency_overrides[get_chat_principal] = lambda: AuthenticatedPrincipal("u1")
    app.dependency_overrides[get_authorization_service] = lambda: StubAuthorization()
    try:
        response = TestClient(app).post(
            "/api/chat",
            json={"question": "What is the annual leave policy?", "project_id": "p1"},
        )
        assert response.status_code == 200
        assert callable(OrchestratorSpy.received_contact_lookup)
        assert OrchestratorSpy.received_contact_lookup("p2") == {
            "project_id": "p2",
            "project_name": "Project Bravo",
            "manager_name": "Sara Blake",
        }
        assert OrchestratorSpy.received_question == "What is the annual leave policy?"
    finally:
        app.dependency_overrides.clear()


def test_chat_route_returns_safe_access_response_without_probing_real_store(monkeypatch):
    monkeypatch.setattr(chat_routes, "QueryOrchestrator", OrchestratorSpy)
    app.dependency_overrides[get_chat_principal] = lambda: AuthenticatedPrincipal("u1")
    app.dependency_overrides[get_authorization_service] = lambda: StubAuthorization()
    try:
        response = TestClient(app).post(
            "/api/chat",
            json={"question": "What is the annual leave policy?", "project_id": None},
        )
        assert response.status_code == 200
        body = response.json()
        assert "do not currently have access to" in body["answer"]
        assert "Project Bravo" in body["answer"]
        assert body["citations"] == []
        assert OrchestratorSpy.received_scope.project_ids == []
        assert OrchestratorSpy.received_scope.is_admin is False
    finally:
        app.dependency_overrides.clear()


def test_chat_route_still_rejects_explicit_unauthorized_project(monkeypatch):
    monkeypatch.setattr(chat_routes, "QueryOrchestrator", OrchestratorSpy)
    app.dependency_overrides[get_chat_principal] = lambda: AuthenticatedPrincipal("u1")
    app.dependency_overrides[get_authorization_service] = lambda: StubAuthorization()
    try:
        response = TestClient(app).post(
            "/api/chat",
            json={"question": "What is the annual leave policy?", "project_id": "p-denied"},
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()