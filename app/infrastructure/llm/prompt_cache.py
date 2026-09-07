import json
from collections import OrderedDict
from threading import RLock
from typing import Dict, List, Optional


class PromptLRUCache:
    """Thread-safe in-memory LRU cache for generated prompt responses."""

    def __init__(self, maxsize: int = 128):
        self.maxsize = max(0, maxsize)
        self._entries: OrderedDict[str, str] = OrderedDict()
        self._lock = RLock()

    @staticmethod
    def make_key(messages: List[Dict[str, str]]) -> str:
        return json.dumps(messages, sort_keys=True, separators=(",", ":"))

    def get(self, messages: List[Dict[str, str]]) -> Optional[str]:
        if self.maxsize == 0:
            return None

        key = self.make_key(messages)
        with self._lock:
            response = self._entries.get(key)
            if response is not None:
                self._entries.move_to_end(key)
            return response

    def put(self, messages: List[Dict[str, str]], response: str) -> None:
        if self.maxsize == 0:
            return

        key = self.make_key(messages)
        with self._lock:
            self._entries[key] = response
            self._entries.move_to_end(key)
            while len(self._entries) > self.maxsize:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()