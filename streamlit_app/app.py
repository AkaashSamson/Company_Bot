import streamlit as st
import requests
import uuid

from streamlit_app.services.chat_service import ChatService
from streamlit_app.services.organization_service import OrganizationService
from streamlit_app.services.authentication_service import AuthenticationService

st.set_page_config(page_title="KnowLayer HR Chatbot", page_icon="📘")

if "auth" not in st.session_state:
    st.session_state.auth = None
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if st.session_state.auth is None:
    st.title("KnowLayer Login")
    with st.form("login"):
        login_username = st.text_input("Username")
        login_password = st.text_input("Password", type="password")
        login_submitted = st.form_submit_button("Log in")
    if login_submitted:
        try:
            st.session_state.auth = AuthenticationService().login(login_username, login_password)
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

def handle_logout():
    st.session_state.update(auth=None)
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []

st.sidebar.button("Log out", on_click=handle_logout)
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

with st.sidebar.expander("📊 Token Metrics"):
    if st.button("Refresh Stats"):
        st.rerun()
    try:
        token_res = requests.get("http://127.0.0.1:8000/api/tokens/stats", timeout=3)
        if token_res.status_code == 200:
            stats = token_res.json()
            st.write(f"**Total Tokens:** {stats.get('total_tokens', 0):,}")
            st.write(f"**API Calls:** {stats.get('call_count', 0)}")
            st.write(f"**Cache Hit Rate:** {stats.get('cache_hit_rate_percent', 0.0):.1f}%")
            st.write(f"**Prompt:** {stats.get('prompt_tokens', 0):,} | **Completion:** {stats.get('completion_tokens', 0):,}")
    except requests.exceptions.RequestException:
        st.caption("Token stats unavailable")

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

if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_response" not in st.session_state:
    st.session_state.last_response = None


def _format_citations(citations: list) -> str:
    """Convert citations list to a plain markdown string that persists in chat history."""
    if not citations:
        return ""
    lines = ["\n\n---\n**References:**"]
    for c in citations:
        source = c.get("source", "Policy")
        section = c.get("section", "")
        text = c.get("text", "")
        lines.append(f"\n📄 **{source}** — {section}")
        if text:
            lines.append(f"\n> {text}")
    return "\n".join(lines)


def _format_token_info(tokens: dict | None) -> str:
    """Format token usage info for display."""
    if not tokens:
        return ""
    
    prompt = tokens.get("prompt_tokens", 0)
    completion = tokens.get("completion_tokens", 0)
    total = tokens.get("total_tokens", 0)
    cached = tokens.get("cache_hit", False)
    
    if cached:
        return "\n\n💾 *Response from cache (0 tokens used)*"
    elif total > 0:
        return f"\n\n📊 *Tokens used: {prompt}P + {completion}C = {total}T*"
    else:
        return ""


# Replay full chat history (citations already embedded in content)
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

user_input = st.chat_input("Ask about the HR policy...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    conversation_history = list(st.session_state.messages[:-1])
    service = ChatService()
    try:
        response = service.ask(
            user_input,
            session_id=st.session_state.session_id,
            history=conversation_history,
            project_id=selected_project_id,
        )
        answer = response.get("answer", "I could not find a relevant answer in the policy source.")
        citations = response.get("citations", [])
        tokens = response.get("tokens")
    except requests.exceptions.ConnectionError:
        answer = "The chat backend is not running. Start FastAPI with: python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
        citations = []
        tokens = None
    except requests.exceptions.RequestException as error:
        answer = f"The chat backend could not process the request: {error}"
        citations = []
        tokens = None

    # Embed citations and token info as plain markdown into the answer so they persist in history
    full_content = answer + _format_citations(citations) + _format_token_info(tokens)

    st.session_state.messages.append({"role": "assistant", "content": full_content})
    with st.chat_message("assistant"):
        st.markdown(full_content)
