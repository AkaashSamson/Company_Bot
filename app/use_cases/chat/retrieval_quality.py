"""
Multi-Dimensional Retrieval Quality Gate Core (Task AB-5.1)

Implements evidence quality assessment for RAG pipeline according to C.R.E.A.T.E. rules:
- Multi-dimensional scoring (cosine distance, lexical grounding, separation gap)
- EvidenceQualityLevel classification (STRONG, BORDERLINE, WEAK, INVALID)
- Continuous adaptive confidence scoring (0.0 to 1.0)
- Hard rejection gate when distance >= 0.85
- Safe separation gap calculation guarded against k < 2
- Early exit decision without invoking expensive LLM generation on ungrounded evidence
"""

import logging
import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class EvidenceQualityLevel(Enum):
    """Quality classification for retrieved evidence based on C.R.E.A.T.E. rules."""
    STRONG = "strong"          # High confidence, clearly relevant (distance < 0.60)
    BORDERLINE = "borderline"  # Acceptable, proceed with caution (0.60 <= distance < 0.70)
    WEAK = "weak"              # Low confidence, questionable relevance (0.70 <= distance < 0.85)
    INVALID = "invalid"        # Not relevant, hard reject / early exit (distance >= 0.85)


@dataclass
class QualityScore:
    """Detailed multi-dimensional quality score breakdown."""
    overall_score: float       # Composite adaptive confidence score (0.0 - 1.0)
    distance_score: float      # Score derived from top-1 vector distance
    grounding_score: float     # Score derived from lexical token overlap with query
    separation_gap: float      # Gap between top-1 and top-2 candidates
    evidence_count: int        # Number of candidate chunks evaluated
    quality_level: EvidenceQualityLevel
    dimension_scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert score breakdown to dictionary."""
        return {
            "overall_score": round(self.overall_score, 4),
            "distance_score": round(self.distance_score, 4),
            "grounding_score": round(self.grounding_score, 4),
            "separation_gap": round(self.separation_gap, 4),
            "evidence_count": self.evidence_count,
            "quality_level": self.quality_level.value,
            "dimension_scores": self.dimension_scores,
        }


@dataclass
class QualityGateResult:
    """Result of multi-dimensional quality gate evaluation."""
    passed: bool
    quality_level: EvidenceQualityLevel
    quality_score: QualityScore
    evidence: list[dict]
    early_exit: bool
    exit_reason: Optional[str] = None
    query: str = ""

    @property
    def confidence(self) -> float:
        """Alias for overall composite confidence score (0.0 to 1.0)."""
        return self.quality_score.overall_score

    @property
    def level(self) -> EvidenceQualityLevel:
        """Alias for quality level enum."""
        return self.quality_level

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "passed": self.passed,
            "quality_level": self.quality_level.value,
            "confidence": round(self.confidence, 4),
            "early_exit": self.early_exit,
            "exit_reason": self.exit_reason,
            "quality_score": self.quality_score.to_dict(),
            "evidence_count": len(self.evidence),
        }


# Type alias for plan documentation consistency
RetrievalQualityResult = QualityGateResult


class RetrievalQualityGate:
    """
    Multi-dimensional quality gate for RAG retrieval.
    
    Evaluates evidence across three primary dimensions:
    1. Distance Score: Top vector cosine distance (<0.60 STRONG, >=0.85 INVALID).
    2. Grounding Score: Lexical overlap between user query and retrieved chunks.
    3. Separation Gap: Margin between top-1 and top-2 results (guarded against k < 2).
    
    Decision Flow:
    - INVALID (distance >= 0.85 or overall < 0.25): Early exit without LLM call.
    - WEAK (0.70 <= distance < 0.85): Mark as low confidence; proceed with disclaimer.
    - BORDERLINE (0.60 <= distance < 0.70): Usable context; caution recommended.
    - STRONG (distance < 0.60): Full confidence in retrieval.
    """

    # Common English stop words to filter out during lexical grounding calculation
    DEFAULT_STOP_WORDS = frozenset({
        "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
        "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
        "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
        "did", "do", "does", "doing", "don't", "down", "during", "each", "few", "for",
        "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers",
        "him", "himself", "his", "how", "i", "if", "in", "into", "is", "isn't", "it",
        "its", "itself", "let's", "me", "more", "most", "my", "myself", "no", "nor",
        "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours",
        "ourselves", "out", "over", "own", "same", "she", "should", "so", "some", "such",
        "than", "that", "the", "their", "theirs", "them", "themselves", "then", "there",
        "these", "they", "this", "those", "through", "to", "too", "under", "until", "up",
        "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were", "what",
        "when", "where", "which", "while", "who", "whom", "why", "with", "won't", "would",
        "you", "you'd", "you'll", "you're", "you've", "your", "yours", "yourself",
    })

    def __init__(
        self,
        strong_distance_threshold: float = 0.60,
        borderline_distance_threshold: float = 0.70,
        invalid_distance_threshold: float = 0.85,
        min_separation_gap: float = 0.10,
        min_grounding_score: float = 0.20,
        min_evidence_count: int = 1,
        min_quality_score: float = 0.40,
        enable_adaptive_thresholds: bool = True,
        stop_words: Optional[set[str]] = None,
    ):
        """
        Initialize the multi-dimensional retrieval quality gate.

        Args:
            strong_distance_threshold: Top distance cutoff for STRONG evidence (<0.60)
            borderline_distance_threshold: Cutoff for BORDERLINE evidence (<0.70)
            invalid_distance_threshold: Cutoff for hard rejection / INVALID (>=0.85)
            min_separation_gap: Target separation gap between top candidates (>=0.10)
            min_grounding_score: Target lexical token overlap (>=0.20)
            min_evidence_count: Minimum chunks required to avoid insufficient evidence penalty
            min_quality_score: Minimum composite score required to pass gate
            enable_adaptive_thresholds: Dynamically shift dimension weights based on strength
            stop_words: Custom stop words set for lexical tokenization
        """
        self.strong_distance_threshold = strong_distance_threshold
        self.borderline_distance_threshold = borderline_distance_threshold
        self.invalid_distance_threshold = invalid_distance_threshold
        self.min_separation_gap = min_separation_gap
        self.min_grounding_score = min_grounding_score
        self.min_evidence_count = min_evidence_count
        self.min_quality_score = min_quality_score
        self.enable_adaptive_thresholds = enable_adaptive_thresholds
        self.stop_words = stop_words if stop_words is not None else self.DEFAULT_STOP_WORDS

        # Backward compatibility aliases
        self.distance_threshold = strong_distance_threshold
        self.distance_relaxation = borderline_distance_threshold - strong_distance_threshold

        logger.info(
            "retrieval_quality_gate initialized strong=%.2f borderline=%.2f invalid=%.2f grounding=%.2f gap=%.2f",
            self.strong_distance_threshold,
            self.borderline_distance_threshold,
            self.invalid_distance_threshold,
            self.min_grounding_score,
            self.min_separation_gap,
        )

    @staticmethod
    def classify_distance(distance: float) -> EvidenceQualityLevel:
        """
        Classify a single vector distance into a C.R.E.A.T.E. quality level.

        Bands:
        - < 0.60: STRONG
        - 0.60 to 0.6999: BORDERLINE
        - 0.70 to 0.8499: WEAK
        - >= 0.85: INVALID (hard rejection)
        """
        if distance < 0.60:
            return EvidenceQualityLevel.STRONG
        elif distance < 0.70:
            return EvidenceQualityLevel.BORDERLINE
        elif distance < 0.85:
            return EvidenceQualityLevel.WEAK
        else:
            return EvidenceQualityLevel.INVALID

    def evaluate(
        self,
        query: str,
        evidence: list[dict],
    ) -> QualityGateResult:
        
        return self.assess(query=query, evidence=evidence)

    def assess(
        self,
        query: str,
        evidence: list[dict],
    ) -> QualityGateResult:
        """
        Assess quality of retrieved evidence across distance, grounding, and separation.

        Args:
            query: User's original or normalized search query
            evidence: List of candidate chunk dicts (must include 'distance' or 'text')

        Returns:
            QualityGateResult containing classification, confidence, and early-exit flags
        """
        if not evidence:
            zero_score = QualityScore(
                overall_score=0.0,
                distance_score=0.0,
                grounding_score=0.0,
                separation_gap=0.0,
                evidence_count=0,
                quality_level=EvidenceQualityLevel.INVALID,
                dimension_scores={"distance": 0.0, "grounding": 0.0, "separation": 0.0},
            )
            return QualityGateResult(
                passed=False,
                quality_level=EvidenceQualityLevel.INVALID,
                quality_score=zero_score,
                evidence=[],
                early_exit=True,
                exit_reason="No evidence retrieved",
                query=query,
            )

        # 1. Calculate individual dimensional scores
        distance_score, best_distance = self._calculate_distance_score(evidence)
        grounding_score, best_chunk_grounding = self._calculate_grounding_score(query, evidence)
        separation_gap, raw_gap = self._calculate_separation_gap(evidence)

        # 2. Derive composite adaptive confidence score (0.0 to 1.0)
        overall_score, dim_scores = self._calculate_overall_score(
            distance_score=distance_score,
            grounding_score=grounding_score,
            separation_gap=separation_gap,
            evidence=evidence,
        )

        # 3. Determine discrete EvidenceQualityLevel with hard gate overrides
        quality_level = self._determine_quality_level(
            best_distance=best_distance,
            overall_score=overall_score,
            distance_score=distance_score,
            grounding_score=grounding_score,
            evidence=evidence,
        )

        quality_score = QualityScore(
            overall_score=overall_score,
            distance_score=distance_score,
            grounding_score=grounding_score,
            separation_gap=separation_gap,
            evidence_count=len(evidence),
            quality_level=quality_level,
            dimension_scores=dim_scores,
        )

        # 4. Evaluation decision logic
        early_exit = (quality_level == EvidenceQualityLevel.INVALID)
        passed = (
            quality_level in (EvidenceQualityLevel.STRONG, EvidenceQualityLevel.BORDERLINE)
            and overall_score >= self.min_quality_score
            and len(evidence) >= self.min_evidence_count
        )

        exit_reason: Optional[str] = None
        if early_exit:
            if best_distance is not None and best_distance >= self.invalid_distance_threshold:
                exit_reason = (
                    f"Evidence distance ({best_distance:.3f}) exceeds invalid threshold "
                    f"({self.invalid_distance_threshold:.2f})"
                )
            elif overall_score < self.min_quality_score:
                exit_reason = (
                    f"Composite retrieval score ({overall_score:.3f}) below minimum "
                    f"quality threshold ({self.min_quality_score:.2f})"
                )
            else:
                exit_reason = "Evidence below quality threshold"

        logger.info(
            "quality_gate_assessment level=%s confidence=%.3f passed=%s early_exit=%s count=%d best_dist=%s",
            quality_level.value,
            overall_score,
            passed,
            early_exit,
            len(evidence),
            f"{best_distance:.4f}" if best_distance is not None else "None",
        )

        return QualityGateResult(
            passed=passed,
            quality_level=quality_level,
            quality_score=quality_score,
            evidence=evidence,
            early_exit=early_exit,
            exit_reason=exit_reason,
            query=query,
        )

    # Alias for method name consistency across codebase
    evaluate = assess

    def _calculate_distance_score(self, evidence: list[dict]) -> tuple[float, Optional[float]]:
        """
        Calculate normalized score based on minimum vector distance.
        
        Uses piece-wise linear scaling matching C.R.E.A.T.E. bands:
        - d = 0.0 -> score = 1.0
        - d = 0.60 -> score = 0.70 (STRONG boundary)
        - d = 0.70 -> score = 0.45 (BORDERLINE boundary)
        - d = 0.85 -> score = 0.00 (INVALID boundary)
        - d >= 0.85 -> score = 0.00 (Hard zero)
        
        Returns:
            Tuple of (distance_score, best_distance)
        """
        distances = [
            e.get("distance")
            for e in evidence
            if isinstance(e.get("distance"), (int, float))
        ]

        if not distances:
            # If no distances are provided, return neutral score
            return 0.50, None

        best_distance = float(min(distances))

        # Hard boundary: distances at or above 0.85 receive 0.0 score
        if best_distance >= self.invalid_distance_threshold:
            return 0.0, best_distance

        if best_distance <= 0.0:
            return 1.0, best_distance

        # Piece-wise linear mapping:
        if best_distance < self.strong_distance_threshold:
            # Scale from 1.0 down to 0.70
            fraction = best_distance / self.strong_distance_threshold
            score = 1.0 - (fraction * 0.30)
        elif best_distance < self.borderline_distance_threshold:
            # Scale from 0.70 down to 0.45
            span = self.borderline_distance_threshold - self.strong_distance_threshold
            fraction = (best_distance - self.strong_distance_threshold) / (span or 0.10)
            score = 0.70 - (fraction * 0.25)
        else:
            # Scale from 0.45 down to 0.0
            span = self.invalid_distance_threshold - self.borderline_distance_threshold
            fraction = (best_distance - self.borderline_distance_threshold) / (span or 0.15)
            score = 0.45 - (fraction * 0.45)

        return round(max(0.0, min(1.0, score)), 4), best_distance

    def _calculate_grounding_score(
        self,
        query: str,
        evidence: list[dict],
    ) -> tuple[float, float]:
        """
        Calculate lexical grounding score between query tokens and evidence text.
        
        Measures the fraction of meaningful query tokens present in the evidence.
        Combines maximum single-chunk grounding (70% weight) with average (30% weight).
        
        Returns:
            Tuple of (composite_grounding_score, best_chunk_grounding)
        """
        if not evidence:
            return 0.0, 0.0

        query_terms = self._extract_terms(query)
        if not query_terms:
            # Neutral grounding for empty or pure stop-word queries
            return 0.50, 0.50

        grounding_scores: list[float] = []
        for e in evidence:
            text = e.get("text") or e.get("content") or ""
            evidence_terms = self._extract_terms(text)

            if not evidence_terms:
                grounding_scores.append(0.0)
                continue

            overlap = query_terms & evidence_terms
            score = len(overlap) / len(query_terms)
            grounding_scores.append(score)

        if not grounding_scores:
            return 0.0, 0.0

        best_score = max(grounding_scores)
        avg_score = sum(grounding_scores) / len(grounding_scores)

        # Weighted blend favoring the best matching chunk
        composite = (0.70 * best_score) + (0.30 * avg_score)
        return round(max(0.0, min(1.0, composite)), 4), round(best_score, 4)

    def _calculate_separation_gap(self, evidence: list[dict]) -> tuple[float, float]:
        """
        Calculate separation gap between top-1 and top-2 candidates.
        
        Guard clause: If fewer than 2 candidates or fewer than 2 valid distance
        values exist, separation gap is defined as 0.0 (prevents IndexError and
        false score inflation).
        
        Returns:
            Tuple of (normalized_gap_score, raw_distance_gap)
        """
        # Guard clause: k < 2
        if len(evidence) < 2:
            return 0.0, 0.0

        distances = [
            float(e["distance"])
            for e in evidence
            if isinstance(e.get("distance"), (int, float))
        ]

        if len(distances) < 2:
            return 0.0, 0.0

        sorted_distances = sorted(distances)
        raw_gap = sorted_distances[1] - sorted_distances[0]

        # Normalize against min_separation_gap (target 0.10)
        gap_score = min(1.0, max(0.0, raw_gap / (self.min_separation_gap or 0.10)))
        return round(gap_score, 4), round(raw_gap, 4)

    def _calculate_overall_score(
        self,
        distance_score: float,
        grounding_score: float,
        separation_gap: float,
        evidence: list[dict],
    ) -> tuple[float, dict[str, float]]:
        """
        Calculate composite adaptive confidence score.
        
        Dynamically shifts weights based on the strength of primary indicators:
        - When vector distance is exceptional, distance weight increases.
        - When distance is borderline, lexical grounding weight increases.
        """
        # Base weight profile: 50% distance, 35% grounding, 15% separation
        w_dist = 0.50
        w_ground = 0.35
        w_sep = 0.15

        if self.enable_adaptive_thresholds:
            if distance_score >= 0.85:
                # Strong vector alignment: rely more on distance
                w_dist = 0.60
                w_ground = 0.25
                w_sep = 0.15
            elif distance_score < 0.40:
                # Weak vector alignment: require higher lexical confirmation
                w_dist = 0.35
                w_ground = 0.50
                w_sep = 0.15

        composite = (w_dist * distance_score) + (w_ground * grounding_score) + (w_sep * separation_gap)

        # Penalize if evidence count is lower than required minimum
        if len(evidence) < self.min_evidence_count:
            penalty = (self.min_evidence_count - len(evidence)) * 0.15
            composite = max(0.0, composite - penalty)

        final_score = round(max(0.0, min(1.0, composite)), 4)
        dim_scores = {
            "distance_weight": w_dist,
            "grounding_weight": w_ground,
            "separation_weight": w_sep,
            "distance_component": round(w_dist * distance_score, 4),
            "grounding_component": round(w_ground * grounding_score, 4),
            "separation_component": round(w_sep * separation_gap, 4),
        }

        return final_score, dim_scores

    def _determine_quality_level(
        self,
        best_distance: Optional[float],
        overall_score: float,
        distance_score: float,
        grounding_score: float,
        evidence: list[dict],
    ) -> EvidenceQualityLevel:
        """
        Determine discrete EvidenceQualityLevel with C.R.E.A.T.E. hard gate overrides.
        """
        if not evidence:
            return EvidenceQualityLevel.INVALID

        # HARD GATE OVERRIDE 1: Distance >= 0.85 is unconditionally INVALID
        if best_distance is not None and best_distance >= self.invalid_distance_threshold:
            return EvidenceQualityLevel.INVALID

        # HARD GATE OVERRIDE 2: Zero distance score AND zero grounding is INVALID
        if distance_score == 0.0 and grounding_score < self.min_grounding_score:
            return EvidenceQualityLevel.INVALID

        # C.R.E.A.T.E. Band Classification
        if best_distance is not None:
            if best_distance < self.strong_distance_threshold:
                # Distance < 0.60: STRONG unless grounding is completely zero
                if grounding_score >= 0.10 or overall_score >= 0.60:
                    return EvidenceQualityLevel.STRONG
                return EvidenceQualityLevel.BORDERLINE
            elif best_distance < self.borderline_distance_threshold:
                # 0.60 <= Distance < 0.70: BORDERLINE
                if overall_score >= 0.40:
                    return EvidenceQualityLevel.BORDERLINE
                return EvidenceQualityLevel.WEAK
            elif best_distance < self.invalid_distance_threshold:
                # 0.70 <= Distance < 0.85: WEAK
                return EvidenceQualityLevel.WEAK

        # Fallback based on composite score if distance metadata was absent
        if overall_score >= 0.70:
            return EvidenceQualityLevel.STRONG
        elif overall_score >= 0.50:
            return EvidenceQualityLevel.BORDERLINE
        elif overall_score >= 0.30:
            return EvidenceQualityLevel.WEAK
        else:
            return EvidenceQualityLevel.INVALID

    def _extract_terms(self, text: str) -> set[str]:
        """
        Extract normalized alphanumeric tokens from text excluding stop words.
        """
        if not text:
            return set()

        raw_tokens = re.findall(r"[a-z0-9]+", text.lower())
        return {
            t for t in raw_tokens
            if t not in self.stop_words and len(t) >= 2
        }

    def should_early_exit(self, query: str, evidence: list[dict]) -> tuple[bool, Optional[str]]:
        """
        Quick check if pipeline should terminate early without LLM generation.

        Returns:
            Tuple of (should_exit, reason)
        """
        result = self.assess(query, evidence)
        if result.early_exit:
            return True, result.exit_reason
        return False, None


# Global singleton instance
_retrieval_quality_gate: Optional[RetrievalQualityGate] = None


def get_retrieval_quality_gate() -> RetrievalQualityGate:
    """Get or initialize the global RetrievalQualityGate singleton."""
    global _retrieval_quality_gate
    if _retrieval_quality_gate is None:
        _retrieval_quality_gate = RetrievalQualityGate()
    return _retrieval_quality_gate