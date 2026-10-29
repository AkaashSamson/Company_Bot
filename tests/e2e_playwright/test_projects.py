import uuid
import pytest
from playwright.sync_api import Page, expect
from tests.e2e_playwright.conftest import wait_for_streamlit_ready


def ensure_create_project_expander_open(page: Page):
    """Ensure the Create New Project expander is open and input fields are visible."""
    expander = page.locator("[data-testid='stExpander']", has_text="Create New Project")
    name_input = expander.locator("input[aria-label='Project Name *']")
    if not name_input.is_visible():
        expander.locator("summary").click()
        wait_for_streamlit_ready(page)
    expect(name_input).to_be_visible(timeout=10000)
    return expander


@pytest.mark.e2e
def test_admin_projects_page_renders_sections(authenticated_admin_page: Page, streamlit_url: str):
    """Test that the Projects page renders core administrative sections for admins."""
    page = authenticated_admin_page
    page.goto(f"{streamlit_url}/projects")
    wait_for_streamlit_ready(page)

    expect(page.locator("h1:has-text('Projects')")).to_be_visible(timeout=15000)
    expect(page.locator("h2:has-text('Project Administration')")).to_be_visible()
    expect(page.locator("[data-testid='stExpander'] summary:has-text('Create New Project')")).to_be_visible()
    expect(page.locator("h2:has-text('Project Details & Explorer')")).to_be_visible()


@pytest.mark.e2e
def test_create_project_validation(authenticated_admin_page: Page, streamlit_url: str):
    """Test that submitting an empty project name triggers a validation error."""
    page = authenticated_admin_page
    page.goto(f"{streamlit_url}/projects")
    wait_for_streamlit_ready(page)

    expander = ensure_create_project_expander_open(page)

    # Click Create Project with empty name
    submit_button = expander.locator("button:has-text('Create Project')")
    expect(submit_button).to_be_visible(timeout=10000)
    submit_button.click()

    wait_for_streamlit_ready(page)

    # Assert error alert is shown
    error_alert = page.locator("[data-testid='stAlert']")
    expect(error_alert).to_be_visible(timeout=10000)
    expect(error_alert).to_contain_text("Project Name is required.")


@pytest.mark.e2e
def test_create_project_successful(authenticated_admin_page: Page, streamlit_url: str):
    """Test creating a new project successfully as an administrator."""
    page = authenticated_admin_page
    page.goto(f"{streamlit_url}/projects")
    wait_for_streamlit_ready(page)

    expander = ensure_create_project_expander_open(page)

    project_name = f"Test Alpha {uuid.uuid4().hex[:6]}"
    name_input = expander.locator("input[aria-label='Project Name *']")
    name_input.fill(project_name)

    submit_button = expander.locator("button:has-text('Create Project')")
    submit_button.click()

    wait_for_streamlit_ready(page)

    # After successful creation and rerun, Total Projects metric is displayed
    expect(page.locator("text=Total Projects")).to_be_visible()
    # Ensure error alert is NOT present
    expect(page.locator("[data-testid='stAlert']")).to_have_count(0)


@pytest.mark.e2e
def test_employee_projects_page_renders_my_projects(authenticated_employee_page: Page, streamlit_url: str):
    """Test that standard employees see My Projects section."""
    page = authenticated_employee_page
    page.goto(f"{streamlit_url}/projects")
    wait_for_streamlit_ready(page)

    expect(page.locator("h1:has-text('Projects')")).to_be_visible(timeout=15000)
    expect(page.locator("h2:has-text('My Projects')")).to_be_visible()
