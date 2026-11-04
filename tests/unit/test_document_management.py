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


def test_duplicate_file_hash_rejection_cites_existing_name():
    import base64
    content = base64.b64encode(b"# Apollo Blueprint\nArchitecture details").decode()
    unit_of_work = InMemoryUnitOfWork(
        users=[User("elena", "Elena", "elena@example.com", "Manager", "d1")],
        departments=[Department("d1", "Engineering")],
        projects=[Project("p-apollo", "Apollo", "d1", manager_uid="elena")],
        documents=[],
    )
    service = DocumentManagementService(lambda: unit_of_work)

    # 1. First upload succeeds
    doc = service.register_document(
        AuthenticatedPrincipal("elena"),
        document_name="apollo_blueprint.md",
        project_id="p-apollo",
        content=content,
    )
    assert doc.status == "active"
    assert doc.version == "1.0"

    # 2. Re-upload identical file (same name & content) is rejected citing existing name
    try:
        service.register_document(
            AuthenticatedPrincipal("elena"),
            document_name="apollo_blueprint.md",
            project_id="p-apollo",
            content=content,
        )
    except Exception as err:
        assert "Identical file content already exists in this project with name 'apollo_blueprint.md'" in str(err)
    else:
        raise AssertionError("Exact duplicate upload must be rejected")

    # 3. Renamed copy (different name, same content) is rejected citing original name
    try:
        service.register_document(
            AuthenticatedPrincipal("elena"),
            document_name="apollo_copy.md",
            project_id="p-apollo",
            content=content,
        )
    except Exception as err:
        assert "Identical file content already exists in this project with name 'apollo_blueprint.md'" in str(err)
    else:
        raise AssertionError("Renamed duplicate upload must be rejected")


def test_filename_collision_replacement_and_version_bump():
    import base64
    content_v1 = base64.b64encode(b"Version 1 content").decode()
    content_v2 = base64.b64encode(b"Version 2 updated content").decode()
    unit_of_work = InMemoryUnitOfWork(
        users=[User("elena", "Elena", "elena@example.com", "Manager", "d1")],
        departments=[Department("d1", "Engineering")],
        projects=[Project("p-apollo", "Apollo", "d1", manager_uid="elena")],
        documents=[],
    )
    service = DocumentManagementService(lambda: unit_of_work)

    doc1 = service.register_document(
        AuthenticatedPrincipal("elena"),
        document_name="apollo_blueprint.md",
        project_id="p-apollo",
        content=content_v1,
    )
    assert doc1.version == "1.0"

    # Uploading different content with same name without replace_existing -> rejected
    try:
        service.register_document(
            AuthenticatedPrincipal("elena"),
            document_name="apollo_blueprint.md",
            project_id="p-apollo",
            content=content_v2,
            replace_existing=False,
        )
    except Exception as err:
        assert "Document 'apollo_blueprint.md' already exists in this project. Confirm replacement to overwrite it." in str(err)
    else:
        raise AssertionError("Filename collision without replace_existing must be rejected")

    # Uploading different content with replace_existing=True -> old deleted, new registered at 1.0
    doc2 = service.register_document(
        AuthenticatedPrincipal("elena"),
        document_name="apollo_blueprint.md",
        project_id="p-apollo",
        content=content_v2,
        replace_existing=True,
    )
    assert doc2.version == "1.0"
    assert doc1.document_id != doc2.document_id
    assert unit_of_work.documents.get(doc1.document_id) is None


def test_unassigned_document_deduplication_and_collision():
    import base64
    from unittest.mock import MagicMock
    content_v1 = base64.b64encode(b"Unassigned initial content").decode()
    content_v2 = base64.b64encode(b"Unassigned revised content").decode()
    unit_of_work = InMemoryUnitOfWork(
        users=[User("admin", "Admin", "admin@example.com", "Admin", None)],
        departments=[],
        projects=[],
        documents=[],
    )
    service = DocumentManagementService(lambda: unit_of_work)

    doc1 = service.register_document(
        AuthenticatedPrincipal("admin"),
        document_name="testingdocx.docx",
        project_id=None,
        content=content_v1,
    )
    assert doc1.version == "1.0"

    # Re-upload same hash in unassigned scope -> rejected
    try:
        service.register_document(
            AuthenticatedPrincipal("admin"),
            document_name="another_copy.docx",
            project_id=None,
            content=content_v1,
        )
    except Exception as err:
        assert "Identical file content already exists in unassigned documents with name 'testingdocx.docx'" in str(err)
    else:
        raise AssertionError("Duplicate unassigned file hash must be rejected")

    # Upload different content with same name in unassigned scope -> rejected
    try:
        service.register_document(
            AuthenticatedPrincipal("admin"),
            document_name="testingdocx.docx",
            project_id=None,
            content=content_v2,
            replace_existing=False,
        )
    except Exception as err:
        assert "Document 'testingdocx.docx' already exists in unassigned documents. Confirm replacement to overwrite it." in str(err)
    else:
        raise AssertionError("Unassigned filename collision without replace must be rejected")

    # Upload with replace_existing=True in unassigned scope -> old purged, new created at 1.0
    doc2 = service.register_document(
        AuthenticatedPrincipal("admin"),
        document_name="testingdocx.docx",
        project_id=None,
        content=content_v2,
        replace_existing=True,
    )
    assert doc2.version == "1.0"
    assert doc1.document_id != doc2.document_id
    assert unit_of_work.documents.get(doc1.document_id) is None
