import streamlit as st
import requests

from streamlit_app.services.chat_service import ChatService
#
st.set_page_config(page_title="KnowLayer HR Chatbot", page_icon="📘")
st.title("KnowLayer HR Policy Assistant")

# Sidebar for token metrics
with st.sidebar:
    st.header("📊 Token Metrics")
    if st.button("Refresh Stats"):
        st.rerun()
    
    try:
        # Fetch token statistics from backend
        response = requests.get("http://localhost:8000/api/tokens/stats", timeout=5)
        if response.status_code == 200:
            stats = response.json()
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric(
                    "Total Tokens",
                    f"{stats['total_tokens']:,}",
                    help="Total tokens consumed across all calls"
                )
                st.metric(
                    "API Calls",
                    stats['call_count'],
                    help="Total number of LLM API calls"
                )
            
            with col2:
                st.metric(
                    "Avg per Call",
                    f"{stats['avg_tokens_per_call']:.0f}",
                    help="Average tokens per API call"
                )
                st.metric(
                    "Cache Hit Rate",
                    f"{stats['cache_hit_rate_percent']:.1f}%",
                    help="Percentage of cached responses"
                )
            
            with st.expander("📈 Detailed Stats"):
                st.write(f"**Prompt Tokens:** {stats['prompt_tokens']:,}")
                st.write(f"**Completion Tokens:** {stats['completion_tokens']:,}")
                st.write(f"**Cache Hits:** {stats['cache_hits']}")
                st.write(f"**Cache Misses:** {stats['cache_misses']}")
                
    except requests.exceptions.RequestException:
        st.warning("Could not fetch token metrics (backend not running)")


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
    service = ChatService(base_url="http://localhost:8000")
    try:
        response = service.ask(
            user_input,
            session_id="streamlit-session",
            history=conversation_history,
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
