"""
KnowLayer Semantic Chunk Merger
===============================
Implements pairwise semantic merging for unstructured, noisy, or over-fragmented
document chunks prior to vector embedding (based on Rahul Jangir's paradigm).

Key Responsibilities:
1. Fragment Consolidation: Merges stub fragments (< Z chars) into highly similar
   neighboring or thematic parent chunks (<= Y chars) up to a hard cap (<= X chars).
2. Noise Deduplication: Collapses repeated boilerplate (disclaimers, headers) into
   a single consolidated chunk to prevent crowding in the retrieval top-k funnel.
3. Strict Partition Isolation: Enforces tenant/document/project scope isolation
   so chunks from different departments or documents never merge.
4. Lineage Preservation: Records composite metadata (merged IDs, combined pages,
   audit trace) so citations remain grounded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
# pyrefly: ignore[missing-import]
import numpy as np

logger = logging.getLogger("knowlayer.ingestion.merger")


@dataclass
class SemanticMergeConfig:
    """Configuration parameters for pairwise semantic chunk merging.
    
    Constraint: candidate_max_chars (Z) < absorber_max_chars (Y) < max_chunk_chars (X)
    """
    max_chunk_chars: int = 1200         # X: Hard cap on merged text length (~240 tokens)
    absorber_max_chars: int = 800       # Y: Maximum size of chunk eligible to absorb others (~160 tokens)
    candidate_max_chars: int = 250      # Z: Maximum size of small fragment eligible to be absorbed (~50 tokens)
    similarity_threshold: float = 0.85  # Minimum cosine similarity required to trigger a merge (aligned with 0.85 target)
    scope_field: str = "document_id"    # Field name enforcing strict boundary isolation (e.g. document_id)
    enabled: bool = True
    join_separator: str = "\n\n"        # Text separator when concatenating chunks


@dataclass
class MergeAction:
    """Details of an individual merge operation between two chunks."""
    target_id: str
    absorbed_id: str
    similarity: float
    target_original_len: int
    absorbed_len: int
    merged_len: int
    target_preview: str
    absorbed_preview: str


@dataclass
class MergeResult:
    """Execution summary and audit trail for a semantic merge pass."""
    total_input_chunks: int = 0
    total_output_chunks: int = 0
    absorbed_chunks_count: int = 0
    reduction_percentage: float = 0.0
    actions: List[MergeAction] = field(default_factory=list)


class SemanticChunkMerger:
    """Merges semantically similar micro-fragments into substantive chunks."""

    def __init__(self, config: Optional[SemanticMergeConfig] = None, embedding_model: Any = None):
        self.config = config or SemanticMergeConfig()
        self._embedding_model = embedding_model

    @property
    def embedding_model(self):
        if self._embedding_model is None:
            from sentence_transformers import SentenceTransformer
            from app.core.settings import EMBEDDING_MODEL
            self._embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        return self._embedding_model

    def merge_chunks(
        self,
        records: List[Dict[str, Any]],
        config_override: Optional[SemanticMergeConfig] = None,
    ) -> Tuple[List[Dict[str, Any]], MergeResult]:
        """
        Executes pairwise semantic merging across a list of chunk records.
        
        Args:
            records: List of chunk dictionaries with format:
                     {"id": str, "text": str, "metadata": dict}
            config_override: Optional per-run configuration override.

        Returns:
            Tuple of (surviving_records, MergeResult)
        """
        cfg = config_override or self.config
        if not records or not cfg.enabled:
            return records, MergeResult(
                total_input_chunks=len(records),
                total_output_chunks=len(records),
                absorbed_chunks_count=0,
                reduction_percentage=0.0,
            )

        # 1. Group records by isolation scope (e.g. document_id or project_id)
        scoped_groups: Dict[str, List[Dict[str, Any]]] = {}
        for rec in records:
            meta = rec.get("metadata", {})
            scope_val = str(meta.get(cfg.scope_field) or meta.get("document_id") or "global_scope")
            scoped_groups.setdefault(scope_val, []).append(rec)

        final_records: List[Dict[str, Any]] = []
        all_actions: List[MergeAction] = []
        total_absorbed = 0

        # 2. Process each partition independently to prevent cross-contamination
        for scope_key, group_records in scoped_groups.items():
            merged_group, actions = self._merge_partition(group_records, cfg)
            final_records.extend(merged_group)
            all_actions.extend(actions)
            total_absorbed += len(actions)

        # 3. Calculate metrics
        in_count = len(records)
        out_count = len(final_records)
        reduction_pct = ((in_count - out_count) / in_count * 100.0) if in_count > 0 else 0.0

        result = MergeResult(
            total_input_chunks=in_count,
            total_output_chunks=out_count,
            absorbed_chunks_count=total_absorbed,
            reduction_percentage=round(reduction_pct, 2),
            actions=all_actions,
        )

        logger.info(
            "SemanticChunkMerger completed: %d in -> %d out (%d absorbed, %.1f%% reduction)",
            in_count, out_count, total_absorbed, reduction_pct
        )
        return final_records, result

    def _merge_partition(
        self,
        partition_records: List[Dict[str, Any]],
        cfg: SemanticMergeConfig,
    ) -> Tuple[List[Dict[str, Any]], List[MergeAction]]:
        """Executes pairwise comparison and merging inside a single isolated partition."""
        if len(partition_records) < 2:
            return partition_records, []

        # Work on deep-copies of records so caller records are not mutated unexpectedly
        active_records = [
            {
                "id": r["id"],
                "text": str(r["text"]),
                "metadata": dict(r.get("metadata", {})),
            }
            for r in partition_records
        ]

        # Identify candidate indices (Z) and absorber indices (Y)
        # Chunks <= Z can be absorbed
        candidate_indices = {
            i for i, r in enumerate(active_records)
            if len(r["text"].strip()) <= cfg.candidate_max_chars
        }
        # Chunks <= Y can absorb smaller chunks (this includes candidates themselves)
        absorber_indices = {
            i for i, r in enumerate(active_records)
            if len(r["text"].strip()) <= cfg.absorber_max_chars
        }

        if not candidate_indices or not absorber_indices:
            return active_records, []

        # Compute embeddings for all candidates and absorbers
        indices_to_embed = sorted(list(candidate_indices | absorber_indices))
        texts_to_embed = [active_records[i]["text"] for i in indices_to_embed]

        try:
            raw_embeddings = self.embedding_model.encode(
                texts_to_embed,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            # Normalize for fast cosine dot products
            norms = np.linalg.norm(raw_embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1e-9
            normalized_embeddings = raw_embeddings / norms
        except Exception as e:
            logger.warning("SemanticChunkMerger failed to compute embeddings: %s", e)
            return active_records, []

        idx_to_pos = {idx: pos for pos, idx in enumerate(indices_to_embed)}

        absorbed_indices = set()
        actions: List[MergeAction] = []

        # Process candidates from shortest to longest (prioritizing stub fragments first)
        sorted_candidates = sorted(candidate_indices, key=lambda idx: len(active_records[idx]["text"]))

        for c_idx in sorted_candidates:
            if c_idx in absorbed_indices:
                continue

            c_rec = active_records[c_idx]
            c_text = c_rec["text"].strip()
            c_emb = normalized_embeddings[idx_to_pos[c_idx]]

            best_absorber_idx = None
            best_sim = -1.0

            # Compare against all valid absorbers (j != c_idx and not already absorbed)
            for a_idx in absorber_indices:
                if a_idx == c_idx or a_idx in absorbed_indices:
                    continue

                a_rec = active_records[a_idx]
                combined_len = len(a_rec["text"]) + len(cfg.join_separator) + len(c_text)
                if combined_len > cfg.max_chunk_chars:
                    continue  # Would exceed hard cap X

                a_emb = normalized_embeddings[idx_to_pos[a_idx]]
                sim = float(np.dot(c_emb, a_emb))

                if sim >= cfg.similarity_threshold and sim > best_sim:
                    best_sim = sim
                    best_absorber_idx = a_idx

            # If a suitable absorber is found, execute the merge
            if best_absorber_idx is not None:
                a_rec = active_records[best_absorber_idx]
                target_orig_len = len(a_rec["text"])
                c_len = len(c_text)

                # Merge text
                a_rec["text"] = f"{a_rec['text']}{cfg.join_separator}{c_text}"
                merged_len = len(a_rec["text"])

                # Merge and preserve metadata lineage
                a_meta = a_rec["metadata"]
                c_meta = c_rec["metadata"]

                # Track merged chunk IDs
                merged_ids = a_meta.get("merged_chunk_ids", [a_rec["id"]])
                if not isinstance(merged_ids, list):
                    merged_ids = [str(merged_ids)]
                merged_ids.append(c_rec["id"])
                a_meta["merged_chunk_ids"] = merged_ids
                a_meta["is_merged"] = True
                a_meta["merge_count"] = len(merged_ids) - 1

                # Aggregate page numbers if distinct
                a_page = a_meta.get("page_number")
                c_page = c_meta.get("page_number")
                if c_page is not None and c_page != a_page:
                    pages_set = set()
                    for p in [a_page, c_page]:
                        if p is not None:
                            pages_set.add(str(p))
                    a_meta["page_number"] = ", ".join(sorted(pages_set))

                # Record action
                actions.append(
                    MergeAction(
                        target_id=a_rec["id"],
                        absorbed_id=c_rec["id"],
                        similarity=round(best_sim, 4),
                        target_original_len=target_orig_len,
                        absorbed_len=c_len,
                        merged_len=merged_len,
                        target_preview=a_rec["text"][:100].replace("\n", " "),
                        absorbed_preview=c_text[:100].replace("\n", " "),
                    )
                )

                # Mark candidate as absorbed
                absorbed_indices.add(c_idx)

                # Update absorber's eligibility: if it now exceeds Y, remove from absorbers
                if merged_len > cfg.absorber_max_chars and best_absorber_idx in absorber_indices:
                    absorber_indices.remove(best_absorber_idx)

        # Assemble surviving records
        surviving = [r for idx, r in enumerate(active_records) if idx not in absorbed_indices]
        return surviving, actions


def semantic_merge_chunk_records(
    records: List[Dict[str, Any]],
    config: Optional[SemanticMergeConfig] = None,
    embedding_model: Any = None,
) -> Tuple[List[Dict[str, Any]], MergeResult]:
    """Helper function to execute semantic chunk merging in a single call."""
    merger = SemanticChunkMerger(config=config, embedding_model=embedding_model)
    return merger.merge_chunks(records)
