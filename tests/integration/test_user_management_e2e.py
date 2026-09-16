import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_principal
from app.domain.entities.organization_models import Department
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.infrastructure.persistence.factory import get_session_factory
from app.infrastructure.persistence.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork
from app.main import app
from app.use_cases.organization.user_management import UserManagementService


def test_user_management_requires_authentication():
    client = TestClient(app)
    response = client.get("/api/users/u1")
    assert response.status_code == 401


def _admin_exists(session_factory) -> bool:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        actor = uow.users.get_by_uid("admin")
        return actor is not None and actor.status == "active" and actor.role.casefold() == "admin"


@pytest.mark.skipif(
    not _admin_exists(get_session_factory()),
    reason="seed admin not provisioned: ADMIN_INITIAL_PASSWORD is not configured",
)
def test_authenticated_admin_can_deactivate_user_when_storage_is_configured():
    session_factory = get_session_factory()
    users = UserManagementService(lambda: SqlAlchemyUnitOfWork(session_factory))
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        if uow.departments.get("d1") is None:
            uow.departments.save(Department("d1", "Engineering"))
            uow.commit()
        if uow.users.get_by_uid("e2e-deactivate") is not None:
            uow.users.delete("e2e-deactivate")
            uow.commit()
    users.create_user("admin", "e2e-deactivate", "Deactivate Me", "deactivate@example.com", "Developer", "d1")

    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("admin")
    client = TestClient(app)
    try:
        response = client.delete("/api/users/e2e-deactivate")
        assert response.status_code == 204
    finally:
        app.dependency_overrides.clear()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.users.get_by_uid("e2e-deactivate").status == "inactive"