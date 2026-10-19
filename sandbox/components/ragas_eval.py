"""
KnowLayer Test Studio — Ragas Evaluator (OpenRouter Engine)
==========================================================
Evaluates LLM response quality, grounding, and edge-case handling using
the 5 core Ragas metrics:
1. Faithfulness: Are response claims grounded in retrieved context?
2. Answer Relevancy: Does the response address the user's actual question?
3. Factual Correctness: Does the response agree with the reference answer?
4. Context Precision: Were relevant chunks ranked higher than irrelevant ones?
5. Context Recall: Did retrieval capture the reference information needed?

Supports remote evaluation via OpenRouter and deterministic offline fallback.
"""

import os
import re
import json
import time
from typing import Any, Dict, List, Optional

from app.core.settings import OPENROUTER_API_KEY, LLM_MODEL
from app.infrastructure.llm.openrouter_client import OpenRouterClient
from sandbox.engine.schema import TestCase, AssertionResult


def _build_ragas_evaluation_prompt(
    user_input: str,
    response: str,
    retrieved_contexts: List[str],
    reference: str,
    is_edge_case: bool = False,
    is_refusal_case: bool = False,
) -> List[Dict[str, str]]:
    """
    Constructs an evaluator prompt following Ragas metric definitions and edge-case rubrics.
    """
    context_str = "\n\n".join([f"[Passage {i+1}]: {c}" for i, c in enumerate(retrieved_contexts[:4])])
    
    sys_prompt = (
        "You are an expert impartial AI evaluator evaluating a RAG (Retrieval-Augmented Generation) system. "
        "Your task is to calculate 5 standardized Ragas metrics for the given test scenario on a scale from 0.0 to 1.0.\n\n"
        "METRIC DEFINITIONS:\n"
        "1. Faithfulness (0.0 - 1.0): Are the claims in the response supported entirely by the retrieved context? "
        "Deduct points if the response makes factual claims not found in the context.\n"
        "2. Answer Relevancy (0.0 - 1.0): Does the response directly address the user's inquiry without extraneous fluff? "
        "For refusal cases, a polite direct refusal is 1.0 relevant.\n"
        "3. Factual Correctness (0.0 - 1.0): Does the response align factually with the reference answer? "
        "If reference is provided, check if key claims agree.\n"
        "4. Context Precision (0.0 - 1.0): Did retrieval rank the most relevant and useful passages near the top? "
        "1.0 if the best evidence is in Passage 1 or 2.\n"
        "5. Context Recall (0.0 - 1.0): Did the retrieved context contain the necessary facts from the reference? "
        "(If the question is unanswerable or requires refusal, set to 1.0 if no policy exists).\n\n"
        "EDGE CASE & NEGATIVE / BOUNDARY INSTRUCTIONS:\n"
        "- If the case is an Edge Case with missing/conflicting policy, reward the model if it explains what is known "
        "and transparently flags what is missing or ambiguous.\n"
        "- If the case is a Negative case, the model should provide the most relevant answer based on the references, "
        "clearly explaining what the policy states and clarifying why an unsupported request, bypass, or violation is not permitted, "
        "or indicating that the information is absent. Reward accurate reference-grounded answers and policy clarifications.\n\n"
        "Return ONLY a valid JSON object with the exact keys: "
        "faithfulness (float), answer_relevancy (float), factual_correctness (float), "
        "context_precision (float), context_recall (float), diagnosis (string explaining the scores)."
    )

    user_content = (
        f"USER QUESTION: {user_input}\n\n"
        f"RETRIEVED CONTEXT:\n{context_str}\n\n"
        f"GENERATED RESPONSE:\n{response}\n\n"
        f"REFERENCE ANSWER:\n{reference or 'N/A'}\n\n"
        f"IS_EDGE_CASE: {is_edge_case}\n"
        f"IS_REFUSAL_EXPECTED: {is_refusal_case}\n\n"
        "Provide your evaluation JSON:"
    )

    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_content},
    ]


