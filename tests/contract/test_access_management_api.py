"""Contract tests for document access and project access API endpoints."""
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_authorization_service,
    get_current_principal,
    get_document_access_service,
    get_project_access_service,
)
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationEngine, AuthorizationScope
from app.infrastructure.persistence.rbac_seed import seed_rbac
from app.main import app
from tests.fixtures.organization_repositories import InMemoryUnitOfWork

client = TestClient(app)


def _build():
    from app.domain.entities.organization_models import (
        Department, Document, Project, User, UserProject,
    )
    from app.use_cases.organization.document_access import DocumentAccessService
    from app.use_cases.organization.project_access import ProjectAccessService

    users = [
        User("admin", "Admin", "a@ex.com", "Admin", "d1"),
        User("mgr", "Manager", "m@ex.com", "Manager", "d1"),
        User("dev", "Developer", "d@ex.com", "Developer", "d1"),
        User("tester", "Tester", "t@ex.com", "Tester", "d1"),
    ]
    uow = InMemoryUnitOfWork(
        users,
        [Department("d1", "Eng")],
        [Project("p1", "Project A", "d1")],
        [UserProject("dev", "p1")],
        [Document("d1", "Doc 1", project_id="p1")],
        [],
    )
    seed_rbac(lambda: uow)
    engine = AuthorizationEngine(lambda: uow)

    class StubAuthorization:
        def is_admin(self, principal):
            return principal.uid == "admin"
        def authorized_project_ids(self, principal, selected_project_id=None):
            return None if principal.uid == "admin" else ["p1"]
        def authorization_scope(self, principal, selected_project_id=None):
            return engine.authorization_scope(principal, selected_project_id)

    return uow, engine, StubAuthorization(), DocumentAccessService(lambda: uow, engine), ProjectAccessService(lambda: uow, engine)


_uow, _engine, _authz, _doc_svc, _prj_svc = _build()


def _override(principal_uid="admin"):
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal(principal_uid)
    app.dependency_overrides[get_authorization_service] = lambda: _authz
    app.dependency_overrides[get_document_access_service] = lambda: _doc_svc
    app.dependency_overrides[get_project_access_service] = lambda: _prj_svc


def test_document_access_list_and_grant_and_revoke():
    _override("admin")
    try:
        r = client.get("/api/documents/d1/access")
        assert r.status_code == 200
        assert r.json() == []

        r = client.post("/api/documents/d1/access", json={"principal_type": "user", "user_id": "dev"})
        assert r.status_code == 201
        grant = r.json()
        gid = grant["internal_id"]

        r = client.get("/api/documents/d1/access")
        assert r.status_code == 200
        assert len(r.json()) == 1

        r = client.delete(f"/api/document-access/{gid}")
        assert r.status_code == 204

        r = client.get("/api/documents/d1/access")
        assert r.status_code == 200
        assert r.json() == []
    finally:
        app.dependency_overrides.clear()


def test_project_access_list_and_grant_and_revoke():
    _override("admin")
    try:
        r = client.get("/api/projects/p1/access")
        assert r.status_code == 200
        assert r.json() == []

        r = client.post("/api/projects/p1/access", json={"principal_type": "user", "user_id": "dev"})
        assert r.status_code == 201
        grant = r.json()
        gid = grant["internal_id"]

        r = client.get("/api/projects/p1/access")
        assert r.status_code == 200
        assert len(r.json()) == 1

        r = client.delete(f"/api/project-access/{gid}")
        assert r.status_code == 204

        r = client.get("/api/projects/p1/access")
        assert r.status_code == 200
        assert r.json() == []
    finally:
        app.dependency_overrides.clear()


def test_developer_cannot_grant_document_access():
    _override("dev")
    try:
        r = client.post("/api/documents/d1/access", json={"principal_type": "user", "user_id": "tester"})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_developer_cannot_grant_project_access():
    _override("dev")
    try:
        r = client.post("/api/projects/p1/access", json={"principal_type": "user", "user_id": "tester"})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_manager_can_grant_and_revoke():
    _override("mgr")
    try:
        r = client.post("/api/documents/d1/access", json={"principal_type": "user", "user_id": "tester"})
        assert r.status_code == 201
        gid = r.json()["internal_id"]

        r = client.delete(f"/api/document-access/{gid}")
        assert r.status_code == 204
    finally:
        app.dependency_overrides.clear()


def test_duplicate_grant_returns_409():
    _override("admin")
    try:
        client.post("/api/documents/d1/access", json={"principal_type": "user", "user_id": "dev"})
        r = client.post("/api/documents/d1/access", json={"principal_type": "user", "user_id": "dev"})
        assert r.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_revoke_nonexistent_returns_404():
    _override("admin")
    try:
        r = client.delete("/api/document-access/999")
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_invalid_principal_type_returns_422():
    _override("admin")
    try:
        r = client.post("/api/documents/d1/access", json={"principal_type": "invalid"})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()
