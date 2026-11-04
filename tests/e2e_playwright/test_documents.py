import os
import tempfile
import pytest
from playwright.sync_api import Page, expect
from tests.e2e_playwright.conftest import wait_for_streamlit_ready


@pytest.mark.e2e
def test_documents_page_renders_library_and_tabs(authenticated_admin_page: Page, streamlit_url: str):
    """Test that the Documents page loads with Document Library and Chunk Inspector tabs."""
    page = authenticated_admin_page
    page.goto(f"{streamlit_url}/documents")
    wait_for_streamlit_ready(page)

    expect(page.locator("h1:has-text('Documents')")).to_be_visible(timeout=15000)

    # Check tab roles
    expect(page.get_by_role("tab", name="Document Library")).to_be_visible()
    expect(page.get_by_role("tab", name="Chunk Inspector & Vector Search")).to_be_visible()

    # Check expander
    expect(page.locator("[data-testid='stExpander'] summary:has-text('Upload & Ingest New Document')")).to_be_visible()


@pytest.mark.e2e
def test_documents_upload_small_file_flow(authenticated_admin_page: Page, streamlit_url: str):
    """Test uploading a small markdown/txt policy document and verifying it is listed."""
    page = authenticated_admin_page
    page.goto(f"{streamlit_url}/documents")
    wait_for_streamlit_ready(page)

    # Open the upload expander if not already open
    expander = page.locator("[data-testid='stExpander']", has_text="Upload & Ingest New Document")
    if not expander.locator("[data-testid='stFileUploaderDropzoneInput']").is_visible():
        expander.locator("summary").click()
        wait_for_streamlit_ready(page)

    # Create a temporary test document
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("Company Bot Policy: Work hours are 9am to 5pm Monday to Friday.")
        temp_file_path = f.name
        filename = os.path.basename(temp_file_path)

    try:
        # File uploader input
        file_input = page.locator("[data-testid='stFileUploaderDropzoneInput']")
        expect(file_input).to_be_attached(timeout=10000)
        file_input.set_input_files(temp_file_path)

        wait_for_streamlit_ready(page)

        # Submit upload form
        submit_btn = page.locator("button:has-text('Upload and Ingest')")
        expect(submit_btn).to_be_visible(timeout=10000)
        submit_btn.click()

        wait_for_streamlit_ready(page)

        # After upload and rerun, the new document is listed under Manage Documents / Document Library
        expect(page.locator("text=" + filename).first).to_be_visible(timeout=20000)
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
