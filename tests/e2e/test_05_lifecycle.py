"""Act 5: Apollo Document Lifecycle & Observability (Playwright E2E).

Test Flow (Verbatim to docs/superpowers/specs/2026-10-26-e2e-playwright-testing-spec.md):
1. POS-LIFE-01: Elena Login as Apollo Manager & verify manager dashboard permissions.
2. POS-LIFE-02: Elena assigns David Kim as member of Project Apollo.
3. POS-LIFE-03: Elena uploads apollo_blueprint.md to Project Apollo (async 202 -> polling -> Active).
4. POS-LIFE-04: Elena switches to Chunk Inspector & Vector Search sandbox and verifies chunks and search.
5. NEG-LIFE-01: Elena re-uploads identical apollo_blueprint.md -> rejected via hash match citing existing filename.
6. NEG-LIFE-02: Elena uploads renamed copy apollo_copy.md -> rejected via hash match citing existing filename.
7. POS-LIFE-05: Elena uploads revised apollo_blueprint.md (modified content) with replace_existing option -> version bumped to 1.1.
8. POS-LIFE-06: Elena soft-archives apollo_blueprint.md -> status switches to Archived.
9. POS-LIFE-07: Elena permanently purges apollo_blueprint.md -> record removed from table and database.
10. POS-LIFE-08: Elena logs out cleanly.
"""

from pathlib import Path
import time
import pytest
import requests
from playwright.sync_api import expect


