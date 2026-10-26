import pytest
from playwright.sync_api import expect


def test_admin_login_and_logout(ui):
    """Smoke test: verify isolated backend + frontend boots and admin logs in."""
    print("\n  👉 [Step 1/4] Navigating to Streamlit login card...", flush=True)
    ui.goto_home()

    print("  👉 [Step 2/4] Entering Admin credentials & logging in...", flush=True)
    ui.login("admin", "change-me-before-first-login")

    print("  👉 [Step 3/4] Verifying Admin profile badge and sidebar navigation...", flush=True)
    sidebar = ui.page.locator('[data-testid="stSidebar"]')
    expect(sidebar.get_by_text("Administrator", exact=False)).to_be_visible()

    expect(sidebar.get_by_text("Users", exact=False)).to_be_visible()
    expect(sidebar.get_by_text("Departments", exact=False)).to_be_visible()
    expect(sidebar.get_by_text("Roles", exact=False)).to_be_visible()
    expect(sidebar.get_by_text("Projects", exact=False)).to_be_visible()
    expect(sidebar.get_by_text("Documents", exact=False)).to_be_visible()

    print("  👉 [Step 4/4] Logging out and confirming session cleared...", flush=True)
    ui.logout()

    print("  🎉 [Success] Admin smoke test completed successfully!\n", flush=True)
