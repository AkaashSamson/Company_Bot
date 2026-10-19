"""
KnowLayer Test Studio — Reranking Component
===========================================
Executes Stage 2 Cross-Encoder Reranking, verifies needle retention,
and computes rank shifts for ground-truth passages.
"""

import time
from typing import Any, Dict, List, Optional
from app.infrastructure.vector.reranker_factory import get_reranker
from sandbox.engine.schema import TestCase, AssertionResult


_RERANKER_INSTANCE = None


def get_cached_engine_reranker():
    global _RERANKER_INSTANCE
    if _RERANKER_INSTANCE is None:
        _RERANKER_INSTANCE = get_reranker()
    return _RERANKER_INSTANCE


def execute_reranking(
    test_case: TestCase,
    candidates: List[Dict[str, Any]],
    top_k: int = 4,
    reranker_model: str = "BAAI/bge-reranker-base",
) -> Dict[str, Any]:
    """
    Reranks candidate chunks with Cross-Encoder and tests for needle / gold chunk retention.
    """
    if not candidates:
        return {
            "reranked_chunks": [],
            "top_k_chunk_ids": [],
            "needle_found": False,
            "latency_ms": 0.0,
            "passed": False if test_case.gold_evidence.required_chunk_ids else True,
            "assertions": [],
        }

    t0 = time.perf_counter()
    reranker = get_cached_engine_reranker()
    reranked = reranker.rerank(test_case.input.question, candidates, top_k=top_k)
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    top_chunk_ids = [c.get("id") for c in reranked]
    req_cids = test_case.gold_evidence.required_chunk_ids
    needle_text = test_case.gold_evidence.needle_text

    # Check chunk ID retention
    matched_in_top_k = [cid for cid in req_cids if cid in top_chunk_ids]
    
    # Check text needle retention
    needle_found_in_text = False
    if needle_text:
        needle_clean = needle_text.strip().lower()
        for c in reranked:
            if needle_clean in c.get("text", "").lower():
                needle_found_in_text = True
                break

    # Check document match
    expected_doc = test_case.gold_evidence.document
    doc_matched = False
    if expected_doc:
        from pathlib import Path
        doc_stem = Path(expected_doc).stem.lower()
        for c in reranked:
            src = str(c.get("metadata", {}).get("source", "")).lower()
            if doc_stem in src or src in doc_stem:
                doc_matched = True
                break

    needle_passed = bool(matched_in_top_k) or needle_found_in_text or doc_matched if (req_cids or needle_text or expected_doc) else True

    assertions: List[AssertionResult] = []
    if req_cids or needle_text:
        assertions.append(AssertionResult(
            component="reranking",
            type="needle_present",
            passed=needle_passed,
            actual_value=top_chunk_ids[:top_k],
            expected_value=req_cids,
            severity="BLOCKER",
            message=f"Needle or required chunk in top {top_k}: {matched_in_top_k if req_cids else needle_found_in_text}"
        ))

    return {
        "reranked_chunks": reranked,
        "top_k_chunk_ids": top_chunk_ids,
        "matched_in_top_k": matched_in_top_k,
        "needle_found": needle_passed,
        "passed": needle_passed,
        "latency_ms": latency_ms,
        "assertions": assertions,
    }
