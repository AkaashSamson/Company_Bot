from app.domain.entities.organization_models import DepartmentMember, User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_service import OrganizationAuthorizationService
from tests.fixtures.rbac import build_rbac_context


def test_admin_has_every_permission_including_unknown():
    _, unit_of_work = build_rbac_context()
    service = OrganizationAuthorizationService(unit_of_work)
    principal = AuthenticatedPrincipal("admin")

    assert service.has_permission(principal, "DOCUMENT_DELETE") is True
    assert service.has_permission(principal, "NOT_IN_THE_CATALOG") is True


def test_permission_is_db_driven_not_hard_coded():
    _, unit_of_work = build_rbac_context(users=[User("dev", "Dev", "dev@example.com", "Developer", "d1")])
    service = OrganizationAuthorizationService(unit_of_work)
    principal = AuthenticatedPrincipal("dev")

    assert service.has_permission(principal, "DOCUMENT_VIEW") is True
    assert service.has_permission(principal, "USER_CREATE") is False

    developer = unit_of_work.roles.get_by_name("Developer")
    create_id = unit_of_work.permissions.get_by_name("USER_CREATE").permission_id
    current = [permission.permission_id for permission in unit_of_work.roles.permissions_for_role(developer.role_id)]
    unit_of_work.roles.set_permissions(developer.role_id, current + [create_id])

    assert service.has_permission(principal, "USER_CREATE") is True


def test_department_scoped_role_permission_is_scoped():
    role_service, unit_of_work = build_rbac_context(users=[
        User("eng", "Eng", "eng@example.com", "Engineering Lead", "d1"),
        User("outsider", "Out", "out@example.com", "Engineering Lead", "d2"),
    ])
    create_id = unit_of_work.permissions.get_by_name("USER_CREATE").permission_id
    role_service.create_role(
        "admin", "Engineering Lead", "Engineering lead",
        scope="department", department_id="d1", permission_ids=[create_id],
    )
    service = OrganizationAuthorizationService(unit_of_work)

    assert service.has_permission(AuthenticatedPrincipal("eng"), "USER_CREATE") is True
    assert service.has_permission(AuthenticatedPrincipal("outsider"), "USER_CREATE") is False


def test_inactive_user_has_no_permissions():
    _, unit_of_work = build_rbac_context(users=[User("dev", "Dev", "dev@example.com", "Developer", "d1", status="inactive")])
    service = OrganizationAuthorizationService(unit_of_work)

    assert service.permissions_for_user("dev") == set()
    assert service.has_permission(AuthenticatedPrincipal("dev"), "DOCUMENT_VIEW") is False


def test_unknown_user_has_no_permissions():
    _, unit_of_work = build_rbac_context()
    service = OrganizationAuthorizationService(unit_of_work)

    assert service.permissions_for_user("ghost") == set()
    assert service.has_permission(AuthenticatedPrincipal("ghost"), "DOCUMENT_VIEW") is False


def test_roles_for_user_resolves_named_and_membership_roles():
    role_service, unit_of_work = build_rbac_context(users=[User("dev", "Dev", "dev@example.com", "Developer", "d1")])
    service = OrganizationAuthorizationService(unit_of_work)

    assert "Developer" in {role.name for role in service.roles_for_user("dev")}

    role_service.create_role("admin", "Engineering Lead", "Eng lead", scope="department", department_id="d1")
    unit_of_work.department_members.save(DepartmentMember("dev", "d1", membership_role="Engineering Lead"))

    assert "Engineering Lead" in {role.name for role in service.roles_for_user("dev")}


def test_can_manage_role_respects_scope():
    role_service, unit_of_work = build_rbac_context()
    service = OrganizationAuthorizationService(unit_of_work)
    global_role = unit_of_work.roles.get_by_name("Developer")
    engineering_role = role_service.create_role("admin", "Engineering Lead", "Eng lead", scope="department", department_id="d1")
    qa_role = role_service.create_role("admin", "QA Lead", "QA lead", scope="department", department_id="d2")

    assert service.can_manage_role(AuthenticatedPrincipal("admin"), global_role) is True
    assert service.can_manage_role(AuthenticatedPrincipal("mgr"), global_role) is False
    assert service.can_manage_role(AuthenticatedPrincipal("mgr"), engineering_role) is True
    assert service.can_manage_role(AuthenticatedPrincipal("mgr"), qa_role) is False
