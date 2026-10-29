"""
tests/integration/test_chunk_normalizer_provisioner.py
Tier 5 End-to-End Pipeline & Corpus Remediation Dry-Run Tests (TC-I01 through TC-I03).
"""

from app.infrastructure.document.chunk_normalizer import (
    ChunkNormalizer,
    NormalizedChunk,
)


# TC-I01: End-to-End Provisioner Batch Invariant Check
def test_end_to_end_provisioner_pipeline():
    normalizer = ChunkNormalizer(hard_token_ceiling=245)
    simulated_docling_batch = [
        NormalizedChunk(
            chunk_id=f"prov_{i}",
            text=(
                f"Page {i} of 20\n"
                + ("Standard HR leave policy requires 14 days notice before travel. " * (i % 12 + 1))
            ),
            metadata={
                "source_filename": "hr_master_policy.pdf",
                "document_id": "DOC-MASTER",
                "page_number": i + 1,
                "heading_hierarchy": "HR > Leave Policy",
            },
        )
        for i in range(15)
    ]
    normalized = normalizer.normalize_chunks(simulated_docling_batch)
    assert len(normalized) > 0
    assert all(c.metadata["token_count"] <= 245 for c in normalized)
    assert all(c.metadata.get("content_hash") for c in normalized)


# TC-I02: Chroma Corpus Remediation Dry Run Simulation
def test_chroma_corpus_remediation_dry_run():
    normalizer = ChunkNormalizer(hard_token_ceiling=245)
    legacy_chroma_dump = [
        NormalizedChunk(
            chunk_id="legacy_1",
            text="Short stub.",
            metadata={"source_file": "legacy.pdf", "page_number": 1},
        ),
        NormalizedChunk(
            chunk_id="legacy_2",
            text="Continuation of legacy policy document with full eligibility details for staff.",
            metadata={"source_file": "legacy.pdf", "page_number": 1},
        ),
    ]
    planned_updates = normalizer.normalize_chunks(legacy_chroma_dump)
    assert len(planned_updates) == 1
    assert planned_updates[0].metadata["source_filename"] == "legacy.pdf"


# TC-I03: Reverse Retrieval Hit Rate Invariant
def test_reverse_retrieval_hit_rate():
    normalizer = ChunkNormalizer(hard_token_ceiling=245)
    corpus = normalizer.normalize_chunks([
        NormalizedChunk(
            chunk_id="pol_paternity",
            text="Full-time employees are entitled to 15 paid days of paternity leave within 6 months of birth.",
            metadata={"source_filename": "parental.pdf", "heading_hierarchy": "Leave > Paternity"},
        ),
        NormalizedChunk(
            chunk_id="pol_tuition",
            text="Tuition reimbursement covers up to $5,250 annually for accredited degree programs.",
            metadata={"source_filename": "education.pdf", "heading_hierarchy": "Benefits > Tuition"},
        ),
    ])
    # Verify injected header + body produces unambiguous lexical/semantic self-containment
    assert any("Paternity" in c.text and "15 paid days" in c.text for c in corpus)
    assert any("Tuition" in c.text and "$5,250" in c.text for c in corpus)
