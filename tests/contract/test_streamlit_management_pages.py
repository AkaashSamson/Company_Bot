from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_management_pages_use_http_services_and_shared_api_base_url():
    app_source = (ROOT / "streamlit_app" / "app.py").read_text(encoding="utf-8")
    for page_name, service_name in {
        "users.py": "OrganizationService",
        "projects.py": "OrganizationService",
        "documents.py": "DocumentService",
    }.items():
        page_source = (ROOT / "streamlit_app" / "pages" / page_name).read_text(encoding="utf-8")
        assert service_name in page_source
        assert "sqlite" not in page_source.lower()
    assert "STREAMLIT_API_BASE_URL" in (ROOT / "streamlit_app" / "services" / "chat_service.py").read_text(encoding="utf-8")
    assert all(f'page_link("pages/{page_name}"' in app_source for page_name in ("users.py", "projects.py", "documents.py"))