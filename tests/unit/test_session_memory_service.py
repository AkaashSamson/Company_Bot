from datetime import datetime, timezone, timedelta
import pytest

from app.domain.ports.session_store import SessionData, SessionStorePort
from app.domain.services.session_memory_service import SessionMemoryService
from app.infrastructure.session.in_memory_store import InMemorySessionStore


def test_add_turn_and_get_history():
    memory = SessionMemoryService()
    session_id = "test-session-1"

    memory.add_turn(session_id, "Hello", "Hi there!", user_id="user_123")
    history = memory.get_history(session_id, user_id="user_123")

    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "Hello"}
    assert history[1] == {"role": "assistant", "content": "Hi there!"}


def test_sliding_window_buffer_limits_to_k_turns():
    # 2 turns = 4 messages max
    memory = SessionMemoryService(max_turns=2)
    session_id = "sliding-session"

    memory.add_turn(session_id, "q1", "a1")
    memory.add_turn(session_id, "q2", "a2")
    memory.add_turn(session_id, "q3", "a3")

    history = memory.get_history(session_id)
    assert len(history) == 4
    # q1/a1 should have slid out of buffer
    assert history[0]["content"] == "q2"
    assert history[1]["content"] == "a2"
    assert history[2]["content"] == "q3"
    assert history[3]["content"] == "a3"


def test_user_ownership_isolation():
    memory = SessionMemoryService()
    session_id = "secure-session"

    memory.add_turn(session_id, "Secret question", "Secret answer", user_id="user_alice")

    # Alice can read
    alice_history = memory.get_history(session_id, user_id="user_alice")
    assert len(alice_history) == 2

    # Bob cannot read Alice's session (session hijacking prevented)
    bob_history = memory.get_history(session_id, user_id="user_bob")
    assert bob_history == []

    # Bob cannot clear Alice's session
    assert memory.clear_session(session_id, user_id="user_bob") is False
    assert len(memory.get_history(session_id, user_id="user_alice")) == 2


def test_inactivity_ttl_expiration():
    memory = SessionMemoryService(inactivity_timeout_hours=1.0)
    session_id = "stale-session"

    memory.add_turn(session_id, "Old question", "Old answer")

    # Manually backdate last_activity by 2 hours
    stored = memory.store.get(session_id)
    assert stored is not None
    stored.last_activity = datetime.now(timezone.utc) - timedelta(hours=2)

    # Next access should trigger lazy expiration and return empty list
    history = memory.get_history(session_id)
    assert history == []
    assert memory.store.get(session_id) is None


def test_clear_session_explicit():
    memory = SessionMemoryService()
    session_id = "clear-me"

    memory.add_turn(session_id, "q", "a")
    assert len(memory.get_history(session_id)) == 2

    success = memory.clear_session(session_id)
    assert success is True
    assert memory.get_history(session_id) == []


def test_purge_expired_sessions():
    memory = SessionMemoryService(inactivity_timeout_hours=1.0)

    # Session 1: Active
    memory.add_turn("sess_active", "q_active", "a_active")

    # Session 2: Stale (3 hours old)
    memory.add_turn("sess_stale", "q_stale", "a_stale")
    stale_data = memory.store.get("sess_stale")
    assert stale_data is not None
    stale_data.last_activity = datetime.now(timezone.utc) - timedelta(hours=3)

    purged_count = memory.purge_expired_sessions(max_age_hours=1.0)
    assert purged_count == 1
    assert memory.store.get("sess_stale") is None
    assert memory.store.get("sess_active") is not None


def test_custom_session_store_injection():
    """Verify Open-Closed principle: custom store conforming to SessionStorePort can be injected."""
    custom_store = InMemorySessionStore()
    memory = SessionMemoryService(store=custom_store)

    memory.add_turn("custom_sess", "hello", "world")
    assert custom_store.get("custom_sess") is not None
    assert len(memory.get_history("custom_sess")) == 2


def test_backward_compatibility_get_recent_messages():
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
