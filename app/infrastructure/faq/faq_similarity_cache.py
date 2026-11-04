"""
Similarity-based FAQ cache backed by a static JSON file.

On construction the cache loads all FAQ entries, embeds their questions
using the same sentence-transformer model used by the vector store, and
holds the resulting matrix in memory.

When search() is called with an incoming question, it computes the cosine
similarity between the question embedding and every stored FAQ embedding
and returns the best match if its similarity score meets the configured
threshold — otherwise returns None (cache miss).

This runs entirely in-process, no network calls, no database round-trips.
"""

import json
import logging
from pathlib import Path
from threading import RLock
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.settings import (
    EMBEDDING_MODEL,
    FAQ_JSON_PATH,
    FAQ_SIMILARITY_CACHE_ENABLED,
    FAQ_SIMILARITY_THRESHOLD,
)

logger = logging.getLogger(__name__)


class FAQSimilarityCache:
    """
    In-memory semantic cache over a static FAQ JSON file.

    The JSON file must be a list of objects with at least:
        { "id": str, "question": str, "answer": str }

    Parameters
    ----------
    faq_path : str | Path | None
        Path to the FAQ JSON file. Defaults to FAQ_JSON_PATH from settings.
    threshold : float
        Minimum cosine similarity (0-1) required for a cache hit.
        Defaults to FAQ_SIMILARITY_THRESHOLD from settings.
    enabled : bool
        When False the cache always returns None (pass-through mode).
        Defaults to FAQ_SIMILARITY_CACHE_ENABLED from settings.
    model_name : str
        Sentence-transformer model used for embedding questions.
        Must match the model used for document retrieval.
    """

    def __init__(
        self,
        faq_path: Optional[str] = None,
        threshold: float = FAQ_SIMILARITY_THRESHOLD,
        enabled: bool = FAQ_SIMILARITY_CACHE_ENABLED,
        model_name: str = EMBEDDING_MODEL,
    ):
        self.threshold = threshold
        self.enabled = enabled
        self.model_name = model_name
        self.faq_path = Path(faq_path or FAQ_JSON_PATH)
        self._lock = RLock()

        # Entries parallel to _matrix rows: list of FAQ dicts
        self._entries: list[dict] = []
        # Shape (N, D) float32 — normalised question embeddings
        self._matrix: Optional[np.ndarray] = None

        if not self.enabled:
            logger.info("FAQSimilarityCache is disabled via configuration.")
            return

        if not self.faq_path.exists():
            logger.warning(
                "FAQSimilarityCache: JSON file not found at %s — cache disabled.", self.faq_path
            )
            self.enabled = False
            return

        try:
            faqs = json.loads(self.faq_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "FAQSimilarityCache: could not load %s (%s) — cache disabled.", self.faq_path, exc
            )
            self.enabled = False
            return

        if not faqs:
            logger.warning("FAQSimilarityCache: FAQ file is empty — cache disabled.")
            self.enabled = False
            return

        logger.info("FAQSimilarityCache: loading embedding model '%s'…", model_name)
        model = SentenceTransformer(model_name)

        questions = [entry["question"] for entry in faqs]
        raw: np.ndarray = model.encode(
            questions,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        self._entries = list(faqs)
        self._matrix = raw.astype(np.float32)
        self._model = model  # reuse in _search — avoids reloading

        logger.info(
            "FAQSimilarityCache: indexed %d FAQs (threshold=%.2f).",
            len(self._entries),
            self.threshold,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, question: str) -> Optional[dict]:
        """
        Return the best-matching FAQ entry if similarity >= threshold.

        Returns a dict with keys: id, question, answer, similarity.
        Returns None on a cache miss or when the cache is disabled.
        """
        if not self.enabled or self._matrix is None:
            return None

        with self._lock:
            return self._search(question)

    def size(self) -> int:
        """Number of FAQ entries currently indexed."""
        return len(self._entries)

    def delete_entry(self, question_or_id: str) -> bool:
        """
        Delete an FAQ entry by ID or question text from both the in-memory cache
        and the persistent JSON file on disk, then re-index the similarity matrix.
        Returns True if an entry was matched and deleted, False otherwise.
        """
        with self._lock:
            if not self._entries:
                return False

            target = question_or_id.strip().lower()
            initial_count = len(self._entries)

            remaining = [
                entry for entry in self._entries
                if entry.get("id", "").strip().lower() != target
                and entry.get("question", "").strip().lower() != target
            ]

            if len(remaining) == initial_count:
                logger.info(
                    "FAQSimilarityCache: no matching entry found to delete for '%s'",
                    question_or_id,
                )
                return False

            self._entries = remaining

            # Persist updated entries to JSON file on disk
            try:
                self.faq_path.parent.mkdir(parents=True, exist_ok=True)
                temp_file = self.faq_path.with_suffix(".tmp")
                temp_file.write_text(
                    json.dumps(self._entries, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                temp_file.replace(self.faq_path)
                logger.info(
                    "FAQSimilarityCache: persisted deletion of '%s' to %s",
                    question_or_id,
                    self.faq_path,
                )
            except Exception as exc:
                logger.error(
                    "FAQSimilarityCache: failed to write updated FAQs to %s: %s",
                    self.faq_path,
                    exc,
                )

            # Re-index similarity matrix
            if self._entries:
                if not hasattr(self, "_model") or self._model is None:
                    self._model = SentenceTransformer(self.model_name)
                questions = [entry["question"] for entry in self._entries]
                raw = self._model.encode(
                    questions,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                self._matrix = raw.astype(np.float32)
            else:
                self._matrix = None

            logger.info(
                "FAQSimilarityCache: successfully deleted '%s'. %d entries remaining.",
                question_or_id,
                len(self._entries),
            )
            return True

    def clear(self) -> None:
        """Clear all in-memory FAQ entries and similarity matrix."""
        with self._lock:
            self._entries = []
            self._matrix = None
            logger.info("FAQSimilarityCache: cleared in-memory entries and matrix.")

    def reload(self) -> bool:
        """Reload and re-index the FAQ JSON file from disk."""
        with self._lock:
            if not self.faq_path.exists():
                logger.warning("FAQSimilarityCache: reload failed, %s does not exist.", self.faq_path)
                return False
            try:
                faqs = json.loads(self.faq_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.error("FAQSimilarityCache: failed to reload %s: %s", self.faq_path, exc)
                return False

            if not isinstance(faqs, list):
                logger.warning("FAQSimilarityCache: JSON content at %s is not a list.", self.faq_path)
                return False

            self._entries = list(faqs)
            if self._entries:
                if not hasattr(self, "_model") or self._model is None:
                    self._model = SentenceTransformer(self.model_name)
                questions = [entry["question"] for entry in self._entries]
                raw = self._model.encode(
                    questions,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                self._matrix = raw.astype(np.float32)
            else:
                self._matrix = None

            logger.info(
                "FAQSimilarityCache: reloaded %d FAQs from %s.",
                len(self._entries),
                self.faq_path,
            )
            return True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _search(self, question: str) -> Optional[dict]:
        if not hasattr(self, "_model"):
            self._model = SentenceTransformer(EMBEDDING_MODEL)

        query_vec: np.ndarray = self._model.encode(
            [question],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0].astype(np.float32)   # shape (D,)

        # Cosine similarity = dot product of unit vectors
        scores: np.ndarray = self._matrix @ query_vec   # shape (N,)

        best_idx: int = int(np.argmax(scores))
        best_score: float = float(scores[best_idx])

        logger.debug(
            "FAQSimilarityCache: best match '%s' (score=%.4f, threshold=%.2f)",
            self._entries[best_idx]["question"],
            best_score,
            self.threshold,
        )

        if best_score >= self.threshold:
            return {
                **self._entries[best_idx],
                "similarity": round(best_score, 4),
            }

        return None
