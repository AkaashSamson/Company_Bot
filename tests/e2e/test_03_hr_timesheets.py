from pathlib import Path
import pytest
from playwright.sync_api import expect


def test_act3_roy_hr_policy_ingestion_and_employee_onboarding(ui, ensure_act2_state, tmp_path):
    """Act 3: HR Manager Roy Miller logs in, attempts uploading an invalid file (.exe),
    uploads the official weekly timesheet policy document, verifies ingestion progression
    from processing to active, and onboards employee David Kim.
    """
    print("\n" + "=" * 60, flush=True)
    print("[ACT 3] Roy Miller HR Timesheet Policy & Employee Onboarding", flush=True)
    print("=" * 60, flush=True)

    roy_creds = ensure_act2_state["leads"]["roy"]

    # 1. POS-HR-01: Roy Miller Login
    print("-> [Act 3.1] Roy Miller logging in as HR Manager...", flush=True)
    ui.login(roy_creds["username"], roy_creds["password"])

    sidebar = ui.page.locator('[data-testid="stSidebar"]')
    expect(sidebar.get_by_text("Roy Miller", exact=False)).to_be_visible()
    expect(sidebar.get_by_text("Human Resources", exact=False)).to_be_visible()
    print("   [OK] Roy Miller logged in successfully (Role: Manager, Dept: Human Resources)!", flush=True)

    # 2. NEG-HR-01: Negative Test - Invalid File Upload (.exe)
    print("-> [Act 3.2] Testing negative file upload validation (.exe rejected)...", flush=True)
    ui.navigate_to("Documents")
    expect(ui.page.get_by_role("heading", name="Documents", exact=True)).to_be_visible()

    # Create dummy .exe file
    invalid_file = tmp_path / "malicious_script.exe"
    invalid_file.write_bytes(b"MZ\x90\x00\x03\x00\x00\x00fake_executable")

    # Open expander and upload invalid file
    ui.open_expander("Upload & Ingest New Document")
    ui.upload_file(str(invalid_file), container="Upload & Ingest New Document")

    # Assert Streamlit file uploader rejection
    uploader = ui.page.locator('[data-testid="stFileUploader"]').first
    expect(
        uploader.get_by_text("not accepted", exact=False).or_(
            uploader.get_by_text("not allowed", exact=False)
        )
    ).to_be_visible(timeout=10000)
    print("   [OK] Invalid file 'malicious_script.exe' correctly rejected by file uploader!", flush=True)

    # 3. POS-HR-02: Upload Official Timesheet Policy (.md)
    print("-> [Act 3.3] Uploading official weekly timesheet policy document...", flush=True)
    policy_path = Path("tests/fixtures/synthetic_data/timesheet_policy.md").resolve()
    assert policy_path.exists(), f"Timesheet policy file not found at {policy_path}"

    ui.upload_file(str(policy_path), container="Upload & Ingest New Document")

    # Fill metadata and submit ingestion
    ui.fill_input("Description (optional)", "Official weekly timesheet submission and billing protocol", container="Upload & Ingest New Document")
    ui.page.get_by_role("button", name="Upload and Ingest").click()

    # 4. POS-HR-03: Verify Ingestion Progression (Initiated -> In-Flight -> Active)
    print("-> [Act 3.4] Tracking document ingestion lifecycle...", flush=True)
    expect(
        ui.page.get_by_text("Document upload initiated", exact=False).first
    ).to_be_visible(timeout=10000)
    print("   - Ingestion initiated (Status: processing / 202 Accepted)", flush=True)

    # Wait for document to appear in table/list
    expect(
        ui.page.get_by_text("timesheet_policy.md", exact=False).first
    ).to_be_visible(timeout=30000)

    # Wait for background embedding and Chroma indexing to complete (Status transitions to Active)
    expect(
        ui.page.locator("p").filter(has_text="🟢 Active").first
    ).to_be_visible(timeout=45000)
    print("   [OK] Document 'timesheet_policy.md' successfully indexed and Active!", flush=True)

    # 5. POS-HR-04: Onboard Employee David Kim
    print("-> [Act 3.5] Navigating to Users to onboard employee David Kim...", flush=True)
    ui.navigate_to("Users")
    expect(ui.page.get_by_role("heading", name="Users", exact=True)).to_be_visible()

    ui.fill_input("Username", "david.emp", container="Add User")
    ui.fill_input("Name *", "David Kim", container="Add User")
    ui.fill_input("Email *", "david@nexora.com", container="Add User")
    ui.select_dropdown("Role", "Developer", container="Add User")
    ui.select_dropdown("Department", "Human Resources", container="Add User")
    ui.fill_input("Initial password", "Password123!", container="Add User")
    ui.page.get_by_role("button", name="Create user").click()

    expect(
        ui.page.locator('[data-testid^="glide-cell-"]').filter(has_text="David Kim").first
    ).to_be_attached(timeout=15000)
    print("   [OK] Employee David Kim onboarded into Human Resources!", flush=True)

    # 6. POS-HR-05: Roy Miller Logout
    print("-> [Act 3.6] Roy Miller logging out...", flush=True)
    ui.logout()
    print("[ACT 3 COMPLETE] HR timesheet policy ingested and employee onboarded!\n", flush=True)
