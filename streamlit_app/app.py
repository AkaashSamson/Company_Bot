import os
import sys
import uuid
from pathlib import Path

# Ensure repository root is on sys.path for absolute imports
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import re
import streamlit as st
import requests
from datetime import datetime, timezone
import importlib

from streamlit_app.session_auth import bootstrap_cookies, persist_auth, restore_auth
import streamlit_app.services.chat_service as chat_service_module
importlib.reload(chat_service_module)
from streamlit_app.services.chat_service import ChatService
from streamlit_app.services.organization_service import OrganizationService
from streamlit_app.services.authentication_service import AuthenticationService


st.set_page_config(page_title="KnowLayer HR Chatbot", page_icon="📘")

cookies = bootstrap_cookies()
if "auth" not in st.session_state:
    st.session_state.auth = None
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_response" not in st.session_state:
    st.session_state.last_response = None

if st.session_state.get("auth") is None:
    restore_auth(cookies)
    st.title("KnowLayer Login")
    with st.form("login"):
        login_username = st.text_input("Username")
        login_password = st.text_input("Password", type="password")
        login_submitted = st.form_submit_button("Log in")
    if login_submitted:
        try:
            auth = AuthenticationService().login(login_username, login_password)
            st.session_state.auth = auth
            st.rerun()
        except requests.exceptions.HTTPError as error:
            status_code = error.response.status_code if error.response is not None else None
            if status_code == 401:
                st.error("Invalid username or password.")
            else:
                st.error(f"Login failed (HTTP {status_code}). Please try again.")
        except requests.exceptions.RequestException:
            st.error(
                "The authentication service is not reachable. "
                "Start the FastAPI backend on http://127.0.0.1:8000 and try again."
            )
    st.stop()

persist_auth(cookies)

def _logout():
    st.session_state.auth = None
    st.session_state.messages = []
    st.session_state.last_response = None
    st.session_state.session_id = str(uuid.uuid4())
    try:
        cookies.remove("knowlayer_auth")
    except KeyError:
        pass

st.sidebar.button("Log out", on_click=_logout)
st.title("KnowLayer HR Policy Assistant")

st.sidebar.page_link("app.py", label="Chat")
st.sidebar.page_link("pages/profile.py", label="My Profile")
st.sidebar.page_link("pages/users.py", label="Users")
st.sidebar.page_link("pages/departments.py", label="Departments")
st.sidebar.page_link("pages/projects.py", label="Projects")
st.sidebar.page_link("pages/documents.py", label="Documents")
st.sidebar.page_link("pages/explorer.py", label="Organization Explorer")
st.sidebar.page_link("pages/roles.py", label="Roles")
st.sidebar.page_link("pages/organization.py", label="Organization")

st.sidebar.divider()
st.sidebar.caption(f"Session: `{st.session_state.session_id}`")

col_chat, col_cache = st.sidebar.columns(2)
with col_chat:
    if st.button("🗑️ Clear Chat", use_container_width=True, help="Reset conversation history and start a new session"):
        st.session_state.messages = []
        st.session_state.last_response = None
        st.session_state.session_id = f"st-{uuid.uuid4().hex[:8]}"
        st.rerun()

with col_cache:
    if st.button("🧹 Clear Cache", use_container_width=True, help="Flush backend semantic and prompt caches"):
        try:
            service = ChatService()
            if hasattr(service, "clear_cache"):
                service.clear_cache()
            else:
                base_url = (getattr(service, "base_url", None) or os.getenv("STREAMLIT_API_BASE_URL", "http://127.0.0.1:8000")).rstrip("/")
                headers = service._headers() if hasattr(service, "_headers") else {}
                res = requests.post(f"{base_url}/api/chat/cache/clear", headers=headers, timeout=10)
                res.raise_for_status()
            st.sidebar.success("Cache cleared!")
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                st.sidebar.warning(
                    "The running FastAPI backend does not have `/api/chat/cache/clear` loaded yet. "
                    "Please restart FastAPI with: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`"
                )
            else:
                st.sidebar.error(f"Failed to clear cache: {e}")
        except Exception as e:
            st.sidebar.error(f"Failed to clear cache: {e}")



chat_service = ChatService()

