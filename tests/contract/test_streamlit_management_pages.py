from pathlib import Path


ROOT = Path(__file__).parents[2]


def _navigation_source():
    app_source = (ROOT / "streamlit_app" / "app.py").read_text(encoding="utf-8")
    sidebar_path = ROOT / "streamlit_app" / "sidebar.py"
    if sidebar_path.exists():
        app_source += "\n" + sidebar_path.read_text(encoding="utf-8")
    return app_source


def test_management_pages_use_http_services_and_shared_api_base_url():
    nav_source = _navigation_source()
    for page_name, service_name in {
        "users.py": "OrganizationService",
        "projects.py": "OrganizationService",
        "documents.py": "DocumentService",
    }.items():
        page_source = (ROOT / "streamlit_app" / "pages" / page_name).read_text(encoding="utf-8")
        assert service_name in page_source
        assert "sqlite" not in page_source.lower()
    assert "STREAMLIT_API_BASE_URL" in (ROOT / "streamlit_app" / "services" / "chat_service.py").read_text(encoding="utf-8")
    assert all(f'page_link("pages/{page_name}"' in nav_source for page_name in ("users.py", "projects.py", "documents.py"))


def test_admin_pages_are_http_clients_without_local_persistence():
    admin_pages = ("departments.py", "roles.py")
    for page_name in admin_pages:
        page_source = (ROOT / "streamlit_app" / "pages" / page_name).read_text(encoding="utf-8")
        assert "AdminAPI" in page_source
        assert "sqlite" not in page_source.lower()
        assert "STREAMLIT_API_BASE_URL" in (
            ROOT / "streamlit_app" / "services" / "admin_api.py"
        ).read_text(encoding="utf-8")

    nav_source = _navigation_source()
    for page_name in admin_pages:
        assert f'page_link("pages/{page_name}"' in nav_source


def test_admin_api_client_covers_admin_endpoints():
    api_source = (ROOT / "streamlit_app" / "services" / "admin_api.py").read_text(encoding="utf-8")
    for method in (
        "list_users",
        "create_user",
        "update_user",
        "deactivate_user",
        "list_department_members",
        "assign_department_member",
        "update_department_member",
        "create_role",
        "update_role",
        "delete_role",
        "set_role_permissions",
        "list_role_permissions",
        "list_permissions",
        "list_project_members",
        "update_project",
        "list_project_documents",
        "list_document_access_grants",
        "grant_document_access",
        "revoke_document_access",
    ):
        assert f"def {method}" in api_source


def test_profile_page_is_a_thin_read_only_http_client():
    page_source = (ROOT / "streamlit_app" / "pages" / "profile.py").read_text(encoding="utf-8")
    api_source = (ROOT / "streamlit_app" / "services" / "profile_api.py").read_text(encoding="utf-8")

    assert "ProfileAPI" in page_source
    assert "sqlite" not in page_source.lower()
    assert "STREAMLIT_API_BASE_URL" in api_source
    assert "leave_project" in api_source
    assert "profile" in api_source

    assert "can_" not in page_source
    assert "has_permission" not in page_source
    assert "AuthorizationEngine" not in page_source

    nav_source = _navigation_source()
    assert 'page_link("pages/profile.py"' in nav_source


def test_organization_explorer_page_is_a_read_only_http_client():
    page_source = (ROOT / "streamlit_app" / "pages" / "explorer.py").read_text(encoding="utf-8")
    api_source = (ROOT / "streamlit_app" / "services" / "explorer_api.py").read_text(encoding="utf-8")

    assert "ExplorerAPI" in page_source
    assert "sqlite" not in page_source.lower()
    assert "STREAMLIT_API_BASE_URL" in api_source
    assert "def organization" in api_source

    assert "can_" not in page_source
    assert "has_permission" not in page_source
    assert "AuthorizationEngine" not in page_source
    assert "access_token" in api_source
