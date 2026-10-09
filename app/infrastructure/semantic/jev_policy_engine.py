"""
Jev Policy Engine (System One Macro Decision Adapter).

Implements DecisionProvider protocol to enforce enterprise-wide risk tiers,
RBAC authorization, and high-consequence revalidation policies.
"""

from app.domain.entities.cache import (
    CacheDecisionInput,
    EvidenceStatus,
    PolicyDecision,
    RiskLevel,
)
from app.domain.ports.decision import DecisionProvider


class JevPolicyEngine(DecisionProvider):
    """
    Jev Macro Policy Engine (System One).
    Produces 3-state decisions: REUSE, REJECT, or REVALIDATE.
    """

    def evaluate(self, decision_input: CacheDecisionInput) -> PolicyDecision:
        # Gate 1: Authorization
        if not decision_input.is_authorized:
            return PolicyDecision.REJECT

        # Gate 2: Semantic Integrity (Contradictions or unsupported claims)
        if (
            decision_input.evidence_status == EvidenceStatus.CONTRADICTED
            or decision_input.unsupported_claims_count > 0
            or decision_input.nli_max_contradiction_score >= 0.50
        ):
            return PolicyDecision.REJECT

        # Gate 3: High Risk / High Consequence Policy Triggers
        # Compensation, executive salaries, and active legal queries require real-time revalidation
        sensitive_intents = {"COMPENSATION", "EXECUTIVE_PAY", "LEGAL_DISPUTE"}
        if decision_input.risk_level == RiskLevel.HIGH and decision_input.query_intent in sensitive_intents:
            return PolicyDecision.REVALIDATE

        # Gate 4: Unverified or Ambiguous evidence
        if decision_input.evidence_status == EvidenceStatus.UNKNOWN:
            return PolicyDecision.REVALIDATE

        return PolicyDecision.REUSE
