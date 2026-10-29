import numpy as np
import pytest
from unittest.mock import MagicMock

from scripts.evaluate_chunking_quality import (
    ChunkRecord,
    ChunkScorecard,
    KnowLayerChunkEvaluator,
    CANONICAL_METADATA_FIELDS,
    TOKEN_HARD_CEILING,
)


class MockTokenizer:
    """Mock tokenizer returning token IDs based on word count."""
    def encode(self, text, add_special_tokens=True, truncation=False):
        words = text.split()
        return [101] + [1000] * len(words) + [102]


class MockSentenceTransformer:
    """Mock SentenceTransformer returning normalized vectors."""
    def encode(self, texts, normalize_embeddings=True, show_progress_bar=False, batch_size=64):
        if isinstance(texts, str):
            texts = [texts]
        vecs = []
        for t in texts:
            # Deterministic pseudo-embedding based on length
            v = np.zeros(384, dtype=np.float32)
            v[0] = 1.0
            vecs.append(v)
        return np.array(vecs, dtype=np.float32)


@pytest.fixture
def evaluator():
    eval_obj = KnowLayerChunkEvaluator.__new__(KnowLayerChunkEvaluator)
    eval_obj.tokenizer = MockTokenizer()
    eval_obj.embedder = MockSentenceTransformer()
    eval_obj.reranker = None
    return eval_obj


# ---------------------------------------------------------------------------
# Parameter 1: Token Budget
# ---------------------------------------------------------------------------
def test_token_budget_sweet_spot(evaluator):
    # ~100 tokens
    text = " " .join(["word"] * 100)
    score, count, flags = evaluator.score_token_budget(text)
    assert score == 1.0
    assert not flags
    assert count == 102  # 100 + 2 special tokens


def test_token_budget_truncation_failure(evaluator):
    # > 256 tokens
    text = " ".join(["word"] * 300)
    score, count, flags = evaluator.score_token_budget(text)
    assert score == 0.0
    assert any("TRUNCATION_FAILURE" in f for f in flags)
    assert count > TOKEN_HARD_CEILING


def test_token_budget_micro_fragment(evaluator):
    # < 40 tokens
    text = "Short text."
    score, count, flags = evaluator.score_token_budget(text)
    assert score < 0.5
    assert any("MICRO_FRAGMENT" in f for f in flags)


def test_token_budget_near_ceiling(evaluator):
    # 245 words -> 247 tokens
    text = " ".join(["word"] * 245)
    score, count, flags = evaluator.score_token_budget(text)
    assert 0.1 <= score < 1.0
    assert any("NEAR_TOKEN_CEILING" in f for f in flags)


# ---------------------------------------------------------------------------
# Parameter 2: Boundary Integrity
# ---------------------------------------------------------------------------
def test_boundary_integrity_clean(evaluator):
    text = "Employees are entitled to 20 days of annual leave per year."
    score, flags = evaluator.score_boundary_integrity(text, "text")
    assert score == 1.0
    assert not flags


def test_boundary_integrity_mid_sentence_and_unfinished(evaluator):
    text = "and this is continuing an earlier sentence without terminal stop"
    score, flags = evaluator.score_boundary_integrity(text, "text")
    assert score < 0.60
    assert "MID_SENTENCE_START" in flags
    assert "UNFINISHED_SENTENCE_END" in flags


def test_boundary_integrity_orphan_heading(evaluator):
    text = "Policy details follow.\n\n### Section 4: Eligibility"
    score, flags = evaluator.score_boundary_integrity(text, "text")
    assert "ORPHAN_TRAILING_HEADING" in flags
    assert score <= 0.5


def test_boundary_integrity_table(evaluator):
    valid_table = (
        "| Role | Entitlement |\n"
        "| --- | --- |\n"
        "| Full-Time | 20 Days |\n"
        "| Part-Time | 10 Days |"
    )
    score, flags = evaluator.score_boundary_integrity(valid_table, "table")
    assert score == 1.0
    assert not flags

    orphan_table = (
        "| Full-Time | 20 Days |\n"
        "| Part-Time | 10 Days |"
    )
    score_orph, flags_orph = evaluator.score_boundary_integrity(orphan_table, "table")
    assert "ORPHAN_TABLE_ROWS_NO_HEADER" in flags_orph
    assert score_orph < 0.5


