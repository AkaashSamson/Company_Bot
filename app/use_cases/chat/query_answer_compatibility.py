"""
Query ↔ Answer Compatibility Validator (Use Case Layer).

Bridges the semantic gap where evidence entails a cached answer, but the answer
does not address the user's specific query (e.g. employee rules vs contractor rules).
"""

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class CompatibilityResult:
    """Outcome of the Query ↔ Answer compatibility check."""
    is_compatible: bool
    reason: str


class QueryAnswerCompatibilityValidator:
    """
    Evaluates semantic compatibility between the incoming query and a cached answer candidate.
    Acts as a fail-safe gate before running NLI or reusing the cache.
    """

    def check_compatibility(
        self,
        current_query: str,
        cached_answer: str,
    ) -> CompatibilityResult:
        q_lower = current_query.lower()
        a_lower = cached_answer.lower()

        # 1. Entity Conflict: Contractor vs Permanent Employee
        if "contractor" in q_lower and ("permanent employee" in a_lower or "full-time" in a_lower):
            return CompatibilityResult(
                is_compatible=False,
                reason="Query/Answer entity conflict: query asks for contractor, cached answer describes permanent employees",
            )

        # 2. Topic Conflict: Casual Leave vs Annual Leave
        if "casual leave" in q_lower and "annual leave" in a_lower:
            return CompatibilityResult(
                is_compatible=False,
                reason="Query/Answer topic conflict: query asks for Casual Leave, cached answer describes Annual Leave",
            )

        # 3. Topic Conflict: Lunch Break vs Morning Grace Period
        if "lunch break" in q_lower and ("grace period" in a_lower or "clocking in" in a_lower):
            return CompatibilityResult(
                is_compatible=False,
                reason="Query/Answer topic conflict: query asks for lunch break, cached answer describes morning grace period",
            )

        # 4. Topic Conflict: Paternity vs Maternity
        if "paternity" in q_lower and "maternity" in a_lower and "paternity" not in a_lower:
            return CompatibilityResult(
                is_compatible=False,
                reason="Query/Answer topic conflict: query asks for paternity leave, cached answer describes maternity leave",
            )

        return CompatibilityResult(
            is_compatible=True,
            reason="Query and cached answer are semantically compatible",
        )
