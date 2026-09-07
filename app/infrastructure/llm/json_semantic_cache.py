import json
import logging
import math
from pathlib import Path
from threading import RLock
from typing import Callable, Dict, List, Optional, Sequence

from sentence_transformers import SentenceTransformer

from app.core.settings import EMBEDDING_MODEL, LLM_CACHE_SIMILARITY_THRESHOLD

logger = logging.getLogger(__name__)


class JsonSemanticResponseCache:
    """Persistent semantic response cache storing question vectors and outputs in JSON."""

    def __init__(
        self,
        path: str | Path,
        maxsize: int = 128,
        similarity_threshold: float = LLM_CACHE_SIMILARITY_THRESHOLD,
        embedder: Callable[[str], Sequence[float]] | None = None,
    ):
        self.path = Path(path)
        self.maxsize = max(0, maxsize)
        self.similarity_threshold = similarity_threshold
        self._embedder = embedder
        self._embedding_model = None
        self._lock = RLock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _question(messages: List[Dict[str, str]]) -> str:
        return " ".join(
            message.get("content", "")
            for message in messages
            if message.get("role") == "user"
        ) or json.dumps(messages, sort_keys=True, separators=(",", ":"))

    def _embed(self, question: str) -> list[float]:
        if self._embedder is not None:
            return list(self._embedder(question))
        if self._embedding_model is None:
            self._embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        return self._embedding_model.encode(
            question,
            convert_to_numpy=True,
        ).tolist()

    @staticmethod
    def _similarity(left: Sequence[float], right: Sequence[float]) -> float:
        numerator = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if not left_norm or not right_norm:
            return 0.0
        return numerator / (left_norm * right_norm)

    def _load_entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            entries = data.get("entries", []) if isinstance(data, dict) else []
            return entries if isinstance(entries, list) else []
        except (OSError, json.JSONDecodeError):
            logger.warning("response_json_cache_read_failed path=%s", self.path)
            return []

    def _save_entries(self, entries: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps({"entries": entries}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self.path)

    def get(self, messages: List[Dict[str, str]]) -> Optional[str]:
        if self.maxsize == 0:
            self._misses += 1
            return None

        question = self._question(messages)
        vector = self._embed(question)
        with self._lock:
            entries = self._load_entries()
            best_entry = None
            best_score = 0.0
            for entry in entries:
                score = self._similarity(vector, entry.get("vector", []))
                if score > best_score:
                    best_entry = entry
                    best_score = score
            if best_entry is not None and best_score >= self.similarity_threshold:
                self._hits += 1
                entries.remove(best_entry)
                entries.append(best_entry)
                self._save_entries(entries)
                logger.info(
                    "response_json_cache_hit score=%.3f threshold=%.3f path=%s",
                    best_score,
                    self.similarity_threshold,
                    self.path,
                )
                return best_entry.get("output")
            self._misses += 1
            logger.info("response_json_cache_miss path=%s", self.path)
            return None

    def put(self, messages: List[Dict[str, str]], response: str) -> None:
        if self.maxsize == 0:
            return

        question = self._question(messages)
        entry = {
            "input": question,
            "vector": self._embed(question),
            "output": response,
        }
        with self._lock:
            entries = [item for item in self._load_entries() if item.get("input") != question]
            entries.append(entry)
            entries = entries[-self.maxsize:]
            self._save_entries(entries)
            logger.info(
                "response_json_cache_store size=%d capacity=%d path=%s",
                len(entries),
                self.maxsize,
                self.path,
            )

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._load_entries())
