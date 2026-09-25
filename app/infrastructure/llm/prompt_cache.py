import json
import logging
import math
from collections import OrderedDict
from threading import RLock
from typing import Any, Callable, Dict, List, Optional, Sequence

from sentence_transformers import SentenceTransformer

from app.core.settings import EMBEDDING_MODEL, LLM_CACHE_SIMILARITY_THRESHOLD

logger = logging.getLogger(__name__)


class PromptLRUCache:
    """Thread-safe in-memory LRU cache for generated prompt responses."""

    def __init__(
        self,
        maxsize: int = 128,
        similarity_threshold: float = LLM_CACHE_SIMILARITY_THRESHOLD,
        embedder: Callable[[str], Sequence[float]] | None = None,
    ):
        self.maxsize = max(0, maxsize)
        self.similarity_threshold = similarity_threshold
        self._embedder = embedder
        self._embedding_model = None
        self._entries: OrderedDict[str, tuple[str, list[float]]] = OrderedDict()
        self._lock = RLock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def make_key(messages: Any) -> str:
        if isinstance(messages, str):
            return messages
        return json.dumps(messages, sort_keys=True, separators=(",", ":"))

    def _embed(self, key: str) -> list[float]:
        if self._embedder is not None:
            return list(self._embedder(key))
        try:
            parsed = json.loads(key)
            if isinstance(parsed, list):
                embed_text = " ".join(
                    message.get("content", "")
                    for message in parsed
                    if isinstance(message, dict) and message.get("role") in ("system", "user")
                ) or key
            elif isinstance(parsed, str):
                embed_text = parsed
            else:
                embed_text = str(parsed)
        except (TypeError, ValueError):
            embed_text = key

        # If the user message is formatted with document context and "Question: ...",
        # isolate the question so that shared background context does not dominate the embedding.
        if "Question:" in embed_text:
            embed_text = embed_text.split("Question:", 1)[1].strip()

        if self._embedding_model is None:
            self._embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        return self._embedding_model.encode(embed_text, convert_to_numpy=True).tolist()

    @staticmethod
    def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
        numerator = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if not left_norm or not right_norm:
            return 0.0
        return numerator / (left_norm * right_norm)

    def get(self, messages: List[Dict[str, str]]) -> Optional[str]:
        if self.maxsize == 0:
            with self._lock:
                self._misses += 1
            logger.info("cache_miss cache=llm reason=disabled")
            return None

        key = self.make_key(messages)
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                self._entries.move_to_end(key)
                self._hits += 1
                logger.info("cache_hit cache=llm size=%d hits=%d", len(self._entries), self._hits)
                return entry[0]

        query_vector = self._embed(key)
        with self._lock:
            best_key = None
            best_score = 0.0
            for cached_key, (_, cached_vector) in self._entries.items():
                score = self._cosine_similarity(query_vector, cached_vector)
                if score > best_score:
                    best_key = cached_key
                    best_score = score
            if best_key is not None and best_score >= self.similarity_threshold:
                self._entries.move_to_end(best_key)
                self._hits += 1
                logger.info(
                    "cache_hit cache=llm mode=semantic score=%.3f threshold=%.3f",
                    best_score,
                    self.similarity_threshold,
                )
                return self._entries[best_key][0]

            self._misses += 1
            logger.info("cache_miss cache=llm size=%d misses=%d", len(self._entries), self._misses)
            return None

    @property
    def hits(self) -> int:
        with self._lock:
            return self._hits

    @property
    def misses(self) -> int:
        with self._lock:
            return self._misses

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    def put(self, messages: List[Dict[str, str]], response: str) -> None:
        if self.maxsize == 0:
            return

        key = self.make_key(messages)
        vector = self._embed(key)
        with self._lock:
            self._entries[key] = (response, vector)
            self._entries.move_to_end(key)
            while len(self._entries) > self.maxsize:
                self._entries.popitem(last=False)
            logger.info("cache_store cache=llm size=%d capacity=%d", len(self._entries), self.maxsize)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._hits = 0
            self._misses = 0