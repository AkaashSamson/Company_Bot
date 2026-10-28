"""Act 4: Engineering Projects Lifecycle & Manager Handoff (Playwright E2E).

Test Flow (Verbatim to docs/superpowers/specs/2026-10-26-e2e-playwright-testing-spec.md):
1. POS-ENG-01: Engineering Lead Marcus Vance onboards developer Elena Rostova.
2. POS-ENG-02: Marcus creates Project Titan and uploads titan_architecture.md (async 202 -> Active).
3. POS-ENG-03: Marcus grants Roy Miller cross-department access via Project Titan membership.
4. POS-ENG-04: Roy Miller logs in and verifies access to titan_architecture.md under Project Titan.
5. POS-ENG-05: Marcus creates Project Apollo and adds Elena Rostova to Apollo membership.
6. NEG-ENG-01: Marcus verifies manager leave-lock constraint on Apollo ('Manager (Transfer before leaving)').
7. POS-ENG-06: Marcus transfers Apollo manager role to Elena Rostova in Update Project and leaves Apollo.
8. POS-ENG-07: Marcus logs out cleanly.
"""

from pathlib import Path
import pytest
from playwright.sync_api import expect


def test_act4_engineering_projects_and_manager_handoff(ui, ensure_act2_state):
    """Act 4: Engineering Projects Lifecycle & Manager Handoff."""
    print("\n" + "=" * 60, flush=True)
    print("[ACT 4] Engineering Projects, Cross-Dept Access & Manager Handoff", flush=True)
    print("=" * 60, flush=True)

    marcus_creds = ensure_act2_state["leads"]["marcus"]
    roy_creds = ensure_act2_state["leads"]["roy"]

    # -------------------------------------------------------------------------
    # 1. POS-ENG-01: Marcus Login & Onboard Elena Rostova
    # -------------------------------------------------------------------------
    print("-> [Act 4.1] Marcus Vance logging in to onboard Elena Rostova...", flush=True)
    ui.login(marcus_creds["username"], marcus_creds["password"])

    sidebar = ui.page.locator('[data-testid="stSidebar"]')
    expect(sidebar.get_by_text("Marcus Vance", exact=False)).to_be_visible()
    expect(sidebar.get_by_text("Engineering", exact=False)).to_be_visible()

    ui.navigate_to("Users")
    expect(ui.page.get_by_role("heading", name="Users", exact=True)).to_be_visible()

    ui.fill_input("Username", "elena.dev", container="Add User")
    ui.fill_input("Name *", "Elena Rostova", container="Add User")
    ui.fill_input("Email *", "elena@nexora.com", container="Add User")
    ui.select_dropdown("Role", "Developer", container="Add User")
    ui.select_dropdown("Department", "Engineering", container="Add User")
    ui.fill_input("Initial password", "Password123!", container="Add User")
    ui.page.get_by_role("button", name="Create user").click()

    expect(
        ui.page.locator('[data-testid^="glide-cell-"]').filter(has_text="Elena Rostova").first
    ).to_be_attached(timeout=15000)
    print("   [OK] Elena Rostova onboarded into Engineering department!", flush=True)

    # -------------------------------------------------------------------------
    # 2. POS-ENG-02: Create Project Titan & Upload Blueprint
    # -------------------------------------------------------------------------
    print("-> [Act 4.2] Marcus creating Project Titan & uploading blueprint...", flush=True)
    ui.navigate_to("Projects")
    expect(ui.page.get_by_role("heading", name="Projects", exact=True)).to_be_visible()

    ui.open_expander("Create New Project")
    ui.fill_input("Project Name *", "Project Titan", container="Create New Project")
    ui.select_dropdown("Department *", "Engineering", container="Create New Project")
    ui.select_dropdown("Manager", "Marcus Vance", container="Create New Project")
    ui.fill_input("Description (optional)", "High-throughput telemetry and analytics platform", container="Create New Project")
    ui.page.get_by_role("button", name="Create Project").click()
    expect(ui.page.locator('[data-testid="stToast"]')).to_contain_text("Project created successfully", timeout=10000)

    # Upload Titan architecture blueprint
    ui.navigate_to("Documents")
    expect(ui.page.get_by_role("heading", name="Documents", exact=True)).to_be_visible()

    titan_path = Path("tests/fixtures/synthetic_data/titan_architecture.md").resolve()
    assert titan_path.exists(), f"Titan architecture file not found at {titan_path}"

    ui.open_expander("Upload & Ingest New Document")
    ui.upload_file(str(titan_path), container="Upload & Ingest New Document")
    ui.select_dropdown("Project", "Project Titan", container="Upload & Ingest New Document")
    ui.fill_input("Description (optional)", "Titan high-throughput telemetry blueprint", container="Upload & Ingest New Document")
    ui.page.get_by_role("button", name="Upload and Ingest").click()

    expect(
        ui.page.get_by_text("Document upload initiated", exact=False).first
    ).to_be_visible(timeout=10000)

    expect(
        ui.page.locator('[data-testid^="glide-cell-"]').filter(has_text="titan_architecture.md").first
    ).to_be_attached(timeout=30000)

    expect(
        ui.page.locator("p").filter(has_text="🟢 Active").first
    ).to_be_visible(timeout=45000)
    print("   [OK] Project Titan created and titan_architecture.md is Active!", flush=True)

    # -------------------------------------------------------------------------
    # 3. POS-ENG-03: Grant Roy Cross-Department Access via Project Titan Membership
    # -------------------------------------------------------------------------
    print("-> [Act 4.3] Marcus assigning Roy Miller to Project Titan...", flush=True)
    ui.navigate_to("Projects")
    expect(ui.page.get_by_role("heading", name="Projects", exact=True)).to_be_visible()

    ui.open_expander("Manage Project Membership")
    ui.select_dropdown("Project", "Project Titan", container="Manage Project Membership")
    ui.select_dropdown("User", "Roy Miller", container="Manage Project Membership")
    ui.page.get_by_role("button", name="Assign Member").click()
    expect(ui.page.locator('[data-testid="stToast"]')).to_contain_text("Member assigned successfully", timeout=10000)
    print("   [OK] Roy Miller granted membership to Project Titan!", flush=True)

    ui.logout()

    # -------------------------------------------------------------------------
    # 4. POS-ENG-04: Verify Roy Access to Titan Documents
    # -------------------------------------------------------------------------
    print("-> [Act 4.4] Roy Miller logging in to verify cross-department Titan access...", flush=True)
    ui.login(roy_creds["username"], roy_creds["password"])

    sidebar = ui.page.locator('[data-testid="stSidebar"]')
    expect(sidebar.get_by_text("Roy Miller", exact=False)).to_be_visible()
    expect(sidebar.get_by_text("Human Resources", exact=False)).to_be_visible()

    ui.navigate_to("Documents")
    expect(ui.page.get_by_role("heading", name="Documents", exact=True)).to_be_visible()

    # Confirm titan_architecture.md is present in Document Library table and Manage Documents
    expect(
        ui.page.locator('[data-testid^="glide-cell-"]').filter(has_text="titan_architecture.md").first
    ).to_be_attached(timeout=15000)
    expect(
        ui.page.locator("strong").filter(has_text="titan_architecture.md").first
    ).to_be_visible(timeout=15000)
    print("   [OK] Roy Miller in HR successfully accesses 'titan_architecture.md' via Project Titan!", flush=True)

    ui.logout()

    # -------------------------------------------------------------------------
    # 5. POS-ENG-05: Create Project Apollo & Add Elena Rostova
    # -------------------------------------------------------------------------
    print("-> [Act 4.5] Marcus creating Project Apollo & adding Elena Rostova...", flush=True)
    ui.login(marcus_creds["username"], marcus_creds["password"])

    ui.navigate_to("Projects")
    expect(ui.page.get_by_role("heading", name="Projects", exact=True)).to_be_visible()

    ui.open_expander("Create New Project")
    ui.fill_input("Project Name *", "Project Apollo", container="Create New Project")
    ui.select_dropdown("Department *", "Engineering", container="Create New Project")
    ui.select_dropdown("Manager", "Marcus Vance", container="Create New Project")
    ui.fill_input("Description (optional)", "Autonomous telemetry exploration payload", container="Create New Project")
    ui.page.get_by_role("button", name="Create Project").click()
    expect(ui.page.locator('[data-testid="stToast"]')).to_contain_text("Project created successfully", timeout=10000)

    # Add Elena to Apollo
    ui.open_expander("Manage Project Membership")
    ui.select_dropdown("Project", "Project Apollo", container="Manage Project Membership")
    ui.select_dropdown("User", "Elena Rostova", container="Manage Project Membership")
    ui.page.get_by_role("button", name="Assign Member").click()
    expect(ui.page.locator('[data-testid="stToast"]')).to_contain_text("Member assigned successfully", timeout=10000)
    print("   [OK] Project Apollo created and Elena Rostova added as member!", flush=True)

    # -------------------------------------------------------------------------
    # 6. NEG-ENG-01: Marcus Locked from Leaving Apollo as Manager
    # -------------------------------------------------------------------------
    print("-> [Act 4.6] Marcus verifying manager leave-lock constraint on Apollo...", flush=True)
    expect(
        ui.page.locator("button:disabled").filter(has_text="Leave Project").first
    ).to_be_visible(timeout=10000)
    expect(
        ui.page.get_by_text("Manager (Transfer before leaving)", exact=False).first
    ).to_be_visible(timeout=10000)
    print("   [OK] Leave locked with disabled button and 'Manager (Transfer before leaving)' indicator!", flush=True)

    # -------------------------------------------------------------------------
    # 7. POS-ENG-06: Marcus transfers Apollo manager role to Elena & Leaves
    # -------------------------------------------------------------------------
    print("-> [Act 4.7] Marcus transferring Apollo manager role to Elena & leaving...", flush=True)
    ui.open_expander("Update Project")
    ui.select_dropdown("Project to Update", "Project Apollo", container="Update Project")
    ui.select_dropdown("Manager", "Elena Rostova", container="Update Project")
    ui.page.get_by_role("button", name="Save Changes").click()
    expect(ui.page.locator('[data-testid="stToast"]')).to_contain_text("Project updated successfully", timeout=10000)

    # Wait for update toast to dismiss so toasts do not collide in Streamlit queue
    ui.page.locator('[data-testid="stToast"]').wait_for(state="detached", timeout=6000)

    # Leave Project Apollo (now unlocked because Marcus is no longer manager)
    leave_btn = ui.page.locator("button:not([disabled])").filter(has_text="Leave Project").first
    leave_btn.click()
    expect(
        ui.page.locator('[data-testid="stToast"]').filter(has_text="Left project Project Apollo")
    ).to_be_visible(timeout=10000)

    # Verify Project Apollo is completely removed from Marcus's My Projects table (spec requirement)
    expect(
        ui.page.locator('[data-testid="stVerticalBlock"]')
        .filter(has=ui.page.get_by_role("heading", name="My Projects", exact=True))
        .get_by_text("Project Apollo")
    ).to_have_count(0, timeout=10000)
    print("   [OK] Marcus Vance transferred manager role to Elena and left Project Apollo!", flush=True)

    # -------------------------------------------------------------------------
    # 8. POS-ENG-07: Marcus Logout
    # -------------------------------------------------------------------------
    print("-> [Act 4.8] Logging out Marcus cleanly...", flush=True)
    ui.logout()
    print("[ACT 4 COMPLETE] Engineering projects lifecycle and manager handoff verified!\n", flush=True)
