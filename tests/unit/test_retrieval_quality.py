"""
Comprehensive Unit Tests for Multi-Dimensional Retrieval Quality Gate (Task AB-5.1)

Validates:
- EvidenceQualityLevel classifications (STRONG, BORDERLINE, WEAK, INVALID)
- C.R.E.A.T.E. distance boundary thresholds (<0.60, 0.60-0.70, 0.70-0.85, >=0.85)
- Separation gap calculation and k < 2 guard safety
- Lexical grounding token overlap with stop-word filtering
- Adaptive confidence scoring (0.0 to 1.0)
- Hard gate early exit on invalid evidence
- Alias methods (evaluate vs assess) and property accessors
"""

import pytest
from app.use_cases.chat.retrieval_quality import (
    EvidenceQualityLevel,
    QualityGateResult,
    QualityScore,
    RetrievalQualityGate,
    RetrievalQualityResult,
    get_retrieval_quality_gate,
)


class TestEvidenceQualityLevel:
    """Tests for EvidenceQualityLevel classification and boundaries."""

    def test_enum_values(self):
        """Verify enum string values match expected contracts."""
        assert EvidenceQualityLevel.STRONG.value == "strong"
        assert EvidenceQualityLevel.BORDERLINE.value == "borderline"
        assert EvidenceQualityLevel.WEAK.value == "weak"
        assert EvidenceQualityLevel.INVALID.value == "invalid"

    @pytest.mark.parametrize(
        "distance,expected_level",
        [
            (0.00, EvidenceQualityLevel.STRONG),
            (0.35, EvidenceQualityLevel.STRONG),
            (0.59, EvidenceQualityLevel.STRONG),
            (0.60, EvidenceQualityLevel.BORDERLINE),
            (0.65, EvidenceQualityLevel.BORDERLINE),
            (0.699, EvidenceQualityLevel.BORDERLINE),
            (0.70, EvidenceQualityLevel.WEAK),
            (0.78, EvidenceQualityLevel.WEAK),
            (0.849, EvidenceQualityLevel.WEAK),
            (0.85, EvidenceQualityLevel.INVALID),
            (0.92, EvidenceQualityLevel.INVALID),
            (1.20, EvidenceQualityLevel.INVALID),
        ],
    )
    def test_classify_distance_boundaries(self, distance, expected_level):
        """Verify C.R.E.A.T.E. distance threshold classifications."""
        assert RetrievalQualityGate.classify_distance(distance) == expected_level


