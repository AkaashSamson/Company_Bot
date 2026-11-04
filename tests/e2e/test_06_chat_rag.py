"""Act 6: Scoped Chat & RAG Authorization Verification (Playwright E2E).

Test Flow (Verbatim to docs/superpowers/specs/2026-10-26-e2e-playwright-testing-spec.md):
1. POS-CHAT-01: David Queries General Timesheet Policy
   - David logs in (david.hr / Password123!).
   - Project scope set to General Knowledge Base (All Accessible Documents).
   - Asks: "What is the deadline for submitting weekly timesheets?".
   - Assistant answers with Friday 5 PM rule and citations citing timesheet_policy.md.
2. NEG-CHAT-01: David Blocked from Project Titan Knowledge
   - Project scope dropdown does NOT show Project Titan (David was never added and has no grant).
   - In General KB scope, David asks: "What is the microservices topology in Project Titan?".
   - Assistant returns negative response or zero Titan citations. Zero data leak.
3. POS-CHAT-02: David Clears Chat
   - Clicks "Clear" in top actions bar -> chat history wiped, session ID refreshed.
   - David logs out.
4. POS-CHAT-03: Roy Queries Titan via Cross-Department Grant
   - Roy logs in (roy.hr / Password123!).
   - Project scope dropdown shows Project Titan. Selects Project Titan.
   - Roy asks: "Describe the Titan architecture microservices topology".
   - Assistant returns technical answer citing titan_architecture.md.
   - Roy logs out.
5. POS-CHAT-04: Elena Queries Titan as Project Member
   - Elena logs in (elena.dev / Password123!).
   - Selects Project Titan in Project scope.
   - Asks: "What cache topology does Project Titan use?".
   - Assistant returns Redis cache details citing titan_architecture.md.
   - Elena logs out.
"""

import pytest
from playwright.sync_api import expect


