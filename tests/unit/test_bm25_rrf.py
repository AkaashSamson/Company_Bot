import pytest
from app.infrastructure.search.bm25 import (
    BM25Retriever,
    PurePythonBM25Okapi,
    compute_rrf,
    tokenize_for_bm25,
)


def test_tokenize_for_bm25_preserves_acronyms_and_codes():
    text = "Form 1095-C for health coverage under ISO-27001 with Tier-3 deductible <!-- CUTOFF_START -->"
    tokens = tokenize_for_bm25(text)
    assert "1095-c" in tokens
    assert "iso-27001" in tokens
    assert "tier-3" in tokens
    assert "form" in tokens
    assert "<!--" not in tokens
    assert "cutoff_start" not in tokens


def test_pure_python_bm25_okapi():
    docs = [
        ["form", "1095-c", "tax", "statement"],
        ["travel", "meal", "reimbursement", "per", "diem"],
        ["health", "insurance", "tier-3", "deductible"],
    ]
    bm25 = PurePythonBM25Okapi(docs)
    scores = bm25.get_scores(["1095-c"])
    assert scores[0] > 0
    assert scores[1] == 0.0
    assert scores[2] == 0.0


def test_bm25_retriever_search():
    chunks = [
        {"id": "c1", "text": "Form 1095-C employer provided health insurance offer.", "metadata": {}},
        {"id": "c2", "text": "Annual leave accrual for level 3 engineers.", "metadata": {}},
        {"id": "c3", "text": "Travel reimbursement policy per diem guidelines.", "metadata": {}},
    ]
    retriever = BM25Retriever()
    retriever.index_chunks(chunks)

    results = retriever.search("1095-C form", top_k=2)
    assert len(results) == 1
    assert results[0]["id"] == "c1"
    assert results[0]["_bm25_score"] > 0
    assert results[0]["_bm25_rank"] == 1


def test_compute_rrf_forces_sparse_match_into_pool():
    # Dense bi-encoder placed target chunk at rank #20 (missing Top-15)
    vector_candidates = [
        {"id": f"vec_{i}", "text": f"general passage {i}", "distance": 0.1 + (i * 0.01)}
        for i in range(1, 16)
    ]
    # Sparse BM25 caught exact keyword and ranked target at rank #1
    bm25_candidates = [
        {"id": "target_chunk", "text": "Exact code ISO-27001 specifications.", "_bm25_score": 4.5}
    ]

    fused = compute_rrf(vector_candidates, bm25_candidates, k=60, top_k=5)
    top_ids = [c["id"] for c in fused]
    # Target chunk with BM25 rank #1 gets RRF score 1/(60+1) = 0.01639, competing directly with vector top ranks
    assert "target_chunk" in top_ids

