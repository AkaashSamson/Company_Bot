import pytest
from playwright.sync_api import Page, expect
from tests.e2e_playwright.conftest import wait_for_streamlit_ready


@pytest.mark.e2e
def test_chat_session_info_popover(authenticated_admin_page: Page):
    """Test clicking the Info popover button displays session, user, and scope details."""
    page = authenticated_admin_page

    info_btn = page.locator("button:has-text('Info')").first
    expect(info_btn).to_be_visible(timeout=10000)
    info_btn.click()

    # The popover content should display session and user metadata
    expect(page.locator("text=Session:")).to_be_visible(timeout=5000)
    expect(page.locator("text=Scope:")).to_be_visible(timeout=5000)


@pytest.mark.e2e
def test_chat_project_scope_dropdown(authenticated_admin_page: Page):
    """Test that the project scope selectbox defaults to General Knowledge Base."""
    page = authenticated_admin_page

    combobox = page.get_by_role("combobox", name="Project scope")
    expect(combobox).to_be_visible(timeout=10000)
    expect(combobox).to_have_value("General Knowledge Base (All Accessible Documents)")


@pytest.mark.e2e
def test_chat_citations_interaction_flow(authenticated_admin_page: Page):
    """Test asking a policy question and verifying whether citation sources can be inspected."""
    page = authenticated_admin_page

    chat_input = page.locator("[data-testid='stChatInput'] textarea")
    expect(chat_input).to_be_visible(timeout=10000)

    # Ask a policy question likely to retrieve policy evidence
    chat_input.fill("What is the policy regarding working hours and leave?")
    chat_input.press("Enter")

    # Wait for response
    user_msg = page.locator("[data-testid='stChatMessage']", has_text="working hours and leave")
    expect(user_msg).to_be_visible(timeout=10000)

    # Wait for assistant response
    messages = page.locator("[data-testid='stChatMessage']")
    expect(messages).to_have_count(2, timeout=30000)

    # Check if citations expander is present; if so, test opening it
    citations_expander = page.locator("text=Sources & References")
    if citations_expander.count() > 0 and citations_expander.first.is_visible():
        citations_expander.first.click()
        wait_for_streamlit_ready(page)
