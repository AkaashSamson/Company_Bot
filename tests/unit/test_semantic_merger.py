import pytest
from app.infrastructure.ingestion.semantic_merger import (
    SemanticChunkMerger,
    SemanticMergeConfig,
    semantic_merge_chunk_records,
)


class DummyEmbeddingModel:
    """Mock embedding model that returns fixed or calculated vectors for fast unit tests."""
    def __init__(self, mapping=None):
        self.mapping = mapping or {}

    def encode(self, texts, convert_to_numpy=True, show_progress_bar=False):
        # pyrefly: ignore[missing-import]
        import numpy as np
        res = []
        for t in texts:
            # If specified in mapping, use that vector
            if t in self.mapping:
                res.append(self.mapping[t])
            elif "Leave Policy Disclaimer" in t or "Disclaimer" in t:
                # Highly similar vector
                res.append([0.99, 0.01, 0.0])
            elif "Leave Policy" in t:
                res.append([0.98, 0.02, 0.0])
            else:
                # Orthogonal
                res.append([0.0, 1.0, 0.0])
        return np.array(res, dtype=np.float32)


def test_semantic_merger_absorbs_similar_stub():
    mock_model = DummyEmbeddingModel()
    config = SemanticMergeConfig(
        max_chunk_chars=1000,
        absorber_max_chars=600,
        candidate_max_chars=200,
        similarity_threshold=0.85,
        scope_field="document_id",
    )

    records = [
        {
            "id": "doc1-0",
            "text": "Company Leave Policy: All full-time employees are entitled to 20 days paid annual leave.",
            "metadata": {"document_id": "doc1", "page_number": 1},
        },
        {
            "id": "doc1-1",
            "text": "Leave Policy Disclaimer: Standard HR guidelines apply to all annual leave.",
            "metadata": {"document_id": "doc1", "page_number": 2},
        },
    ]

    merger = SemanticChunkMerger(config=config, embedding_model=mock_model)
    surviving, result = merger.merge_chunks(records)

    assert len(surviving) == 1
    assert result.absorbed_chunks_count == 1
    assert result.reduction_percentage == 50.0

    merged = surviving[0]
    assert merged["id"] == "doc1-0"
    assert "Company Leave Policy" in merged["text"]
    assert "Leave Policy Disclaimer" in merged["text"]
    assert merged["metadata"]["is_merged"] is True
    assert merged["metadata"]["merged_chunk_ids"] == ["doc1-0", "doc1-1"]
    assert "1" in str(merged["metadata"]["page_number"])
    assert "2" in str(merged["metadata"]["page_number"])


def test_semantic_merger_respects_isolation_scope():
    """Chunks with high similarity from different documents/scopes must NOT merge."""
    mock_model = DummyEmbeddingModel()
    config = SemanticMergeConfig(
        max_chunk_chars=1000,
        absorber_max_chars=600,
        candidate_max_chars=200,
        similarity_threshold=0.80,
        scope_field="document_id",
    )

    records = [
        {
            "id": "doc-HR-0",
            "text": "Company Leave Policy: All employees receive annual leave.",
            "metadata": {"document_id": "doc-HR"},
        },
        {
            "id": "doc-ENG-0",
            "text": "Leave Policy Disclaimer: Standard engineering guidelines.",
            "metadata": {"document_id": "doc-ENG"},
        },
    ]

    merger = SemanticChunkMerger(config=config, embedding_model=mock_model)
    surviving, result = merger.merge_chunks(records)

    assert len(surviving) == 2
    assert result.absorbed_chunks_count == 0


def test_semantic_merger_respects_hard_cap():
    """Merging is skipped if combined length would exceed max_chunk_chars (X)."""
    mock_model = DummyEmbeddingModel()
    config = SemanticMergeConfig(
        max_chunk_chars=100,  # Strict cap
        absorber_max_chars=80,
        candidate_max_chars=50,
        similarity_threshold=0.80,
        scope_field="document_id",
    )

    records = [
        {
            "id": "doc1-0",
            "text": "Company Leave Policy: 20 days paid annual leave for regular full-time team members.",  # 83 chars
            "metadata": {"document_id": "doc1"},
        },
        {
            "id": "doc1-1",
            "text": "Leave Policy Disclaimer: Standard HR guidelines.",  # 48 chars
            "metadata": {"document_id": "doc1"},
        },
    ]

    merger = SemanticChunkMerger(config=config, embedding_model=mock_model)
    surviving, result = merger.merge_chunks(records)

    # 83 + 2 (separator) + 48 = 133 > 100 max cap => Must NOT merge
    assert len(surviving) == 2
    assert result.absorbed_chunks_count == 0
