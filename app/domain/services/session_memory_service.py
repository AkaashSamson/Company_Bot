from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class SessionMemoryService:
    max_messages: int = 6

    def get_recent_messages(self, history: List[Dict[str, str]]) -> List[Dict[str, str]]:
        if not history:
            return []
        return history[-self.max_messages:]
