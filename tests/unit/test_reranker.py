import pytest
from unittest.mock import patch, MagicMock
from app.infrastructure.vector.bge_reranker import BgeReranker

@pytest.fixture
def mock_cross_encoder():
    with patch("app.infrastructure.vector.bge_reranker.CrossEncoder") as MockCE:
        mock_instance = MagicMock()
        MockCE.return_value = mock_instance
        yield mock_instance

def test_normal_ranking(mock_cross_encoder):
    mock_cross_encoder.predict.return_value = [0.1, 0.9, 0.5]
    
    reranker = BgeReranker()
    candidates = [
        {"text": "bad match", "id": 1, "metadata": {"foo": "bar"}},
        {"text": "best match", "id": 2, "metadata": {"foo": "baz"}},
        {"text": "okay match", "id": 3, "metadata": {"foo": "qux"}},
    ]
    
    result = reranker.rerank("query", candidates, top_k=2)
    
    assert len(result) == 2
    assert result[0]["id"] == 2
    assert result[0]["_rerank_score"] == 0.9
    assert result[0]["_original_rank"] == 2
    assert result[0]["_new_rank"] == 1
    assert result[0]["metadata"] == {"foo": "baz"}
    
    assert result[1]["id"] == 3
    assert result[1]["_rerank_score"] == 0.5
    assert result[1]["_original_rank"] == 3
    assert result[1]["_new_rank"] == 2
    
def test_empty_candidates(mock_cross_encoder):
    reranker = BgeReranker()
    result = reranker.rerank("query", [], top_k=5)
    assert result == []
    mock_cross_encoder.predict.assert_not_called()

def test_fewer_than_k_candidates(mock_cross_encoder):
    mock_cross_encoder.predict.return_value = [0.8]
    reranker = BgeReranker()
    candidates = [{"text": "only match", "id": 1}]
    result = reranker.rerank("query", candidates, top_k=5)
    assert len(result) == 1
    assert result[0]["id"] == 1
    assert result[0]["_new_rank"] == 1

def test_missing_metadata(mock_cross_encoder):
    mock_cross_encoder.predict.return_value = [0.9]
    reranker = BgeReranker()
    # Missing text, should handle gracefully by substituting empty string
    candidates = [{"id": 1}]
    result = reranker.rerank("query", candidates, top_k=1)
    
    assert len(result) == 1
    assert result[0]["id"] == 1
    # predict should have been called with empty string
    mock_cross_encoder.predict.assert_called_once_with([["query", ""]])

def test_model_inference_failure(mock_cross_encoder):
    mock_cross_encoder.predict.side_effect = Exception("Inference failed")
    reranker = BgeReranker()
    candidates = [
        {"text": "doc1", "id": 1},
        {"text": "doc2", "id": 2},
    ]
    
    # Should fallback to original order
    result = reranker.rerank("query", candidates, top_k=2)
    assert len(result) == 2
    assert result[0]["id"] == 1
    assert result[1]["id"] == 2
    assert "_rerank_score" not in result[0]

def test_fallback_behavior_truncation(mock_cross_encoder):
    mock_cross_encoder.predict.side_effect = Exception("Inference failed")
    reranker = BgeReranker()
    candidates = [
        {"text": "doc1", "id": 1},
        {"text": "doc2", "id": 2},
        {"text": "doc3", "id": 3},
    ]
    
    # Should fallback and truncate to top_k
    result = reranker.rerank("query", candidates, top_k=2)
    assert len(result) == 2
    assert result[0]["id"] == 1
    assert result[1]["id"] == 2
    
def test_duplicate_similar_chunks(mock_cross_encoder):
    mock_cross_encoder.predict.return_value = [0.8, 0.8, 0.4]
    reranker = BgeReranker()
    candidates = [
        {"text": "duplicate", "id": 1},
        {"text": "duplicate", "id": 2},
        {"text": "other", "id": 3},
    ]
    result = reranker.rerank("query", candidates, top_k=3)
    assert len(result) == 3
    # Same score, python sort is stable, so original order for duplicates is preserved
    assert result[0]["id"] == 1
    assert result[1]["id"] == 2
    assert result[2]["id"] == 3
