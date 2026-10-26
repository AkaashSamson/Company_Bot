import pytest
from playwright.sync_api import expect


def test_admin_login_and_logout(ui):
    """Smoke test: verify isolated backend + frontend boots and admin logs in."""
    ui.login("admin", "change-me-before-first-login")

    # Verify admin identity rendered in sidebar
    sidebar = ui.page.locator('[data-testid="stSidebar"]')
    expect(sidebar.get_by_text("Administrator", exact=False)).to_be_visible()

    # Verify core navigation links exist for Admin
    expect(sidebar.get_by_text("Users", exact=False)).to_be_visible()
    expect(sidebar.get_by_text("Departments", exact=False)).to_be_visible()
    expect(sidebar.get_by_text("Roles", exact=False)).to_be_visible()
    expect(sidebar.get_by_text("Projects", exact=False)).to_be_visible()
    expect(sidebar.get_by_text("Documents", exact=False)).to_be_visible()

    # Logout
    ui.logout()