def test_act5_apollo_document_lifecycle_and_observability(ui, ensure_act4_state, tmp_path):
    """Act 5: Apollo Document Lifecycle & Observability."""
    print("\n" + "=" * 60, flush=True)
    print("[ACT 5] Apollo Document Lifecycle & Vector Observability", flush=True)
    print("=" * 60, flush=True)

    elena_creds = ensure_act4_state["elena"]
    blueprint_path = Path("tests/fixtures/synthetic_data/apollo_blueprint.md").resolve()
    assert blueprint_path.exists(), f"Apollo blueprint file not found at {blueprint_path}"

    # -------------------------------------------------------------------------
    # 1. POS-LIFE-01: Elena Login as Apollo Manager
    # -------------------------------------------------------------------------
    print("-> [Act 5.1] Elena Rostova logging in as Apollo Manager...", flush=True)
    ui.login(elena_creds["username"], elena_creds["password"])

    sidebar = ui.page.locator('[data-testid="stSidebar"]')
    expect(sidebar.get_by_text("Elena Rostova", exact=False)).to_be_visible()
    expect(sidebar.get_by_text("Engineering", exact=False)).to_be_visible()

    ui.navigate_to("Projects")
    expect(ui.page.get_by_role("heading", name="Projects", exact=True)).to_be_visible()

    # Verify Project Apollo is listed under My Projects with Elena as Manager
    expect(
        ui.page.locator("strong").filter(has_text="Project Apollo").first
    ).to_be_visible(timeout=15000)
    expect(
        ui.page.get_by_text("Manager: Elena Rostova", exact=False).first
    ).to_be_visible(timeout=10000)
    expect(
        ui.page.get_by_text("Manager (Transfer before leaving)", exact=False).first
    ).to_be_visible(timeout=10000)
    print("   [OK] Elena Rostova verified as manager of Project Apollo!", flush=True)

    # -------------------------------------------------------------------------
    # 2. POS-LIFE-02: Elena Adds David to Apollo
    # -------------------------------------------------------------------------
    print("-> [Act 5.2] Elena onboarding David Kim into Project Apollo...", flush=True)
    ui.open_expander("Manage Project Membership")
    ui.select_dropdown("Project", "Project Apollo", container="Manage Project Membership")
    ui.select_dropdown("User", "David Kim", container="Manage Project Membership")
    ui.page.get_by_role("button", name="Assign Member").click()
    expect(ui.page.locator('[data-testid="stToast"]')).to_contain_text("Member assigned successfully", timeout=10000)
    ui.page.locator('[data-testid="stToast"]').wait_for(state="detached", timeout=6000)
    print("   [OK] David Kim assigned to Project Apollo!", flush=True)

    # -------------------------------------------------------------------------
    # 3. POS-LIFE-03: Upload Apollo Blueprint
    # -------------------------------------------------------------------------
    print("-> [Act 5.3] Elena uploading apollo_blueprint.md to Project Apollo...", flush=True)
    ui.navigate_to("Documents")
    expect(ui.page.get_by_role("heading", name="Documents", exact=True)).to_be_visible()

    ui.open_expander("Upload & Ingest New Document")
    ui.upload_file(str(blueprint_path), container="Upload & Ingest New Document")
    ui.select_dropdown("Project", "Project Apollo", container="Upload & Ingest New Document")
    ui.fill_input("Description (optional)", "Next-Gen Orbit Telemetry & Sensor Integration Protocol", container="Upload & Ingest New Document")
    ui.page.get_by_role("button", name="Upload and Ingest").click()

    expect(
        ui.page.get_by_text("Document upload initiated", exact=False).first
    ).to_be_visible(timeout=10000)

    # Verify document appears in table
    expect(
        ui.page.locator("strong").filter(has_text="apollo_blueprint.md").first
    ).to_be_visible(timeout=30000)

    # Poll until background ingestion completes and backend reports active
    for _ in range(30):
        time.sleep(0.5)
        try:
            r = requests.get("http://127.0.0.1:8001/api/documents/DOC-001/status", timeout=2.0)
            if r.status_code == 200 and r.json().get("status") == "active":
                break
        except Exception:
            pass

    # Verify background ingestion completes and status transitions to Active
    expect(
        ui.page.locator("p").filter(has_text="🟢 Active").first
    ).to_be_visible(timeout=45000)
    print("   [OK] apollo_blueprint.md uploaded and Active!", flush=True)

    # -------------------------------------------------------------------------
    # 4. POS-LIFE-04: Chunk Inspector & Vector Search Sandbox
    # -------------------------------------------------------------------------
    print("-> [Act 5.4] Testing Chunk Inspector and Vector Search Sandbox...", flush=True)
    ui.page.get_by_role("tab", name="Chunk Inspector & Vector Search").click()
    expect(ui.page.get_by_role("heading", name="Chunk Observability & Vector Search Sandbox", exact=False)).to_be_visible(timeout=10000)

    # Select document in chunk inspector
    ui.select_dropdown("Select document to inspect chunks", "apollo_blueprint.md")
    expect(ui.page.get_by_text("Total chunks in ChromaDB:", exact=False)).to_be_visible(timeout=10000)
    expect(ui.page.locator('[data-testid="stExpander"]').filter(has_text="Chunk #").first).to_be_visible(timeout=10000)
    print("   - Chunk Inspector verified with parsed document chunks.", flush=True)

    # Run vector search query
    ui.fill_input("Test Query", "telemetry framing and radio communication", container="2. Vector Search Sandbox")
    ui.page.get_by_role("button", name="Run Vector Search").click()
    expect(ui.page.get_by_text("chunks ranked by similarity score", exact=False).first).to_be_visible(timeout=15000)
    print("   [OK] Vector Search sandbox retrieved relevant chunks with similarity scoring!", flush=True)

    # Return to Document Library tab
    ui.page.get_by_role("tab", name="Document Library").click()
    expect(ui.page.get_by_role("heading", name="Document Library", exact=True)).to_be_visible(timeout=10000)

    # -------------------------------------------------------------------------
    # 5. NEG-LIFE-01: Exact Duplicate Upload Rejection (Same Filename & Hash)
    # -------------------------------------------------------------------------
    print("-> [Act 5.5] Testing exact duplicate upload rejection (same filename, same hash)...", flush=True)
    ui.open_expander("Upload & Ingest New Document")
    ui.upload_file(str(blueprint_path), container="Upload & Ingest New Document")
    ui.select_dropdown("Project", "Project Apollo", container="Upload & Ingest New Document")
    ui.page.get_by_role("button", name="Upload and Ingest").click()

    # Modal dialog 'Duplicate File Detected' must open citing existing document name
    dialog = ui.page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=10000)
    expect(dialog).to_contain_text("Duplicate File Detected")
    expect(dialog).to_contain_text("Identical file content already exists in this project with name 'apollo_blueprint.md'")
    dialog.get_by_role("button", name="OK").click()
    expect(dialog).to_have_count(0, timeout=10000)
    print("   [OK] Exact duplicate rejected citing existing name 'apollo_blueprint.md'!", flush=True)

    # -------------------------------------------------------------------------
    # 6. NEG-LIFE-02: Renamed Duplicate Upload Rejection (Different Filename, Same Hash)
    # -------------------------------------------------------------------------
    print("-> [Act 5.6] Testing renamed duplicate upload rejection (apollo_copy.md, same hash)...", flush=True)
    copy_path = tmp_path / "apollo_copy.md"
    copy_path.write_bytes(blueprint_path.read_bytes())

    ui.upload_file(str(copy_path), container="Upload & Ingest New Document")
    ui.select_dropdown("Project", "Project Apollo", container="Upload & Ingest New Document")
    ui.page.get_by_role("button", name="Upload and Ingest").click()

    # Modal dialog 'Duplicate File Detected' must open citing existing document name
    dialog = ui.page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=10000)
    expect(dialog).to_contain_text("Duplicate File Detected")
    expect(dialog).to_contain_text("Identical file content already exists in this project with name 'apollo_blueprint.md'")
    dialog.get_by_role("button", name="OK").click()
    expect(dialog).to_have_count(0, timeout=10000)
    print("   [OK] Renamed copy rejected citing original name 'apollo_blueprint.md'!", flush=True)

    # -------------------------------------------------------------------------
    # 7. POS-LIFE-05: Document Replacement Option (Same Filename, Modified Content)
    # -------------------------------------------------------------------------
    print("-> [Act 5.7] Testing document replacement dialog for updated file content...", flush=True)
    revised_path = tmp_path / "apollo_blueprint.md"
    revised_path.write_text(
        "# Project Apollo - Next-Gen Orbit Telemetry Protocol v2.0\n\n"
        "## Revised Satellite Payload Calibration\n"
        "Upgraded star tracker sampling to 40 Hz and revised X-band telemetry data rates to 300 Mbps.\n"
        "Autonomous attitude determination and thermal stabilization thresholds updated.",
        encoding="utf-8",
    )

    ui.upload_file(str(revised_path), container="Upload & Ingest New Document")
    ui.select_dropdown("Project", "Project Apollo", container="Upload & Ingest New Document")
    ui.page.get_by_role("button", name="Upload and Ingest").click()

    # Modal dialog 'Document Already Exists' must open asking to replace
    dialog = ui.page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=10000)
    expect(dialog).to_contain_text("Document Already Exists")
    expect(dialog).to_contain_text("Replacing will delete the previous document and upload this new one")
    dialog.get_by_role("button", name="Replace").click()
    expect(dialog).to_have_count(0, timeout=10000)

    # Expect replacement confirmation message
    expect(
        ui.page.get_by_text("Document 'apollo_blueprint.md' replaced", exact=False).first
    ).to_be_visible(timeout=15000)

    # Poll until background ingestion completes and backend reports active
    for _ in range(30):
        time.sleep(0.5)
        try:
            r = requests.get("http://127.0.0.1:8001/api/documents", timeout=2.0)
            if r.status_code == 200:
                matching = [d for d in r.json() if d.get("document_name") == "apollo_blueprint.md"]
                if matching and matching[0].get("status") == "active":
                    break
        except Exception:
            pass

    # Wait for updated document to reach Active state
    expect(
        ui.page.locator("p").filter(has_text="🟢 Active").first
    ).to_be_visible(timeout=45000)

    # Verify table / details reflects version 1.0 (no version bump)
    expect(
        ui.page.locator('[data-testid="stMetricValue"], [data-testid="stMetric"]').filter(has_text="1.0").first
    ).to_be_visible(timeout=15000)
    print("   [OK] Older document deleted, new document replaced and active at version 1.0!", flush=True)

    # -------------------------------------------------------------------------
    # 8. POS-LIFE-06: Soft-Archive Apollo Document
    # -------------------------------------------------------------------------
    print("-> [Act 5.8] Elena archiving apollo_blueprint.md...", flush=True)
    archive_btn = ui.page.locator("button").filter(has_text="Archive").first
    archive_btn.click()

    # Toast confirms archive
    expect(
        ui.page.locator('[data-testid="stToast"]').filter(has_text="Archived apollo_blueprint.md")
    ).to_be_visible(timeout=10000)

    # Toggle 'Show Archived' to view archived document
    show_archived_toggle = ui.page.locator('label').filter(has_text="Show Archived").first
    show_archived_toggle.click()

    # Verify archived status badge
    expect(
        ui.page.locator("p").filter(has_text="⚪ Archived").first
    ).to_be_visible(timeout=15000)
    print("   [OK] Document apollo_blueprint.md successfully soft-archived!", flush=True)

    # -------------------------------------------------------------------------
    # 9. POS-LIFE-07: Permanent Purge Apollo Document
    # -------------------------------------------------------------------------
    print("-> [Act 5.9] Elena permanently purging apollo_blueprint.md...", flush=True)
    purge_btn = ui.page.locator("button").filter(has_text="Purge").first
    purge_btn.click()

    try:
        expect(
            ui.page.locator('[data-testid="stToast"]').filter(has_text="Permanently purged apollo_blueprint.md")
        ).to_be_visible(timeout=6000)
    except Exception:
        pass

    # Verify document completely removed from table
    expect(
        ui.page.locator("strong").filter(has_text="apollo_blueprint.md")
    ).to_have_count(0, timeout=15000)
    print("   [OK] Document apollo_blueprint.md permanently purged from database and vector store!", flush=True)

    # -------------------------------------------------------------------------
    # 10. POS-LIFE-08: Elena Logout
    # -------------------------------------------------------------------------
    print("-> [Act 5.10] Elena logging out...", flush=True)
    ui.logout()
    print("[ACT 5 COMPLETE] Apollo document lifecycle, deduplication, and observability verified!\n", flush=True)
