"""
KnowLayer Test Studio — Grounding Component
===========================================
Evaluates response grounding against retrieved chunks using lexical needle assertions
and context token coverage. Operates 100% deterministically without NLI models.
"""

import re
from typing import Any, Dict, List, Optional
from sandbox.engine.schema import TestCase, AssertionResult


def execute_grounding(
    test_case: TestCase,
    context_chunks: List[Dict[str, Any]],
    response_text: str,
    nli_mode: str = "lexical",
) -> Dict[str, Any]:
    """
    Evaluates factual grounding and hallucination metrics without NLI dependencies.
    """
    if not response_text.strip() or not context_chunks:
        return {
            "entailment_ratio": 0.0,
            "contradiction_ratio": 0.0,
            "needle_grounded": False,
            "passed": False,
            "assertions": [],
        }

    # 1. Needle assertion
    needle_grounded = False
    needle_text = test_case.gold_evidence.needle_text
    if needle_text:
        clean_n = needle_text.strip().lower()
        if clean_n in response_text.lower():
            needle_grounded = True
        else:
            words = [w for w in re.findall(r"\b\w+\b", clean_n) if len(w) > 2 or w.isdigit()]
            matching_words = [w for w in words if w in response_text.lower()]
            if words and len(matching_words) >= max(1, int(len(words) * 0.6)):
                needle_grounded = True
    else:
        needle_grounded = True

    # 2. Lexical Token Grounding (Token Overlap & Coverage against context)
    combined_context = "\n\n".join([c.get("text", "") for c in context_chunks[:3]]).lower()
    resp_words = [w for w in re.findall(r"\b\w+\b", response_text.lower()) if len(w) > 3]
    supported_words = [w for w in resp_words if w in combined_context]
    
    grounding_ratio = len(supported_words) / len(resp_words) if resp_words else 1.0
    contradiction_ratio = 0.0 if grounding_ratio >= 0.50 else (1.0 - grounding_ratio)

    passed = needle_grounded and (grounding_ratio >= 0.50)

    assertions: List[AssertionResult] = []
    if needle_text:
        assertions.append(AssertionResult(
            component="grounding",
            type="needle_grounded",
            passed=needle_grounded,
            actual_value=needle_grounded,
            expected_value=True,
            severity="BLOCKER",
            message=f"Needle '{needle_text[:40]}...' present in generated text: {needle_grounded}"
        ))

    assertions.append(AssertionResult(
        component="grounding",
        type="lexical_grounding_coverage",
        passed=(grounding_ratio >= 0.50),
        actual_value=f"{grounding_ratio*100:.1f}% token overlap",
        expected_value=">=50.0%",
        severity="BLOCKER",
        message=f"Lexical Context Overlap: {grounding_ratio*100:.1f}%"
    ))

    return {
        "entailment_ratio": round(grounding_ratio, 3),
        "contradiction_ratio": round(contradiction_ratio, 3),
        "needle_grounded": needle_grounded,
        "claims_breakdown": [],
        "passed": passed,
        "assertions": assertions,
    }
