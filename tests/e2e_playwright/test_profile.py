import pytest
from playwright.sync_api import Page, expect
from tests.e2e_playwright.conftest import wait_for_streamlit_ready


@pytest.mark.e2e
def test_profile_renders_personal_information(authenticated_admin_page: Page, streamlit_url: str):
    """Test that My Profile properly displays personal details, roles, and status for the current user."""
    page = authenticated_admin_page
    page.goto(f"{streamlit_url}/profile")
    wait_for_streamlit_ready(page)

    expect(page.locator("h1:has-text('My Profile')")).to_be_visible(timeout=15000)
    expect(page.locator("text=Personal Information")).to_be_visible()
    expect(page.locator("text=Assigned Roles & Permissions")).to_be_visible()
    expect(page.locator("text=Security & Password")).to_be_visible()


@pytest.mark.e2e
def test_change_password_mismatch_validation(authenticated_admin_page: Page, streamlit_url: str):
    """Test validation alert when new password and confirmation password do not match."""
    page = authenticated_admin_page
    page.goto(f"{streamlit_url}/profile")
    wait_for_streamlit_ready(page)

    # Open Change Password expander
    page.locator("[data-testid='stExpander'] summary:has-text('Change Password')").click()
    wait_for_streamlit_ready(page)

    curr_input = page.locator("input[aria-label='Current password']")
    new_input = page.locator("input[aria-label='New password']")
    confirm_input = page.locator("input[aria-label='Confirm new password']")
    submit_btn = page.locator("button:has-text('Update Password')")

    expect(curr_input).to_be_visible(timeout=10000)
    curr_input.fill("current-pass-xyz")
    new_input.fill("NewPassword123!")
    confirm_input.fill("MismatchPassword999!")

    submit_btn.click()
    wait_for_streamlit_ready(page)

    error_alert = page.locator("[data-testid='stAlert']", has_text="New password and confirmation do not match.")
    expect(error_alert).to_be_visible(timeout=10000)


@pytest.mark.e2e
def test_employee_profile_displays_employee_role(authenticated_employee_page: Page, streamlit_url: str):
    """Test that an employee's profile reflects their specific employee role."""
    page = authenticated_employee_page
    page.goto(f"{streamlit_url}/profile")
    wait_for_streamlit_ready(page)

    expect(page.locator("h1:has-text('My Profile')")).to_be_visible(timeout=15000)
    expect(page.locator("text=test_employee_uid")).to_be_visible()
