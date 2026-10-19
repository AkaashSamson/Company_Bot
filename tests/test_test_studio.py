"""
Test KnowLayer Test Studio Engine & Orchestrator
================================================
Verifies canonical schema, component execution, orchestrator pipelines,
assertion checks, and persistence.
"""

import pytest
from pathlib import Path
from sandbox.engine.schema import TestCase, RunConfig
from sandbox.engine.registry import COMPONENT_REGISTRY, get_registered_component
from sandbox.engine.orchestrator import RunOrchestrator
from sandbox.engine.persistence import save_suite_run, list_recent_runs, compare_two_runs
from app.core.settings import BASE_DIR


def test_component_registry():
    assert "retrieval" in COMPONENT_REGISTRY
    assert "reranking" in COMPONENT_REGISTRY
    assert "generation" in COMPONENT_REGISTRY
    assert "grounding" in COMPONENT_REGISTRY
    assert "policy_eval" in COMPONENT_REGISTRY

    ret_comp = get_registered_component("retrieval")
    assert ret_comp.supports_offline_strict is True
    assert "recall_at_k" in ret_comp.supported_assertions


def test_canonical_test_case_conversion():
    legacy_sample = {
        "id": "MGR-01",
        "category": "POLICY_PLAYBOOK",
        "question": "What is the process for approving an employee leave application in the portal?",
        "role": "MANAGER",
        "answerability": "DIRECT",
        "required_chunk_ids": ["TEST-001-3", "TEST-001-4"],
        "required_evidence_topics": ["Verify available leave balance", "Check departmental minimum staffing"],
        "prohibited_claims": ["Approve leave verbally without portal record"],
        "expect_rejection": False,
        "needle_text": "HRMS leave portal",
    }
    tc = TestCase.from_legacy_benchmark(legacy_sample)
    assert tc.id == "MGR-01"
    assert tc.input.role == "MANAGER"
    assert tc.answerability == "DIRECT"
    assert len(tc.expected_behavior.prohibited_claims) == 1
    assert len(tc.assertions) >= 3


def test_orchestrator_execution_and_persistence():
    legacy_sample = {
        "id": "UNIT-TEST-01",
        "category": "FACTOID_POLICY",
        "question": "What is the standard probation period for new employees?",
        "required_chunk_ids": [],
        "prohibited_claims": ["Probation can be extended indefinitely"],
        "needle_text": "probation",
    }
    tc = TestCase.from_legacy_benchmark(legacy_sample)

    config = RunConfig(
        suite_id="test_suite",
        execution_mode="offline_strict",
        components=["generation", "policy_eval"],
        llm_provider="local_heuristic",
    )
    orchestrator = RunOrchestrator(config)
    result = orchestrator.run_suite([tc])

    assert result.total_tests == 1
    assert result.passed == 1
    assert result.pass_rate == 100.0

    # Test persistence
    run_id = save_suite_run(result)
    assert run_id == config.run_id

    recent = list_recent_runs(limit=5)
    assert len(recent) >= 1
    assert any(r["run_id"] == run_id for r in recent)
