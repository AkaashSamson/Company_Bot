#!/usr/bin/env python3
"""
KnowLayer — 7-Parameter Chunk Quality Evaluator (3-Gate Pipeline)
=================================================================
Evaluates every chunk in ChromaDB against the architectural constraints of:
  - Embedding Model : sentence-transformers/all-MiniLM-L6-v2 (256 token limit)
  - Reranker        : BAAI/bge-reranker-base
  - Merge Threshold : 0.88 (semantic_merger.py)
  - Metadata Contract: app.domain.entities.chunk_metadata.ChunkMetadata

Seven core parameters across three tiers:

  Tier 1 — Deterministic (Intrinsic)
    1. Token Budget Utilization   (s_token)   — fits 256-token window?
    2. Boundary Integrity         (s_bound)   — clean sentence/table boundaries?
    3. Metadata Completeness      (s_meta)    — ChunkMetadata contract satisfied?

  Tier 2 — Semantic (Embedding-level)
    4. Intra-Chunk Coherence      (s_coh)     — single-topic within chunk?
    5. Inter-Chunk Distinctiveness (s_dist)    — distinct from neighbors?

  Tier 3 — Contextual (LLM/Reranker-level)
    6. Self-Containment           (s_self)    — no dangling pronouns/anaphora?
    7. Reverse-Query Retrievability(s_ret)    — chunk findable via round-trip?

Three evaluation gates:
  Gate 1: Fast Static + Embedding Audit (100% of chunks, seconds)
  Gate 2: Synthetic Round-Trip Retrieval (sampled %, uses reranker)
  Gate 3: Strategy A/B Benchmarking (external — see docs)

Usage:
  # Full audit (Gate 1 + 30-chunk Gate 2 sample)
  python scripts/evaluate_chunking_quality.py --sample-ret 30 --output reports/chunk_audit.json

  # Fast CI/CD mode (Gate 1 only, zero CrossEncoder overhead)
  python scripts/evaluate_chunking_quality.py --sample-ret 0 --skip-reranker

  # JSON-only output
  python scripts/evaluate_chunking_quality.py --json --sample-ret 20
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Project Root & sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Safe stdout encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.settings import (
    BASE_DIR,
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    RAG_CANDIDATE_COUNT,
    RAG_FINAL_K,
    RAG_RERANKER_MODEL,
    SEMANTIC_MERGE_SIMILARITY_THRESHOLD,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("chunk_evaluator")


# ---------------------------------------------------------------------------
# Constants & Regex Heuristics
# ---------------------------------------------------------------------------

# Canonical metadata fields from app/domain/entities/chunk_metadata.py
# These are the keys that ChunkMetadata.as_dict() emits.
CANONICAL_METADATA_FIELDS = (
    "document_id",
    "project_id",
    "source_filename",
    "chunk_index",
    "content_type",
)
# Optional (present only when the source provides them):
OPTIONAL_METADATA_FIELDS = (
    "page_number",
    "section_heading",
    "hierarchy_path",
)

# Dangling anaphora / unresolved reference words at start of chunk
DANGLING_PRONOUNS = frozenset({
    "this", "that", "these", "those", "it", "its", "they", "them",
    "their", "he", "she", "his", "her", "such", "above", "below",
    "aforementioned", "former", "latter", "thereof", "herein",
})

SENTENCE_SPLIT_REGEX = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")
MARKDOWN_HEADING_END_REGEX = re.compile(r"(?:^|\n)#{1,6}\s+[^\n]+\s*$")
MARKDOWN_TABLE_SEP_REGEX = re.compile(r"\|\s*:?-{3,}:?\s*\|")
TERMINAL_PUNCTUATION = (".", "?", "!", ":", "|", ")", "]", '"', "'")

# Token budget zones (word-piece tokens for all-MiniLM-L6-v2)
TOKEN_HARD_CEILING = 256
TOKEN_SWEET_UPPER = 240
TOKEN_SWEET_LOWER = 80
TOKEN_MICRO_FRAGMENT = 40


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------
@dataclass
class ChunkRecord:
    """Internal representation of a chunk loaded from ChromaDB."""
    chunk_id: str
    text: str
    metadata: Dict[str, Any]
    embedding: Optional[np.ndarray] = None


@dataclass
class ChunkScorecard:
    """Per-chunk quality scorecard across all 7 parameters."""
    chunk_id: str
    source_file: str
    chunk_type: str
    token_count: int

    # 7 Core Parameters (0.0 to 1.0)
    s_token: float          # 1. Token Budget Utilization
    s_bound: float          # 2. Boundary & Structural Integrity
    s_meta: float           # 3. Metadata & Hierarchy Completeness
    s_coh: float            # 4. Intra-Chunk Semantic Coherence
    s_dist: float           # 5. Inter-Chunk Distinctiveness
    s_self: float           # 6. De-contextualization / Self-Containment
    s_ret: Optional[float]  # 7. Reverse-Query Retrievability (Gate 2 only)

    # Composite Score & Diagnostic Flags
    composite_intrinsic_score: float
    failure_flags: List[str] = field(default_factory=list)
    synthetic_query: Optional[str] = None
    retrieval_rank: Optional[int] = None


# ---------------------------------------------------------------------------
# Core Evaluator Engine
# ---------------------------------------------------------------------------
class KnowLayerChunkEvaluator:
    """7-Parameter chunk quality evaluator for the KnowLayer RAG pipeline.

    Uses the same embedding model (all-MiniLM-L6-v2) and reranker
    (BAAI/bge-reranker-base) as the production pipeline for accurate
    assessment of retrieval fitness.
    """

    def __init__(
        self,
        embedding_model_name: str = EMBEDDING_MODEL,
        reranker_model_name: str = RAG_RERANKER_MODEL,
        enable_reranker: bool = True,
    ) -> None:
        from sentence_transformers import CrossEncoder, SentenceTransformer
        from transformers import AutoTokenizer

        logger.info("Loading tokenizer & embedding model: %s", embedding_model_name)
        self.tokenizer = AutoTokenizer.from_pretrained(embedding_model_name)
        self.embedder = SentenceTransformer(embedding_model_name)
        self.reranker = None
        if enable_reranker:
            logger.info("Loading BGE cross-encoder reranker: %s", reranker_model_name)
            self.reranker = CrossEncoder(reranker_model_name)

    # -----------------------------------------------------------------------
    # Parameter 1: Token Budget Utilization (s_token)
    # -----------------------------------------------------------------------
    def score_token_budget(self, text: str) -> Tuple[float, int, List[str]]:
        """Score whether the chunk fits all-MiniLM-L6-v2's hard 256-token window.

        Scoring zones:
          - > 256 tokens: 0.0 (silent truncation failure)
          - < 40 tokens:  max(0.1, N/80)  (micro-fragment penalty)
          - 40..79 tokens: N/80  (below sweet spot)
          - 80..240 tokens: 1.0  (ideal range)
          - 241..256 tokens: 1.0 - (N-240)/16  (near-ceiling warning)
        """
        flags: List[str] = []
        tokens = self.tokenizer.encode(text, add_special_tokens=True, truncation=False)
        n_tokens = len(tokens)

        if n_tokens > TOKEN_HARD_CEILING:
            flags.append(f"TRUNCATION_FAILURE ({n_tokens}>{TOKEN_HARD_CEILING} tokens)")
            return 0.0, n_tokens, flags

        if n_tokens < TOKEN_MICRO_FRAGMENT:
            flags.append(f"MICRO_FRAGMENT ({n_tokens} tokens)")
            return round(max(0.1, n_tokens / TOKEN_SWEET_LOWER), 4), n_tokens, flags

        if n_tokens < TOKEN_SWEET_LOWER:
            return round(n_tokens / TOKEN_SWEET_LOWER, 4), n_tokens, flags

        if n_tokens <= TOKEN_SWEET_UPPER:
            return 1.0, n_tokens, flags

        # 241..256: Near-ceiling warning zone
        flags.append(f"NEAR_TOKEN_CEILING ({n_tokens}/{TOKEN_HARD_CEILING})")
        score = 1.0 - ((n_tokens - TOKEN_SWEET_UPPER) / 16.0)
        return round(max(0.1, score), 4), n_tokens, flags

    # -----------------------------------------------------------------------
    # Parameter 2: Boundary & Structural Integrity (s_bound)
    # -----------------------------------------------------------------------
    def score_boundary_integrity(
        self, text: str, chunk_type: str
    ) -> Tuple[float, List[str]]:
        """Check for mid-sentence cuts, orphan headings, and broken table structure.

        Deductions:
          - 0.30 for mid-sentence start (lowercase/punctuation first char)
          - 0.25 for unterminated end (no terminal punctuation)
          - 0.50 for orphan trailing heading (heading with no body)
          - 0.65 for table rows without column header separator
          - 0.25 for inconsistent table column counts
        """
        flags: List[str] = []
        stripped = text.strip()
        if not stripped:
            return 0.0, ["EMPTY_CHUNK"]

        score = 1.0

        # 1. Check start boundary (unless Markdown structure char or tracked cutoff continuation)
        eval_start = re.sub(r"<!--\s*CUTOFF_START\s*-->", "", stripped).strip()
        first_char = eval_start[0] if eval_start else ""
        if first_char and (first_char.islower() or first_char in (",", ";", ".", ")", "]")):
            if "<!-- CUTOFF_START -->" not in stripped:
                score -= 0.30
                flags.append("MID_SENTENCE_START")

        # 2. Check terminal boundary (strip cutoff tags for punctuation check)
        eval_end = re.sub(r"<!--\s*CUTOFF_END\s*-->", "", stripped).strip()
        if not eval_end.endswith(TERMINAL_PUNCTUATION):
            if "<!-- CUTOFF_END -->" not in stripped:
                score -= 0.25
                flags.append("UNFINISHED_SENTENCE_END")

        # 3. Check orphan trailing heading
        if MARKDOWN_HEADING_END_REGEX.search(stripped):
            # Only flag if the heading is the LAST significant line
            last_line = stripped.rsplit("\n", 1)[-1].strip()
            if last_line.startswith("#"):
                score -= 0.50
                flags.append("ORPHAN_TRAILING_HEADING")

        # 4. Table structural integrity (only for actual pipe-formatted markdown tables)
        has_table_pipes = stripped.count("|") >= 4
        is_table = (chunk_type.lower() in ("table", "table_dense") and has_table_pipes) or stripped.count("|") >= 6
        if is_table:
            if not MARKDOWN_TABLE_SEP_REGEX.search(stripped):
                score -= 0.65
                flags.append("ORPHAN_TABLE_ROWS_NO_HEADER")
            lines = [ln.strip() for ln in stripped.splitlines() if "|" in ln]
            if len(lines) >= 2:
                col_counts = {ln.count("|") for ln in lines}
                if len(col_counts) > 2:
                    score -= 0.25
                    flags.append("MALFORMED_TABLE_COLUMNS")

        return round(max(0.0, score), 4), flags

    # -----------------------------------------------------------------------
    # Parameter 3: Metadata & Hierarchy Completeness (s_meta)
    # -----------------------------------------------------------------------
    def score_metadata_completeness(
        self, metadata: Dict[str, Any]
    ) -> Tuple[float, List[str]]:
        """Validate compliance with ChunkMetadata canonical contract.

        Checks the 5 required canonical fields (document_id, project_id,
        source_filename, chunk_index, content_type) plus optional structural
        fields (page_number, section_heading, hierarchy_path).
        """
        flags: List[str] = []
        present = 0

        for req_key in CANONICAL_METADATA_FIELDS:
            val = metadata.get(req_key)
            if val is not None and str(val).strip() not in ("", "None", "unknown"):
                present += 1
            else:
                flags.append(f"MISSING_META_{req_key.upper()}")

        base_score = present / len(CANONICAL_METADATA_FIELDS)

        # Bonus/penalty for hierarchy depth (hierarchy_path is a list of headings)
        hierarchy = metadata.get("hierarchy_path")
        section = metadata.get("section_heading") or metadata.get("section")
        has_hierarchy = (
            (isinstance(hierarchy, (list, tuple)) and len(hierarchy) >= 1)
            or (isinstance(hierarchy, str) and len(hierarchy.strip()) >= 3)
        )
        has_section = section and str(section).strip() not in ("", "None")

        if not has_hierarchy and not has_section:
            base_score = max(0.0, base_score - 0.15)
            flags.append("NO_HIERARCHY_OR_SECTION")
        elif has_hierarchy:
            # Reward deeper hierarchy
            depth = len(hierarchy) if isinstance(hierarchy, (list, tuple)) else hierarchy.count(">") + 1
            if depth >= 2:
                base_score = min(1.0, base_score + 0.05)

        return round(base_score, 4), flags

    # -----------------------------------------------------------------------
    # Parameter 4: Intra-Chunk Semantic Coherence (s_coh)
    # -----------------------------------------------------------------------
    def score_intra_coherence(
        self, text: str, chunk_type: str
    ) -> Tuple[float, List[str]]:
        """Measure mean pairwise sentence coherence and topic integrity.

        Target: Mean pairwise / centroid sentence cosine similarity >= 0.65.
        Tables get a neutral-high score (0.85) since sentence splitting
        is unreliable on structured rows.
        """
        flags: List[str] = []
        if chunk_type.lower() in ("table", "table_dense"):
            return 0.85, flags

        # Strip contextual prefix and hidden comment tags so sentence coherence
        # measures actual intra-body prose coherence rather than header-to-body contrast
        clean_body = re.sub(r"^\s*\[(?:Policy|Doc|Document Scope):[^\n]+\]\s*\n?", "", text.strip(), flags=re.IGNORECASE).strip()
        clean_body = re.sub(r"<!--\s*CUTOFF_(?:START|END)\s*-->", "", clean_body).strip()
        clean_body = re.sub(r"^\s*[\]\)\}\>]+\s*\n?", "", clean_body).strip()

        sentences = [
            s.strip()
            for s in SENTENCE_SPLIT_REGEX.split(clean_body)
            if len(s.strip()) > 12
        ]
        if len(sentences) <= 1:
            # Single sentence or very short — neutral high
            return 0.80, flags

        sent_embeddings = self.embedder.encode(
            sentences, normalize_embeddings=True, show_progress_bar=False
        )
        # 1. Consecutive sentence similarity
        consec_sims = np.sum(sent_embeddings[:-1] * sent_embeddings[1:], axis=1)
        mean_consec = float(np.mean(consec_sims))
        min_consec = float(np.min(consec_sims))

        # 2. Centroid semantic alignment across all sentences in the chunk
        centroid = np.mean(sent_embeddings, axis=0)
        c_norm = np.linalg.norm(centroid)
        if c_norm > 0:
            centroid = centroid / c_norm
        centroid_sims = np.dot(sent_embeddings, centroid)
        mean_centroid = float(np.mean(centroid_sims))
        min_centroid = float(np.min(centroid_sims))

        # Composite coherence score (blending consecutive progression with holistic topical unity)
        composite_mean = 0.50 * mean_consec + 0.50 * mean_centroid
        normalized_score = float(np.clip((composite_mean - 0.30) / 0.40, 0.0, 1.0))

        if min_consec < 0.12 or min_centroid < 0.30:
            flags.append(f"TOPIC_DRIFT_DETECTED (min_consec={min_consec:.2f}, min_cent={min_centroid:.2f})")
            normalized_score = max(0.0, normalized_score - 0.15)

        if composite_mean < 0.45:
            flags.append(f"LOW_COHERENCE (mean_coh={composite_mean:.2f}<0.45)")

        return round(normalized_score, 4), flags

    # -----------------------------------------------------------------------
    # Parameter 5: Inter-Chunk Distinctiveness (s_dist)
    # -----------------------------------------------------------------------
    def score_inter_distinctiveness(
        self,
        idx: int,
        chunks: List[ChunkRecord],
    ) -> Tuple[float, List[str]]:
        """Compare chunk C_i against neighbors C_{i-1} and C_{i+1} from the SAME source file.

        Rubric Target:
          - Neighbor cosine similarity between 0.35 and 0.85 -> 1.0 (ideal distinctiveness)
          - 0.85..0.88 -> Warning zone (gradual linear penalty)
          - > 0.88 -> Missed merge (0.0 score, flag REDUNDANT_NEIGHBOR_OVERLAP)
        """
        flags: List[str] = []
        current = chunks[idx]
        cur_source = current.metadata.get("source_filename") or current.metadata.get("source")
        if current.embedding is None:
            return 1.0, flags

        neighbor_sims: List[float] = []
        for neighbor_idx in (idx - 1, idx + 1):
            if 0 <= neighbor_idx < len(chunks):
                neighbor = chunks[neighbor_idx]
                neigh_source = (
                    neighbor.metadata.get("source_filename")
                    or neighbor.metadata.get("source")
                )
                if neigh_source == cur_source and neighbor.embedding is not None:
                    sim = float(np.dot(current.embedding, neighbor.embedding))
                    neighbor_sims.append(sim)

        if not neighbor_sims:
            return 1.0, flags

        max_adj_sim = max(neighbor_sims)

        # Above 0.88 -> semantic_merger missed a merge
        if max_adj_sim > 0.88:
            flags.append(
                f"REDUNDANT_NEIGHBOR_OVERLAP (sim={max_adj_sim:.2f}>0.88)"
            )
            return 0.0, flags

        if max_adj_sim > 0.85:
            flags.append(f"HIGH_NEIGHBOR_SIMILARITY (sim={max_adj_sim:.2f})")
            return round(1.0 - ((max_adj_sim - 0.85) / 0.03), 4), flags

        return 1.0, flags

    # -----------------------------------------------------------------------
    # Parameter 6: Self-Containment / De-contextualization (s_self)
    # -----------------------------------------------------------------------
    def score_self_containment(
        self, text: str, metadata: Dict[str, Any]
    ) -> Tuple[float, List[str]]:
        """Check if the chunk is self-contained in Top-4 RAG context.

        Detects dangling anaphora ("This policy", "They must") in the first
        25 words and checks whether the heading hierarchy has been injected
        into the chunk text (bridge_linked_chunking.py pattern).
        """
        flags: List[str] = []
        stripped = text.strip()
        words = re.findall(r"\b[a-zA-Z]+\b", stripped[:200])
        if not words:
            return 0.0, ["NO_ALPHA_TOKENS"]

        first_window = [w.lower() for w in words[:25]]
        dangling_hits = [w for w in first_window if w in DANGLING_PRONOUNS]

        # Check if parent heading is explicitly injected into the chunk body
        hierarchy = metadata.get("hierarchy_path")
        section = metadata.get("section_heading") or metadata.get("section")
        hierarchy_text = ""
        if isinstance(hierarchy, (list, tuple)) and hierarchy:
            hierarchy_text = " > ".join(str(h) for h in hierarchy)
        elif isinstance(hierarchy, str):
            hierarchy_text = hierarchy

        has_injected_header = (
            stripped.startswith("[")
            or stripped.startswith("#")
            or (hierarchy_text and hierarchy_text.lower() in stripped[:200].lower())
            or (section and str(section).lower() in stripped[:150].lower())
        )

        score = 1.0
        if dangling_hits and not has_injected_header:
            penalty = min(0.60, len(dangling_hits) * 0.20)
            score -= penalty
            flags.append(f"DANGLING_ANAPHORA_AT_START ({','.join(dangling_hits[:3])})")

        if not has_injected_header:
            score -= 0.15
            flags.append("NO_INJECTED_HEADING_PREFIX")

        return round(max(0.0, score), 4), flags

    # -----------------------------------------------------------------------
    # Parameter 7: Reverse-Query Retrievability (s_ret) — Gate 2
    # -----------------------------------------------------------------------
    @staticmethod
    def _build_synthetic_query(chunk: ChunkRecord) -> str:
        """Build a deterministic synthetic employee query from heading + key phrase.

        This is the zero-LLM-cost fallback. For higher-quality synthetic
        queries, an LLM call (e.g. Groq llama-3.1-8b-instant) can be
        substituted by the caller.
        """
        hierarchy = chunk.metadata.get("hierarchy_path")
        section = chunk.metadata.get("section_heading") or chunk.metadata.get("section")

        heading = ""
        if isinstance(hierarchy, (list, tuple)) and hierarchy:
            heading = " ".join(str(h) for h in hierarchy)
        elif isinstance(hierarchy, str) and hierarchy:
            heading = hierarchy.replace(">", " ").strip()
        elif section:
            heading = str(section)

        sentences = SENTENCE_SPLIT_REGEX.split(chunk.text.strip())
        anchor_sent = max(sentences, key=len) if sentences else chunk.text[:120]
        anchor_clean = re.sub(r"[|#*_`\[\]]+", " ", anchor_sent).strip()
        anchor_words = anchor_clean.split()[:14]
        query = f"What is the policy regarding {heading} {' '.join(anchor_words)}?".strip()
        return re.sub(r"\s+", " ", query)

    def evaluate_retrievability_sample(
        self,
        all_chunks: List[ChunkRecord],
        scorecards: Dict[str, ChunkScorecard],
        sample_size: int = 30,
        candidate_k: int = RAG_CANDIDATE_COUNT,
        final_k: int = RAG_FINAL_K,
    ) -> None:
        """Gate 2: Synthetic round-trip retrieval (Vector Top-K → BGE Reranker Top-4).

        For each sampled chunk:
          1. Generate a synthetic employee question from the chunk
          2. Embed the query and find Top-K nearest chunks (simulating ChromaDB)
          3. Rerank with BGE cross-encoder
          4. Score based on the target chunk's final rank

        Diagnostic value:
          - MISSED_VECTOR_TOP_K: chunk is invisible to embedding search
          - DEMOTED_BY_BGE_RERANKER: embedding found it, but cross-encoder dropped it
        """
        if not all_chunks or sample_size <= 0:
            return

        valid_indices = [i for i, c in enumerate(all_chunks) if len(c.text.strip()) > 50]
        sampled_indices = random.sample(
            valid_indices, min(sample_size, len(valid_indices))
        )

        logger.info(
            "Running Gate 2 Reverse-Query Retrievability on %d sampled chunks...",
            len(sampled_indices),
        )

        # Build embedding matrix for exact cosine search
        emb_matrix = np.vstack([
            c.embedding for c in all_chunks if c.embedding is not None
        ])

        for idx in sampled_indices:
            target = all_chunks[idx]
            card = scorecards.get(target.chunk_id)
            if card is None:
                continue

            query = self._build_synthetic_query(target)
            card.synthetic_query = query

            # Vector search (cosine similarity against all chunk embeddings)
            q_emb = self.embedder.encode(
                [query], normalize_embeddings=True, show_progress_bar=False
            )[0]
            sims = np.dot(emb_matrix, q_emb)
            top_cand_indices = np.argsort(sims)[::-1][:candidate_k]

            if idx not in top_cand_indices:
                card.s_ret = 0.0
                card.retrieval_rank = None
                card.failure_flags.append(f"MISSED_VECTOR_TOP_{candidate_k}")
                continue

            # Rerank with BGE cross-encoder
            if self.reranker is not None:
                pairs = [[query, all_chunks[c_idx].text] for c_idx in top_cand_indices]
                rerank_scores = self.reranker.predict(pairs, show_progress_bar=False)
                ranked_order = np.argsort(rerank_scores)[::-1]
                reranked_indices = [int(top_cand_indices[r]) for r in ranked_order]
            else:
                reranked_indices = [int(i) for i in top_cand_indices]

            if idx in reranked_indices:
                rank_1_based = reranked_indices.index(idx) + 1
            else:
                # Should not happen since idx was in top_cand_indices, but guard
                card.s_ret = 0.0
                card.retrieval_rank = None
                card.failure_flags.append(f"MISSED_VECTOR_TOP_{candidate_k}")
                continue

            card.retrieval_rank = rank_1_based

            if rank_1_based == 1:
                card.s_ret = 1.0
            elif rank_1_based <= final_k:
                card.s_ret = round(1.0 / rank_1_based, 4)
            else:
                # Found by embedding search but demoted by BGE reranker
                card.s_ret = 0.20
                card.failure_flags.append(
                    f"DEMOTED_BY_BGE_RERANKER (rank={rank_1_based}>{final_k})"
                )

    # -----------------------------------------------------------------------
    # Main Evaluation Loop
    # -----------------------------------------------------------------------
    def evaluate_corpus(
        self,
        chunks: List[ChunkRecord],
        sample_retrievability: int = 30,
    ) -> Dict[str, Any]:
        """Run the 3-gate evaluation pipeline across all loaded chunks.

        Gate 1 runs on 100% of chunks (fast — seconds).
        Gate 2 runs on a stratified sample (uses reranker — minutes).
        Returns a comprehensive JSON-serializable report.
        """
        if not chunks:
            raise ValueError("No chunks provided for evaluation.")

        logger.info("Encoding %d chunks with %s...", len(chunks), EMBEDDING_MODEL)
        texts = [c.text for c in chunks]
        embeddings = self.embedder.encode(
            texts, normalize_embeddings=True, show_progress_bar=True, batch_size=64
        )
        for chunk, emb in zip(chunks, embeddings):
            chunk.embedding = emb

        scorecards: Dict[str, ChunkScorecard] = {}

        logger.info("Computing Gate 1 — Intrinsic & Semantic Parameters (all %d chunks)...", len(chunks))
        for idx, chunk in enumerate(chunks):
            chunk_type = str(chunk.metadata.get("content_type", "text"))
            source_file = str(
                chunk.metadata.get("source_filename")
                or chunk.metadata.get("source")
                or "unknown"
            )

            s_token, n_tokens, f_tok = self.score_token_budget(chunk.text)
            s_bound, f_bnd = self.score_boundary_integrity(chunk.text, chunk_type)
            s_meta, f_met = self.score_metadata_completeness(chunk.metadata)
            s_coh, f_coh = self.score_intra_coherence(chunk.text, chunk_type)
            s_dist, f_dst = self.score_inter_distinctiveness(idx, chunks)
            s_self, f_slf = self.score_self_containment(chunk.text, chunk.metadata)

            # Weighted Composite Score (Gate 1)
            # Weights: token=0.25, boundary=0.20, coherence=0.20, self=0.15, distinct=0.10, meta=0.10
            composite = (
                0.25 * s_token
                + 0.20 * s_bound
                + 0.20 * s_coh
                + 0.15 * s_self
                + 0.10 * s_dist
                + 0.10 * s_meta
            )

            flags = f_tok + f_bnd + f_met + f_coh + f_dst + f_slf

            scorecards[chunk.chunk_id] = ChunkScorecard(
                chunk_id=chunk.chunk_id,
                source_file=source_file,
                chunk_type=chunk_type,
                token_count=n_tokens,
                s_token=s_token,
                s_bound=s_bound,
                s_meta=s_meta,
                s_coh=s_coh,
                s_dist=s_dist,
                s_self=s_self,
                s_ret=None,
                composite_intrinsic_score=round(composite, 4),
                failure_flags=flags,
            )

        # Gate 2: Sampled Reverse-Query Retrievability
        if sample_retrievability > 0:
            self.evaluate_retrievability_sample(
                chunks, scorecards, sample_size=sample_retrievability
            )

        return self._compile_report(list(scorecards.values()))

    # -----------------------------------------------------------------------
    # Report Compilation
    # -----------------------------------------------------------------------
    @staticmethod
    def _compile_report(cards: List[ChunkScorecard]) -> Dict[str, Any]:
        """Compile per-chunk scorecards into an aggregate summary report."""
        ret_scores = [c.s_ret for c in cards if c.s_ret is not None]

        # Tally failure flags (use first word/tag as the key)
        flag_counts: Dict[str, int] = {}
        for c in cards:
            for flg in c.failure_flags:
                key = flg.split(" ")[0]
                flag_counts[key] = flag_counts.get(key, 0) + 1

        sorted_cards = sorted(cards, key=lambda x: x.composite_intrinsic_score)
        token_counts = [c.token_count for c in cards]

        # Composite quality index (legacy-compatible CQI out of 100)
        mean_composite = float(np.mean([c.composite_intrinsic_score for c in cards]))
        cqi_100 = round(mean_composite * 100, 2)
        grade = (
            "A+ (Exceptional)" if cqi_100 >= 95
            else "A (High Quality)" if cqi_100 >= 90
            else "B (Good / Acceptable)" if cqi_100 >= 80
            else "C (Needs Tuning)" if cqi_100 >= 70
            else "D (Severe Quality Issues)"
        )

        summary: Dict[str, Any] = {
            "summary": {
                "total_chunks_evaluated": len(cards),
                "composite_quality_index": cqi_100,
                "quality_grade": grade,
            },
            "mean_scores": {
                "1_token_budget (s_token)": round(
                    float(np.mean([c.s_token for c in cards])), 4
                ),
                "2_boundary_integrity (s_bound)": round(
                    float(np.mean([c.s_bound for c in cards])), 4
                ),
                "3_metadata_completeness (s_meta)": round(
                    float(np.mean([c.s_meta for c in cards])), 4
                ),
                "4_intra_coherence (s_coh)": round(
                    float(np.mean([c.s_coh for c in cards])), 4
                ),
                "5_inter_distinctiveness (s_dist)": round(
                    float(np.mean([c.s_dist for c in cards])), 4
                ),
                "6_self_containment (s_self)": round(
                    float(np.mean([c.s_self for c in cards])), 4
                ),
                "7_retrievability_mrr (s_ret)": (
                    round(float(np.mean(ret_scores)), 4) if ret_scores else None
                ),
                "composite_intrinsic_score": round(mean_composite, 4),
            },
            "token_stats": {
                "min_tokens": int(min(token_counts)),
                "median_tokens": int(np.median(token_counts)),
                "p90_tokens": int(np.percentile(token_counts, 90)),
                "max_tokens": int(max(token_counts)),
                "mean_tokens": round(float(np.mean(token_counts)), 1),
                "std_tokens": round(float(np.std(token_counts)), 1),
                "exceeding_256_limit_count": sum(1 for t in token_counts if t > 256),
                "optimal_range_80_240_pct": round(
                    sum(1 for t in token_counts if 80 <= t <= 240) / len(token_counts) * 100, 1
                ),
            },
            "failure_flag_distribution": dict(
                sorted(flag_counts.items(), key=lambda x: x[1], reverse=True)
            ),
            "gate2_retrievability": {
                "chunks_sampled": len(ret_scores),
                "mean_mrr": round(float(np.mean(ret_scores)), 4) if ret_scores else None,
                "rank_1_count": sum(1 for c in cards if c.s_ret == 1.0),
                "missed_vector_count": sum(
                    1 for c in cards
                    if any("MISSED_VECTOR" in f for f in c.failure_flags)
                ),
                "demoted_by_reranker_count": sum(
                    1 for c in cards
                    if any("DEMOTED_BY_BGE_RERANKER" in f for f in c.failure_flags)
                ),
            },
            "bottom_10_worst_chunks": [asdict(c) for c in sorted_cards[:10]],
            "bottom_20_worst_chunks": [asdict(c) for c in sorted_cards[:20]],
            "all_chunk_scorecards": [asdict(c) for c in sorted_cards],
        }
        return summary


# ---------------------------------------------------------------------------
# Loaders — ChromaDB or JSON file fallback
# ---------------------------------------------------------------------------
def load_chunks_from_chroma(
    persist_dir: str, collection_name: str
) -> List[ChunkRecord]:
    """Load all chunks from a ChromaDB persistent collection."""
    import chromadb

    logger.info(
        "Connecting to ChromaDB at '%s' (collection='%s')...",
        persist_dir, collection_name,
    )
    client = chromadb.PersistentClient(path=persist_dir)
    collection = client.get_collection(name=collection_name)
    total = collection.count()
    if total == 0:
        logger.error("ChromaDB collection '%s' is empty.", collection_name)
        return []

    raw = collection.get(include=["documents", "metadatas"])
    ids = raw.get("ids", [])
    docs = raw.get("documents", [])
    metas = raw.get("metadatas", [])

    records: List[ChunkRecord] = []
    for cid, doc, meta in zip(ids, docs, metas):
        if doc is not None:
            records.append(
                ChunkRecord(chunk_id=str(cid), text=doc, metadata=meta or {})
            )

    # Sort by source_file + page + chunk_index so neighbor distinctiveness is accurate
    records.sort(
        key=lambda r: (
            str(r.metadata.get("source_filename", r.metadata.get("source", ""))),
            int(r.metadata.get("page_number", 0) or 0),
            int(r.metadata.get("chunk_index", 0) or 0),
            r.chunk_id,
        )
    )
    logger.info("Loaded %d chunks from collection '%s'.", len(records), collection_name)
    return records


def load_chunks_from_json(json_path: str) -> List[ChunkRecord]:
    """Load chunks from a JSON dump file (alternative to ChromaDB)."""
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"JSON chunk file not found: {json_path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    records: List[ChunkRecord] = []

    items = data if isinstance(data, list) else data.get("chunks", data.get("documents", []))
    for item in items:
        chunk_id = str(item.get("id", item.get("chunk_id", f"chunk-{len(records)}")))
        text = str(item.get("text", item.get("document", "")))
        meta = item.get("metadata", {})
        if text.strip():
            records.append(ChunkRecord(chunk_id=chunk_id, text=text, metadata=meta))

    records.sort(
        key=lambda r: (
            str(r.metadata.get("source_filename", "")),
            int(r.metadata.get("page_number", 0) or 0),
            int(r.metadata.get("chunk_index", 0) or 0),
            r.chunk_id,
        )
    )
    logger.info("Loaded %d chunks from JSON file '%s'.", len(records), json_path)
    return records


# ---------------------------------------------------------------------------
# CLI Report Printer
# ---------------------------------------------------------------------------
def print_report(report: Dict[str, Any]) -> None:
    """Pretty-print the chunk quality audit to the console."""
    summary = report["summary"]
    scores = report["mean_scores"]
    tokens = report["token_stats"]
    flags = report["failure_flag_distribution"]
    gate2 = report["gate2_retrievability"]

    print("\n" + "=" * 70)
    print("  📊 KNOWLAYER 7-PARAMETER CHUNK QUALITY AUDIT")
    print("=" * 70)
    print(f"  Total Chunks Audited         : {summary['total_chunks_evaluated']:,}")
    print(f"  Composite Quality Index      : {summary['composite_quality_index']:.2f} / 100")
    print(f"  Overall Quality Grade        : {summary['quality_grade']}")
    print("-" * 70)

    print("  📐 TOKEN DISTRIBUTION:")
    print(f"    • Mean Tokens              : {tokens['mean_tokens']}")
    print(f"    • Median Tokens            : {tokens['median_tokens']}")
    print(f"    • P90 Tokens               : {tokens['p90_tokens']}")
    print(f"    • Range (Min — Max)        : {tokens['min_tokens']} — {tokens['max_tokens']}")
    print(f"    • Std Deviation            : {tokens['std_tokens']}")
    print(f"    • Exceeding 256 (Trunc!)   : {tokens['exceeding_256_limit_count']}")
    print(f"    • In Sweet Spot (80-240)   : {tokens['optimal_range_80_240_pct']}%")
    print("-" * 70)

    print("  🎯 GATE 1 — INTRINSIC & SEMANTIC SCORES (mean across all chunks):")
    for key, val in scores.items():
        label = f"    {key:<38}"
        if val is not None:
            print(f"{label}: {val:.4f}")
        else:
            print(f"{label}: N/A (not sampled)")
    print("-" * 70)

    print("  🔄 GATE 2 — RETRIEVAL ROUND-TRIP:")
    print(f"    • Chunks Sampled           : {gate2['chunks_sampled']}")
    if gate2["mean_mrr"] is not None:
        print(f"    • Mean MRR@{RAG_FINAL_K}              : {gate2['mean_mrr']:.4f}")
    print(f"    • Rank-1 Hits              : {gate2['rank_1_count']}")
    print(f"    • Missed Vector Search     : {gate2['missed_vector_count']}")
    print(f"    • Demoted by BGE Reranker  : {gate2['demoted_by_reranker_count']}")
    print("-" * 70)

    print("  🚩 TOP FAILURE FLAGS:")
    for flag, count in list(flags.items())[:8]:
        print(f"    • {flag:<32}: {count} chunks")
    print("=" * 70)

    # Show bottom 20 worst chunks
    bottom = (report.get("bottom_20_worst_chunks") or report.get("bottom_10_worst_chunks", []))[:20]
    if bottom:
        print(f"\n  ⚠️  BOTTOM {len(bottom)} WORST-SCORING CHUNKS:")
        for i, card in enumerate(bottom, 1):
            flag_str = ", ".join(card.get("failure_flags", [])[:3])
            print(f"    {i:2d}. [{card['chunk_id']}] "
                  f"score={card['composite_intrinsic_score']:.4f} | "
                  f"tokens={card['token_count']} | "
                  f"src={card.get('source_file', 'unknown')} | "
                  f"flags=[{flag_str}]")
        print()


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="KnowLayer 7-Parameter Chunk Quality Evaluator (3-Gate Pipeline)"
    )
    parser.add_argument(
        "--chroma-dir",
        default=str(BASE_DIR / ".chroma"),
        help="Path to ChromaDB persist directory",
    )
    parser.add_argument(
        "--collection",
        default=COLLECTION_NAME,
        help="ChromaDB collection name",
    )
    parser.add_argument(
        "--json-input",
        default=None,
        help="Path to a JSON file of chunks (alternative to ChromaDB)",
    )
    parser.add_argument(
        "--sample-ret",
        type=int,
        default=30,
        help="Number of chunks to sample for Gate 2 Retrievability (0 to skip)",
    )
    parser.add_argument(
        "--skip-reranker",
        action="store_true",
        help="Disable BGE cross-encoder during Gate 2 (faster, embedding-only)",
    )
    parser.add_argument(
        "--output",
        default="chunk_quality_report.json",
        help="Path to write the JSON evaluation report",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print JSON report to stdout instead of human-readable table",
    )
    parser.add_argument(
        "--list-worst",
        type=int,
        nargs="?",
        const=20,
        default=None,
        metavar="N",
        help="List the top N (default 20) worst chunks from the quality report with scores and flags",
    )
    parser.add_argument(
        "--add-back",
        type=str,
        default=None,
        metavar="CHUNK_ID",
        help="Add/restore a specific chunk back into ChromaDB (marking it Good Enough)",
    )
    parser.add_argument(
        "--quarantine",
        type=str,
        default=None,
        metavar="CHUNK_ID",
        help="Quarantine / prune a specific chunk from ChromaDB into quarantine archive",
    )
    args = parser.parse_args()

    # Fast-path 1: Add chunk back to ChromaDB
    if args.add_back:
        from sandbox.engine.chunk_quarantine_manager import add_chunk_to_chroma, load_quarantined_chunks
        target_id = args.add_back
        quarantined = load_quarantined_chunks()

        chunk_text = ""
        chunk_meta = {}
        if target_id in quarantined:
            chunk_text = quarantined[target_id].get("text", "")
            chunk_meta = quarantined[target_id].get("metadata", {})
        else:
            # Check report file or ChromaDB
            report_p = Path(args.output) if Path(args.output).exists() else (Path(BASE_DIR) / "chunk_quality_report.json")
            if not report_p.exists():
                report_p = Path(BASE_DIR).parent / "chunk_quality_report.json"
            if report_p.exists():
                try:
                    d = json.loads(report_p.read_text(encoding="utf-8"))
                    cards = d.get("all_chunk_scorecards", [])
                    match = next((c for c in cards if c.get("chunk_id") == target_id), None)
                    if match:
                        chunk_meta = {
                            "document_id": match.get("source_file", "").split(".")[0],
                            "source_filename": match.get("source_file", ""),
                            "token_count": match.get("token_count", 0),
                        }
                except Exception:
                    pass

            # Try to fetch document text from ChromaDB if it already exists or was stored
            try:
                from app.infrastructure.vector.chroma_client import ChromaVectorStore
                c_store = ChromaVectorStore(collection_name=args.collection, persist_directory=args.chroma_dir)
                res = c_store.collection.get(ids=[target_id], include=["documents", "metadatas"])
                if res.get("documents") and len(res["documents"]) > 0:
                    chunk_text = res["documents"][0]
                    chunk_meta = res["metadatas"][0] if res.get("metadatas") else chunk_meta
            except Exception:
                pass

        if not chunk_text:
            print(f"ERROR: Cannot find text for chunk '{target_id}' in quarantine store or ChromaDB.")
            print("Please ensure the chunk exists or provide text.")
            sys.exit(1)

        succ, msg = add_chunk_to_chroma(
            chunk_id=target_id,
            text=chunk_text,
            metadata=chunk_meta,
            collection_name=args.collection,
            persist_directory=args.chroma_dir,
            reviewer_notes="Restored via evaluate_chunking_quality.py CLI",
        )
        if succ:
            print(f"✅ {msg}")
        else:
            print(f"❌ {msg}")
        sys.exit(0 if succ else 1)

    # Fast-path 2: Quarantine chunk from ChromaDB
    if args.quarantine:
        from sandbox.engine.chunk_quarantine_manager import quarantine_chunk_from_chroma
        target_id = args.quarantine
        succ, msg = quarantine_chunk_from_chroma(
            chunk_id=target_id,
            reason="Quarantined via evaluate_chunking_quality.py CLI",
            collection_name=args.collection,
            persist_directory=args.chroma_dir,
        )
        if succ:
            print(f"🗑️ {msg}")
        else:
            print(f"❌ {msg}")
        sys.exit(0 if succ else 1)

    # Fast-path 3: List top N worst chunks from report
    if args.list_worst is not None:
        report_p = Path(args.output) if Path(args.output).exists() else (Path(BASE_DIR) / "chunk_quality_report.json")
        if not report_p.exists():
            report_p = Path(BASE_DIR).parent / "chunk_quality_report.json"
        if not report_p.exists():
            print(f"ERROR: Report file not found at '{args.output}' or '{report_p}'.")
            print("Run evaluation first without --list-worst.")
            sys.exit(1)

        d = json.loads(report_p.read_text(encoding="utf-8"))
        cards = d.get("all_chunk_scorecards", [])
        if not cards:
            cards = d.get("bottom_20_worst_chunks") or d.get("bottom_10_worst_chunks", [])
        worst = sorted(cards, key=lambda x: x.get("composite_intrinsic_score", 1.0))[:args.list_worst]

        from sandbox.engine.chunk_quarantine_manager import get_chroma_chunk_presence
        cids = [c["chunk_id"] for c in worst]
        presence = get_chroma_chunk_presence(cids, collection_name=args.collection, persist_directory=args.chroma_dir)

        print("\n" + "=" * 80)
        print(f"  ⚠️  TOP {len(worst)} WORST-SCORING CHUNKS (from {report_p.name}):")
        print("=" * 80)
        for i, card in enumerate(worst, 1):
            cid = card["chunk_id"]
            status = "🟢 In ChromaDB" if presence.get(cid, False) else "🔴 Quarantined/Missing"
            flags = ", ".join(card.get("failure_flags", []))
            print(f" {i:2d}. [{cid}] ({status})")
            print(f"     Source : {card.get('source_file', 'unknown')} | Tokens: {card.get('token_count')}")
            print(f"     Score  : CQI={card.get('composite_intrinsic_score', 0):.4f} | s_token={card.get('s_token', 0):.2f} | s_bound={card.get('s_bound', 0):.2f} | s_coh={card.get('s_coh', 0):.2f}")
            print(f"     Flags  : {flags}")
            print("-" * 80)
        print(f"\nTip: To add any chunk back to ChromaDB, run:")
        print(f"  python scripts/evaluate_chunking_quality.py --add-back <CHUNK_ID>\n")
        sys.exit(0)

    # Load chunks
    if args.json_input:
        chunks = load_chunks_from_json(args.json_input)
    else:
        chunks = load_chunks_from_chroma(args.chroma_dir, args.collection)

    if not chunks:
        print("ERROR: No chunks found. Run scripts/ingest_documents.py first.")
        sys.exit(1)

    # Run evaluation
    evaluator = KnowLayerChunkEvaluator(enable_reranker=not args.skip_reranker)
    report = evaluator.evaluate_corpus(chunks, sample_retrievability=args.sample_ret)

    # Write JSON report to file
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    # Print to console
    if args.json_output:
        # Strip the large all_chunk_scorecards for stdout
        stdout_report = {k: v for k, v in report.items() if k != "all_chunk_scorecards"}
        print(json.dumps(stdout_report, indent=2, default=str))
    else:
        print_report(report)
        print(f"  📄 Full diagnostic report saved to: {out_path.resolve()}\n")


if __name__ == "__main__":
    main()
