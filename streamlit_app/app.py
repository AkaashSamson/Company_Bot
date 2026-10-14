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



# Replay full chat history with citations collapsed in an expander
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        citations = message.get("citations") or []
        if citations:
            with st.expander(f"📚 Sources & References ({len(citations)})", expanded=False):
                for c in citations:
                    src = c.get("source") or "Policy"
                    sec = c.get("section") or ""
                    txt = c.get("text") or ""
                    sec_lbl = f" — *{sec}*" if sec else ""
                    st.markdown(f"📄 **{src}**{sec_lbl}")
                    if txt:
                        st.markdown(f"> {_strip_citation_numbering(txt)}")

user_input = st.chat_input("Ask about the HR policy...")

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

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "citations": citations,
        "raw_answer": answer,
        "action_type": action_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    with st.chat_message("assistant"):
        st.markdown(answer)
        if citations:
            with st.expander(f"📚 Sources & References ({len(citations)})", expanded=False):
                for c in citations:
                    src = c.get("source") or "Policy"
                    sec = c.get("section") or ""
                    txt = c.get("text") or ""
                    sec_lbl = f" — *{sec}*" if sec else ""
                    st.markdown(f"📄 **{src}**{sec_lbl}")
                    if txt:
                        st.markdown(f"> {_strip_citation_numbering(txt)}")


