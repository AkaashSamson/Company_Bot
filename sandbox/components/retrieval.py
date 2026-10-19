"""
KnowLayer Test Studio — Retrieval Component
===========================================
Executes Stage 1 Vector Retrieval with RBAC scope enforcement,
calculating Recall@k and candidate metrics against ChromaDB.
"""

import time
from typing import Any, Dict, List, Optional
from app.infrastructure.vector.chroma_client import ChromaVectorStore
from app.core.settings import BASE_DIR, COLLECTION_NAME
from sandbox.engine.schema import TestCase, AssertionResult


# Global cached vector store instance
_STORE_INSTANCE: Optional[ChromaVectorStore] = None


def get_engine_vector_store() -> ChromaVectorStore:
    global _STORE_INSTANCE
    if _STORE_INSTANCE is None:
        _STORE_INSTANCE = ChromaVectorStore(
            collection_name=COLLECTION_NAME,
            persist_directory=str(BASE_DIR / ".chroma"),
        )
    return _STORE_INSTANCE


def execute_retrieval(
    test_case: TestCase,
    top_k: int = 13,
    enforce_rbac: bool = True,
    store: Optional[ChromaVectorStore] = None,
) -> Dict[str, Any]:
    """
    Executes dense retrieval for the test case query.
    Enforces project/role scopes if configured.
    """
    store = store or get_engine_vector_store()
    query = test_case.input.question
    role = test_case.input.role
    
    # RBAC project filtering
    project_ids = None
    if enforce_rbac:
        if test_case.input.project_ids is not None:
            project_ids = test_case.input.project_ids
        elif role == "EMPLOYEE":
            # Standard employees have access to General/HR policies (project_id 121 or None)
            project_ids = ["121", "unassigned", "default"]
        # If MANAGER or HR or ALL, project_ids can remain unrestricted (None) unless specified

    t0 = time.perf_counter()
    candidates = store.query(
        query_text=query,
        top_k=top_k,
        project_ids=project_ids,
    )
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    retrieved_cids = [c["id"] for c in candidates]
    req_cids = test_case.gold_evidence.required_chunk_ids
    evidence_mode = test_case.gold_evidence.evidence_mode or "any"

    # Calculate Recall
    matched_cids = [cid for cid in req_cids if cid in retrieved_cids]
    if not req_cids:
        recall = 1.0  # Out-of-scope or no explicit gold chunks required
    elif evidence_mode == "all":
        recall = len(matched_cids) / len(req_cids)
    else:  # "any"
        recall = 1.0 if len(matched_cids) > 0 else 0.0

    retrieval_pass = (recall >= 1.0) if evidence_mode == "all" else (recall > 0.0 or not req_cids)

    assertions: List[AssertionResult] = []
    if req_cids:
        assertions.append(AssertionResult(
            component="retrieval",
            type="recall_at_k",
            passed=retrieval_pass,
            actual_value=round(recall, 3),
            expected_value=1.0 if evidence_mode == "all" else 0.5,
            threshold=1.0 if evidence_mode == "all" else 0.5,
            severity="BLOCKER",
            message=f"Matched {len(matched_cids)}/{len(req_cids)} required chunks (mode={evidence_mode}). Found: {matched_cids}"
        ))

    return {
        "candidates": candidates,
        "retrieved_chunk_ids": retrieved_cids,
        "matched_chunk_ids": matched_cids,
        "recall_at_k": recall,
        "passed": retrieval_pass,
        "latency_ms": latency_ms,
        "assertions": assertions,
    }
