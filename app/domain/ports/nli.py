"""
NLI Port and Aggregation Protocol (Domain Layer).

Defines vendor-neutral abstractions for claim-level Natural Language Inference
and the strict non-averaging aggregation policy.
"""

from typing import Protocol, Sequence, runtime_checkable

from app.domain.entities.cache import ClaimEvidencePair, NLILabel, NLIResult


@runtime_checkable
class EvidenceVerifier(Protocol):
    """Protocol for batched NLI claim-level verification."""

    def verify_batch(self, pairs: Sequence[ClaimEvidencePair]) -> Sequence[NLIResult]:
        """
        Verify multiple (claim, evidence) pairs in a single batched pass.
        
        Args:
            pairs: Sequence of ClaimEvidencePair objects
            
        Returns:
            Sequence of NLIResult corresponding 1-to-1 with pairs.
        """
        ...


def aggregate_nli_claims(
    results: Sequence[NLIResult],
    material_flags: Optional[Sequence[bool]] = None,
    contradiction_threshold: float = 0.50,
    entailment_threshold: float = 0.65,
) -> NLILabel:
    """
    Strict non-averaging aggregation policy for claim verification:
    
    1. Contradiction Rule: If ANY material claim receives CONTRADICTION (score >= threshold) -> CONTRADICTION.
    2. Neutral Rule: If ANY material claim receives NEUTRAL (or entailment below threshold) -> NEUTRAL.
    3. Entailment Rule: Return ENTAILMENT if and only if 100% of material claims are ENTAILMENT.
    """
    if not results:
        return NLILabel.NEUTRAL

    flags = list(material_flags) if material_flags is not None else [True] * len(results)

    # Check contradiction on material claims
    for res, is_mat in zip(results, flags):
        if is_mat and res.label == NLILabel.CONTRADICTION and res.score >= contradiction_threshold:
            return NLILabel.CONTRADICTION

    # Check neutral or below entailment threshold on material claims
    for res, is_mat in zip(results, flags):
        if is_mat and (
            res.label == NLILabel.NEUTRAL
            or (res.label == NLILabel.ENTAILMENT and res.score < entailment_threshold)
        ):
            return NLILabel.NEUTRAL

    return NLILabel.ENTAILMENT
