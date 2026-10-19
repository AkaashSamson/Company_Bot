"""
KnowLayer Test Studio — Run Orchestrator
========================================
Coordinates preflight validation, modular stage execution, trace recording,
assertion evaluation, and unified metric aggregation for test suites.
"""

import time
from typing import Any, Callable, Dict, List, Optional
from sandbox.engine.schema import (
    TestCase,
    RunConfig,
    ExecutionTrace,
    StageTrace,
    AssertionResult,
    TestCaseResult,
    SuiteRunResult,
)
from sandbox.engine.registry import COMPONENT_REGISTRY
from sandbox.components.retrieval import execute_retrieval
from sandbox.components.reranking import execute_reranking
from sandbox.components.generation import execute_generation
from sandbox.components.grounding import execute_grounding
from sandbox.components.policy_eval import execute_policy_eval
from sandbox.components.ragas_eval import execute_ragas_evaluation



class RunOrchestrator:
    """
    Central orchestrator executing canonical test cases through registered components.
    """

    def __init__(self, config: RunConfig):
        self.config = config

    def preflight_check(self, test_cases: List[TestCase]) -> List[str]:
        """
        Validates environment, component availability, and execution mode constraints.
        Returns a list of warnings or error strings (empty if clean).
        """
        warnings = []
        if not test_cases:
            warnings.append("Preflight Warning: No test cases provided to orchestrator.")

        for comp_name in self.config.components:
            if comp_name not in COMPONENT_REGISTRY:
                warnings.append(f"Preflight Error: Unknown component '{comp_name}' requested in RunConfig.")
                continue

            decl = COMPONENT_REGISTRY[comp_name]
            if self.config.execution_mode == "offline_strict" and decl.network_required and self.config.llm_provider != "local_heuristic":
                warnings.append(
                    f"Preflight Notice: Component '{comp_name}' requires network in remote mode, but execution_mode='offline_strict'. "
                    "Auto-switching provider to 'local_heuristic'."
                )

        return warnings

    def execute_test_case(self, test_case: TestCase) -> TestCaseResult:
        """
        Executes a single test case across all active components, building the full trace.
        """
        trace = ExecutionTrace(test_id=test_case.id)
        all_assertions: List[AssertionResult] = []
        failure_stage: Optional[str] = None
        t_start = time.perf_counter()

        # Shared pipeline context
        candidates: List[Dict[str, Any]] = []
        reranked_chunks: List[Dict[str, Any]] = []
        response_text = ""

        # Stage 1: Retrieval
        if "retrieval" in self.config.components:
            try:
                ret_out = execute_retrieval(
                    test_case=test_case,
                    top_k=self.config.retrieval_k,
                    enforce_rbac=self.config.enforce_rbac,
                )
                candidates = ret_out.get("candidates", [])
                trace.stages["retrieval"] = StageTrace(
                    stage="retrieval",
                    status="PASS" if ret_out.get("passed") else "FAIL",
                    latency_ms=ret_out.get("latency_ms", 0.0),
                    inputs={"question": test_case.input.question, "role": test_case.input.role, "top_k": self.config.retrieval_k},
                    outputs={"candidate_count": len(candidates), "recall": ret_out.get("recall_at_k")},
                )
                all_assertions.extend(ret_out.get("assertions", []))
                if not ret_out.get("passed") and not failure_stage:
                    failure_stage = "retrieval"
            except Exception as e:
                trace.stages["retrieval"] = StageTrace(
                    stage="retrieval",
                    status="ERROR",
                    error_message=str(e),
                )
                if not failure_stage:
                    failure_stage = "retrieval"

        # Stage 2: Reranking
        if "reranking" in self.config.components and failure_stage != "retrieval":
            try:
                rerank_out = execute_reranking(
                    test_case=test_case,
                    candidates=candidates,
                    top_k=self.config.reranker_top_k,
                    reranker_model=self.config.reranker_model,
                )
                reranked_chunks = rerank_out.get("reranked_chunks", [])
                trace.stages["reranking"] = StageTrace(
                    stage="reranking",
                    status="PASS" if rerank_out.get("passed") else "FAIL",
                    latency_ms=rerank_out.get("latency_ms", 0.0),
                    inputs={"candidate_count": len(candidates), "top_k": self.config.reranker_top_k},
                    outputs={"reranked_count": len(reranked_chunks), "needle_found": rerank_out.get("needle_found")},
                )
                all_assertions.extend(rerank_out.get("assertions", []))
                if not rerank_out.get("passed") and not failure_stage:
                    failure_stage = "reranking"
            except Exception as e:
                trace.stages["reranking"] = StageTrace(
                    stage="reranking",
                    status="ERROR",
                    error_message=str(e),
                )
                if not failure_stage:
                    failure_stage = "reranking"
        elif "reranking" not in self.config.components:
            reranked_chunks = candidates[:self.config.reranker_top_k]

        # Stage 3: Generation
        if "generation" in self.config.components and not failure_stage:
            try:
                gen_out = execute_generation(
                    test_case=test_case,
                    context_chunks=reranked_chunks,
                    execution_mode=self.config.execution_mode,
                    llm_provider=self.config.llm_provider,
                    llm_model=self.config.llm_model,
                )
                response_text = gen_out.get("response_text", "")
                trace.stages["generation"] = StageTrace(
                    stage="generation",
                    status="PASS" if gen_out.get("passed") else "FAIL",
                    latency_ms=gen_out.get("latency_ms", 0.0),
                    inputs={"model": gen_out.get("model_name"), "context_tokens": gen_out.get("context_tokens")},
                    outputs={"response_text": response_text[:200], "response_tokens": gen_out.get("response_tokens")},
                )
                all_assertions.extend(gen_out.get("assertions", []))
                if not gen_out.get("passed") and not failure_stage:
                    failure_stage = "generation"
            except Exception as e:
                trace.stages["generation"] = StageTrace(
                    stage="generation",
                    status="ERROR",
                    error_message=str(e),
                )
                if not failure_stage:
                    failure_stage = "generation"

        # Stage 4: Grounding
        if "grounding" in self.config.components and response_text and not failure_stage:
            try:
                ground_out = execute_grounding(
                    test_case=test_case,
                    context_chunks=reranked_chunks,
                    response_text=response_text,
                    nli_mode=self.config.nli_evaluator,
                )
                trace.stages["grounding"] = StageTrace(
                    stage="grounding",
                    status="PASS" if ground_out.get("passed") else "FAIL",
                    latency_ms=0.0,
                    inputs={"nli_evaluator": self.config.nli_evaluator},
                    outputs={"entailment": ground_out.get("entailment_ratio"), "contradiction": ground_out.get("contradiction_ratio")},
                )
                all_assertions.extend(ground_out.get("assertions", []))
                if not ground_out.get("passed") and not failure_stage:
                    failure_stage = "grounding"
            except Exception as e:
                trace.stages["grounding"] = StageTrace(
                    stage="grounding",
                    status="ERROR",
                    error_message=str(e),
                )

        # Stage 5: Policy Evaluation
        if "policy_eval" in self.config.components and response_text:
            try:
                pol_out = execute_policy_eval(
                    test_case=test_case,
                    response_text=response_text,
                    context_chunks=reranked_chunks,
                )
                trace.stages["policy_eval"] = StageTrace(
                    stage="policy_eval",
                    status="PASS" if pol_out.get("passed") else "FAIL",
                    latency_ms=0.0,
                    inputs={"required_claims": len(test_case.expected_behavior.required_claims), "prohibited": len(test_case.expected_behavior.prohibited_claims)},
                    outputs={"prohibited_leaks": pol_out.get("prohibited_leaks"), "coverage": pol_out.get("coverage_ratio")},
                )
                all_assertions.extend(pol_out.get("assertions", []))
                if not pol_out.get("passed") and not failure_stage:
                    failure_stage = "policy_eval"
            except Exception as e:
                trace.stages["policy_eval"] = StageTrace(
                    stage="policy_eval",
                    status="ERROR",
                    error_message=str(e),
                )

        # Stage 6: Ragas Evaluation (Edge Cases & Response Quality via OpenRouter)
        if "ragas_eval" in self.config.components and response_text:
            try:
                ragas_out = execute_ragas_evaluation(
                    test_case=test_case,
                    response_text=response_text,
                    context_chunks=reranked_chunks,
                    execution_mode=self.config.execution_mode,
                    llm_provider=self.config.llm_provider,
                    evaluator_model=self.config.llm_model,
                )
                trace.stages["ragas_eval"] = StageTrace(
                    stage="ragas_eval",
                    status="PASS" if ragas_out.get("passed") else "FAIL",
                    latency_ms=ragas_out.get("latency_ms", 0.0),
                    inputs={"user_input": test_case.input.question, "reference_available": bool(test_case.expected_behavior.answer)},
                    outputs={
                        "faithfulness": ragas_out.get("faithfulness"),
                        "answer_relevancy": ragas_out.get("answer_relevancy"),
                        "factual_correctness": ragas_out.get("factual_correctness"),
                        "context_precision": ragas_out.get("context_precision"),
                        "context_recall": ragas_out.get("context_recall"),
                        "diagnosis": ragas_out.get("diagnosis"),
                    },
                )
                all_assertions.extend(ragas_out.get("assertions", []))
                if not ragas_out.get("passed") and not failure_stage:
                    failure_stage = "ragas_eval"
            except Exception as e:
                trace.stages["ragas_eval"] = StageTrace(
                    stage="ragas_eval",
                    status="ERROR",
                    error_message=str(e),
                )

        trace.total_latency_ms = round((time.perf_counter() - t_start) * 1000, 2)


        # Determine overall status
        blocker_failures = [a for a in all_assertions if not a.passed and a.severity == "BLOCKER"]
        status = "FAIL" if (blocker_failures or failure_stage) else "PASS"

        return TestCaseResult(
            test_id=test_case.id,
            status=status,
            failure_stage=failure_stage,
            assertion_results=all_assertions,
            trace=trace,
            metrics={
                "latency_ms": trace.total_latency_ms,
                "response_text": response_text,
            }
        )

    def run_suite(
        self,
        test_cases: List[TestCase],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> SuiteRunResult:
        """
        Runs the full suite of test cases and calculates 4-level unified metrics.
        """
        results: List[TestCaseResult] = []
        passed_count = 0
        failed_count = 0
        error_count = 0
        failed_cases: List[Dict[str, Any]] = []

        total = len(test_cases)
        for idx, tc in enumerate(test_cases):
            if progress_callback:
                progress_callback(idx, total, f"Evaluating [{tc.id}]: {tc.title[:45]}...")

            res = self.execute_test_case(tc)
            results.append(res)

            if res.status == "PASS":
                passed_count += 1
            elif res.status == "FAIL":
                failed_count += 1
                failed_cases.append({
                    "id": tc.id,
                    "title": tc.title,
                    "failure_stage": res.failure_stage,
                    "question": tc.input.question,
                    "failed_assertions": [a.model_dump() for a in res.assertion_results if not a.passed],
                })
            else:
                error_count += 1

        pass_rate = round((passed_count / total * 100) if total > 0 else 0.0, 1)

        # Level 2 Component metrics aggregation
        retrieval_recalls = []
        needle_hits = 0
        total_needles = 0
        prohibited_clean = 0
        policy_checks = 0

        for r in results:
            for a in r.assertion_results:
                if a.type == "recall_at_k" and isinstance(a.actual_value, (int, float)):
                    retrieval_recalls.append(a.actual_value)
                elif a.type in ("needle_present", "needle_grounded"):
                    total_needles += 1
                    if a.passed:
                        needle_hits += 1
                elif a.type == "no_prohibited_claims":
                    policy_checks += 1
                    if a.passed:
                        prohibited_clean += 1

        mean_recall = round((sum(retrieval_recalls) / len(retrieval_recalls) * 100) if retrieval_recalls else 100.0, 1)
        needle_rate = round((needle_hits / total_needles * 100) if total_needles else 100.0, 1)
        compliance_rate = round((prohibited_clean / policy_checks * 100) if policy_checks else 100.0, 1)

        # Ragas metrics aggregation
        faith_scores = []
        rel_scores = []
        prec_scores = []
        fact_scores = []

        for r in results:
            for a in r.assertion_results:
                if a.component == "ragas_eval":
                    if a.type == "faithfulness" and isinstance(a.actual_value, (int, float)):
                        faith_scores.append(a.actual_value)
                    elif a.type == "answer_relevancy" and isinstance(a.actual_value, (int, float)):
                        rel_scores.append(a.actual_value)
                    elif a.type == "context_precision" and isinstance(a.actual_value, (int, float)):
                        prec_scores.append(a.actual_value)
                    elif a.type == "factual_correctness" and isinstance(a.actual_value, (int, float)):
                        fact_scores.append(a.actual_value)

        component_metrics = {
            "retrieval": {
                "mean_recall_at_k": mean_recall,
                "tested_cases": len(retrieval_recalls),
            },
            "reranking": {
                "needle_retention_rate": needle_rate,
                "tested_needles": total_needles,
            },
            "policy_eval": {
                "prohibited_claim_free_rate": compliance_rate,
                "policies_tested": policy_checks,
            }
        }

        if faith_scores:
            component_metrics["ragas_eval"] = {
                "mean_faithfulness": round(sum(faith_scores) / len(faith_scores), 2),
                "mean_answer_relevancy": round(sum(rel_scores) / len(rel_scores), 2) if rel_scores else 0.0,
                "mean_context_precision": round(sum(prec_scores) / len(prec_scores), 2) if prec_scores else 0.0,
                "mean_factual_correctness": round(sum(fact_scores) / len(fact_scores), 2) if fact_scores else 0.0,
                "cases_evaluated": len(faith_scores),
            }

        return SuiteRunResult(
            run_id=self.config.run_id,
            suite_id=self.config.suite_id,
            config=self.config,
            created_at=self.config.created_at,
            total_tests=total,
            passed=passed_count,
            failed=failed_count,
            errors=error_count,
            inconclusive=0,
            pass_rate=pass_rate,
            component_metrics=component_metrics,
            failed_cases=failed_cases,
            test_results=results,
        )
