import streamlit as st

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
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    service = ChatService(base_url="http://localhost:8000")
    response = service.ask(user_input, session_id="streamlit-session")
    answer = response.get("answer", "I could not find a relevant answer in the policy source.")
    st.session_state.messages.append({"role": "assistant", "content": answer})
    with st.chat_message("assistant"):
        st.markdown(answer)
        for citation in response.get("citations", []):
            st.caption(f"Source: {citation.get('source', 'Policy')} | Section: {citation.get('section', 'Policy')}")
            st.write(citation.get("text", ""))
