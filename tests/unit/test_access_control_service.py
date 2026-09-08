from app.domain.entities.access_models import AccessPolicy
from app.use_cases.access.access_control_service import AccessControlService


def _policy(**kwargs):
    base = {
        "document_id": "d1",
        "owner_user_id": "owner",
        "allowed_role_codes": [],
        "allowed_user_ids": [],
    }
    base.update(kwargs)
    return AccessPolicy(**base)


def test_owner_can_access_own_document():
    policy = _policy(owner_user_id="alice")
    assert AccessControlService.can_access(policy, "alice", "developer")


def test_explicit_user_grants_access():
    policy = _policy(allowed_user_ids=["bob"])
    assert AccessControlService.can_access(policy, "bob", "developer")


def test_role_grant_grants_access():
    policy = _policy(allowed_role_codes=["manager"])
    assert AccessControlService.can_access(policy, "carol", "manager")


def test_unauthorized_user_is_denied():
    policy = _policy(allowed_role_codes=["manager"])
    assert not AccessControlService.can_access(policy, "dave", "developer")


def test_denied_when_no_user_id():
    policy = _policy(owner_user_id="alice")
    assert not AccessControlService.can_access(policy, None, "developer")


def test_build_chroma_where_restricts_to_document_ids():
    where = AccessControlService.build_chroma_where(["DOC001", "DOC004", "DOC004"])
    assert where == {"document_id": {"$in": ["DOC001", "DOC004"]}}


def test_build_chroma_where_none_for_empty_list():
    assert AccessControlService.build_chroma_where([]) is None
    assert AccessControlService.build_chroma_where(None) is None


def test_normalize_allow_lists_deduplicates():
    result = AccessControlService.normalize_allow_lists(
        ["manager", "manager", "developer"],
        ["bob", "alice", "bob"],
    )
    assert result["allowed_role_codes"] == ["manager", "developer"]
    assert result["allowed_user_ids"] == ["bob", "alice"]