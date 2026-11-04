"""
Unit Tests for Task AB-5.2: Retrieval Quality Gate Integration in RetrievalService

Validates:
- RetrievalQualityGate.evaluate() contract
- Attaching quality metrics (quality_level, grounding_score, confidence) to candidate evidence
- Reranker hook execution and fallback handling
"""

import pytest
from unittest.mock import MagicMock

from app.use_cases.chat.retrieval_service import RetrievalService
from app.use_cases.chat.retrieval_quality import (
    RetrievalQualityGate,
    QualityGateResult,
    EvidenceQualityLevel,
)


class TestRetrievalQualityGateIntegration:
    """Test suite for Task AB-5.2 Quality Gate Integration."""

    def test_evaluate_alias_method(self):
        gate = RetrievalQualityGate()
        evidence = [
            {"text": "Employees get 18 days of annual leave.", "distance": 0.35},
            {"text": "Sick leave requires medical certificate after 2 days.", "distance": 0.55},
        ]
        result = gate.evaluate("How many days of annual leave?", evidence)
        assert isinstance(result, QualityGateResult)
        assert result.quality_level == EvidenceQualityLevel.STRONG
        assert result.confidence > 0.70
        assert result.passed is True

    def test_retrieve_attaches_quality_metrics_to_chunks(self):
        # Create service with mock store
        service = RetrievalService.__new__(RetrievalService)
        service.store = MagicMock()
        service.store.query.return_value = [
            {"text": "Annual leave policy allows 18 days.", "distance": 0.30, "metadata": {"source": "leave.pdf"}},
            {"text": "Probation period is 6 months.", "distance": 0.75, "metadata": {"source": "probation.pdf"}},
        ]
        service.quality_gate = RetrievalQualityGate()
        service.reranker = None
        service.last_quality_result = None

        chunks = service.retrieve("How much annual leave do I get?", top_k=5, max_evidence=2)

        assert len(chunks) > 0
        for chunk in chunks:
            # Task AB-5.2 requirement: attach level, grounding_score, confidence
            assert "quality_level" in chunk
            assert "grounding_score" in chunk
            assert "confidence" in chunk
            assert isinstance(chunk["confidence"], float)
            assert chunk["quality_level"] in {"strong", "borderline", "weak", "invalid"}

        assert service.last_quality_result is not None
        assert service.last_quality_result.confidence > 0.0

    def test_reranker_hook_and_quality_gate_pipeline(self):
        # Test that if Neha's reranker is provided, RetrievalService calls it then evaluates quality
        mock_reranker = MagicMock()
        mock_reranked_chunks = [
            {"text": "Reranked chunk 1: 18 days annual leave", "distance": 0.25, "rerank_score": 0.98},
            {"text": "Reranked chunk 2: Leave approval process", "distance": 0.40, "rerank_score": 0.85},
        ]
        mock_reranker.rerank.return_value = mock_reranked_chunks

        service = RetrievalService.__new__(RetrievalService)
        service.store = MagicMock()
        service.store.query.return_value = [
            {"text": "Candidate 1", "distance": 0.60},
            {"text": "Candidate 2", "distance": 0.65},
        ]
        service.quality_gate = RetrievalQualityGate()
        service.reranker = mock_reranker
        service.last_quality_result = None

        chunks = service.retrieve("annual leave allowance", top_k=2, max_evidence=2)

        mock_reranker.rerank.assert_called_once()
        assert chunks == mock_reranked_chunks

        # Quality metrics must be attached to the reranked chunks
        assert chunks[0]["quality_level"] == "strong"
        assert chunks[0]["confidence"] > 0.7
        assert "grounding_score" in chunks[0]
