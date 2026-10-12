"""
Test Suite: Current Pipeline Test Set with In-Between Edge Cases.

Executes tests against the dedicated fixture:
`tests/fixtures/current_pipeline_test_set.json`

Validates:
1. Threshold In-Between Boundaries (Confidence, Evidence Distances, Lexical Grounding, Separation Gap).
2. Content Boundaries (Empty string, Whitespace).
3. Negative Filter In-Between Nuances (Affirmative false positive guard vs subtle refusal).
4. RBAC In-Between Semantics (Case-insensitivity, Multi-role match, Role mismatch, Admin bypass, Public bypass).
5. Freshness In-Between Timestamps (Exact identity, Slight newer eviction, Past timestamp).
6. Architectural Seams (Numeric contradiction leak, Negation leak, Entity leak, Coarse file timestamp miss).
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List
import pytest

from app.core.cache_quality import is_negative_response
from app.infrastructure.cache.quality_aware_cache import (
    InMemoryQualityAwareCache,
    CacheQualityValidator,
    CacheEntrySource,
    EvidenceQualityLevel,
    QualityGateDecision,
)

class DummyEmbeddingModel:
    def encode(self, texts, **kwargs):
        import numpy as np
        return np.ones((len(texts), 384), dtype=np.float32)


FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "current_pipeline_test_set.json"


def load_test_cases() -> List[Dict[str, Any]]:
    assert FIXTURE_PATH.exists(), f"Test set fixture not found at {FIXTURE_PATH}"
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(autouse=True)
def mock_document_project_service(monkeypatch):
    """Ensure in-memory cache operations run isolated from external databases."""
    monkeypatch.setattr(
        "app.domain.services.document_project_service.get_document_project_service",
        lambda: None,
    )


# ============================================================================
# 1. PARAMETERIZED EXECUTION OF ALL CASES IN THE CURRENT PIPELINE TEST SET
# ============================================================================

class TestCurrentPipelineTestSet:
    """Parametrized execution across all in-between edge cases in current_pipeline_test_set.json."""

    @pytest.mark.parametrize("case", load_test_cases(), ids=lambda c: c["id"])
    def test_case_write_gate_evaluation(self, case):
        inp = case["input"]
        exp = case["expected_output"]

        validator = CacheQualityValidator(
            min_confidence_threshold=0.60,
            max_distance_threshold=0.85,
            min_lexical_grounding=0.20,
            min_separation_gap=0.10,
        )

        res = validator.validate(
            query=inp["query"],
            response=inp["response"],
            confidence=inp.get("confidence", 0.0),
            evidence_count=inp.get("evidence_count", 0),
            evidence_distances=inp.get("evidence_distances"),
            lexical_grounding=inp.get("lexical_grounding"),
            separation_gap=inp.get("separation_gap"),
        )

        # Assert write admission decision
        assert res.is_valid == exp["write_admitted"], (
            f"Case {case['id']}: expected is_valid={exp['write_admitted']}, got {res.is_valid} ({res.reason})"
        )

        # Assert decision enum value if specified
        if "gate_decision" in exp:
            assert res.decision.value == exp["gate_decision"], (
                f"Case {case['id']}: expected decision {exp['gate_decision']}, got {res.decision.value}"
            )

        # Assert specific reason substring if expected
        if "rejection_reason_contains" in exp:
            assert exp["rejection_reason_contains"].lower() in res.reason.lower(), (
                f"Case {case['id']}: expected reason to contain '{exp['rejection_reason_contains']}', got '{res.reason}'"
            )

        # Assert distance quality classification if expected
        if "classified_quality_level" in exp:
            best_dist = min(inp["evidence_distances"])
            lvl = validator.classify_distance(best_dist)
            assert lvl.value == exp["classified_quality_level"], (
                f"Case {case['id']}: expected quality level '{exp['classified_quality_level']}', got '{lvl.value}'"
            )

        # Assert separation gap warning if expected
        if "separation_gap_warning" in exp:
            assert res.metrics.get("separation_gap_warning", False) == exp["separation_gap_warning"]

    @pytest.mark.parametrize("case", [c for c in load_test_cases() if "retrieval_context" in c], ids=lambda c: c["id"])
    def test_case_cache_retrieval_lifecycle(self, case):
        inp = case["input"]
        ctx = case["retrieval_context"]
        exp = case["expected_output"]

        ttl = 0.05 if ctx.get("simulate_expired") else 3600.0
        cache = InMemoryQualityAwareCache(
            max_entries=100,
            ttl_seconds=ttl,
            min_confidence_threshold=0.60,
            semantic_similarity_threshold=0.0,
            embedding_model=DummyEmbeddingModel(),
            enable_stats=False,
        )

        # Put entry
        put_ok = cache.put(
            cache_key=inp["query"],
            original_query=inp["query"],
            response=inp["response"],
            confidence=inp.get("confidence", 0.90),
            evidence_count=inp.get("evidence_count", 1),
            assigned_role=inp.get("assigned_role"),
            document_ids=inp.get("document_ids"),
            project_ids=inp.get("project_ids"),
            is_public=inp.get("is_public", False),
            doc_last_updated=inp.get("doc_last_updated"),
        )

        assert put_ok == exp["write_admitted"], f"Case {case['id']}: write admission mismatch"

        if not put_ok:
            return  # Rejected at write gate, no retrieval test

        if ctx.get("simulate_expired"):
            # Sub-second sleep past TTL
            time.sleep(0.08)

        # Get entry
        entry = cache.get(
            cache_key=ctx["query"],
            role=ctx["user_roles"][0] if ctx.get("user_roles") else None,
            roles=ctx.get("user_roles"),
            project_ids=ctx.get("user_project_ids"),
            is_admin=ctx.get("is_admin", False),
            document_timestamps=ctx.get("current_document_timestamps"),
        )

        action = exp["retrieval_action"]
        if action == "HIT":
            assert entry is not None, f"Case {case['id']}: expected HIT, got None"
            assert entry.response == inp["response"]
        elif action in ("RBAC_DENIED", "STALE_EVICTION", "EXPIRED"):
            assert entry is None, f"Case {case['id']}: expected {action} (None), but got an entry"