# ---------------------------------------------------------------------------
# Parameter 3: Metadata Completeness
# ---------------------------------------------------------------------------
def test_metadata_completeness_full(evaluator):
    meta = {
        "document_id": "doc-01",
        "project_id": "proj-default",
        "source_filename": "leave_policy.pdf",
        "chunk_index": 0,
        "content_type": "text",
        "hierarchy_path": ["HR", "Leave Policy", "Annual Leave"],
        "section_heading": "Annual Leave",
    }
    score, flags = evaluator.score_metadata_completeness(meta)
    assert score >= 1.0
    assert not flags


def test_metadata_completeness_missing_fields(evaluator):
    meta = {
        "document_id": "doc-01",
        "source_filename": "leave_policy.pdf",
    }
    score, flags = evaluator.score_metadata_completeness(meta)
    assert score < 0.5
    assert any("MISSING_META_PROJECT_ID" in f for f in flags)
    assert any("NO_HIERARCHY_OR_SECTION" in f for f in flags)


# ---------------------------------------------------------------------------
# Parameter 5: Inter-Chunk Distinctiveness
# ---------------------------------------------------------------------------
def test_inter_distinctiveness_identical_neighbor(evaluator):
    v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    c1 = ChunkRecord(
        chunk_id="c1",
        text="Text 1",
        metadata={"source_filename": "doc.pdf"},
        embedding=v,
    )
    c2 = ChunkRecord(
        chunk_id="c2",
        text="Text 2",
        metadata={"source_filename": "doc.pdf"},
        embedding=v,  # Dot product 1.0 >= 0.88
    )
    chunks = [c1, c2]

    score, flags = evaluator.score_inter_distinctiveness(0, chunks)
    assert score == 0.0
    assert any("REDUNDANT_NEIGHBOR_OVERLAP" in f for f in flags)


def test_inter_distinctiveness_different_source(evaluator):
    v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    c1 = ChunkRecord(
        chunk_id="c1",
        text="Text 1",
        metadata={"source_filename": "docA.pdf"},
        embedding=v,
    )
    c2 = ChunkRecord(
        chunk_id="c2",
        text="Text 2",
        metadata={"source_filename": "docB.pdf"},  # Different source file
        embedding=v,
    )
    chunks = [c1, c2]

    score, flags = evaluator.score_inter_distinctiveness(0, chunks)
    assert score == 1.0
    assert not flags


# ---------------------------------------------------------------------------
# Parameter 6: Self-Containment
# ---------------------------------------------------------------------------
def test_self_containment_dangling_pronoun(evaluator):
    text = "This policy applies to all associates immediately upon hiring."
    meta = {"document_id": "doc1"}
    score, flags = evaluator.score_self_containment(text, meta)
    assert any("DANGLING_ANAPHORA_AT_START" in f for f in flags)
    assert score < 1.0


def test_self_containment_with_injected_header(evaluator):
    text = "[HR > Leave Policy] This policy applies to all associates immediately."
    meta = {"hierarchy_path": ["HR", "Leave Policy"]}
    score, flags = evaluator.score_self_containment(text, meta)
    assert not any("DANGLING_ANAPHORA_AT_START" in f for f in flags)
    assert score == 1.0


# ---------------------------------------------------------------------------
# Corpus Evaluation & Report Compilation
# ---------------------------------------------------------------------------
def test_compile_report_cqi_and_grades(evaluator):
    cards = [
        ChunkScorecard(
            chunk_id="c1",
            source_file="doc.pdf",
            chunk_type="text",
            token_count=120,
            s_token=1.0,
            s_bound=1.0,
            s_meta=1.0,
            s_coh=0.9,
            s_dist=1.0,
            s_self=1.0,
            s_ret=1.0,
            composite_intrinsic_score=0.98,
            failure_flags=[],
        ),
        ChunkScorecard(
            chunk_id="c2",
            source_file="doc.pdf",
            chunk_type="text",
            token_count=150,
            s_token=1.0,
            s_bound=0.8,
            s_meta=1.0,
            s_coh=0.85,
            s_dist=1.0,
            s_self=0.9,
            s_ret=0.5,
            composite_intrinsic_score=0.92,
            failure_flags=["UNFINISHED_SENTENCE_END"],
        ),
    ]

    report = KnowLayerChunkEvaluator._compile_report(cards)
    assert report["summary"]["total_chunks_evaluated"] == 2
    assert report["summary"]["composite_quality_index"] == 95.0
    assert "A+ (Exceptional)" in report["summary"]["quality_grade"]
    assert report["token_stats"]["mean_tokens"] == 135.0
    assert "UNFINISHED_SENTENCE_END" in report["failure_flag_distribution"]
