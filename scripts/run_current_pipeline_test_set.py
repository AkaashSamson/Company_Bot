"""
Runner: Current Pipeline Test Set (with In-Between Edge Cases).

Executes and benchmarks Company_Bot's Current Pipeline against the dedicated
test set fixture `tests/fixtures/current_pipeline_test_set.json`.

Tests:
1. Exact Threshold Boundaries (Confidence, Evidence Distance, Lexical Overlap, Separation Gap)
2. Negative Filter Nuances & False Positive Guards (Affirmative sentences with negation particles)
3. RBAC Scoping Boundaries (Case-insensitivity, Multi-role lists, Admin override, Public entries)
4. Document Timestamp Freshness (Exact identity, Microsecond newer eviction, Stale past)
5. Architectural Seams & Failure Modes (Numeric contradictions, Negation inversions, Entity shifts)
"""

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

# Mock document project mapping service to ensure isolated testing without external DBs
import unittest.mock as mock
mock_doc_proj_svc = mock.MagicMock()
mock_doc_proj_svc.resolve_doc_and_project.side_effect = lambda doc_id: (doc_id, None)

try:
    import app.domain.services.document_project_service
    app.domain.services.document_project_service.get_document_project_service = lambda: mock_doc_proj_svc
except Exception:
    pass

from app.core.cache_quality import is_negative_response
from app.infrastructure.cache.quality_aware_cache import (
    InMemoryQualityAwareCache,
    CacheQualityValidator,
    CacheEntrySource,
    EvidenceQualityLevel,
    QualityGateDecision,
)

FIXTURE_PATH = WORKSPACE_ROOT / "tests" / "fixtures" / "current_pipeline_test_set.json"


class DummyEmbeddingModel:
    """Fast deterministic stub avoiding disk/network weights for unit testing."""
    def encode(self, texts, **kwargs):
        import numpy as np
        return np.ones((len(texts), 384), dtype=np.float32)


def run_current_pipeline_test_set():
    if not FIXTURE_PATH.exists():
        print(f"[ERROR] Test set fixture not found at {FIXTURE_PATH}")
        sys.exit(1)

    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        cases: List[Dict[str, Any]] = json.load(f)

    print("=" * 105)
    print("   COMPANY_BOT: CURRENT PIPELINE TEST SET BENCHMARK (WITH IN-BETWEEN EDGE CASES)")
    print(f"   Total Cases: {len(cases)} | Source Fixture: {FIXTURE_PATH.name}")
    print("=" * 105)

    validator = CacheQualityValidator(
        min_confidence_threshold=0.60,
        max_distance_threshold=0.85,
        min_lexical_grounding=0.20,
        min_separation_gap=0.10,
    )

    passed_count = 0
    failed_count = 0
    results = []

    for c in cases:
        cid = c["id"]
        cat = c["category"]
        edge_type = c["expected_output"].get("in_between_edge_type", "GENERAL")
        inp = c["input"]
        exp = c["expected_output"]

        # 1. Evaluate Write Gate
        val_res = validator.validate(
            query=inp["query"],
            response=inp["response"],
            confidence=inp.get("confidence", 0.0),
            evidence_count=inp.get("evidence_count", 0),
            evidence_distances=inp.get("evidence_distances"),
            lexical_grounding=inp.get("lexical_grounding"),
            separation_gap=inp.get("separation_gap"),
        )

        write_ok = (val_res.is_valid == exp["write_admitted"])
        if "gate_decision" in exp:
            write_ok = write_ok and (val_res.decision.value == exp["gate_decision"])

        # 2. Evaluate Retrieval Lifecycle if retrieval_context provided
        retrieval_ok = True
        actual_action = "N/A"
        if "retrieval_context" in c:
            ctx = c["retrieval_context"]
            ttl = 0.05 if ctx.get("simulate_expired") else 3600.0
            cache = InMemoryQualityAwareCache(
                max_entries=100,
                ttl_seconds=ttl,
                min_confidence_threshold=0.60,
                semantic_similarity_threshold=0.0,
                embedding_model=DummyEmbeddingModel(),
                enable_stats=False,
            )

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

            if ctx.get("simulate_expired"):
                time.sleep(0.08)

            entry = cache.get(
                cache_key=ctx["query"],
                role=ctx["user_roles"][0] if ctx.get("user_roles") else None,
                roles=ctx.get("user_roles"),
                project_ids=ctx.get("user_project_ids"),
                is_admin=ctx.get("is_admin", False),
                document_timestamps=ctx.get("current_document_timestamps"),
            )

            if entry is not None:
                actual_action = "HIT"
            elif ctx.get("simulate_expired"):
                actual_action = "EXPIRED"
            elif ctx.get("current_document_timestamps") and any(
                ctx["current_document_timestamps"].get(d, 0) > inp.get("doc_last_updated", {}).get(d, 0)
                for d in inp.get("document_ids", [])
            ):
                actual_action = "STALE_EVICTION"
            elif not put_ok:
                actual_action = "WRITE_REJECTED"
            else:
                actual_action = "RBAC_DENIED"

            retrieval_ok = (actual_action == exp.get("retrieval_action"))

        case_passed = write_ok and retrieval_ok
        if case_passed:
            passed_count += 1
        else:
            failed_count += 1

        results.append({
            "id": cid,
            "category": cat,
            "edge_type": edge_type,
            "exp_admit": exp["write_admitted"],
            "act_admit": val_res.is_valid,
            "exp_action": exp.get("retrieval_action", "N/A"),
            "act_action": actual_action,
            "passed": case_passed,
        })

    # Print Table
    header = f"{'Case ID':<30} | {'Category':<28} | {'Edge Type':<32} | {'Status'}"
    print(header)
    print("-" * 105)
    for r in results:
        status_str = "PASS [OK]" if r["passed"] else "FAIL [X]"
        print(f"{r['id']:<30} | {r['category'][:28]:<28} | {r['edge_type'][:32]:<32} | {status_str}")

    print("=" * 105)
    print(f"Total Cases: {len(cases)}  |  Passed: {passed_count}  |  Failed: {failed_count}  |  Accuracy: {(passed_count/len(cases))*100:.1f}%")
    print("=" * 105)


if __name__ == "__main__":
    run_current_pipeline_test_set()
