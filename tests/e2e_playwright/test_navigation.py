import pytest
from playwright.sync_api import Page, expect
from tests.e2e_playwright.conftest import wait_for_streamlit_ready


@pytest.mark.e2e
def test_admin_sidebar_navigation_items(authenticated_admin_page: Page):
    """Test that all administrative and navigation page links are displayed in the sidebar."""
    page = authenticated_admin_page
    sidebar = page.locator("[data-testid='stSidebar']")

    expected_links = [
        "Chat",
        "My Profile",
        "Projects",
        "Documents",
        "Users",
        "Departments",
        "Roles",
    ]

    for link_text in expected_links:
        link_elem = sidebar.locator(f"a:has-text('{link_text}')")
        expect(link_elem).to_be_visible(timeout=10000)


@pytest.mark.e2e
def test_navigate_to_profile(authenticated_admin_page: Page):
    """Test navigating to the My Profile page."""
    page = authenticated_admin_page
    sidebar = page.locator("[data-testid='stSidebar']")

    sidebar.locator("a:has-text('My Profile')").click()
    wait_for_streamlit_ready(page)

    profile_title = page.locator("h1:has-text('My Profile')")
    expect(profile_title).to_be_visible(timeout=15000)

    personal_info = page.locator("text=Personal Information")
    expect(personal_info).to_be_visible()


@pytest.mark.e2e
def test_navigate_to_projects(authenticated_admin_page: Page):
    """Test navigating to the Projects page."""
    page = authenticated_admin_page
    sidebar = page.locator("[data-testid='stSidebar']")

    sidebar.locator("a:has-text('Projects')").click()
    wait_for_streamlit_ready(page)

    projects_title = page.locator("h1:has-text('Projects')")
    expect(projects_title).to_be_visible(timeout=15000)


@pytest.mark.e2e
def test_navigate_to_documents(authenticated_admin_page: Page):
    """Test navigating to the Documents page."""
    page = authenticated_admin_page
    sidebar = page.locator("[data-testid='stSidebar']")

    sidebar.locator("a:has-text('Documents')").click()
    wait_for_streamlit_ready(page)

    documents_title = page.locator("h1:has-text('Documents')")
    expect(documents_title).to_be_visible(timeout=15000)


@pytest.mark.e2e
def test_navigate_back_to_chat(authenticated_admin_page: Page):
    """Test returning back to the Chat page from another page."""
    page = authenticated_admin_page
    sidebar = page.locator("[data-testid='stSidebar']")

    # Go to Projects first
    sidebar.locator("a:has-text('Projects')").click()
    wait_for_streamlit_ready(page)
    expect(page.locator("h1:has-text('Projects')")).to_be_visible(timeout=15000)

    # Return to Chat
    sidebar.locator("a:has-text('Chat')").click()
    wait_for_streamlit_ready(page)
    expect(page.locator("h1:has-text('KnowLayer HR Policy Assistant')")).to_be_visible(timeout=15000)


@pytest.mark.e2e
def test_navigate_to_organization_explorer(authenticated_admin_page: Page, streamlit_url: str):
    """Test navigating to the Organization Explorer page."""
    page = authenticated_admin_page
    page.goto(f"{streamlit_url}/explorer")
    wait_for_streamlit_ready(page)

    explorer_title = page.locator("h1:has-text('Organization Explorer')")
    expect(explorer_title).to_be_visible(timeout=15000)