def test_act6_scoped_chat_rag_authorization(ui, ensure_act6_state):
    """Act 6: Scoped Chat & RAG Authorization Verification."""
    print("\n" + "=" * 60, flush=True)
    print("[ACT 6] Scoped Chat & RAG Authorization Verification", flush=True)
    print("=" * 60, flush=True)

    david_creds = ensure_act6_state["david"]
    roy_creds = ensure_act6_state["roy"]
    elena_creds = ensure_act6_state["elena"]

    # -------------------------------------------------------------------------
    # 1. POS-CHAT-01: David Queries General Timesheet Policy
    # -------------------------------------------------------------------------
    print("-> [Act 6.1] David Kim logging in to query General Timesheet Policy...", flush=True)
    ui.login(david_creds["username"], david_creds["password"])

    sidebar = ui.page.locator('[data-testid="stSidebar"]')
    expect(sidebar.get_by_text("David Kim", exact=False)).to_be_visible()

    # Verify home page heading
    expect(
        ui.page.get_by_role("heading", name="KnowLayer HR Policy Assistant", exact=True)
    ).to_be_visible(timeout=10000)

    # Verify default scope is General Knowledge Base
    scope_combobox = ui.page.get_by_role("combobox", name="Project scope")
    expect(scope_combobox).to_be_visible(timeout=5000)
    expect(scope_combobox).to_have_value("General Knowledge Base (All Accessible Documents)")

    # Ask weekly timesheet deadline question
    print("   - David asking: 'What is the deadline for submitting weekly timesheets?'...", flush=True)
    ui.send_chat_message("What is the deadline for submitting weekly timesheets?")

    # Expect assistant response (2 messages: user + assistant)
    chat_messages = ui.page.locator('[data-testid="stChatMessage"]')
    expect(chat_messages).to_have_count(2, timeout=60000)
    assistant_msg = chat_messages.last

    # Verify answer contains Friday 5 PM rule
    expect(assistant_msg.get_by_text("Friday", exact=False).first).to_be_visible()
    expect(
        assistant_msg.get_by_text("5:00 PM", exact=False)
        .or_(assistant_msg.get_by_text("5 PM", exact=False))
        .or_(assistant_msg.get_by_text("17:00", exact=False))
        .first
    ).to_be_visible()

    # Verify citations citing timesheet_policy.md
    citations_expander = assistant_msg.locator('[data-testid="stExpander"]').filter(has_text="Sources & References").first
    expect(citations_expander).to_be_visible(timeout=10000)
    citations_expander.locator("summary").first.click()
    expect(citations_expander.get_by_text("timesheet_policy.md", exact=False).first).to_be_visible()
    print("   [OK] David successfully queried timesheet policy and verified citation!", flush=True)

    # -------------------------------------------------------------------------
    # 2. NEG-CHAT-01: David Blocked from Project Titan Knowledge
    # -------------------------------------------------------------------------
    print("-> [Act 6.2] Verifying David is blocked from Project Titan scope & knowledge...", flush=True)

    # Click selectbox to inspect dropdown options
    scope_combobox = ui.page.get_by_role("combobox", name="Project scope")
    scope_combobox.click()
    ui.page.wait_for_timeout(500)

    # Verify 'Project Titan' is NOT available in David's options
    expect(ui.page.locator('[role="option"]').filter(has_text="Project Titan")).not_to_be_visible()
    ui.page.keyboard.press("Escape")
    ui.page.wait_for_timeout(400)
    print("   - Project Titan correctly absent from David's project scope options.", flush=True)

    # In General KB scope, David asks about Project Titan microservices topology
    print("   - David asking unauthorized query: 'What is the microservices topology in Project Titan?'...", flush=True)
    ui.send_chat_message("What is the microservices topology in Project Titan?")

    # Wait for second assistant response (total 4 messages: 2 user + 2 assistant)
    expect(chat_messages).to_have_count(4, timeout=60000)
    neg_assistant_msg = chat_messages.last

    # Verify zero Titan citations and zero confidential data leak
    expect(neg_assistant_msg.get_by_text("titan_architecture.md", exact=False)).not_to_be_visible()
    expect(neg_assistant_msg.get_by_text("TITAN-ENV-KEY-SECURE-9941", exact=False)).not_to_be_visible()
    expect(neg_assistant_msg.get_by_text("s3://nexora-titan-cold-archive", exact=False)).not_to_be_visible()
    print("   [OK] Zero Titan citations or confidential data leaked to unauthorized user David!", flush=True)

    # -------------------------------------------------------------------------
    # 3. POS-CHAT-02: David Clears Chat
    # -------------------------------------------------------------------------
    print("-> [Act 6.3] David clearing conversation history...", flush=True)
    clear_button = ui.page.get_by_role("button", name="🗑️ Clear")
    clear_button.click()
    ui.page.wait_for_load_state("domcontentloaded")
    ui.page.wait_for_timeout(1000)

    # Verify all chat messages are cleared
    expect(ui.page.locator('[data-testid="stChatMessage"]')).to_have_count(0, timeout=10000)
    print("   [OK] Chat history successfully wiped!", flush=True)

    ui.logout()

    # -------------------------------------------------------------------------
    # 4. POS-CHAT-03: Roy Queries Titan via Cross-Department Grant
    # -------------------------------------------------------------------------
    print("-> [Act 6.4] Roy Miller logging in to query Project Titan via cross-department grant...", flush=True)
    ui.login(roy_creds["username"], roy_creds["password"])

    sidebar = ui.page.locator('[data-testid="stSidebar"]')
    expect(sidebar.get_by_text("Roy Miller", exact=False)).to_be_visible()

    # Select Project Titan from Project Scope
    ui.select_dropdown("Project scope", "Project Titan")
    ui.page.wait_for_timeout(500)

    print("   - Roy asking: 'Describe the Titan architecture microservices topology'...", flush=True)
    ui.send_chat_message("Describe the Titan architecture microservices topology")

    roy_chat_messages = ui.page.locator('[data-testid="stChatMessage"]')
    expect(roy_chat_messages).to_have_count(2, timeout=60000)
    roy_assistant_msg = roy_chat_messages.last

    # Verify answer describes microservices architecture
    expect(
        roy_assistant_msg.get_by_text("microservices", exact=False)
        .or_(roy_assistant_msg.get_by_text("Kubernetes", exact=False))
        .or_(roy_assistant_msg.get_by_text("Kafka", exact=False))
        .or_(roy_assistant_msg.get_by_text("Rust", exact=False))
        .first
    ).to_be_visible()

    # Verify citation cites titan_architecture.md
    roy_citations_expander = roy_assistant_msg.locator('[data-testid="stExpander"]').filter(has_text="Sources & References").first
    expect(roy_citations_expander).to_be_visible(timeout=10000)
    roy_citations_expander.locator("summary").first.click()
    expect(roy_citations_expander.get_by_text("titan_architecture.md", exact=False).first).to_be_visible()
    print("   [OK] Roy successfully queried Project Titan with valid citation!", flush=True)

    ui.logout()

    # -------------------------------------------------------------------------
    # 5. POS-CHAT-04: Elena Queries Titan as Project Member
    # -------------------------------------------------------------------------
    print("-> [Act 6.5] Elena Rostova logging in to query Project Titan cache topology...", flush=True)
    ui.login(elena_creds["username"], elena_creds["password"])

    sidebar = ui.page.locator('[data-testid="stSidebar"]')
    expect(sidebar.get_by_text("Elena Rostova", exact=False)).to_be_visible()

    # Select Project Titan from Project Scope
    ui.select_dropdown("Project scope", "Project Titan")
    ui.page.wait_for_timeout(500)

    print("   - Elena asking: 'What cache topology does Project Titan use?'...", flush=True)
    ui.send_chat_message("What cache topology does Project Titan use?")

    elena_chat_messages = ui.page.locator('[data-testid="stChatMessage"]')
    expect(elena_chat_messages).to_have_count(2, timeout=60000)
    elena_assistant_msg = elena_chat_messages.last

    # Verify Redis cache details
    expect(elena_assistant_msg.get_by_text("Redis", exact=False).first).to_be_visible()

    # Verify citation cites titan_architecture.md
    elena_citations_expander = elena_assistant_msg.locator('[data-testid="stExpander"]').filter(has_text="Sources & References").first
    expect(elena_citations_expander).to_be_visible(timeout=10000)
    elena_citations_expander.locator("summary").first.click()
    expect(elena_citations_expander.get_by_text("titan_architecture.md", exact=False).first).to_be_visible()
    print("   [OK] Elena successfully queried cache topology with valid citation!", flush=True)

    ui.logout()
    print("\n[ACT 6 COMPLETE] Scoped Chat & RAG Authorization fully verified!\n", flush=True)
