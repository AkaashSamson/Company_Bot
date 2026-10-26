import pytest
from playwright.sync_api import expect


def test_act1_admin_bootstrap_and_sarah_creation(ui):
    """Act 1: System Admin boots system, provisions Sarah Chen as delegated admin,
    verifies Admin role immutability, and logs out.
    """
    print("\n" + "=" * 60, flush=True)
    print("[ACT 1] System Admin Bootstrap & Delegated Admin Setup", flush=True)
    print("=" * 60, flush=True)

    # 1. POS-BOOT-01: System Admin Login
    print("-> [Act 1.1] System Admin logging in...", flush=True)
    ui.login("admin", "change-me-before-first-login")
    sidebar = ui.page.locator('[data-testid="stSidebar"]')
    expect(sidebar.get_by_text("Administrator", exact=False)).to_be_visible()

    # 2. POS-BOOT-02: Navigate to Users and Create Delegated Admin Sarah
    print("-> [Act 1.2] Navigating to Users and onboarding Sarah Chen (Admin)...", flush=True)
    ui.navigate_to("Users")
    expect(ui.page.get_by_role("heading", name="Users", exact=True)).to_be_visible()

    ui.open_expander("Add User")
    ui.page.get_by_label("Username").fill("sarah.admin")
    ui.page.get_by_label("Name *").fill("Sarah Chen")
    ui.page.get_by_label("Email *").fill("sarah@nexora.com")
    ui.select_dropdown("Role", "Admin")
    ui.page.get_by_label("Initial password").fill("Password123!")
    ui.page.get_by_role("button", name="Create user").click()

    # Verify Sarah is listed
    expect(ui.page.get_by_text("User Sarah Chen created successfully", exact=False)).to_be_visible()
    print("   [OK] Delegated admin Sarah Chen created successfully!", flush=True)

    # 3. NEG-BOOT-01: Verify Admin Role Immutability on Roles Page
    print("-> [Act 1.3] Navigating to Roles to verify Admin role immutability...", flush=True)
    ui.navigate_to("Roles")
    expect(ui.page.get_by_role("heading", name="Roles & Permissions", exact=True)).to_be_visible()

    # In "Assign permissions to role", select Admin and assert system lock notice
    ui.select_dropdown("Role", "Admin")
    expect(
        ui.page.get_by_text("The system Admin role cannot be modified", exact=False)
    ).to_be_visible()
    print("   [OK] Admin role immutability verified (permission edit locked)!", flush=True)

    # 4. POS-BOOT-03: Admin Logout
    print("-> [Act 1.4] Admin logging out...", flush=True)
    ui.logout()
    print("[ACT 1 COMPLETE] System Admin bootstrap verified!\n", flush=True)
