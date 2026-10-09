"""
Decision Provider Port (Domain Layer).

Defines the contract for the Jev 3-state macro policy engine (System One).
Produces deterministic outcomes: REUSE, REJECT, or REVALIDATE.
"""

from typing import Protocol, runtime_checkable

from app.domain.entities.cache import CacheDecisionInput, PolicyDecision


@runtime_checkable
class DecisionProvider(Protocol):
    """Protocol for Jev policy decision engine."""

    def evaluate(self, decision_input: CacheDecisionInput) -> PolicyDecision:
        """
        Evaluate cache entry context against risk, permissions, and policy rules.
        
        Args:
            decision_input: Standardized CacheDecisionInput
            
        Returns:
            PolicyDecision (REUSE, REJECT, or REVALIDATE)
        """
        ...
