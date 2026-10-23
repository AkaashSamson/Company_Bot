"""
OCR & VLM Chunk Quality Scoring Engine (KnowLayer Sandbox)
===========================================================
Specialized quality diagnostic framework for evaluating chunks generated
via Optical Character Recognition (Docling / EasyOCR) and Vision-Language
Models (SmolVLM / Visual Enrichment).

Evaluates:
  1. OCR Lexical Validity & Gibberish Detection (CER/WER approximation)
  2. Noise Symbol Ratio (unprintable glyphs, scan artifacts, skew lines)
  3. Broken Line-Wrap Hyphenation Glitches
  4. VLM Description Specificity & Information Density
  5. VLM Repetition Loop & Degeneration Detection
  6. VLM Generic Boilerplate / Hallucination Detection
  7. Contextual Anchoring (Diagram / Picture Heading Linkage)
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Sequence


# Common English stop-words and functional words for lexical validity verification
COMMON_ENGLISH_WORDS = {
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it", "for",
    "not", "on", "with", "he", "as", "you", "do", "at", "this", "but", "his",
    "by", "from", "they", "we", "say", "her", "she", "or", "an", "will", "my",
    "one", "all", "would", "there", "their", "what", "so", "up", "out", "if",
    "about", "who", "get", "which", "go", "me", "when", "make", "can", "like",
    "time", "no", "just", "him", "know", "take", "people", "into", "year", "your",
    "good", "some", "could", "them", "see", "other", "than", "then", "now", "look",
    "only", "come", "its", "over", "think", "also", "back", "after", "use", "two",
    "how", "our", "work", "first", "well", "way", "even", "new", "want", "because",
    "any", "these", "give", "day", "most", "us", "policy", "employee", "leave",
    "company", "management", "department", "process", "approval", "request",
    "service", "system", "date", "status", "report", "manager", "team", "project",
    "user", "account", "access", "form", "review", "annual", "eligible", "standard",
    "guidelines", "compliance", "action", "hours", "days", "months", "years",
    "procedure", "plan", "document", "section", "table", "figure", "chart", "diagram",
    "workflow", "step", "input", "output", "client", "business", "support", "office"
}

GENERIC_VLM_FILLER = [
    r"this is an image of",
    r"an image showing",
    r"a photo of",
    r"a screenshot of a",
    r"this picture depicts",
    r"a black and white",
    r"there is no text",
    r"unable to decipher",
    r"image cannot be displayed",
    r"placeholder image",
]


@dataclass
class ChunkQualityAnnotation:
    """Individual quality audit annotation for a single chunk."""
    chunk_id: str
    text: str
    chunk_type: str  # "OCR", "VLM", "HYBRID_OCR_VLM", "TEXT"
    quality_score: float  # 0.0 to 100.0
    grade: str  # "A+", "B", "C", "F"
    lexical_validity: float  # 0.0 to 1.0
    noise_ratio: float  # 0.0 to 1.0
    specificity_score: float  # 0.0 to 1.0 (for VLM)
    repetition_ratio: float  # 0.0 to 1.0
    char_count: int
    token_count: int
    flags: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OcrVlmQualitySummary:
    """Batch quality summary across all inspected chunks."""
    total_chunks: int = 0
    ocr_count: int = 0
    vlm_count: int = 0
    text_count: int = 0
    composite_score: float = 0.0
    ocr_mean_score: float = 0.0
    vlm_mean_score: float = 0.0
    composite_grade: str = "A+"
    flagged_count: int = 0
    annotations: list[ChunkQualityAnnotation] = field(default_factory=list)
    flag_breakdown: dict[str, int] = field(default_factory=dict)


def detect_chunk_type(chunk_record: dict) -> str:
    """Identify whether a chunk was produced by OCR, VLM, or standard parser."""
    meta = chunk_record.get("metadata", {})
    produced_by = str(meta.get("produced_by", "")).lower()
    route = str(meta.get("route", "")).upper()
    content_type = str(meta.get("content_type", "")).lower()

    if "easyocr" in produced_by or route == "OCR":
        return "OCR"
    if "smolvlm" in produced_by or "vlm" in produced_by or route == "VLM":
        return "VLM"
    if route == "OCR+VLM":
        return "HYBRID_OCR_VLM"
    if content_type in ("picture", "figure", "image", "diagram"):
        return "VLM"

    # Heuristic fallback based on text markers
    text = chunk_record.get("text", "")
    if text.startswith("[IMAGE_DESCRIPTION:") or text.startswith("[VLM:"):
        return "VLM"
    if text.startswith("[OCR_EXTRACT:") or text.startswith("[OCR:"):
        return "OCR"

    return "TEXT"


def calculate_lexical_validity(text: str) -> float:
    """Calculate the ratio of legitimate English words vs gibberish OCR tokens."""
    tokens = re.findall(r"\b[A-Za-z]{3,}\b", text.lower())
    if not tokens:
        return 0.5 if len(text.strip()) > 0 else 0.0

    recognized = sum(1 for t in tokens if t in COMMON_ENGLISH_WORDS or _is_plausible_word(t))
    return round(recognized / len(tokens), 3)


def _is_plausible_word(word: str) -> bool:
    """Heuristic check for plausible English morphology (vowel/consonant balance)."""
    vowels = set("aeiouy")
    vowel_count = sum(1 for ch in word if ch in vowels)
    length = len(word)
    if length <= 2:
        return True
    # Word with no vowels or all vowels is usually OCR garbage
    vowel_ratio = vowel_count / length
    if vowel_ratio == 0 or vowel_ratio >= 0.8:
        return False
    # Triple identical consecutive consonants is OCR noise (e.g. "jjj", "qqq")
    if re.search(r"([bcdfghjklmnpqrstvwxyz])\1\1", word):
        return False
    return True


def calculate_noise_ratio(text: str) -> float:
    """Compute the ratio of non-alphanumeric, non-standard punctuation noise."""
    if not text.strip():
        return 1.0
    # Standard acceptable characters: alphanumeric, whitespace, standard punctuation
    standard_pattern = r"[A-Za-z0-9\s.,!?:;\-\'\"()\[\]{}/%$€£@&+=#<>]"
    noise_chars = len(re.sub(standard_pattern, "", text))
    # Count excessive repetitive punctuation sequences like "||||", "~~~", "____", "...."
    repetitive_noise = sum(len(m.group(0)) for m in re.finditer(r"([_\-~|=+*#.]){4,}", text))
    total_len = len(text)
    return round(min(1.0, (noise_chars + repetitive_noise) / total_len), 3)


def detect_hyphenation_breaks(text: str) -> int:
    """Count mid-word line-breaks produced by OCR across column wraps."""
    return len(re.findall(r"[A-Za-z]+-\s*\n\s*[A-Za-z]+", text))


def calculate_vlm_repetition(text: str) -> float:
    """Detect repetitive n-gram loops characteristic of VLM degeneration."""
    words = [w.lower() for w in re.findall(r"\b\w+\b", text)]
    if len(words) < 6:
        return 0.0

    # Check 3-gram repetition
    trigrams = [tuple(words[i:i+3]) for i in range(len(words) - 2)]
    counts = Counter(trigrams)
    repeats = sum(cnt - 1 for cnt in counts.values() if cnt > 1)
    return round(min(1.0, (repeats * 3) / len(words)), 3)


def calculate_vlm_specificity(text: str) -> float:
    """Measure information density: presence of entities, numbers, flowchart flows."""
    if not text.strip():
        return 0.0

    score = 0.5
    # Numbers and metrics increase specificity
    if re.search(r"\b\d+(?:\.\d+)?%?\b", text):
        score += 0.15
    # Diagram/flowchart transition markers
    if re.search(r"(?:->|-->|leads to|flows into|connects to|step \d+|phase \d+)", text, re.IGNORECASE):
        score += 0.20
    # Technical or operational terms
    if re.search(r"(?:table|column|row|header|chart|axis|legend|component|database|service)", text, re.IGNORECASE):
        score += 0.15
    # Penalize generic filler phrases
    for pattern in GENERIC_VLM_FILLER:
        if re.search(pattern, text, re.IGNORECASE):
            score -= 0.15

    return round(max(0.0, min(1.0, score)), 3)


def score_ocr_chunk(text: str, metadata: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    """Score an OCR-derived chunk and return (score_100, flags, recommendations)."""
    flags: list[str] = []
    recs: list[str] = []

    lex_val = calculate_lexical_validity(text)
    noise_rat = calculate_noise_ratio(text)
    hyphens = detect_hyphenation_breaks(text)
    char_len = len(text.strip())

    # Component weights: 40% lexical validity, 35% clean noise ratio, 15% length adequacy, 10% hyphenation
    length_adequacy = 1.0 if char_len >= 80 else (char_len / 80.0)
    hyphen_score = max(0.0, 1.0 - (hyphens * 0.25))

    raw_score = (
        0.40 * lex_val +
        0.35 * (1.0 - noise_rat) +
        0.15 * length_adequacy +
        0.10 * hyphen_score
    ) * 100.0

    # Boundary checks and flag rules
    if noise_rat > 0.20:
        flags.append("HIGH_OCR_NOISE")
        recs.append("Scattered OCR symbol noise detected (>20%). Apply pre-OCR scan despeckling and noise filter.")

    if lex_val < 0.65:
        flags.append("OCR_GIBBERISH_DETECTED")
        recs.append("Low English word recognition (<65%). OCR text contains garbled character strings.")

    if hyphens >= 2:
        flags.append("BROKEN_LINEWRAP_HYPHENS")
        recs.append(f"Found {hyphens} line-wrapped hyphenated words. De-hyphenate before indexing.")

    if char_len < 30:
        # Check if it looks like a decorative logo or timestamp
        if re.search(r"(?:©|\b20\d{2}\b|logo|all rights reserved)", text, re.IGNORECASE):
            flags.append("DECORATIVE_LOGO_OR_TIMESTAMP")
            recs.append("Appears to be a decorative logo or page timestamp. Filter out using `DOCLING_SKIP_DECORATIVE_OCR`.")
        else:
            flags.append("MICRO_OCR_STUB")
            recs.append("Extremely short OCR chunk (<30 chars). Merge with surrounding section.")

    return round(raw_score, 1), flags, recs


def score_vlm_chunk(text: str, metadata: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    """Score a VLM-derived chunk and return (score_100, flags, recommendations)."""
    flags: list[str] = []
    recs: list[str] = []

    specificity = calculate_vlm_specificity(text)
    repetition = calculate_vlm_repetition(text)
    char_len = len(text.strip())

    # Check if context anchor exists in metadata
    has_anchor = bool(metadata.get("hierarchy_path") or metadata.get("section_heading"))

    # Component weights: 35% specificity, 35% non-repetition, 15% context anchor, 15% length
    length_adequacy = 1.0 if char_len >= 50 else (char_len / 50.0)
    anchor_score = 1.0 if has_anchor else 0.4

    raw_score = (
        0.35 * specificity +
        0.35 * (1.0 - repetition) +
        0.15 * anchor_score +
        0.15 * length_adequacy
    ) * 100.0

    if repetition > 0.25:
        flags.append("VLM_REPETITION_LOOP")
        recs.append("VLM model fell into an autoregressive repetition loop. Lower temperature or penalize repetition.")

    if specificity < 0.40:
        flags.append("GENERIC_VLM_BOILERPLATE")
        recs.append("Description is overly generic without actionable diagram details. Refine VLM prompt template.")

    if not has_anchor:
        flags.append("UNANCHORED_VLM_DESCRIPTION")
        recs.append("VLM chunk has no parent heading or diagram title prepended. Anchor with parent hierarchy.")

    if char_len < 40:
        flags.append("MICRO_VLM_STUB")
        recs.append("VLM generated less than 40 characters. Image may lack extractable visual information.")

    return round(raw_score, 1), flags, recs


def score_text_chunk(text: str, metadata: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    """Score standard text chunks for comparison."""
    flags: list[str] = []
    recs: list[str] = []
    char_len = len(text.strip())
    tokens = len(text.split())

    score = 90.0
    if tokens < 15:
        flags.append("STUB_CHUNK")
        recs.append("Short text chunk (<15 tokens). Potential candidate for merging.")
        score -= 25.0
    elif tokens > 256:
        flags.append("OVERFLOW_CHUNK")
        recs.append("Exceeds standard 256-token embedding window. Model will silently truncate tail.")
        score -= 30.0

    if not text.endswith((".", "?", "!", "\"", "'", ":")):
        flags.append("MID_SENTENCE_BOUNDARY")
        recs.append("Chunk ends without terminal punctuation, indicating split sentence.")
        score -= 15.0

    return round(max(0.0, score), 1), flags, recs


def audit_chunk_record(chunk_record: dict) -> ChunkQualityAnnotation:
    """Analyze a single chunk record and return its full quality annotation."""
    chunk_id = str(chunk_record.get("id") or chunk_record.get("chunk_id", "unknown"))
    text = chunk_record.get("text", "")
    metadata = chunk_record.get("metadata", {})
    chunk_type = detect_chunk_type(chunk_record)

    tokens = len(text.split())
    chars = len(text)
    lex_val = calculate_lexical_validity(text)
    noise_rat = calculate_noise_ratio(text)
    repetition = calculate_vlm_repetition(text)
    specificity = calculate_vlm_specificity(text)

    if chunk_type == "OCR":
        score, flags, recs = score_ocr_chunk(text, metadata)
    elif chunk_type in ("VLM", "HYBRID_OCR_VLM"):
        score, flags, recs = score_vlm_chunk(text, metadata)
    else:
        score, flags, recs = score_text_chunk(text, metadata)

    grade = "A+" if score >= 90.0 else ("B" if score >= 80.0 else ("C" if score >= 70.0 else "F"))

    return ChunkQualityAnnotation(
        chunk_id=chunk_id,
        text=text,
        chunk_type=chunk_type,
        quality_score=score,
        grade=grade,
        lexical_validity=lex_val,
        noise_ratio=noise_rat,
        specificity_score=specificity,
        repetition_ratio=repetition,
        char_count=chars,
        token_count=tokens,
        flags=flags,
        recommendations=recs,
        metadata=metadata,
    )


def audit_chunks_batch(records: Sequence[dict]) -> OcrVlmQualitySummary:
    """Audit a collection of chunk records and produce an aggregate report."""
    if not records:
        return OcrVlmQualitySummary()

    annotations = [audit_chunk_record(r) for r in records]
    total = len(annotations)

    ocr_anns = [a for a in annotations if a.chunk_type == "OCR"]
    vlm_anns = [a for a in annotations if a.chunk_type in ("VLM", "HYBRID_OCR_VLM")]
    text_anns = [a for a in annotations if a.chunk_type == "TEXT"]

    ocr_mean = (sum(a.quality_score for a in ocr_anns) / len(ocr_anns)) if ocr_anns else 0.0
    vlm_mean = (sum(a.quality_score for a in vlm_anns) / len(vlm_anns)) if vlm_anns else 0.0
    comp_score = sum(a.quality_score for a in annotations) / total if total > 0 else 0.0

    flagged = [a for a in annotations if a.flags]
    flag_breakdown: Counter[str] = Counter()
    for a in annotations:
        for f in a.flags:
            flag_breakdown[f] += 1

    grade = "A+" if comp_score >= 90.0 else ("B" if comp_score >= 80.0 else ("C" if comp_score >= 70.0 else "F"))

    return OcrVlmQualitySummary(
        total_chunks=total,
        ocr_count=len(ocr_anns),
        vlm_count=len(vlm_anns),
        text_count=len(text_anns),
        composite_score=round(comp_score, 1),
        ocr_mean_score=round(ocr_mean, 1),
        vlm_mean_score=round(vlm_mean, 1),
        composite_grade=grade,
        flagged_count=len(flagged),
        annotations=annotations,
        flag_breakdown=dict(flag_breakdown.most_common()),
    )