def _deterministic_local_ragas_proxy(
    user_input: str,
    response: str,
    retrieved_contexts: List[str],
    reference: str,
    test_case: TestCase,
) -> Dict[str, Any]:
    """
    Offline zero-network deterministic proxy that models Ragas scoring
    using token attribution and overlap when running in local/offline mode.
    """
    clean_resp = response.lower()
    combined_ctx = " ".join(retrieved_contexts).lower()
    clean_ref = (reference or "").lower()
    should_refuse = test_case.expected_behavior.should_refuse

    # Refusal and boundary handling
    refusal_keywords = [
        "cannot", "not supported", "outside", "consult hr", "prohibited", "confidential",
        "mandates", "no procedure", "does not permit", "does not provide", "not permitted",
        "unauthorized", "expires", "does not mention", "do not mention", "no mention",
        "not provided", "do not contain", "does not contain", "without proper authorization",
        "is not permitted", "are not permitted", "not disclosed", "not available",
        "no provision", "not allowed", "never permitted", "inferred that such actions are not permitted"
    ]
    has_refusal = any(kw in clean_resp for kw in refusal_keywords)

    if should_refuse:
        return {
            "faithfulness": 1.0 if has_refusal else 0.4,
            "answer_relevancy": 1.0 if has_refusal else 0.3,
            "factual_correctness": 1.0 if has_refusal else 0.5,
            "context_precision": 0.8,
            "context_recall": 1.0,
            "diagnosis": "Correctly abstained/refused to answer unauthorized request." if has_refusal else "Failed to refuse restricted request.",
        }

    # 1. Faithfulness (word overlap of response with context)
    resp_words = [w for w in re.findall(r"\b\w+\b", clean_resp) if len(w) > 3]
    supported_words = [w for w in resp_words if w in combined_ctx]
    faithfulness = round(len(supported_words) / len(resp_words), 2) if resp_words else 0.8

    # 2. Answer Relevancy (query overlap)
    q_words = [w for w in re.findall(r"\b\w+\b", user_input.lower()) if len(w) > 3]
    q_hits = [w for w in q_words if w in clean_resp]
    answer_relevancy = round(max(0.6, min(1.0, len(q_hits) / len(q_words))), 2) if q_words else 0.85

    # 3. Factual Correctness (reference agreement)
    if clean_ref:
        ref_words = [w for w in re.findall(r"\b\w+\b", clean_ref) if len(w) > 3]
        ref_hits = [w for w in ref_words if w in clean_resp]
        factual_correctness = round(min(1.0, (len(ref_hits) / len(ref_words)) * 1.2), 2) if ref_words else 0.85
    else:
        factual_correctness = 0.9

    # 4. Context Precision (check if top chunk has query overlap)
    if retrieved_contexts:
        top_chunk = retrieved_contexts[0].lower()
        top_hits = sum(1 for w in q_words if w in top_chunk)
        context_precision = 0.9 if top_hits >= 1 else 0.6
    else:
        context_precision = 0.5

    # 5. Context Recall (did context have reference concepts?)
    if clean_ref:
        ctx_ref_hits = [w for w in ref_words if w in combined_ctx]
        context_recall = round(len(ctx_ref_hits) / len(ref_words), 2) if ref_words else 0.85
    else:
        context_recall = 0.9

    diagnosis = (
        f"Answer is relevant ({answer_relevancy:.2f}) and grounded in context ({faithfulness:.2f}). "
        f"Context precision is {context_precision:.2f} with recall {context_recall:.2f}."
    )

    return {
        "faithfulness": min(1.0, max(0.0, faithfulness)),
        "answer_relevancy": min(1.0, max(0.0, answer_relevancy)),
        "factual_correctness": min(1.0, max(0.0, factual_correctness)),
        "context_precision": min(1.0, max(0.0, context_precision)),
        "context_recall": min(1.0, max(0.0, context_recall)),
        "diagnosis": diagnosis,
    }


