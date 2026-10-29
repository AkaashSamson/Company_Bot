import pytest
from playwright.sync_api import Page, expect
from tests.e2e_playwright.conftest import wait_for_streamlit_ready


@pytest.mark.e2e
def test_chat_interface_controls_rendered(authenticated_admin_page: Page):
    """Test that all core chat controls (scope selector, clear button, chat input) are visible."""
    page = authenticated_admin_page

    # Project scope selector
    project_scope = page.locator("text=Project scope")
    expect(project_scope).to_be_visible(timeout=10000)

    # Clear button
    clear_button = page.locator("button:has-text('Clear')").first
    expect(clear_button).to_be_visible()

    # Chat input textarea
    chat_input = page.locator("[data-testid='stChatInput'] textarea")
    expect(chat_input).to_be_visible()


@pytest.mark.e2e
def test_send_chat_query_and_render_response(authenticated_admin_page: Page):
    """Test entering a question into chat, submitting it, and receiving an assistant response."""
    page = authenticated_admin_page

    chat_input = page.locator("[data-testid='stChatInput'] textarea")
    expect(chat_input).to_be_visible(timeout=10000)

    # Submit a query
    test_query = "What is the company leave policy?"
    chat_input.fill(test_query)
    chat_input.press("Enter")

    # Wait for the user message to appear in the chat view
    user_message = page.locator("[data-testid='stChatMessage']", has_text=test_query)
    expect(user_message).to_be_visible(timeout=10000)

    # Wait for the assistant's reply (allow enough time for RAG / LLM synthesis or backend reply)
    # The second chat message will be the assistant response
    assistant_messages = page.locator("[data-testid='stChatMessage']")
    expect(assistant_messages).to_have_count(2, timeout=30000)

    # Verify assistant message has text content
    last_assistant_msg = assistant_messages.nth(1)
    expect(last_assistant_msg).to_be_visible()
    content_text = last_assistant_msg.inner_text()
    assert len(content_text.strip()) > 0, "Assistant response was empty"


@pytest.mark.e2e
def test_clear_chat_resets_messages(authenticated_admin_page: Page):
    """Test clicking the Clear button resets chat messages and session history."""
    page = authenticated_admin_page

    clear_button = page.locator("button:has-text('Clear')").first
    expect(clear_button).to_be_visible(timeout=10000)
    clear_button.click()

    wait_for_streamlit_ready(page)

    # After clearing, no chat message elements should be displayed
    messages = page.locator("[data-testid='stChatMessage']")
    expect(messages).to_have_count(0, timeout=10000)
