import pytest

from app.domain.entities.organization_models import DepartmentMember, User
from app.domain.services.organization_errors import ConflictError, ForbiddenError, NotFoundError
from app.domain.services.permission_catalog import ALL_PERMISSION_NAMES
from tests.fixtures.rbac import build_rbac_context


def _permission_id(unit_of_work, name):
    return unit_of_work.permissions.get_by_name(name).permission_id


def _role_id(unit_of_work, name):
    return unit_of_work.roles.get_by_name(name).role_id


def test_seed_provisions_configurable_catalog():
    _, unit_of_work = build_rbac_context()

    names = {permission.name for permission in unit_of_work.permissions.list()}
    assert names == set(ALL_PERMISSION_NAMES)
    role_names = {role.name for role in unit_of_work.roles.list()}
    assert {"Admin", "Manager", "Developer", "Tester", "Solution Architect"} <= role_names
    assert all(role.scope == "global" for role in unit_of_work.roles.list())


def test_seed_is_idempotent():
    from app.infrastructure.persistence.rbac_seed import seed_rbac

    _, unit_of_work = build_rbac_context()
    permission_count = len(unit_of_work.permissions.list())
    role_count = len(unit_of_work.roles.list())

    result = seed_rbac(lambda: unit_of_work)

    assert result == {"permissions_created": 0, "roles_created": 0}
    assert len(unit_of_work.permissions.list()) == permission_count
    assert len(unit_of_work.roles.list()) == role_count


def test_seeded_admin_role_has_every_permission():
    _, unit_of_work = build_rbac_context()
    admin_role = unit_of_work.roles.get_by_name("Admin")

    granted = {permission.name for permission in unit_of_work.roles.permissions_for_role(admin_role.role_id)}
    assert granted == set(ALL_PERMISSION_NAMES)


def test_admin_can_create_global_role_with_permission_checkboxes():
    service, unit_of_work = build_rbac_context()
    view_id = _permission_id(unit_of_work, "USER_VIEW")
    create_id = _permission_id(unit_of_work, "USER_CREATE")

    role = service.create_role("admin", "Release Manager", "Manages releases", permission_ids=[view_id, create_id])

    assert role.role_id is not None
    assert role.scope == "global"
    assert role.created_by_uid == "admin"
    granted = {permission.name for permission in unit_of_work.roles.permissions_for_role(role.role_id)}
    assert granted == {"USER_VIEW", "USER_CREATE"}


def test_new_roles_can_be_created_later():
    service, unit_of_work = build_rbac_context()

    first = service.create_role("admin", "Auditor", "Read-only auditor", permission_ids=[])
    second = service.create_role("admin", "Support", "Support desk", permission_ids=[])

    assert unit_of_work.roles.get(first.role_id).name == "Auditor"
    assert unit_of_work.roles.get(second.role_id).name == "Support"


def test_admin_can_create_department_specific_role():
    service, unit_of_work = build_rbac_context()

    role = service.create_role("admin", "Engineering Manager", "Engineering lead", scope="department", department_id="d1")

    assert role.scope == "department"
    assert role.department_id == "d1"


def test_duplicate_role_name_is_rejected():
    service, _ = build_rbac_context()
    service.create_role("admin", "Auditor", "Read-only auditor")

    with pytest.raises(ConflictError):
        service.create_role("admin", "Auditor", "Another auditor")


def test_manager_can_create_department_role_within_scope():
    service, unit_of_work = build_rbac_context()

    role = service.create_role("mgr", "Senior Developer", "Senior engineer", scope="department", department_id="d1")

    assert role.department_id == "d1"
    assert role.created_by_uid == "mgr"


def test_manager_cannot_create_global_role():
    service, _ = build_rbac_context()

    with pytest.raises(ForbiddenError):
        service.create_role("mgr", "Global Auditor", "Global", scope="global")


def test_manager_cannot_create_role_for_other_department():
    service, _ = build_rbac_context()

    with pytest.raises(ForbiddenError):
        service.create_role("mgr", "QA Lead", "QA", scope="department", department_id="d2")


def test_department_role_requires_department_id():
    service, _ = build_rbac_context()

    with pytest.raises(ValueError):
        service.create_role("admin", "Floating Role", "Missing department", scope="department")


