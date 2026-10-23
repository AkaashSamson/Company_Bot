"""
KnowLayer Test Studio — Canonical Schema
========================================
Defines the standard data structures for test cases, assertions, run configurations,
execution traces, and unified test results across all RAG evaluation stages.
"""

from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 1. Canonical Test Case Schema
# ---------------------------------------------------------------------------

class TestInput(BaseModel):
    question: str
    role: str = "ALL"  # "ALL", "EMPLOYEE", "MANAGER", "HR"
    project_ids: Optional[List[str]] = None
    tenant_id: Optional[str] = None
    resource_scope: Optional[str] = None
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    files: List[str] = Field(default_factory=list)


# Backward compatibility alias
InputSpec = TestInput


class ExpectedBehavior(BaseModel):
    answer: Optional[str] = None
    required_claims: List[str] = Field(default_factory=list)
    prohibited_claims: List[str] = Field(default_factory=list)
    citation_required: bool = True
    should_refuse: bool = False  # True for unanswerable / out-of-domain questions
    refusal_phrase: Optional[str] = None
    language_expected: Optional[str] = None  # e.g. "en", "es", "match_input"
    script_expected: Optional[str] = None    # e.g. "Latin", "Romaji", "Japanese"


class GoldEvidence(BaseModel):
    document: Optional[str] = None
    sections: List[str] = Field(default_factory=list)
    required_chunk_ids: List[str] = Field(default_factory=list)
    forbidden_evidence_ids: List[str] = Field(default_factory=list)
    needle_text: Optional[str] = None
    evidence_mode: Literal["any", "all"] = "any"  # "any" = at least 1, "all" = all required chunks


class AssertionSpec(BaseModel):
    component: str  # "retrieval", "reranking", "generation", "grounding", "policy_eval"
    type: str  # e.g. "recall_at_k", "needle_present", "no_prohibited_claims", "refusal_conformance"
    operator: str = "gte"  # "gte", "lte", "eq", "contains", "not_contains", "is_true"
    threshold: Optional[float] = None
    expected_value: Optional[Any] = None
    severity: Literal["BLOCKER", "WARNING", "Critical", "High", "Medium", "Low"] = "BLOCKER"


class TestCase(BaseModel):
    __test__ = False  # Inform pytest this is a data model, not a test suite class
    id: str
    title: str
    category: str = "FACTOID_POLICY"
    tags: List[str] = Field(default_factory=list)
    input: TestInput
    answerability: Literal[
        "DIRECT",
        "SYNTHESIZABLE",
        "INSUFFICIENT",
        "CONFLICTING",
        "OUT_OF_SCOPE",
        "UNAUTHORIZED",
    ] = "DIRECT"
    expected_behavior: ExpectedBehavior = Field(default_factory=ExpectedBehavior)
    gold_evidence: GoldEvidence = Field(default_factory=GoldEvidence)
    forbidden_evidence_ids: List[str] = Field(default_factory=list)
    expected_citations: List[str] = Field(default_factory=list)
    severity: Literal["Critical", "High", "Medium", "Low"] = "Medium"
    automation_level: Literal["Deterministic", "LLM-assisted", "Human-only", "Hybrid"] = "Deterministic"
    owner: str = "Unassigned"
    review_status: Literal["Draft", "Reviewed", "Approved", "Retired"] = "Draft"
    dataset_version: str = "v1.0.0"
    components: List[str] = Field(
        default_factory=lambda: ["retrieval", "reranking", "generation", "grounding", "policy_eval"]
    )
    assertions: List[AssertionSpec] = Field(default_factory=list)
    thresholds: Dict[str, float] = Field(default_factory=dict)
    provenance: Optional[Dict[str, Any]] = None

    @classmethod
    def from_legacy_benchmark(cls, item: Dict[str, Any]) -> "TestCase":
        """Converts legacy items from rag_benchmark_questions.json into canonical TestCase."""
        q_text = item.get("question", "")
        test_id = item.get("id", f"TEST-{uuid.uuid4().hex[:6]}")
        notes = item.get("notes", item.get("scenario_description", q_text))
        category = item.get("category", "FACTOID_POLICY")
        tags = item.get("tags", [category])

        if "expect_rejection" in item:
            should_refuse = bool(item["expect_rejection"])
        elif "expect_abstention" in item:
            should_refuse = bool(item["expect_abstention"])
        else:
            should_refuse = (
                category in ("NEGATIVE_HALLUCINATION_GUARD", "OUT_OF_DOMAIN", "NEGATIVE_UNSUPPORTED")
                or item.get("answerability") in ("INSUFFICIENT", "OUT_OF_SCOPE")
            )

        ans_label = item.get("answerability")
        if not ans_label:
            if should_refuse:
                ans_label = "INSUFFICIENT"
            elif item.get("test_type") == "SYNTHESIS":
                ans_label = "SYNTHESIZABLE"
            else:
                ans_label = "DIRECT"

        req_chunks = item.get("required_chunk_ids", [])
        if isinstance(req_chunks, str):
            req_chunks = [c.strip() for c in req_chunks.split(",") if c.strip()]

        expected_doc = item.get("expected_document")
        req_topics = item.get("required_evidence_topics", [])
        prohibited = item.get("prohibited_claims", [])

        # Default role
        role = item.get("role", "ALL")
        if "MGR-" in test_id or "Manager" in notes or "Manager" in category:
            role = "MANAGER"

        # Assertions
        assertions: List[AssertionSpec] = []
        if req_chunks:
            assertions.append(AssertionSpec(
                component="retrieval",
                type="recall_at_k",
                operator="gte",
                threshold=1.0 if item.get("evidence_mode", "any") == "all" else 0.5,
                severity="BLOCKER"
            ))
            assertions.append(AssertionSpec(
                component="reranking",
                type="needle_present",
                operator="is_true",
                severity="BLOCKER"
            ))

        if prohibited:
            assertions.append(AssertionSpec(
                component="policy_eval",
                type="no_prohibited_claims",
                operator="is_true",
                severity="BLOCKER"
            ))

        if req_topics and not should_refuse:
            assertions.append(AssertionSpec(
                component="policy_eval",
                type="evidence_coverage",
                operator="gte",
                threshold=0.6,
                severity="WARNING"
            ))

        if should_refuse:
            assertions.append(AssertionSpec(
                component="policy_eval",
                type="refusal_conformance",
                operator="is_true",
                severity="BLOCKER"
            ))

        return cls(
            id=test_id,
            title=notes[:80] if notes else q_text[:80],
            category=category,
            tags=tags,
            input=TestInput(
                question=q_text,
                role=role,
                project_ids=item.get("project_ids"),
            ),
            answerability=ans_label,
            expected_behavior=ExpectedBehavior(
                answer=item.get("golden_answer") or item.get("expected_guidance"),
                required_claims=req_topics,
                prohibited_claims=prohibited,
                should_refuse=should_refuse,
            ),
            gold_evidence=GoldEvidence(
                document=expected_doc,
                required_chunk_ids=req_chunks,
                needle_text=item.get("needle_text"),
                evidence_mode=item.get("evidence_mode", "any"),
            ),
            assertions=assertions,
            provenance={"source": "rag_benchmark_questions.json"}
        )


