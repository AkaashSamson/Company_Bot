import pytest
from playwright.sync_api import Page, expect
from tests.e2e_playwright.conftest import wait_for_streamlit_ready


@pytest.mark.e2e
def test_login_page_renders_form(page: Page, streamlit_url: str):
    """Test that the login form properly renders for unauthenticated users."""
    page.goto(streamlit_url)
    wait_for_streamlit_ready(page)

    # Login header
    login_heading = page.locator("text=KnowLayer Login")
    expect(login_heading).to_be_visible(timeout=10000)

    # Input fields
    username_input = page.locator("input[aria-label='Username']")
    password_input = page.locator("input[aria-label='Password']")
    login_button = page.locator("button:has-text('Log in')")

    expect(username_input).to_be_visible()
    expect(password_input).to_be_visible()
    expect(login_button).to_be_visible()


@pytest.mark.e2e
def test_login_invalid_credentials_shows_error(page: Page, streamlit_url: str):
    """Test that submitting invalid credentials displays a user-friendly error message."""
    page.goto(streamlit_url)
    wait_for_streamlit_ready(page)

    username_input = page.locator("input[aria-label='Username']")
    password_input = page.locator("input[aria-label='Password']")
    login_button = page.locator("button:has-text('Log in')")

    username_input.fill("invalid_user_test")
    password_input.fill("incorrect_password_xyz")
    login_button.click()

    wait_for_streamlit_ready(page)

    # An error alert should appear with the failure notice
    error_alert = page.locator("[data-testid='stAlert']")
    expect(error_alert).to_be_visible(timeout=10000)
    expect(error_alert).to_contain_text("Invalid username or password")


@pytest.mark.e2e
def test_login_successful_and_logout(page: Page, streamlit_url: str, admin_credentials: tuple[str, str]):
    """Test successful login with admin credentials, verifying sidebar presence, and logging out."""
    username, password = admin_credentials
    page.goto(streamlit_url)
    wait_for_streamlit_ready(page)

    # Log in
    username_input = page.locator("input[aria-label='Username']")
    password_input = page.locator("input[aria-label='Password']")
    login_button = page.locator("button:has-text('Log in')")

    username_input.fill(username)
    password_input.fill(password)
    login_button.click()

    wait_for_streamlit_ready(page)

    # Verify that the main title is visible
    main_title = page.locator("h1:has-text('KnowLayer HR Policy Assistant')")
    expect(main_title).to_be_visible(timeout=15000)

    # Verify sidebar displays the user identity badge and logout button
    sidebar = page.locator("[data-testid='stSidebar']")
    expect(sidebar).to_be_visible()

    logout_button = sidebar.locator("button:has-text('Log out')")
    expect(logout_button).to_be_visible()

    # Click Log out
    logout_button.click()
    wait_for_streamlit_ready(page)

    # Verify return to login view
    expect(page.locator("text=KnowLayer Login")).to_be_visible(timeout=10000)
