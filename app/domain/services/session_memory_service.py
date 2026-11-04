from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from app.core.settings import (
    SESSION_INACTIVITY_TIMEOUT_HOURS,
    SESSION_MAX_HISTORY_TURNS,
)
from app.domain.ports.session_store import SessionData, SessionStorePort


class SessionMemoryService:
    """Stateful domain service for conversation session memory.
    Enforces sliding window buffer ($k=6$ turns), inactivity TTL, and user isolation.
    Decoupled from storage via SessionStorePort.
    """

    def __init__(
        self,
        max_messages: Optional[int] = None,
        max_turns: int = SESSION_MAX_HISTORY_TURNS,
        inactivity_timeout_hours: float = SESSION_INACTIVITY_TIMEOUT_HOURS,
        store: Optional[SessionStorePort] = None,
    ) -> None:
        self.max_turns = (max_messages // 2) if max_messages is not None else max_turns
        self.max_messages = max_messages if max_messages is not None else (self.max_turns * 2)
        self.inactivity_timeout = timedelta(hours=inactivity_timeout_hours)

        if store is None:
            # Default to in-memory store adapter for convenience
            from app.infrastructure.session.in_memory_store import InMemorySessionStore
            store = InMemorySessionStore()
        self.store: SessionStorePort = store

    def get_history(self, session_id: str, user_id: Optional[str] = None) -> List[Dict[str, str]]:
        """Retrieve conversation history turns for a session.
        Validates user ownership if user_id is provided. Returns empty list if expired or mismatch.
        """
        if not session_id:
            return []
        data = self.store.get(session_id)
        if data is None:
            return []

        # Validate user ownership
        if user_id and data.user_id and data.user_id != user_id:
            return []

        # Lazy check on access for business logic correctness
        now = datetime.now(timezone.utc)
        if (now - data.last_activity) > self.inactivity_timeout:
            self.store.delete(session_id)
            return []

        return list(data.turns)

    def add_turn(
        self,
        session_id: str,
        user_query: str,
        assistant_response: str,
        user_id: Optional[str] = None,
    ) -> None:
        """Append a user/assistant turn to the session history, respecting sliding window and TTL."""
        if not session_id:
            return

        now = datetime.now(timezone.utc)
        data = self.store.get(session_id)
        if data is None or (now - data.last_activity) > self.inactivity_timeout:
            data = SessionData(turns=[], user_id=user_id, last_activity=now)

        if user_id and not data.user_id:
            data.user_id = user_id

        data.turns.append({"role": "user", "content": user_query})
        data.turns.append({"role": "assistant", "content": assistant_response})

        max_msgs = self.max_turns * 2
        if len(data.turns) > max_msgs:
            data.turns = data.turns[-max_msgs:]

        data.last_activity = now
        self.store.save(session_id, data)

    def clear_session(self, session_id: str, user_id: Optional[str] = None) -> bool:
        """Explicitly clear conversation history for a session, checking user ownership if provided."""
        if not session_id:
            return False
        if user_id:
            data = self.store.get(session_id)
            if data and data.user_id and data.user_id != user_id:
                return False
        return self.store.delete(session_id)

    def purge_expired_sessions(self, max_age_hours: Optional[float] = None) -> int:
        """Housekeeping: purge inactive sessions older than max_age_hours."""
        hours = max_age_hours if max_age_hours is not None else (self.inactivity_timeout.total_seconds() / 3600.0)
        return self.store.purge_expired(hours)

    def get_recent_messages(
        self,
        history: List[Dict[str, str]],
        max_messages: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """Stateless backward-compatible helper for existing callers."""
        if not history:
            return []
        limit = max_messages if max_messages is not None else self.max_messages
        return history[-limit:]