def test_invalid_scope_is_rejected():
    service, _ = build_rbac_context()

    with pytest.raises(ValueError):
        service.create_role("admin", "Bad Scope", "Invalid", scope="team")


def test_create_role_rejects_unknown_permission():
    service, _ = build_rbac_context()

    with pytest.raises(NotFoundError):
        service.create_role("admin", "Badged", "Invalid permission", permission_ids=[9999])


def test_manager_cannot_manage_role_in_other_department():
    service, _ = build_rbac_context()
    role = service.create_role("admin", "QA Lead", "QA", scope="department", department_id="d2")

    with pytest.raises(ForbiddenError):
        service.set_role_permissions("mgr", role.role_id, [])


def test_set_role_permissions_uses_checkbox_semantics():
    service, unit_of_work = build_rbac_context()
    role = service.create_role("admin", "Auditor", "Auditor")
    view_id = _permission_id(unit_of_work, "USER_VIEW")
    create_id = _permission_id(unit_of_work, "USER_CREATE")
    delete_id = _permission_id(unit_of_work, "USER_DELETE")

    service.set_role_permissions("admin", role.role_id, [view_id, create_id])
    service.set_role_permissions("admin", role.role_id, [create_id, delete_id])

    granted = {permission.name for permission in service.list_role_permissions("admin", role.role_id)}
    assert granted == {"USER_CREATE", "USER_DELETE"}


def test_create_permission_is_configurable_and_validated():
    service, unit_of_work = build_rbac_context()

    permission = service.create_permission("admin", "REPORT_EXPORT", "Export reports")
    assert permission.name == "REPORT_EXPORT"
    assert unit_of_work.permissions.get_by_name("REPORT_EXPORT") is not None

    with pytest.raises(ConflictError):
        service.create_permission("admin", "REPORT_EXPORT", "Duplicate")
    with pytest.raises(ValueError):
        service.create_permission("admin", "lowercase", "Invalid")


def test_delete_role_rejected_when_assigned_to_user():
    service, unit_of_work = build_rbac_context()
    role = service.create_role("admin", "Auditor", "Auditor")
    unit_of_work.users.save(User("u1", "Aud", "aud@example.com", "Auditor", "d1"))

    with pytest.raises(ConflictError):
        service.delete_role("admin", role.role_id)


def test_delete_unassigned_role_succeeds():
    service, unit_of_work = build_rbac_context()
    role = service.create_role("admin", "Auditor", "Auditor")

    service.delete_role("admin", role.role_id)

    assert unit_of_work.roles.get(role.role_id) is None


def test_manager_listing_hides_other_department_roles():
    service, unit_of_work = build_rbac_context()
    service.create_role("admin", "Global Auditor", "Global")
    service.create_role("admin", "Engineering Lead", "Eng", scope="department", department_id="d1")
    service.create_role("admin", "QA Lead", "QA", scope="department", department_id="d2")

    names = {role.name for role in service.list_roles("mgr")}

    assert "Global Auditor" in names
    assert "Engineering Lead" in names
    assert "QA Lead" not in names


def test_update_role_rejects_duplicate_name():
    service, _ = build_rbac_context()
    service.create_role("admin", "Auditor", "Auditor")
    other = service.create_role("admin", "Reviewer", "Reviewer")

    with pytest.raises(ConflictError):
        service.update_role("admin", other.role_id, {"name": "Auditor"})


def test_effective_permissions_reflect_assigned_role():
    service, _ = build_rbac_context(users=[User("dev", "Dev", "dev@example.com", "Developer", "d1")])

    permissions = service.effective_permissions("admin", "dev")

    assert "DOCUMENT_VIEW" in permissions
    assert "USER_CREATE" not in permissions


def test_department_role_membership_grants_permissions():
    service, unit_of_work = build_rbac_context(users=[User("dev", "Dev", "dev@example.com", "Developer", "d1")])
    create_id = _permission_id(unit_of_work, "USER_CREATE")
    service.create_role("admin", "Engineering Lead", "Eng lead", scope="department", department_id="d1", permission_ids=[create_id])
    unit_of_work.department_members.save(DepartmentMember("dev", "d1", membership_role="Engineering Lead"))

    permissions = service.effective_permissions("admin", "dev")

    assert "USER_CREATE" in permissions
