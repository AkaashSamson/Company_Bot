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


def test_permanent_delete_removes_document_and_calls_deletion_handler():
    deleted_docs = []
    unit_of_work = InMemoryUnitOfWork(
        users=[User("admin", "Admin", "admin@example.com", "Admin", "d1")],
        documents=[],
    )
    service = DocumentManagementService(
        lambda: unit_of_work,
        deletion_handler=lambda doc_id: deleted_docs.append(doc_id),
    )
    service.register_document(AuthenticatedPrincipal("admin"), "doc-1", "Runbook", None)
    assert unit_of_work.documents.get("doc-1") is not None

    service.delete_document(AuthenticatedPrincipal("admin"), "doc-1", permanent=True)

    assert unit_of_work.documents.get("doc-1") is None
    assert deleted_docs == ["doc-1"]


def test_after_archiving_can_permanently_delete_archived_document():
    deleted_docs = []
    unit_of_work = InMemoryUnitOfWork(
        users=[User("admin", "Admin", "admin@example.com", "Admin", "d1")],
        documents=[],
    )
    service = DocumentManagementService(
        lambda: unit_of_work,
        deletion_handler=lambda doc_id: deleted_docs.append(doc_id),
    )
    service.register_document(AuthenticatedPrincipal("admin"), "doc-1", "Runbook", None)

    # Step 1: Archive document
    service.archive_document(AuthenticatedPrincipal("admin"), "doc-1")
    assert unit_of_work.documents.get("doc-1").status == "archived"
    assert deleted_docs == ["doc-1"]  # vectors removed from retrieval

    # Step 2: Permanently delete the archived document
    service.delete_document(AuthenticatedPrincipal("admin"), "doc-1", permanent=True)
    assert unit_of_work.documents.get("doc-1") is None
    assert deleted_docs == ["doc-1", "doc-1"]


def test_archive_and_unarchive_document_restores_active_status():
    unit_of_work = InMemoryUnitOfWork(
        users=[User("admin", "Admin", "admin@example.com", "Admin", "d1")],
        documents=[],
    )
    service = DocumentManagementService(lambda: unit_of_work)
    service.register_document(AuthenticatedPrincipal("admin"), "doc-1", "Runbook", None)

    # Archive
    archived = service.archive_document(AuthenticatedPrincipal("admin"), "doc-1")
    assert archived.status == "archived"
    assert unit_of_work.documents.get("doc-1").status == "archived"

    # Unarchive
    unarchived = service.unarchive_document(AuthenticatedPrincipal("admin"), "doc-1")
    assert unarchived.status == "active"
    assert unit_of_work.documents.get("doc-1").status == "active"