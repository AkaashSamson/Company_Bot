import uuid
import pytest
from playwright.sync_api import Page, expect
from tests.e2e_playwright.conftest import wait_for_streamlit_ready


@pytest.mark.e2e
def test_admin_can_view_users_page(authenticated_admin_page: Page, streamlit_url: str):
    """Test that administrator can access the Users management page and see the add user expander."""
    page = authenticated_admin_page
    page.goto(f"{streamlit_url}/users")
    wait_for_streamlit_ready(page)

    expect(page.locator("h1:has-text('Users')")).to_be_visible(timeout=15000)
    add_user_expander = page.locator("[data-testid='stExpander'] summary:has-text('Add User')")
    expect(add_user_expander).to_be_visible()


@pytest.mark.e2e
def test_admin_create_user_validation(authenticated_admin_page: Page, streamlit_url: str):
    """Test validation errors when creating a user with missing required fields."""
    page = authenticated_admin_page
    page.goto(f"{streamlit_url}/users")
    wait_for_streamlit_ready(page)

    # Expand the Add User section
    page.locator("[data-testid='stExpander'] summary:has-text('Add User')").click()
    wait_for_streamlit_ready(page)

    # Click submit without entering required name and email
    create_button = page.locator("button:has-text('Create user')")
    expect(create_button).to_be_visible(timeout=10000)
    create_button.click()

    wait_for_streamlit_ready(page)

    error_alert = page.locator("[data-testid='stAlert']")
    expect(error_alert).to_be_visible(timeout=10000)
    expect(error_alert).to_contain_text("Name and Email are required.")


@pytest.mark.e2e
def test_admin_create_department(authenticated_admin_page: Page, streamlit_url: str):
    """Test creating a new department via the Departments admin page."""
    page = authenticated_admin_page
    page.goto(f"{streamlit_url}/departments")
    wait_for_streamlit_ready(page)

    expect(page.locator("h1:has-text('Departments')")).to_be_visible(timeout=15000)

    # Open Create Department expander
    page.locator("[data-testid='stExpander'] summary:has-text('Create Department')").click()
    wait_for_streamlit_ready(page)

    dept_name = f"QA Dept {uuid.uuid4().hex[:6]}"
    name_input = page.locator("input[aria-label='Department name *']")
    expect(name_input).to_be_visible(timeout=10000)
    name_input.fill(dept_name)

    submit_button = page.locator("button:has-text('Create department')")
    submit_button.click()

    wait_for_streamlit_ready(page)

    # Check that no error alert was produced and department appears in dropdown options
    expect(page.locator("[data-testid='stAlert'][data-test-type='error']")).to_have_count(0)
    inspect_select = page.get_by_role("combobox", name="Select Department to inspect")
    expect(inspect_select).to_be_visible()
    inspect_select.click()
    expect(page.get_by_role("option", name=dept_name)).to_be_visible()


@pytest.mark.e2e
def test_admin_roles_and_permissions_page(authenticated_admin_page: Page, streamlit_url: str):
    """Test that the Roles & Permissions page properly renders for administrators."""
    page = authenticated_admin_page
    page.goto(f"{streamlit_url}/roles")
    wait_for_streamlit_ready(page)

    expect(page.locator("h1:has-text('Roles & Permissions')")).to_be_visible(timeout=15000)
    expect(page.locator("[data-testid='stExpander'] summary:has-text('Create Role')")).to_be_visible()