class TestRetrievalQualityGate:
    """Test suite for multi-dimensional quality assessment."""

    @pytest.fixture
    def gate(self):
        """Create standard quality gate instance."""
        return RetrievalQualityGate(
            strong_distance_threshold=0.60,
            borderline_distance_threshold=0.70,
            invalid_distance_threshold=0.85,
            min_separation_gap=0.10,
            min_grounding_score=0.20,
            min_evidence_count=1,
            min_quality_score=0.40,
        )

    def test_empty_evidence_early_exit(self, gate):
        """Empty evidence list triggers immediate early exit with INVALID level."""
        result = gate.assess("how many leaves do i have", [])

        assert result.passed is False
        assert result.early_exit is True
        assert result.quality_level == EvidenceQualityLevel.INVALID
        assert result.confidence == 0.0
        assert "No evidence" in (result.exit_reason or "")
        assert len(result.evidence) == 0

    def test_single_evidence_k_less_than_two_guard(self, gate):
        """Single evidence chunk (k=1) must not throw IndexError and separation gap is 0.0."""
        evidence = [
            {
                "text": "Employees receive 18 days of annual leave per year.",
                "distance": 0.42,
            }
        ]
        result = gate.assess("annual leave days", evidence)

        # Must execute cleanly without IndexError
        assert result.quality_score.separation_gap == 0.0
        assert result.quality_score.evidence_count == 1
        assert result.quality_level == EvidenceQualityLevel.STRONG
        assert result.passed is True
        assert result.early_exit is False

    def test_strong_evidence_passes(self, gate):
        """Evidence with low distance and high lexical overlap is rated STRONG."""
        evidence = [
            {
                "text": "McLaren Strategic Solutions provides health insurance and medical benefits to staff.",
                "distance": 0.38,
            },
            {
                "text": "General benefits overview and insurance claims process.",
                "distance": 0.55,
            },
        ]
        result = gate.assess("medical insurance benefits", evidence)

        assert result.passed is True
        assert result.early_exit is False
        assert result.quality_level == EvidenceQualityLevel.STRONG
        assert result.confidence >= 0.65
        assert result.quality_score.distance_score >= 0.70
        assert result.quality_score.grounding_score > 0.40
        assert result.quality_score.separation_gap > 0.0

    def test_borderline_evidence(self, gate):
        """Evidence in 0.60 to 0.70 range is classified as BORDERLINE."""
        evidence = [
            {
                "text": "Company travel expenses and client meeting reimbursements.",
                "distance": 0.64,
            },
            {
                "text": "Expense report submission guidelines for managers.",
                "distance": 0.72,
            },
        ]
        result = gate.assess("client travel expense reimbursement", evidence)

        assert result.quality_level == EvidenceQualityLevel.BORDERLINE
        assert result.passed is True
        assert result.early_exit is False
        assert 0.40 <= result.confidence <= 0.75

    def test_weak_evidence_passes_without_early_exit(self, gate):
        """Evidence in 0.70 to 0.85 range is WEAK but does not trigger early exit."""
        evidence = [
            {
                "text": "General corporate operations and office guidelines.",
                "distance": 0.76,
            }
        ]
        result = gate.assess("cafeteria lunch timings", evidence)

        assert result.quality_level == EvidenceQualityLevel.WEAK
        assert result.early_exit is False

    def test_hard_gate_invalid_distance_triggers_early_exit(self, gate):
        """Top distance >= 0.85 must trigger hard gate INVALID and early_exit=True."""
        evidence = [
            {
                "text": "Completely unrelated text about building maintenance.",
                "distance": 0.89,
            },
            {
                "text": "Parking space allocations.",
                "distance": 0.95,
            },
        ]
        result = gate.assess("annual bonus payout structure", evidence)

        assert result.quality_level == EvidenceQualityLevel.INVALID
        assert result.passed is False
        assert result.early_exit is True
        assert result.quality_score.distance_score == 0.0
        assert "exceeds invalid threshold" in (result.exit_reason or "")

    def test_separation_gap_normalization(self, gate):
        """Separation gap between candidates scales with min_separation_gap."""
        # Top 1 distance = 0.40, Top 2 distance = 0.55 -> gap = 0.15 (exceeds min_separation_gap 0.10)
        evidence_large_gap = [
            {"text": "Leave policy handbook.", "distance": 0.40},
            {"text": "Remote work guidelines.", "distance": 0.55},
        ]
        result_large = gate.assess("leave policy", evidence_large_gap)
        assert result_large.quality_score.separation_gap == 1.0

        # Top 1 distance = 0.40, Top 2 distance = 0.45 -> gap = 0.05 (half of 0.10)
        evidence_small_gap = [
            {"text": "Leave policy handbook.", "distance": 0.40},
            {"text": "Leave request portal.", "distance": 0.45},
        ]
        result_small = gate.assess("leave policy", evidence_small_gap)
        assert 0.45 <= result_small.quality_score.separation_gap <= 0.55

    def test_lexical_grounding_stop_word_filtering(self, gate):
        """Grounding score correctly removes stop words and matches alphanumeric tokens."""
        # Query: "how to apply for casual leaves" -> query terms: {"apply", "casual", "leaves"}
        evidence = [
            {
                "text": "To apply for casual leaves, submit a request via the HR portal.",
                "distance": 0.45,
            }
        ]
        result = gate.assess("how to apply for casual leaves", evidence)
        # All 3 terms (apply, casual, leaves) are in evidence text -> 100% overlap
        assert result.quality_score.grounding_score >= 0.90

    def test_alias_evaluate_matches_assess(self, gate):
        """Method alias gate.evaluate() returns identical output to gate.assess()."""
        evidence = [{"text": "Company guidelines.", "distance": 0.50}]
        res_assess = gate.assess("guidelines", evidence)
        res_evaluate = gate.evaluate("guidelines", evidence)

        assert res_assess.quality_level == res_evaluate.quality_level
        assert res_assess.confidence == res_evaluate.confidence
        assert res_assess.passed == res_evaluate.passed

    def test_should_early_exit_helper(self, gate):
        """should_early_exit returns tuple of (bool, reason)."""
        bad_evidence = [{"text": "Noise", "distance": 0.92}]
        should_exit, reason = gate.should_early_exit("quantum physics", bad_evidence)
        assert should_exit is True
        assert reason is not None

        good_evidence = [{"text": "Company dress code policy.", "distance": 0.45}]
        should_exit_good, reason_good = gate.should_early_exit("dress code", good_evidence)
        assert should_exit_good is False
        assert reason_good is None

    def test_serialization_to_dict(self, gate):
        """to_dict returns structured JSON-compatible dictionaries."""
        evidence = [{"text": "Holiday schedule for 2026.", "distance": 0.48}]
        result = gate.assess("holiday schedule", evidence)

        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)
        assert "quality_level" in result_dict
        assert "confidence" in result_dict
        assert "early_exit" in result_dict
        assert "quality_score" in result_dict
        assert isinstance(result_dict["quality_score"], dict)

    def test_missing_distances_handled_neutrally(self, gate):
        """Evidence without distance keys falls back to neutral distance score."""
        evidence = [{"text": "Document without distance field."}]
        result = gate.assess("document text", evidence)

        # Should not raise KeyError or TypeError
        assert result.quality_score.distance_score == 0.50

    def test_singleton_accessor(self):
        """get_retrieval_quality_gate returns a valid initialized instance."""
        inst1 = get_retrieval_quality_gate()
        inst2 = get_retrieval_quality_gate()
        assert inst1 is inst2
        assert isinstance(inst1, RetrievalQualityGate)