with st.sidebar.expander("📊 Token Metrics"):
    if st.button("Refresh Stats", use_container_width=True):
        st.rerun()
    try:
        token_res = requests.get(f"{chat_service.base_url}/api/tokens/stats", timeout=3)
        if token_res.status_code == 200:
            stats = token_res.json()
            st.write(f"**Total Tokens:** {stats.get('total_tokens', 0):,}")
            st.write(f"**API Calls:** {stats.get('call_count', 0)}")
            st.write(f"**Cache Hit Rate:** {stats.get('cache_hit_rate_percent', 0.0):.1f}%")
            st.write(f"**Prompt:** {stats.get('prompt_tokens', 0):,} | **Completion:** {stats.get('completion_tokens', 0):,}")
    except requests.exceptions.RequestException:
        st.caption("Token stats unavailable")

with st.sidebar.expander("🩺 Provider Health & Circuits"):
    col_ref, col_rst = st.columns([1, 1])
    with col_ref:
        if st.button("🔄 Refresh", use_container_width=True, key="refresh_health"):
            st.rerun()
    with col_rst:
        if st.button("⚡ Reset", use_container_width=True, key="reset_health", help="Reset all circuit breakers to healthy"):
            chat_service.reset_providers()
            st.rerun()

    health_data = chat_service.get_provider_health()
    if health_data:
        for provider_name, info in health_data.items():
            status_val = str(info.get("status", "healthy")).lower()
            if status_val == "healthy":
                icon = "🟢"
                badge = "Healthy"
            elif status_val == "degraded":
                icon = "🟡"
                badge = "Degraded"
            elif status_val == "recovering":
                icon = "🔄"
                badge = "Recovering"
            else:
                icon = "🔴"
                badge = "Open / Tripped"

            st.markdown(f"**{icon} {provider_name.upper()}** (`{badge}`)")
            total_reqs = info.get("total_requests", 0)
            succ_reqs = info.get("successful_requests", 0)
            fail_reqs = info.get("failed_requests", 0)
            avg_lat = info.get("average_latency_ms", 0.0)
            succ_rate = info.get("success_rate", 100.0)
            st.caption(
                f"Success: {succ_rate}% ({succ_reqs}/{total_reqs}) | "
                f"Failures: {fail_reqs} | Latency: {avg_lat:.0f}ms"
            )
    else:
        st.caption("Provider health metrics unavailable.")


try:
    project_options = {"All authorized projects": None}
    project_options.update({
        project["project_name"]: project["project_id"]
        for project in OrganizationService().list_projects()
    })
except requests.exceptions.RequestException:
    project_options = {"All authorized projects": None}

selected_project_name = st.selectbox("Project scope", list(project_options))
selected_project_id = project_options[selected_project_name]


def _strip_citation_numbering(text: str) -> str:
    """Remove leading numbering/bullets from citation text lines."""
    if not text:
        return text
    num_pattern = re.compile(
        r"^\s*(?:"
        r"[-*•]\s*"
        r")?(?:"
        r"\(?\d+(?:\.\d+)*\)?[.):]?\s*(?:[-–—]\s*)?"
        r"|\(?[a-zA-Z]{1,4}\)?[.):]\s*(?:[-–—]\s*)?"
        r"|(?:Section|Article|Clause)\s+\d[\d.]*[:\s-]*"
        r"|[-*•–—]\s+"
        r")",
        re.IGNORECASE,
    )
    cleaned_lines = [num_pattern.sub("", line).strip() for line in text.splitlines()]
    return "\n".join(cleaned_lines).strip()


