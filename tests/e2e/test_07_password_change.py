"""Act 7: User Profile & Self-Service Password Change Verification (Playwright E2E).

Test Flow:
1. POS-PWD-01: David Kim logs in with initial password ('Password123!').
2. POS-PWD-02: David navigates to 'My Profile' and verifies user profile info.
3. NEG-PWD-01: David opens 'Change Password', enters mismatched confirmation -> validation error.
4. POS-PWD-03: David enters valid new password ('NewSecurePass456!') and updates successfully.
5. POS-PWD-04: David logs out cleanly.
6. NEG-PWD-02: David attempts login with OLD password ('Password123!') -> rejected (Invalid credentials).
7. POS-PWD-05: David logs in with NEW password ('NewSecurePass456!') -> authenticated successfully.
8. POS-PWD-06: David restores original password ('Password123!') to maintain idempotent test state.
"""

import pytest
from playwright.sync_api import expect


def test_act7_user_password_change_and_reauthentication(ui, ensure_act6_state):
    """Act 7: Self-Service Password Change & Re-Authentication Lifecycle."""
    print("\n" + "=" * 60, flush=True)
    print("[ACT 7] User Profile & Self-Service Password Change", flush=True)
    print("=" * 60, flush=True)

    david_creds = ensure_act6_state["david"]
    username = david_creds["username"]
    old_password = david_creds["password"]
    new_password = "NewSecurePass456!"

    # -------------------------------------------------------------------------
    # 1. POS-PWD-01: David Kim Login with Initial Password
    # -------------------------------------------------------------------------
    print(f"-> [Act 7.1] David Kim logging in with initial password '{old_password}'...", flush=True)
    ui.login(username, old_password)

    sidebar = ui.page.locator('[data-testid="stSidebar"]')
    expect(sidebar.get_by_text("David Kim", exact=False)).to_be_visible()
    print("   [OK] David Kim logged in successfully!", flush=True)

    # -------------------------------------------------------------------------
    # 2. POS-PWD-02: Navigate to My Profile & Verify Information
    # -------------------------------------------------------------------------
    print("-> [Act 7.2] Navigating to 'My Profile'...", flush=True)
    ui.navigate_to("My Profile")
    expect(ui.page.get_by_role("heading", name="My Profile", exact=True)).to_be_visible(timeout=10000)

    # Verify personal info section
    expect(ui.page.get_by_text("Full Name:", exact=False)).to_be_visible()
    expect(ui.page.get_by_text("David Kim", exact=False).first).to_be_visible()
    expect(ui.page.get_by_text("Security & Password", exact=False)).to_be_visible()
    print("   [OK] Profile page rendered with correct personal details!", flush=True)

    # -------------------------------------------------------------------------
    # 3. NEG-PWD-01: Negative Test - Password Confirmation Mismatch
    # -------------------------------------------------------------------------
    print("-> [Act 7.3] Testing negative validation (mismatched password confirmation)...", flush=True)
    ui.open_expander("Change Password")

    ui.page.get_by_role("textbox", name="Current password", exact=True).fill(old_password)
    ui.page.get_by_role("textbox", name="New password", exact=True).fill(new_password)
    ui.page.get_by_role("textbox", name="Confirm new password", exact=True).fill("MismatchedPass999!")
    ui.page.get_by_role("button", name="Update Password").click()

    expect(
        ui.page.get_by_text("New password and confirmation do not match.", exact=False)
    ).to_be_visible(timeout=10000)
    print("   [OK] Mismatched password rejected with validation error!", flush=True)

    # -------------------------------------------------------------------------
    # 4. POS-PWD-03: Update Password Successfully
    # -------------------------------------------------------------------------
    print(f"-> [Act 7.4] Updating password to '{new_password}'...", flush=True)
    ui.page.get_by_role("textbox", name="Confirm new password", exact=True).fill(new_password)
    ui.page.get_by_role("button", name="Update Password").click()

    expect(
        ui.page.get_by_text("Password changed successfully!", exact=False)
    ).to_be_visible(timeout=15000)
    print("   [OK] Password changed successfully notification confirmed!", flush=True)

    # -------------------------------------------------------------------------
    # 5. POS-PWD-04: David Logs Out
    # -------------------------------------------------------------------------
    print("-> [Act 7.5] David Kim logging out...", flush=True)
    ui.logout()
    print("   [OK] Logged out cleanly!", flush=True)

    # -------------------------------------------------------------------------
    # 6. NEG-PWD-02: Negative Test - Login with OLD Password Must Fail
    # -------------------------------------------------------------------------
    print(f"-> [Act 7.6] Attempting login with OLD password '{old_password}' (expected failure)...", flush=True)
    ui.page.get_by_role("textbox", name="Username").fill(username)
    ui.page.get_by_role("textbox", name="Password").fill(old_password)
    ui.page.get_by_role("button", name="Log in").click()

    expect(
        ui.page.get_by_text("Invalid username or password.", exact=False)
    ).to_be_visible(timeout=10000)
    print("   [OK] Old password correctly rejected by authentication service!", flush=True)

    # -------------------------------------------------------------------------
    # 7. POS-PWD-05: Positive Test - Login with NEW Password Must Succeed
    # -------------------------------------------------------------------------
    print(f"-> [Act 7.7] Logging in with NEW password '{new_password}'...", flush=True)
    ui.page.get_by_role("textbox", name="Password").fill(new_password)
    ui.page.get_by_role("button", name="Log in").click()

    expect(sidebar.get_by_text("David Kim", exact=False)).to_be_visible(timeout=15000)
    print("   [OK] Authenticated successfully with new password!", flush=True)

    # -------------------------------------------------------------------------
    # 8. POS-PWD-06: Restore Original Password for Idempotency
    # -------------------------------------------------------------------------
    print(f"-> [Act 7.8] Restoring original password '{old_password}' for test idempotency...", flush=True)
    ui.navigate_to("My Profile")
    expect(ui.page.get_by_role("heading", name="My Profile", exact=True)).to_be_visible(timeout=10000)

    ui.open_expander("Change Password")
    ui.page.get_by_role("textbox", name="Current password", exact=True).fill(new_password)
    ui.page.get_by_role("textbox", name="New password", exact=True).fill(old_password)
    ui.page.get_by_role("textbox", name="Confirm new password", exact=True).fill(old_password)
    ui.page.get_by_role("button", name="Update Password").click()

    expect(
        ui.page.get_by_text("Password changed successfully!", exact=False)
    ).to_be_visible(timeout=15000)
    print("   [OK] Original password restored!", flush=True)

    ui.logout()
    print("\n[ACT 7 COMPLETE] Password change and re-authentication verified!\n", flush=True)
