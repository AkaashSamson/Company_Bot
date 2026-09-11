import streamlit as st
import requests

from streamlit_app.services.chat_service import ChatService
from streamlit_app.services.organization_service import OrganizationService
from streamlit_app.services.authentication_service import AuthenticationService

st.set_page_config(page_title="KnowLayer HR Chatbot", page_icon="📘")

if "auth" not in st.session_state:
    st.session_state.auth = None

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

st.sidebar.button("Log out", on_click=lambda: st.session_state.update(auth=None))
st.title("KnowLayer HR Policy Assistant")

st.sidebar.page_link("app.py", label="Chat")
st.sidebar.page_link("pages/users.py", label="Users")
st.sidebar.page_link("pages/projects.py", label="Projects")
st.sidebar.page_link("pages/documents.py", label="Documents")

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

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

user_input = st.chat_input("Ask about the HR policy...")

if user_input:
    conversation_history = list(st.session_state.messages)
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    service = ChatService()
    try:
        response = service.ask(
            user_input,
            session_id="streamlit-session",
            history=conversation_history,
            project_id=selected_project_id,
        )
        answer = response.get("answer", "I could not find a relevant answer in the policy source.")
    except requests.exceptions.ConnectionError:
        answer = "The chat backend is not running. Start FastAPI with: python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
        response = {"citations": []}
    except requests.exceptions.RequestException as error:
        answer = f"The chat backend could not process the request: {error}"
        response = {"citations": []}
    st.session_state.messages.append({"role": "assistant", "content": answer})
    with st.chat_message("assistant"):
        st.markdown(answer)
        for citation in response.get("citations", []):
            st.caption(f"Source: {citation.get('source', 'Policy')} | Section: {citation.get('section', 'Policy')}")
            st.write(citation.get("text", ""))
