"""
Integration Test Suite: Current Pipeline vs. Golden Benchmark Dataset.

Evaluates Company_Bot's current C.R.E.A.T.E. + InMemoryQualityAwareCache pipeline
against the official 15-case Golden Dataset extracted from enterprise policy documents.

Quantifies the critical vulnerabilities that prompted ADR v2:
1. 80.0% Fatal False Reuse Rate (Leaks outdated numbers, flipped negations, revoked RBAC, entity mismatches)
2. 0.0% Contradiction Recall (Lexical token overlap passes contradictory claims)
3. 6.7% False Cache Miss Rate (Coarse whole-document timestamp invalidates unchanged chunks)
4. Only 13.3% Decision Accuracy on the golden benchmark.
"""

import json
from pathlib import Path
from typing import Any, Dict, List
import pytest

from scripts.run_golden_benchmark import (
    CurrentPipelineSimulator,
    HybridPipelineSimulator,
    GOLDEN_DATASET_PATH,
)
from app.core.cache_quality import is_negative_response
from app.infrastructure.cache.quality_aware_cache import (
    InMemoryQualityAwareCache,
    CacheQualityValidator,
    CacheEntrySource,
)


def load_golden_cases() -> List[Dict[str, Any]]:
    if not GOLDEN_DATASET_PATH.exists():
        pytest.skip(f"Golden dataset fixture not found at {GOLDEN_DATASET_PATH}")
    with open(GOLDEN_DATASET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def current_pipeline():
    return CurrentPipelineSimulator()


@pytest.fixture
def hybrid_pipeline():
    return HybridPipelineSimulator(use_real_nli=False)


# ============================================================================
# 1. PARAMETERIZED TEST ACROSS ALL 15 GOLDEN CASES
# ============================================================================

class TestCurrentPipelineGoldenDataset:
    """Tests the Current Pipeline Simulator against each case in the Golden Dataset."""

    @pytest.mark.parametrize("case", load_golden_cases(), ids=lambda c: c["id"])
    def test_current_pipeline_matches_expected_behavior(self, current_pipeline, case):
        """
        Verify that the Current Pipeline Simulator accurately reproduces the documented
        expected behavior (action, correctness, and failure type) for each golden case.
        """
        eval_result = current_pipeline.evaluate(case)
        expected_curr = case["current_pipeline_expected"]

        # Assert action matches what the current architecture produces
        assert eval_result["action"] == expected_curr["action"], (
            f"Case {case['id']}: expected current pipeline action {expected_curr['action']}, "
            f"got {eval_result['action']} (reason: {eval_result['reason']})"
        )

        # Verify whether the current pipeline succeeds or fails as documented
        ground_truth = case["ground_truth_decision"]
        is_actually_correct = (eval_result["action"] == ground_truth)
        assert is_actually_correct == expected_curr["is_correct"], (
            f"Case {case['id']}: correctness mismatch. Expected is_correct={expected_curr['is_correct']}, "
            f"but evaluation gave {is_actually_correct}"
        )


# ============================================================================
# 2. VULNERABILITY CATEGORY AUDITS (PROVING WHERE CURRENT PIPELINE FAILS)
# ============================================================================

class TestCurrentPipelineVulnerabilities:
    """Verifies specific vulnerability categories in the current caching pipeline."""

    def test_numeric_contradiction_blindness(self, current_pipeline):
        """Current pipeline suffers from fatal false reuse on numeric updates."""
        cases = [c for c in load_golden_cases() if c["category"] == "NUMERIC_CONTRADICTION"]
        assert len(cases) == 4

        for case in cases:
            res = current_pipeline.evaluate(case)
            # Ground truth is REJECT_FALLBACK_RAG, but current pipeline permits REUSE
            assert res["action"] == "REUSE", f"{case['id']} should leak under current pipeline"
            assert case["current_pipeline_expected"]["failure_type"] == "FATAL_FALSE_REUSE"

    def test_negation_inversion_blindness(self, current_pipeline):
        """Current pipeline suffers from fatal false reuse on flipped negations."""
        cases = [c for c in load_golden_cases() if c["category"] == "NEGATION_INVERSION"]
        assert len(cases) == 4

        for case in cases:
            res = current_pipeline.evaluate(case)
            # Polar opposite meaning passed due to high word overlap
            assert res["action"] == "REUSE", f"{case['id']} should leak under current pipeline"
            assert case["current_pipeline_expected"]["failure_type"] == "FATAL_FALSE_REUSE"

    def test_query_answer_entity_mismatch_blindness(self, current_pipeline):
        """Current pipeline has no query <-> answer compatibility check."""
        cases = [c for c in load_golden_cases() if c["category"] == "QUERY_ANSWER_MISMATCH"]
        assert len(cases) == 2

        for case in cases:
            res = current_pipeline.evaluate(case)
            assert res["action"] == "REUSE", f"{case['id']} leaks mismatched entity"
            assert case["current_pipeline_expected"]["failure_type"] == "QUERY_ANSWER_SEMANTIC_GAP"

    def test_coarse_document_timestamp_causes_false_miss(self, current_pipeline):
        """Whole-document timestamp invalidates unchanged chunk (false cache miss)."""
        case = next(c for c in load_golden_cases() if c["category"] == "STALE_CHUNK_PARTIAL_UPDATE")
        res = current_pipeline.evaluate(case)

        # Ground truth is REUSE (chunk is unchanged), but coarse invalidation rejects
        assert res["action"] == "REJECT_FALLBACK_RAG"
        assert res["gate_tripped"] == "DOCUMENT_TIMESTAMP_POLL"
        assert case["ground_truth_decision"] == "REUSE"
        assert case["current_pipeline_expected"]["failure_type"] == "FALSE_CACHE_MISS"

    def test_successful_current_pipeline_gates(self, current_pipeline):
        """Current pipeline correctly handles negative responses and legitimate paraphrases."""
        # 1. Negative response filter works
        neg_case = next(c for c in load_golden_cases() if c["category"] == "NEGATIVE_RESPONSE_FILTER")
        neg_res = current_pipeline.evaluate(neg_case)
        assert neg_res["action"] == "REJECT_FALLBACK_RAG"
        assert neg_res["gate_tripped"] == "NEGATIVE_FILTER"

        # 2. Legitimate paraphrase works
        para_case = next(c for c in load_golden_cases() if c["category"] == "LEGITIMATE_PARAPHRASE_REUSE")
        para_res = current_pipeline.evaluate(para_case)
        assert para_res["action"] == "REUSE"
        assert para_res["gate_tripped"] is None


# ============================================================================
# 3. DIRECT IN-MEMORY QUALITY-AWARE CACHE COMPONENT TESTS
# ============================================================================

class TestDirectInMemoryQualityAwareCacheBehavior:
    """Directly verifies CacheQualityValidator and InMemoryQualityAwareCache on the golden dataset."""

    def test_negative_response_filtered_at_write_time(self):
        """is_negative_response filter blocks refusal answers from being cached."""
        neg_case = next(c for c in load_golden_cases() if c["category"] == "NEGATIVE_RESPONSE_FILTER")
        validator = CacheQualityValidator()
        result = validator.validate(
            query=neg_case["cached_query"],
            response=neg_case["cached_answer"],
            confidence=0.90,
            evidence_count=0,
        )
        assert not result.is_valid
        assert "Negative/unverified" in result.reason

    def test_numeric_contradiction_passes_current_quality_validator(self):
        """C.R.E.A.T.E. validator accepts the outdated answer because it has high confidence."""
        num_case = next(c for c in load_golden_cases() if c["id"] == "GOLDEN-DOCX-NUM-01")
        validator = CacheQualityValidator()
        result = validator.validate(
            query=num_case["cached_query"],
            response=num_case["cached_answer"],
            confidence=0.90,
            evidence_count=1,
            evidence_distances=[0.35],
            lexical_grounding=0.86,
        )
        # Demonstrates that current C.R.E.A.T.E. validator passes because it lacks NLI
        assert result.is_valid is True
        assert result.decision.value == "PASS"


# ============================================================================
# 4. BENCHMARK METRICS SUMMARY ASSERTIONS
# ============================================================================

class TestGoldenBenchmarkSummaryMetrics:
    """Validates the aggregate safety metrics of Current vs Hybrid pipeline."""

    def test_current_pipeline_metrics(self, current_pipeline):
        cases = load_golden_cases()
        total = len(cases)
        correct = 0
        false_reuse = 0
        false_reject = 0

        for c in cases:
            gt = c["ground_truth_decision"]
            res = current_pipeline.evaluate(c)
            if res["action"] == gt:
                correct += 1
            elif res["action"] == "REUSE" and gt != "REUSE":
                false_reuse += 1
            elif res["action"] != "REUSE" and gt == "REUSE":
                false_reject += 1

        accuracy = correct / total
        fatal_false_reuse_rate = false_reuse / total
        false_reject_rate = false_reject / total

        # Empirical metrics proving current pipeline performance
        assert accuracy == pytest.approx(2 / 15, abs=0.01)  # 13.3%
        assert fatal_false_reuse_rate == pytest.approx(12 / 15, abs=0.01)  # 80.0%
        assert false_reject_rate == pytest.approx(1 / 15, abs=0.01)  # 6.7%
