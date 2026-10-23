def check_domain_view_access(permissions: set[str], domain: str) -> bool:
    if "*" in permissions or "ADMIN" in permissions:
        return True
    domain_perms = {p for p in permissions if p.startswith(domain.upper())}
    return len(domain_perms) > 0

def test_write_implies_read():
    # User with only USER_CREATE must have view access to users page
    user_perms = {"USER_CREATE"}
    assert check_domain_view_access(user_perms, "USER") is True
    assert check_domain_view_access(user_perms, "DEPARTMENT") is False

    # Dept lead with DEPARTMENT_ASSIGN_USERS has view access to departments
    dept_perms = {"DEPARTMENT_ASSIGN_USERS"}
    assert check_domain_view_access(dept_perms, "DEPARTMENT") is True

    # Role admin with only ROLE_UPDATE has view access to roles
    role_perms = {"ROLE_UPDATE"}
    assert check_domain_view_access(role_perms, "ROLE") is True
    assert check_domain_view_access(role_perms, "USER") is False
