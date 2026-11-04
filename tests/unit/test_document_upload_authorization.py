import pytest

from app.domain.entities.organization_models import Department, Project, User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.organization_errors import ForbiddenError, NotFoundError
from app.use_cases.organization.document_management import DocumentManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def _setup():
    unit_of_work = InMemoryUnitOfWork(
        users=[
            User("admin", "Admin", "admin@example.com", "Admin", "d1"),
            User("dev", "Dev", "dev@example.com", "Developer", "d1"),
            User("pm", "PM", "pm@example.com", "Developer", "d1"),
            User("dept-manager", "Dept Manager", "dm@example.com", "Manager", "d1"),
            User("other-manager", "Other Manager", "om@example.com", "Manager", "d2"),
        ],
        departments=[Department("d1", "Engineering"), Department("d2", "Finance")],
        projects=[Project("p1", "Project One", "d1", manager_uid="pm")],
    )
    service = DocumentManagementService(lambda: unit_of_work)
    return unit_of_work, service


def test_admin_can_upload_to_any_project():
    _, service = _setup()
    document = service.register_document(AuthenticatedPrincipal("admin"), document_id="d1", document_name="A.txt", project_id="p1")
    assert document.project_id == "p1"


def test_designated_project_manager_can_upload_even_without_manager_role():
    _, service = _setup()
    document = service.register_document(AuthenticatedPrincipal("pm"), document_id="pm-1", document_name="Runbook.txt", project_id="p1")
    assert document.project_id == "p1"
    assert document.uploaded_by == "pm"


def test_department_manager_can_upload_to_department_project():
    _, service = _setup()
    document = service.register_document(
        AuthenticatedPrincipal("dept-manager"), document_id="dm-1", document_name="Handbook.txt", project_id="p1"
    )
    assert document.project_id == "p1"


def test_regular_developer_cannot_upload_to_project():
    _, service = _setup()
    with pytest.raises(ForbiddenError):
        service.register_document(AuthenticatedPrincipal("dev"), document_id="dev-1", document_name="Sneaky.txt", project_id="p1")


def test_manager_from_other_department_cannot_upload():
    _, service = _setup()
    with pytest.raises(ForbiddenError):
        service.register_document(AuthenticatedPrincipal("other-manager"), document_name="Sneaky.txt", project_id="p1")


def test_regular_developer_cannot_register_unassigned_document():
    _, service = _setup()
    with pytest.raises(ForbiddenError):
        service.register_document(AuthenticatedPrincipal("dev"), document_name="Org.txt")


def test_upload_to_unknown_project_is_not_found():
    _, service = _setup()
    with pytest.raises(NotFoundError):
        service.register_document(AuthenticatedPrincipal("pm"), document_name="Ghost.txt", project_id="missing")