def execute_ragas_evaluation(
    test_case: TestCase,
    response_text: str,
    context_chunks: List[Dict[str, Any]],
    execution_mode: str = "remote_provider_allowed",
    llm_provider: str = "openrouter",
    evaluator_model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes Ragas evaluation for the test case via OpenRouter with local offline fallback.
    """
    user_input = test_case.input.question
    response = response_text
    retrieved_contexts = [c.get("text", "") for c in context_chunks]
    reference = test_case.expected_behavior.answer or getattr(test_case.expected_behavior, "expected_guidance", "") or ""
    is_edge_case = test_case.category == "EDGE_CASE" or "EDGE" in test_case.id
    is_refusal_case = test_case.expected_behavior.should_refuse or test_case.answerability in ("INSUFFICIENT", "OUT_OF_SCOPE")

    scores: Dict[str, Any] = {}
    evaluator_used = "local_proxy"
    latency_ms = 0.0

    effective_api_key = api_key or os.getenv("OPENROUTER_API_KEY") or OPENROUTER_API_KEY

    # Attempt OpenRouter evaluation if allowed and API key is set
    use_remote = (
        execution_mode != "offline_strict"
        and llm_provider == "openrouter"
        and bool(effective_api_key)
    )

    if use_remote:
        t0 = time.perf_counter()
        try:
            client = OpenRouterClient(
                api_key=effective_api_key,
                model=evaluator_model or "openai/gpt-4o-mini",
                timeout=30.0,
                temperature=0.0,
            )
            messages = _build_ragas_evaluation_prompt(
                user_input=user_input,
                response=response,
                retrieved_contexts=retrieved_contexts,
                reference=reference,
                is_edge_case=is_edge_case,
                is_refusal_case=is_refusal_case,
            )
            raw_out = client.generate(messages, temperature=0.0)
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            
            # Extract JSON from response
            match = re.search(r"\{.*\}", raw_out, re.DOTALL)
            if match:
                scores = json.loads(match.group(0))
                evaluator_used = client.model
        except Exception:
            scores = {}

    if not scores:
        scores = _deterministic_local_ragas_proxy(
            user_input=user_input,
            response=response,
            retrieved_contexts=retrieved_contexts,
            reference=reference,
            test_case=test_case,
        )

    # Standardize float values
    faith = float(scores.get("faithfulness", 0.8))
    relevancy = float(scores.get("answer_relevancy", 0.85))
    factual = float(scores.get("factual_correctness", 0.85))
    ctx_prec = float(scores.get("context_precision", 0.8))
    ctx_rec = float(scores.get("context_recall", 0.85))
    diagnosis = scores.get("diagnosis", "Evaluation complete.")

    # Build standardized assertion results
    assertions: List[AssertionResult] = [
        AssertionResult(
            component="ragas_eval",
            type="faithfulness",
            passed=faith >= 0.70,
            actual_value=faith,
            expected_value=">=0.70",
            severity="BLOCKER" if not is_refusal_case else "WARNING",
            message=f"Ragas Faithfulness: {faith:.2f} (grounded in context)" if faith >= 0.70 else f"Low Faithfulness: {faith:.2f} (hallucinated claims)",
        ),
        AssertionResult(
            component="ragas_eval",
            type="answer_relevancy",
            passed=relevancy >= 0.70,
            actual_value=relevancy,
            expected_value=">=0.70",
            severity="BLOCKER",
            message=f"Ragas Answer Relevancy: {relevancy:.2f}" if relevancy >= 0.70 else f"Low Answer Relevancy: {relevancy:.2f}",
        ),
        AssertionResult(
            component="ragas_eval",
            type="context_precision",
            passed=ctx_prec >= 0.60,
            actual_value=ctx_prec,
            expected_value=">=0.60",
            severity="WARNING",
            message=f"Ragas Context Precision: {ctx_prec:.2f}",
        ),
    ]

    if reference:
        assertions.append(AssertionResult(
            component="ragas_eval",
            type="factual_correctness",
            passed=factual >= 0.65,
            actual_value=factual,
            expected_value=">=0.65",
            severity="WARNING",
            message=f"Ragas Factual Correctness: {factual:.2f} vs reference",
        ))

    overall_pass = all(a.passed for a in assertions if a.severity == "BLOCKER")

    return {
        "faithfulness": faith,
        "answer_relevancy": relevancy,
        "factual_correctness": factual,
        "context_precision": ctx_prec,
        "context_recall": ctx_rec,
        "diagnosis": diagnosis,
        "evaluator_used": evaluator_used,
        "latency_ms": latency_ms,
        "passed": overall_pass,
        "assertions": assertions,
    }
