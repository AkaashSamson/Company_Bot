from app.domain.entities.access_models import DocumentModel, UserModel
from app.use_cases.access.authorization_service import (
    AuthorizationError,
    AuthorizationService,
)


class StubUsersRepository:
    def __init__(self, users=None):
        self.users = users or {}

    def get_by_employee_id(self, employee_id):
        return self.users.get(employee_id)


class StubDocumentsRepository:
    def __init__(self, documents=None):
        self.documents = documents or []

    def list_accessible(self, employee_id, role_code=None):
        found = []
        for doc in self.documents:
            if doc.owner_user_id == employee_id:
                found.append(doc)
            elif employee_id in doc.allowed_user_ids:
                found.append(doc)
            elif role_code and role_code in doc.allowed_role_codes:
                found.append(doc)
        return found


ACTIVE_MANAGER = UserModel(
    employee_id="MSS001",
    first_name="Ro",
    last_name="Ya",
    email="ro.ya@mclarensv.com",
    role_code="manager",
    password_hash="h",
    is_active=True,
)

INACTIVE_DEVELOPER = UserModel(
    employee_id="MSS002",
    first_name="De",
    last_name="V",
    email="de.v@mclarensv.com",
    role_code="developer",
    password_hash="h",
    is_active=False,
)


def _doc(document_id, owner="MSS099", roles=None, users=None):
    return DocumentModel(
        document_id=document_id,
        filename=f"{document_id}.txt",
        owner_user_id=owner,
        allowed_role_codes=roles or [],
        allowed_user_ids=users or [],
    )


def test_unknown_user_raises():
    service = AuthorizationService(users=StubUsersRepository(), documents=StubDocumentsRepository())
    try:
        service.get_accessible_document_ids("MSS999")
        assert False, "expected AuthorizationError"
    except AuthorizationError:
        pass


def test_inactive_user_raises():
    service = AuthorizationService(
        users=StubUsersRepository({"MSS002": INACTIVE_DEVELOPER}),
        documents=StubDocumentsRepository(),
    )
    try:
        service.get_accessible_document_ids("MSS002")
        assert False, "expected AuthorizationError"
    except AuthorizationError:
        pass


def test_role_based_access_provides_documents():
    docs = [
        _doc("DOC001", roles=["manager"]),
        _doc("DOC002", roles=["developer"]),
    ]
    service = AuthorizationService(
        users=StubUsersRepository({"MSS001": ACTIVE_MANAGER}),
        documents=StubDocumentsRepository(docs),
    )
    assert service.get_accessible_document_ids("MSS001") == ["DOC001"]


def test_employee_specific_access_ignores_role_denial():
    docs = [
        _doc("DOC002", roles=["manager"]),
        _doc("DOC003", users=["MSS001"]),
    ]
    service = AuthorizationService(
        users=StubUsersRepository({"MSS001": ACTIVE_MANAGER}),
        documents=StubDocumentsRepository(docs),
    )
    # The manager passes on role for DOC002 and direct grant for DOC003.
    ids = service.get_accessible_document_ids("MSS001")
    assert sorted(ids) == ["DOC002", "DOC003"]


def test_owner_is_implicitly_authorized():
    docs = [
        _doc("DOC009", owner="MSS001", roles=[]),
    ]
    service = AuthorizationService(
        users=StubUsersRepository({"MSS001": ACTIVE_MANAGER}),
        documents=StubDocumentsRepository(docs),
    )
    assert service.get_accessible_document_ids("MSS001") == ["DOC009"]


def test_results_are_deduplicated():
    docs = [
        _doc("DOC010", owner="MSS001", roles=["manager"], users=["MSS001"]),
        _doc("DOC011", roles=["manager"]),
        _doc("DOC012", users=["MSS001"]),
    ]
    service = AuthorizationService(
        users=StubUsersRepository({"MSS001": ACTIVE_MANAGER}),
        documents=StubDocumentsRepository(docs),
    )
    ids = service.get_accessible_document_ids("MSS001")
    assert ids == ["DOC010", "DOC011", "DOC012"]
    assert len(ids) == len(set(ids))


def test_document_ids_authorized_filters_out_denied():
    docs = [
        _doc("DOC001", roles=["manager"]),
        _doc("DOC002", roles=["developer"]),
    ]
    service = AuthorizationService(
        users=StubUsersRepository({"MSS001": ACTIVE_MANAGER}),
        documents=StubDocumentsRepository(docs),
    )
    assert service.document_ids_authorized("MSS001", ["DOC001", "DOC002", "DOC999"]) == ["DOC001"]


def test_document_ids_authorized_empty_for_bad_user():
    service = AuthorizationService(users=StubUsersRepository(), documents=StubDocumentsRepository())
    assert service.document_ids_authorized("MSS999", ["DOC001"]) == []