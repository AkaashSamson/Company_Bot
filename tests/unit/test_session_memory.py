from app.domain.services.session_memory_service import SessionMemoryService


def test_recent_messages_limit_is_bounded():
    memory = SessionMemoryService(max_messages=3)
    history = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "q3"},
    ]
    result = memory.get_recent_messages(history)
    assert len(result) == 3
    assert result[-1]["content"] == "q3"
