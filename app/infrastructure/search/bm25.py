"""
app/infrastructure/search/bm25.py
Sparse Lexical BM25 Search & Reciprocal Rank Fusion (RRF) for KnowLayer (Company_Bot).

Cures 'Vector Blindness' by ensuring chunks containing exact acronyms, policy codes,
dollar figures, and technical nouns (e.g. "Form 1095-C", "ISO-27001", "Tier-3 deductible")
are pulled into the Top-15 candidate pool for cross-encoder reranking.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Stop words to suppress high-frequency non-discriminative terms
DEFAULT_STOP_WORDS = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "could", "did", "do", "does", "doing", "down",
    "during", "each", "few", "for", "from", "further", "had", "has", "have",
    "having", "he", "her", "here", "hers", "herself", "him", "himself", "his",
    "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me",
    "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on",
    "once", "only", "or", "other", "our", "ours", "ourselves", "out", "over",
    "own", "same", "she", "should", "so", "some", "such", "than", "that", "the",
    "their", "theirs", "them", "themselves", "then", "there", "these", "they",
    "this", "those", "through", "to", "too", "under", "until", "up", "very",
    "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom",
    "why", "with", "would", "you", "your", "yours", "yourself", "yourselves",
})

# Token pattern capturing words, acronyms, and alphanumeric identifiers with hyphens/slashes
TOKEN_REGEX = re.compile(r"[a-z0-9]+(?:[-_/][a-z0-9]+)*")


def tokenize_for_bm25(text: str, remove_stopwords: bool = True) -> List[str]:
    """Tokenize text into lowercase alphanumeric and hyphenated tokens."""
    if not text:
        return []
    # Strip HTML stitch tags before tokenization
    clean = re.sub(r"<!--\s*CUTOFF(?:_START|_END)?\s*-->", " ", text, flags=re.IGNORECASE)
    tokens = TOKEN_REGEX.findall(clean.lower())
    if remove_stopwords:
        tokens = [t for t in tokens if t not in DEFAULT_STOP_WORDS and len(t) > 1]
    return tokens


class PurePythonBM25Okapi:
    """Zero-dependency reference implementation of BM25Okapi."""

    def __init__(
        self,
        corpus: List[List[str]],
        k1: float = 1.5,
        b: float = 0.75,
        epsilon: float = 0.25,
    ) -> None:
        self.k1 = k1
        self.b = b
        self.epsilon = epsilon
        self.corpus_size = len(corpus)
        self.doc_lengths = [len(doc) for doc in corpus]
        self.avgdl = (
            sum(self.doc_lengths) / self.corpus_size if self.corpus_size > 0 else 1.0
        )
        self.doc_freqs: List[Dict[str, int]] = []
        self.idf: Dict[str, float] = {}
        self._initialize(corpus)

    def _initialize(self, corpus: List[List[str]]) -> None:
        df: Dict[str, int] = {}
        for doc in corpus:
            frequencies: Dict[str, int] = {}
            for term in doc:
                frequencies[term] = frequencies.get(term, 0) + 1
            self.doc_freqs.append(frequencies)
            for term in frequencies.keys():
                df[term] = df.get(term, 0) + 1

        negative_idfs = []
        idf_sum = 0.0
        for term, freq in df.items():
            idf = math.log(
                (self.corpus_size - freq + 0.5) / (freq + 0.5) + 1.0
            )
            self.idf[term] = idf
            idf_sum += idf
            if idf < 0:
                negative_idfs.append(term)

        average_idf = idf_sum / len(df) if df else 0.0
        eps = self.epsilon * average_idf
        for term in negative_idfs:
            self.idf[term] = eps

    def get_scores(self, query: List[str]) -> List[float]:
        score = [0.0] * self.corpus_size
        for q in query:
            q_idf = self.idf.get(q)
            if q_idf is None:
                continue
            for i, doc_freq in enumerate(self.doc_freqs):
                freq = doc_freq.get(q, 0)
                if freq == 0:
                    continue
                denom = freq + self.k1 * (1.0 - self.b + self.b * (self.doc_lengths[i] / self.avgdl))
                score[i] += q_idf * (freq * (self.k1 + 1.0) / denom)
        return score


class BM25Retriever:
    """Manages corpus indexing and sparse BM25 retrieval for hybrid vector search."""

    def __init__(self) -> None:
        self.corpus_chunks: List[Dict[str, Any]] = []
        self.tokenized_corpus: List[List[str]] = []
        self.bm25_model: Optional[Any] = None

    def index_chunks(self, chunks: List[Dict[str, Any]]) -> None:
        """Build or refresh BM25 index over a collection of document chunks."""
        self.corpus_chunks = chunks
        self.tokenized_corpus = [
            tokenize_for_bm25(c.get("text", "")) for c in chunks
        ]
        if not self.tokenized_corpus:
            self.bm25_model = None
            return

        # Use modern Robertson-Spärck Jones (+1.0) smoothed BM25Okapi
        self.bm25_model = PurePythonBM25Okapi(self.tokenized_corpus)

        logger.info("BM25 index built with %d documents", len(self.corpus_chunks))

    def search(
        self,
        query: str,
        top_k: int = 15,
        filter_fn: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> List[Dict[str, Any]]:
        """Search indexed chunks using BM25 and return Top-K scored candidates."""
        if self.bm25_model is None or not self.corpus_chunks:
            return []

        q_tokens = tokenize_for_bm25(query)
        if not q_tokens:
            return []

        scores = self.bm25_model.get_scores(q_tokens)
        max_score = float(max(scores)) if len(scores) > 0 else 0.0

        scored_candidates = []
        for idx, score in enumerate(scores):
            if score <= 0.0:
                continue
            chunk = self.corpus_chunks[idx]
            if filter_fn and not filter_fn(chunk):
                continue
            # Distance approximation from BM25 score (bounded between 0.05 and 0.95)
            approx_dist = round(max(0.05, 1.0 - (score / (max_score * 1.5 if max_score > 0 else 1.0))), 4)
            scored_candidates.append({
                **chunk,
                "_bm25_score": float(score),
                "distance": approx_dist,
            })

        scored_candidates.sort(key=lambda x: x["_bm25_score"], reverse=True)
        top_results = scored_candidates[:top_k]
        for rank, cand in enumerate(top_results, start=1):
            cand["_bm25_rank"] = rank
        return top_results


def compute_rrf(
    vector_candidates: Sequence[Dict[str, Any]],
    bm25_candidates: Sequence[Dict[str, Any]],
    k: int = 60,
    top_k: int = 15,
) -> List[Dict[str, Any]]:
    """Reciprocal Rank Fusion (RRF) between Dense Vector search and Sparse BM25 search.

    Formula:
        RRF_Score(c) = 1 / (60 + rank_vector(c)) + 1 / (60 + rank_bm25(c))

    Ensures chunks with exact lexical matches (acronyms, policy numbers, dollar limits)
    are forced into the Top-15 candidate pool even when bi-encoder vector similarity is low.
    """
    fused: Dict[str, Dict[str, Any]] = {}

    # 1. Process vector candidates
    for rank, cand in enumerate(vector_candidates, start=1):
        cid = str(cand.get("id") or cand.get("chunk_id") or f"vec_{rank}")
        entry = cand.copy()
        entry["_vector_rank"] = rank
        rrf = 1.0 / (k + rank)
        entry["_rrf_score"] = rrf
        fused[cid] = entry

    # 2. Fuse BM25 candidates
    for rank, cand in enumerate(bm25_candidates, start=1):
        cid = str(cand.get("id") or cand.get("chunk_id") or f"bm25_{rank}")
        rrf_delta = 1.0 / (k + rank)
        if cid in fused:
            fused[cid]["_rrf_score"] += rrf_delta
            fused[cid]["_bm25_rank"] = rank
            fused[cid]["_bm25_score"] = cand.get("_bm25_score", 0.0)
        else:
            entry = cand.copy()
            entry["_bm25_rank"] = rank
            entry["_rrf_score"] = rrf_delta
            # Preserve valid finite distance for downstream quality checks
            if entry.get("distance") is None:
                entry["distance"] = 0.45
            fused[cid] = entry

    # Sort descending by fused RRF score
    ranked = sorted(fused.values(), key=lambda x: x.get("_rrf_score", 0.0), reverse=True)
    return ranked[:top_k]
