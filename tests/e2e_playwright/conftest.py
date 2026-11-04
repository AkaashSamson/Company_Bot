import os
import time
import pytest
import requests
from playwright.sync_api import Page, expect

STREAMLIT_URL = os.getenv("STREAMLIT_URL", "http://127.0.0.1:8501")
API_URL = os.getenv("STREAMLIT_API_BASE_URL", "http://127.0.0.1:8000")
ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_INITIAL_PASSWORD", "change-me-before-first-login")


@pytest.fixture(scope="session")
def streamlit_url() -> str:
    """Base URL for the Streamlit UI."""
    return STREAMLIT_URL


@pytest.fixture(scope="session")
def api_url() -> str:
    """Base URL for the FastAPI backend."""
    return API_URL


@pytest.fixture(scope="session")
def admin_credentials() -> tuple[str, str]:
    """Default Admin login credentials."""
    return ADMIN_USER, ADMIN_PASS


@pytest.fixture(scope="session", autouse=True)
def ensure_servers_online(streamlit_url: str, api_url: str):
    """Verify that both FastAPI and Streamlit are reachable before running E2E tests."""
    api_online = False
    streamlit_online = False

    try:
        res = requests.get(f"{api_url}/docs", timeout=3)
        api_online = res.status_code == 200
    except Exception:
        api_online = False

    try:
        res = requests.get(streamlit_url, timeout=3)
        streamlit_online = res.status_code == 200
    except Exception:
        streamlit_online = False

    if not api_online or not streamlit_online:
        pytest.skip(
            f"E2E services not available. FastAPI ({api_url}): {'ONLINE' if api_online else 'OFFLINE'}, "
            f"Streamlit ({streamlit_url}): {'ONLINE' if streamlit_online else 'OFFLINE'}. "
            "Start services with '.\\setup.ps1' or 'uvicorn app.main:app' & 'streamlit run streamlit_app/app.py'."
        )


def wait_for_streamlit_ready(page: Page, timeout_ms: int = 15000):
    """Wait for Streamlit app container to be attached and any initial spinner to disappear."""
    page.wait_for_selector("[data-testid='stAppViewContainer']", timeout=timeout_ms)
    # Streamlit displays a running status widget while scripts execute
    running_status = page.locator("[data-testid='stStatusWidget']")
    if running_status.count() > 0:
        try:
            running_status.wait_for(state="detached", timeout=timeout_ms)
        except Exception:
            pass


def login_user(page: Page, streamlit_url: str, username: str, password: str):
    """Helper function to log in via the Streamlit login form."""
    page.goto(streamlit_url)
    wait_for_streamlit_ready(page)

    # Check if already logged in (sidebar is visible and logout button exists)
    logout_btn = page.locator("[data-testid='stSidebar'] button:has-text('Log out')")
    if logout_btn.is_visible():
        return

    # Fill username and password in the login form
    user_input = page.locator("input[aria-label='Username']")
    pass_input = page.locator("input[aria-label='Password']")
    
    expect(user_input).to_be_visible(timeout=10000)
    expect(pass_input).to_be_visible(timeout=10000)

    user_input.fill(username)
    pass_input.fill(password)

    # Submit login form
    submit_btn = page.locator("button:has-text('Log in')")
    submit_btn.click()

    # Wait for session state transition and main view or sidebar to appear
    wait_for_streamlit_ready(page)


@pytest.fixture
def authenticated_admin_page(page: Page, streamlit_url: str, admin_credentials: tuple[str, str]) -> Page:
    """Fixture providing a Playwright Page already authenticated as Admin."""
    username, password = admin_credentials
    login_user(page, streamlit_url, username, password)

    # Verify admin sidebar badge or logout button is visible
    logout_btn = page.locator("[data-testid='stSidebar'] button:has-text('Log out')")
    expect(logout_btn).to_be_visible(timeout=10000)
    return page


@pytest.fixture(scope="session")
def employee_credentials() -> tuple[str, str]:
    """Test Employee login credentials."""
    return "test_employee", "EmployeePass123!"


@pytest.fixture
def authenticated_employee_page(page: Page, streamlit_url: str, employee_credentials: tuple[str, str]) -> Page:
    """Fixture providing a Playwright Page already authenticated as a standard Employee."""
    username, password = employee_credentials
    login_user(page, streamlit_url, username, password)

    logout_btn = page.locator("[data-testid='stSidebar'] button:has-text('Log out')")
    expect(logout_btn).to_be_visible(timeout=10000)
    return page

