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
        self._lock = RLock()

        # Entries parallel to _matrix rows: list of FAQ dicts
        self._entries: list[dict] = []
        # Shape (N, D) float32 — normalised question embeddings
        self._matrix: Optional[np.ndarray] = None

        if not self.enabled:
            logger.info("FAQSimilarityCache is disabled via configuration.")
            return

        path = Path(faq_path or FAQ_JSON_PATH)
        if not path.exists():
            logger.warning(
                "FAQSimilarityCache: JSON file not found at %s — cache disabled.", path
            )
            self.enabled = False
            return

        try:
            faqs = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "FAQSimilarityCache: could not load %s (%s) — cache disabled.", path, exc
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
