import pytest
from playwright.sync_api import Page, expect
from tests.e2e_playwright.conftest import wait_for_streamlit_ready


@pytest.mark.e2e
def test_employee_sidebar_hides_admin_links(authenticated_employee_page: Page):
    """Verify that a standard employee cannot see administrative navigation links in the sidebar."""
    page = authenticated_employee_page
    sidebar = page.locator("[data-testid='stSidebar']")

    # Allowed links for regular employee
    expect(sidebar.locator("a:has-text('Chat')")).to_be_visible(timeout=10000)
    expect(sidebar.locator("a:has-text('My Profile')")).to_be_visible()
    expect(sidebar.locator("a:has-text('Projects')")).to_be_visible()
    expect(sidebar.locator("a:has-text('Documents')")).to_be_visible()

    # Restricted admin links MUST NOT be visible
    expect(sidebar.locator("a:has-text('Users')")).to_have_count(0)
    expect(sidebar.locator("a:has-text('Departments')")).to_have_count(0)
    expect(sidebar.locator("a:has-text('Roles')")).to_have_count(0)


@pytest.mark.e2e
def test_admin_sidebar_shows_all_management_links(authenticated_admin_page: Page):
    """Verify that an administrator can see all administrative navigation links in the sidebar."""
    page = authenticated_admin_page
    sidebar = page.locator("[data-testid='stSidebar']")

    for item in ["Chat", "My Profile", "Projects", "Documents", "Users", "Departments", "Roles"]:
        expect(sidebar.locator(f"a:has-text('{item}')")).to_be_visible(timeout=10000)


@pytest.mark.e2e
def test_employee_direct_navigation_to_users_page_blocked(authenticated_employee_page: Page, streamlit_url: str):
    """Verify that a standard employee navigating directly to /users receives permission denied."""
    page = authenticated_employee_page
    page.goto(f"{streamlit_url}/users")
    wait_for_streamlit_ready(page)

    warning_msg = page.locator("text=You do not have permission to view users.")
    expect(warning_msg).to_be_visible(timeout=10000)


@pytest.mark.e2e
def test_employee_direct_navigation_to_roles_page_blocked(authenticated_employee_page: Page, streamlit_url: str):
    """Verify that a standard employee navigating directly to /roles receives permission denied."""
    page = authenticated_employee_page
    page.goto(f"{streamlit_url}/roles")
    wait_for_streamlit_ready(page)

    warning_msg = page.locator("text=You do not have permission to view roles.")
    expect(warning_msg).to_be_visible(timeout=10000)
