import streamlit as st
import requests

from streamlit_app.services.chat_service import ChatService

st.set_page_config(page_title="KnowLayer HR Chatbot", page_icon="📘")
st.title("KnowLayer HR Policy Assistant")

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

    service = ChatService(base_url="http://localhost:8000")
    try:
        response = service.ask(
            user_input,
            session_id="streamlit-session",
            history=conversation_history,
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