# ---------------------------------------------------------------------------
# 2. Run Configuration
# ---------------------------------------------------------------------------

class RunConfig(BaseModel):
    run_id: str = Field(default_factory=lambda: f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}")
    suite_id: str = "rag_benchmark_questions"
    execution_mode: Literal["offline_strict", "local_models", "remote_provider_allowed"] = "local_models"
    components: List[str] = Field(
        default_factory=lambda: ["retrieval", "reranking", "generation", "grounding", "policy_eval"]
    )
    retrieval_k: int = 13
    reranker_top_k: int = 4
    reranker_model: str = "BAAI/bge-reranker-base"
    llm_provider: str = "local_heuristic"  # "local_heuristic", "openrouter", "ollama"
    llm_model: str = "openrouter/anthropic/claude-3.5-sonnet"
    nli_evaluator: str = "local_nli"  # "local_nli", "heuristic", "none"
    enforce_rbac: bool = True
    evidence_mode: Literal["any", "all"] = "any"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# 3. Execution Trace & Component Results
# ---------------------------------------------------------------------------

class StageTrace(BaseModel):
    stage: str
    status: Literal["PASS", "FAIL", "SKIPPED", "ERROR"] = "PASS"
    latency_ms: float = 0.0
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None


class ExecutionTrace(BaseModel):
    test_id: str
    total_latency_ms: float = 0.0
    stages: Dict[str, StageTrace] = Field(default_factory=dict)


class AssertionResult(BaseModel):
    component: str
    type: str
    passed: bool
    actual_value: Any = None
    expected_value: Any = None
    threshold: Optional[float] = None
    severity: Literal["BLOCKER", "WARNING"] = "BLOCKER"
    message: str = ""


class TestCaseResult(BaseModel):
    test_id: str
    status: Literal["PASS", "FAIL", "ERROR", "INCONCLUSIVE", "NOT RUN"]
    failure_stage: Optional[str] = None
    assertion_results: List[AssertionResult] = Field(default_factory=list)
    trace: ExecutionTrace
    metrics: Dict[str, Any] = Field(default_factory=dict)


class SuiteRunResult(BaseModel):
    run_id: str
    suite_id: str
    config: RunConfig
    created_at: str
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    inconclusive: int = 0
    not_run: int = 0
    pass_rate: float = 0.0
    gate_passed: Optional[bool] = None
    gate_reasons: List[str] = Field(default_factory=list)
    component_metrics: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    failed_cases: List[Dict[str, Any]] = Field(default_factory=list)
    test_results: List[TestCaseResult] = Field(default_factory=list)
