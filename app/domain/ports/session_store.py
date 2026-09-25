from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Protocol


@dataclass
class SessionData:
    turns: List[Dict[str, str]] = field(default_factory=list)
    user_id: Optional[str] = None
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SessionStorePort(Protocol):
    """Port for session storage, allowing extensible backends (In-Memory, Redis, SQL)."""
    def get(self, session_id: str) -> Optional[SessionData]: ...
    def save(self, session_id: str, data: SessionData) -> None: ...
    def delete(self, session_id: str) -> bool: ...
    def purge_expired(self, max_age_hours: float) -> int: ...
