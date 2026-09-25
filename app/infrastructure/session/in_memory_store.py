from datetime import datetime, timezone, timedelta
import threading
from typing import Dict, Optional

from app.domain.ports.session_store import SessionData, SessionStorePort


class InMemorySessionStore(SessionStorePort):
    """Thread-safe in-memory session store adapter."""

    def __init__(self) -> None:
        self._store: Dict[str, SessionData] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> Optional[SessionData]:
        with self._lock:
            return self._store.get(session_id)

    def save(self, session_id: str, data: SessionData) -> None:
        with self._lock:
            self._store[session_id] = data

    def delete(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self._store:
                del self._store[session_id]
                return True
            return False

    def purge_expired(self, max_age_hours: float) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        with self._lock:
            expired = [
                sid for sid, data in self._store.items()
                if data.last_activity < cutoff
            ]
            for sid in expired:
                del self._store[sid]
            return len(expired)
