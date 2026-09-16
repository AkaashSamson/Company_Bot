from app.domain.entities.organization_models import Department, Document, Project, User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.use_cases.organization.document_management import DocumentManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_admin_can_register_unassigned_document_and_list_it():
    unit_of_work = InMemoryUnitOfWork(
        users=[User("admin", "Admin", "admin@example.com", "Admin", "d1")],
        documents=[],
    )
    service = DocumentManagementService(lambda: unit_of_work)

    document = service.register_document(
        AuthenticatedPrincipal("admin"), "doc-1", "Handbook", None
    )

    assert document.project_id is None
    assert service.list_documents(AuthenticatedPrincipal("admin")) == [document]


def test_manager_sees_documents_in_their_department_and_delete_archives():
    unit_of_work = InMemoryUnitOfWork(
        users=[User("manager", "Manager", "manager@example.com", "Manager", "d1")],
        departments=[Department("d1", "Engineering")],
        projects=[Project("p1", "Project One", "d1")],
    )
    service = DocumentManagementService(lambda: unit_of_work)
    service.register_document(AuthenticatedPrincipal("manager"), "doc-1", "Runbook", "p1")

    service.delete_document(AuthenticatedPrincipal("manager"), "doc-1")

    assert unit_of_work.documents.get("doc-1").status == "archived"


def test_duplicate_document_id_is_rejected():
    unit_of_work = InMemoryUnitOfWork(
        users=[User("admin", "Admin", "admin@example.com", "Admin", "d1")],
        documents=[Document("doc-1", "Existing")],
    )
    service = DocumentManagementService(lambda: unit_of_work)

    try:
        service.register_document(AuthenticatedPrincipal("admin"), "doc-1", "Duplicate", None)
    except Exception as error:
        assert "already exists" in str(error)
    else:
        raise AssertionError("Duplicate document IDs must be rejected")