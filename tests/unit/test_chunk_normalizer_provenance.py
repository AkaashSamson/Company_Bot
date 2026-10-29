"""
tests/unit/test_chunk_normalizer_provenance.py
Tier 3 Provenance, Tenant Isolation, and Idempotence Tests (TC-P01 through TC-P04).
"""

import pytest
from app.infrastructure.document.chunk_normalizer import (
    ChunkNormalizer,
    NormalizedChunk,
)


@pytest.fixture
def normalizer() -> ChunkNormalizer:
    return ChunkNormalizer(hard_token_ceiling=245, coalesce_max_tokens=220, min_fragment_tokens=55)


# TC-P01: Cross-Page Coalescing Preserves Page Span
def test_cross_page_coalescing_preserves_page_span(normalizer: ChunkNormalizer):
    c1 = NormalizedChunk(
        chunk_id="p1",
        text="Leave carry-over rules:",
        metadata={"source_filename": "leave.pdf", "document_id": "DOC-1", "page_number": 1},
    )
    c2 = NormalizedChunk(
        chunk_id="p2",
        text="Up to 5 unused PTO days may be carried over into the next fiscal year.",
        metadata={"source_filename": "leave.pdf", "document_id": "DOC-1", "page_number": 2},
    )
    out = normalizer.normalize_chunks([c1, c2])
    assert len(out) == 1
    assert out[0].metadata.get("page_span") == [1, 2]
    assert out[0].metadata.get("page_number") == 1


# TC-P02: Null Source Does Not Cross-Heal Across Different Documents
def test_null_source_does_not_cross_heal(normalizer: ChunkNormalizer):
    c1 = NormalizedChunk(
        chunk_id="docA",
        text="Confidential severance terms apply to",
        metadata={"source_filename": None, "document_id": "DOC-ALPHA", "page_number": 1},
    )
    c2 = NormalizedChunk(
        chunk_id="docB",
        text="interns hired during the summer session.",
        metadata={"source_filename": None, "document_id": "DOC-BETA", "page_number": 1},
    )
    out = normalizer.normalize_chunks([c1, c2])
    assert len(out) == 2
    assert "interns hired" not in out[0].text


# TC-P03: Deep Hierarchy Prefix Truncation Guard (prefix + body <= 245)
def test_deep_hierarchy_prefix_truncation_guard(normalizer: ChunkNormalizer):
    deep_h = " > ".join([f"Level_{i}_Enterprise_Division_Governance_Subcommittee" for i in range(8)])
    body = " ".join([f"Clause {i} specifies mandatory quarterly audit reporting." for i in range(28)])
    c = NormalizedChunk(
        chunk_id="deep",
        text=body,
        metadata={"source_filename": "global_governance_manual_2026.pdf", "heading_hierarchy": deep_h},
    )
    out = normalizer.normalize_chunks([c])
    for sub in out:
        assert normalizer.count_tokens(sub.text) <= 245


# TC-P04: Pipeline Idempotency Double Run
def test_pipeline_idempotency_double_run(normalizer: ChunkNormalizer):
    raw = [
        NormalizedChunk(
            chunk_id="idemp_1",
            text="Page 1 of 9\nRemote work requires manager approval.... 12\n### Equipment Stipend",
            metadata={"source_filename": "remote.pdf", "document_id": "DOC-REM", "page_number": 1},
        ),
        NormalizedChunk(
            chunk_id="idemp_2",
            text="Employees receive $500 for ergonomic home office setup.",
            metadata={"source_filename": "remote.pdf", "document_id": "DOC-REM", "page_number": 2},
        ),
    ]
    run1 = normalizer.normalize_chunks(raw)
    run2 = normalizer.normalize_chunks(run1)

    assert len(run1) == len(run2)
    for a, b in zip(run1, run2):
        assert a.text == b.text
        assert a.metadata["content_hash"] == b.metadata["content_hash"]
        assert a.metadata["token_count"] == b.metadata["token_count"]
        assert a.chunk_id == b.chunk_id
