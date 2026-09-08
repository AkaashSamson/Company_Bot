from app.db.documents_repository import (
    doc_to_document,
    document_to_doc,
)
from app.db.roles_repository import doc_to_role, role_to_doc
from app.db.users_repository import doc_to_user, user_to_doc
from app.domain.entities.access_models import (
    DocumentModel,
    RoleModel,
    UserModel,
)


def test_role_roundtrip_preserves_fields():
    role = RoleModel(
        code="manager",
        name="Manager",
        description="Team manager",
        is_system=True,
    )
    doc = role_to_doc(role)
    restored = doc_to_role(doc)
    assert restored.code == "manager"
    assert restored.name == "Manager"
    assert restored.description == "Team manager"
    assert restored.is_system is True


def test_user_roundtrip_preserves_fields():
    user = UserModel(
        employee_id="MSS001",
        first_name="Alice",
        last_name="Bond",
        email="alice.bond@mclarensv.com",
        role_code="developer",
        password_hash="h",
        is_active=True,
        extra={"team": "platform"},
    )
    doc = user_to_doc(user)
    restored = doc_to_user(doc)
    assert restored.employee_id == "MSS001"
    assert restored.email == "alice.bond@mclarensv.com"
    assert restored.role_code == "developer"
    assert restored.first_name == "Alice"
    assert restored.last_name == "Bond"
    assert restored.extra == {"team": "platform"}


def test_document_roundtrip_preserves_access_policy():
    doc_model = DocumentModel(
        document_id="DOC001",
        filename="policy.docx",
        owner_user_id="MSS001",
        allowed_role_codes=["manager"],
        allowed_user_ids=["MSS002"],
        metadata={"section": "Policy"},
    )
    doc = document_to_doc(doc_model)
    restored = doc_to_document(doc)
    assert restored.document_id == "DOC001"
    assert restored.owner_user_id == "MSS001"
    assert restored.allowed_role_codes == ["manager"]
    assert restored.allowed_user_ids == ["MSS002"]
    assert restored.metadata == {"section": "Policy"}