def _format_citations(citations: list, answer: str = "") -> str:
    """Convert citations list to a plain markdown string that persists in chat history.

    If the response was already created from the references (the reference text is already
    contained in the answer), skip showing the references again.
    """
    if not citations:
        return ""

    if answer:
        answer_clean = re.sub(r"\s+", " ", answer).strip().lower()
        is_intro = any(
            intro in answer_clean
            for intro in [
                "here are the references from the documents",
                "here are the references for my previous answer",
                "here are the references for your review",
            ]
        )
        if not is_intro:
            # Check if citation text is already contained in the answer
            for c in citations:
                raw = re.sub(r"\s+", " ", c.get("text", "")).strip().lower()
                if raw and (raw[:40] in answer_clean if len(raw) >= 40 else raw in answer_clean):
                    return ""

    lines = ["\n\n---\n**References:**"]
    for c in citations:
        source = c.get("source", "Policy")
        section = c.get("section", "")
        # Clean section as well if it starts with numbering
        clean_section = re.sub(
            r"^\s*(?:(?:Section|Article|Clause)\s+)?\d+(?:\.\d+)*[:\s-]*",
            "",
            section,
            flags=re.IGNORECASE,
        ).strip() or section
        raw_text = c.get("text", "")
        cleaned_text = _strip_citation_numbering(raw_text)
        if clean_section:
            lines.append(f"\n📄 **{source}** — {clean_section}")
        else:
            lines.append(f"\n📄 **{source}**")
        if cleaned_text:
            lines.append(f"\n> {cleaned_text}")
    return "\n".join(lines)


def _format_corrections(corrections: list) -> str:
    """Format spelling / typo corrections for display (excluding internal lemmas)."""
    return ""


def _format_token_info(
    tokens: dict | None,
    cache_id: str | None = None,
    assigned_role: str | None = None,
) -> str:
    """Format token usage and cache info for display."""
    return ""


feedback_input = None

# Replay full chat history with buttons embedded directly inside the latest assistant response
total_messages = len(st.session_state.messages)
for i, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        display_content = message["content"]
        if message.get("role") == "assistant":
            display_content = display_content.replace("Was this response relevant to your question?", "").strip()
            display_content = display_content.replace("Would you like to see the references for this?", "").strip()
        st.markdown(display_content)
        
        # Display references on demand using a native UI expander
        if message.get("role") == "assistant" and message.get("citations"):
            with st.expander("📄 Source References"):
                st.markdown(_format_citations(message["citations"], message.get("raw_answer", "")))
user_input = st.chat_input("Ask about the HR policy...")
if feedback_input:
    user_input = feedback_input

if user_input:
    question_timestamp = datetime.now(timezone.utc).isoformat()
    st.session_state.messages.append({
        "role": "user", 
        "content": user_input,
        "timestamp": question_timestamp
    })
    with st.chat_message("user"):
        st.markdown(user_input)

    # Pass clean conversational text without appended citation footers / cache badges
    conversation_history = [
        {"role": m["role"], "content": m.get("raw_answer", m["content"])}
        for m in st.session_state.messages[:-1]
    ]
    service = ChatService()
    try:
        response = service.ask(
            user_input,
            question_timestamp=question_timestamp,
            session_id=st.session_state.session_id,
            history=conversation_history,
            project_id=selected_project_id,
            defer_citations=False, # Do not defer! We want them on demand immediately in the UI.
        )
        answer = response.get("answer", "I could not find a relevant answer in the policy source.")
        citations = response.get("citations", [])
        tokens = response.get("tokens")
        cache_id = response.get("cache_id")
        assigned_role = response.get("assigned_role")
        is_latest = response.get("is_latest", True)
        corrections = response.get("corrections", [])
        action_type = response.get("action_type")
    except requests.exceptions.ConnectionError:
        answer = "The chat backend is not running. Start FastAPI with: python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
        citations = []
        tokens = None
        cache_id = None
        assigned_role = None
        is_latest = True
        corrections = []
        action_type = None
    except requests.exceptions.RequestException as error:
        answer = f"The chat backend could not process the request: {error}"
        citations = []
        tokens = None
        cache_id = None
        assigned_role = None
        is_latest = True
        corrections = []
        action_type = None

    # Just format token info and corrections into the answer
    full_content = (
        answer
        + _format_corrections(corrections)
        + _format_token_info(tokens, cache_id=cache_id, assigned_role=assigned_role)
    )

    st.session_state.messages.append({
        "role": "assistant",
        "content": full_content,
        "raw_answer": answer,
        "citations": citations,
        "action_type": action_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    with st.chat_message("assistant"):
        st.markdown(full_content)
        
        if citations:
            with st.expander("📄 Source References"):
                st.markdown(_format_citations(citations, answer))

    st.rerun()


