import logging
import math
import logging
import re

from typing import Any, Dict, List, Optional, Iterable, Sequence, Tuple
from app.core.settings import (
    BASE_DIR,
    COLLECTION_NAME,
    RAG_CANDIDATE_COUNT,
    RAG_DISTANCE_RELAXATION,
    RAG_DISTANCE_THRESHOLD,
    RAG_MIN_DISTANCE_GAP,
    RAG_MAX_CONTEXT_CHARS,
    RAG_MAX_EVIDENCE,
    RAG_FINAL_K,
    RAG_RERANKER_MODEL,
)
from app.infrastructure.vector.chroma_client import ChromaVectorStore
from app.domain.ports.reranker import RerankerPort
from app.infrastructure.vector.bge_reranker import BgeReranker

logger = logging.getLogger(__name__)

from app.use_cases.chat.retrieval_quality import (
    RetrievalQualityGate,
    QualityGateResult,
    EvidenceQualityLevel,
)

logger = logging.getLogger("knowlayer.retrieval")


class RetrievalService:
    def __init__(
        self,
        collection_name: str = COLLECTION_NAME,
        persist_directory: str | None = None,
        quality_gate: RetrievalQualityGate | None = None,
        reranker: RerankerPort | None = None,
    ):
        self.store = ChromaVectorStore(
            collection_name=collection_name,
            persist_directory=persist_directory or str(BASE_DIR / ".chroma"),
        )
        self.quality_gate = quality_gate or RetrievalQualityGate()
        self.reranker = reranker or BgeReranker(model_name=RAG_RERANKER_MODEL)
        self.last_quality_result: QualityGateResult | None = None


    def retrieve_raw_candidates(
        self,
        query_text: str,
        top_k: int = RAG_CANDIDATE_COUNT,
        authorized_project_ids: Optional[Iterable[str]] = None,
        authorized_document_ids: Optional[Iterable[str]] = None,
        include_unassigned: bool = True,
    ) -> list[dict]:
        """Fetch raw vector candidates from store without applying cross-encoder reranker."""
        project_ids_for_filter = None
        if authorized_project_ids is not None:
            project_ids_for_filter = list(authorized_project_ids)
            if include_unassigned and "unassigned" not in project_ids_for_filter:
                project_ids_for_filter.append("unassigned")

        where_filter = None
        if authorized_document_ids is not None:
            document_filter = {"document_id": {"$in": list(authorized_document_ids)}}
            if project_ids_for_filter is not None:
                where_filter = {
                    "$or": [
                        {"project_id": {"$in": project_ids_for_filter}},
                        document_filter,
                    ]
                }
            else:
                where_filter = document_filter

        query_kwargs = {"top_k": top_k}
        if where_filter is not None:
            query_kwargs["where"] = where_filter
        elif project_ids_for_filter is not None:
            query_kwargs["project_ids"] = project_ids_for_filter

        candidates = []
        for candidate in self.store.query(query_text, **query_kwargs):
            candidates.append({**candidate, "_query_part_index": 0})

        if authorized_project_ids is not None or authorized_document_ids is not None:
            from app.domain.services.document_project_service import get_document_project_service
            doc_proj_svc = get_document_project_service()
            candidates = [
                c for c in candidates
                if doc_proj_svc.is_chunk_authorized(
                    c.get("metadata") or {},
                    authorized_project_ids=authorized_project_ids,
                    authorized_document_ids=authorized_document_ids,
                    include_unassigned=include_unassigned,
                    is_admin=(authorized_project_ids is None and authorized_document_ids is None),
                )
            ]

        return candidates

    def retrieve(
        self,
        query_text: str,
        rerank: bool = True,
        top_k: int = RAG_CANDIDATE_COUNT,
        max_evidence: int = RAG_MAX_EVIDENCE,
        authorized_project_ids: list[str] | None = None,
        authorized_document_ids: list[str] | None = None,
        include_unassigned: bool = True,
    ):
        project_ids_for_filter = None
        if authorized_project_ids is not None:
            scoped = sorted(set(authorized_project_ids) | ({"unassigned"} if include_unassigned else set()))
            project_ids_for_filter = scoped
            logger.info("retrieval project scope for user: %s", scoped)

        where_filter = None
        if authorized_document_ids:
            document_filter = {"document_id": {"$in": list(authorized_document_ids)}}
            if project_ids_for_filter:
                where_filter = {
                    "$or": [
                        {"project_id": {"$in": project_ids_for_filter}},
                        document_filter,
                    ]
                }
            else:
                where_filter = document_filter
            logger.info("retrieval document scope for user: %s", list(authorized_document_ids))

        candidates = []
        query_kwargs = {"top_k": top_k}
        if where_filter is not None:
            query_kwargs["where"] = where_filter
        elif project_ids_for_filter is not None:
            query_kwargs["project_ids"] = project_ids_for_filter
            
        for candidate in self.store.query(query_text, **query_kwargs):
            candidates.append({**candidate, "_query_part_index": 0})

        # Post-retrieval verification using DocumentProjectMappingService:
        # Strictly ensure zero unauthorized chunks pass into reranking or LLM generation
        if authorized_project_ids is not None or authorized_document_ids is not None:
            from app.domain.services.document_project_service import get_document_project_service
            doc_proj_svc = get_document_project_service()
            filtered_candidates = []
            for candidate in candidates:
                cand_meta = candidate.get("metadata") or {}
                if doc_proj_svc.is_chunk_authorized(
                    cand_meta,
                    authorized_project_ids=authorized_project_ids,
                    authorized_document_ids=authorized_document_ids,
                    include_unassigned=include_unassigned,
                    is_admin=(authorized_project_ids is None and authorized_document_ids is None),
                ):
                    filtered_candidates.append(candidate)
                else:
                    logger.info(
                        "Filtered out unauthorized candidate chunk %s (doc=%s, proj=%s) for scope proj=%s docs=%s",
                        candidate.get("id"),
                        cand_meta.get("document_id") or cand_meta.get("source"),
                        cand_meta.get("project_id"),
                        authorized_project_ids,
                        authorized_document_ids,
                    )
            candidates = filtered_candidates
            
        if self.reranker:
            candidates = self.reranker.rerank(query_text, candidates, top_k=RAG_FINAL_K)
            
        logger.info(
            "retrieval collected %d raw candidates for query %r (authorized_projects=%s documents=%s)",
            len(candidates), query_text, authorized_project_ids, authorized_document_ids,
        )
        selected = self.select_relevant(
            query_text,
            candidates,
            max_evidence=max_evidence,
            distance_threshold=RAG_DISTANCE_THRESHOLD,
            max_context_chars=RAG_MAX_CONTEXT_CHARS,
        )

        gate_result = None
        if getattr(self, "quality_gate", None) is not None:
            try:
                gate_result = self.quality_gate.evaluate(query_text, selected)
                self.last_quality_result = gate_result
                for chunk in selected:
                    chunk["quality_level"] = gate_result.quality_level.value
                    chunk["grounding_score"] = gate_result.quality_score.grounding_score
                    chunk["confidence"] = gate_result.confidence
            except Exception as exc:
                logger.warning("Quality gate evaluation failed: %s", exc)

        logger.info(
            "retrieval accepted %d evidence chunks for query %r (distances=%s, quality=%s, confidence=%s)",
            len(selected), query_text,
            [round(c["distance"], 4) for c in selected if isinstance(c.get("distance"), (int, float))],
            gate_result.quality_level.value if gate_result else "n/a",
            round(gate_result.confidence, 4) if gate_result else "n/a",
        )

        # Dynamically generate unique vocabulary based on set() of NN from retrieved chunks
        if selected:
            try:
                from app.use_cases.chat.query_normalizer import get_query_normalizer
                get_query_normalizer().learn_nouns_from_chunks(selected)
            except Exception as exc:
                logger.debug("Failed dynamically learning nouns from retrieved chunks: %s", exc)

        return selected

    def detect_unauthorized_relevance(
        self,
        query_text: str,
        authorized_project_ids: list[str] | None = None,
        authorized_document_ids: list[str] | None = None,
        include_unassigned: bool = True,
        top_k: int = RAG_CANDIDATE_COUNT,
    ) -> list[dict]:
        """Probe the full corpus for content relevant to the query that lies
        outside the principal's authorized scope.

        The probe runs an unrestricted Chroma query and keeps only candidates
        that are unauthorized AND would have passed the same relevance criteria
        used for authorized evidence (distance threshold + lexical grounding).

        Returns *redacted* hits only — no document text and no full metadata —
        enough to build an access-request response without ever exposing
        document content to the caller or the LLM::

            {"project_id", "document_id", "source", "section", "distance"}

        ``authorized_project_ids=None`` means unrestricted (admin). Such a
        scope can never produce unauthorized hits because nothing is out of
        scope.
        """
        if authorized_project_ids is None:
            return []
        candidates = self.store.query(query_text, top_k=top_k)

        from app.domain.services.document_project_service import get_document_project_service
        doc_proj_svc = get_document_project_service()

        hits = []
        for candidate in candidates:
            distance = candidate.get("distance")
            if not isinstance(distance, (int, float)):
                continue
            if distance > RAG_DISTANCE_THRESHOLD:
                continue
            if not self._has_lexical_grounding(candidate, query_text):
                continue

            metadata = candidate.get("metadata") or {}
            if doc_proj_svc.is_chunk_authorized(
                metadata,
                authorized_project_ids=authorized_project_ids,
                authorized_document_ids=authorized_document_ids,
                include_unassigned=include_unassigned,
            ):
                continue

            raw_doc_id = metadata.get("document_id") or metadata.get("source")
            canonical_doc_id, resolved_proj_id = doc_proj_svc.resolve_doc_and_project(raw_doc_id)
            effective_proj_id = metadata.get("project_id") or resolved_proj_id

            hits.append({
                "project_id": str(effective_proj_id) if effective_proj_id else None,
                "document_id": canonical_doc_id or raw_doc_id,
                "source": metadata.get("source"),
                "distance": distance,
            })

        hits.sort(key=lambda hit: hit["distance"])
        logger.info(
            "authorization probe found %d relevant unauthorized candidates for query %r",
            len(hits), query_text,
        )
        return hits


    @staticmethod
    def select_relevant(
        query_text: str,
        candidates: list[dict],
        max_evidence: int = RAG_MAX_EVIDENCE,
        distance_threshold: float = RAG_DISTANCE_THRESHOLD,
        distance_relaxation: float = RAG_DISTANCE_RELAXATION,
        min_distance_gap: float = RAG_MIN_DISTANCE_GAP,
        max_context_chars: int = RAG_MAX_CONTEXT_CHARS,
    ):
        """Select grounded, ranked, non-redundant evidence.

        Chroma cosine distance is lower for closer matches. Candidates above
        the configured distance threshold are rejected before context assembly.
        Query parts are used only to ensure coverage when separate retrievals
        produce distinct strong evidence; no document-specific vocabulary is
        required.
        """
        if not candidates or max_evidence <= 0:
            return []

        unique_candidates = []
        seen_text = set()
        for candidate in candidates:
            text = candidate.get("text", "").strip()
            if not text or text in seen_text:
                continue
            seen_text.add(text)
            unique_candidates.append(candidate)

        ranked = [
            candidate for candidate in unique_candidates
            if isinstance(candidate.get("distance"), (int, float))
            and math.isfinite(candidate["distance"])
        ]
        ranked.sort(key=lambda candidate: candidate.get("_new_rank", candidate["distance"]))

        accepted = []
        for index, candidate in enumerate(ranked):
            distance = candidate["distance"]
            within_threshold = distance <= distance_threshold
            separated_top_candidate = (
                index == 0
                and len(ranked) > 1
                and distance <= distance_threshold + distance_relaxation
                and ranked[1]["distance"] - distance >= min_distance_gap
                and RetrievalService._has_lexical_grounding(
                    candidate,
                    query_text,
                )
            )
            if within_threshold or separated_top_candidate:
                accepted.append(candidate)
        ranked = accepted

        selected = []
        covered_parts = set()
        for candidate in ranked:
            part_index = candidate.get("_query_part_index")
            if part_index is None or part_index in covered_parts:
                continue
            if any(RetrievalService._is_redundant(candidate, existing) for existing in selected):
                continue
            selected.append(candidate)
            covered_parts.add(part_index)
            if len(selected) >= max_evidence:
                break

        for candidate in ranked:
            if len(selected) >= max_evidence:
                break
            if candidate in selected:
                continue
            if any(RetrievalService._is_redundant(candidate, existing) for existing in selected):
                continue
            selected.append(candidate)
            if len(selected) >= max_evidence:
                break

        context_size = 0
        bounded = []
        for candidate in selected:
            text_size = len(candidate["text"])
            separator_size = 2 if bounded else 0
            if bounded and context_size + separator_size + text_size > max_context_chars:
                break
            bounded.append(candidate)
            context_size += separator_size + text_size
        return bounded

    @staticmethod
    def _is_redundant(candidate: dict, selected: dict) -> bool:
        candidate_terms = set(re.findall(r"[a-z0-9]+", candidate["text"].lower()))
        selected_terms = set(re.findall(r"[a-z0-9]+", selected["text"].lower()))
        if not candidate_terms or not selected_terms:
            return True
        overlap = len(candidate_terms & selected_terms)
        return overlap / min(len(candidate_terms), len(selected_terms)) >= 0.9

    @staticmethod
    def _has_lexical_grounding(candidate: dict, query_text: str) -> bool:
        stop_words = {
            "a", "an", "and", "are", "be", "can", "do", "does", "for",
            "how", "i", "in", "is", "it", "of", "on", "or", "the", "to",
            "what", "when", "where", "which", "who", "why", "with",
        }

        def terms(value: str) -> set[str]:
            normalized = re.findall(r"[a-z0-9]+", value.lower())
            return {
                token[:-1] if token.endswith("s") and len(token) > 3 else token
                for token in normalized
                if token not in stop_words
            }

        query_terms = terms(query_text)
        candidate_terms = terms(candidate.get("text", ""))
        return bool(query_terms & candidate_terms)
