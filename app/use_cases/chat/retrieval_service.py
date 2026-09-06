import math
import re

from app.core.settings import (
    BASE_DIR,
    COLLECTION_NAME,
    RAG_CANDIDATE_COUNT,
    RAG_DISTANCE_RELAXATION,
    RAG_DISTANCE_THRESHOLD,
    RAG_MIN_DISTANCE_GAP,
    RAG_MAX_CONTEXT_CHARS,
    RAG_MAX_EVIDENCE,
)
from app.infrastructure.vector.chroma_client import ChromaVectorStore


class RetrievalService:
    def __init__(self, collection_name: str = COLLECTION_NAME, persist_directory: str | None = None):
        self.store = ChromaVectorStore(
            collection_name=collection_name,
            persist_directory=persist_directory or str(BASE_DIR / ".chroma"),
        )

    def retrieve(
        self,
        query_text: str,
        top_k: int = RAG_CANDIDATE_COUNT,
        max_evidence: int = RAG_MAX_EVIDENCE,
    ):
        candidates = []
        for part_index, retrieval_query in enumerate(self._query_parts(query_text)):
            for candidate in self.store.query(retrieval_query, top_k=top_k):
                candidates.append({**candidate, "_query_part_index": part_index})
        return self.select_relevant(
            query_text,
            candidates,
            max_evidence=max_evidence,
            distance_threshold=RAG_DISTANCE_THRESHOLD,
            max_context_chars=RAG_MAX_CONTEXT_CHARS,
        )

    @staticmethod
    def _query_parts(query_text: str) -> list[str]:
        parts = [
            part.strip(" ,;:")
            for part in re.split(r"[;\n]+|,", query_text)
        ]
        parts = [re.sub(r"^(and|or)\s+", "", part, flags=re.IGNORECASE) for part in parts]
        parts = [part for part in parts if part]
        return [query_text] + [part for part in parts if part.lower() != query_text.lower()]

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
        ranked.sort(key=lambda candidate: candidate["distance"])

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
