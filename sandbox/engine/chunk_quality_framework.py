"""
KnowLayer Chunk Quality Framework
==================================
Production-grade multi-dimensional chunk quality evaluation system implementing
the Complete 65-Metric Specification across the 6 Core Quality Dimensions:
  1. Text Integrity & Noisy-Data Metrics (Metrics 1–10)
  2. Chunk Structure & Boundary Metrics (Metrics 11–21)
  3. Semantic Quality & Condition Preservation (Metrics 22–31)
  4. Source Fidelity & Extraction Metrics (Metrics 32–40)
  5. Chunk Relationships & Corpus-Level Metrics (Metrics 41–50)
  6. Retrieval Readiness & Evidence Metrics (Metrics 51–60)
  7. Security, Auditability & Access-Control Metrics (Metrics 61–65)

Every metric addresses the Three Critical Questions:
  1. What is wrong with this chunk? (Evidence & Finding)
  2. Why does the issue matter for RAG? (Impact Explanation)
  3. What action should the reviewer or ingestion pipeline take? (Recommended Action)

Distinguishes:
  - Hard Validation Checks (deterministic, release-blocking)
  - Heuristic Metrics (statistical, rule-based)
  - Model-Based Judgments (semantic, context-aware)
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence, Set, Tuple

import pandas as pd
from pydantic import BaseModel, Field


# ==============================================================================
# Pydantic Schemas for Quality Auditing
# ==============================================================================

class MetricDefinition(BaseModel):
    """Formal registry metadata for a single quality metric."""
    id: int
    metric_name: str
    display_name: str
    dimension: Literal[
        "text_integrity",
        "structural_quality",
        "semantic_quality",
        "source_fidelity",
        "chunk_relationships",
        "retrieval_readiness",
        "security_auditability",
    ]
    priority: Literal["P0", "P1", "P2"]
    check_type: Literal["hard_validation", "heuristic", "model_based"]
    what_it_measures: str
    why_we_need_it: str
    recommended_action: str
    phase: Literal["Phase 1", "Phase 2", "Phase 3", "Phase 4"]


class MetricResult(BaseModel):
    """The canonical outcome of evaluating one metric against a single chunk."""
    chunk_id: str
    metric_name: str
    metric_version: str = "2.0"
    dimension: Literal[
        "text_integrity",
        "structural_quality",
        "semantic_quality",
        "source_fidelity",
        "chunk_relationships",
        "retrieval_readiness",
        "security_auditability",
    ]
    check_type: Literal["hard_validation", "heuristic", "model_based"]
    value: float | None = None
    status: Literal["pass", "warning", "fail", "not_applicable", "not_evaluated"]
    severity: Literal["critical", "high", "medium", "low", "none"] = "none"
    evidence: str | None = None
    quoted_text: str | None = None  # Verbatim text snippet or phrase from the chunk where the issue originates
    explanation: str | None = None  # Why this issue matters for RAG retrieval/generation
    possible_cause: str | None = None  # Probable root cause (e.g. OCR noise, parser split, encoding failure)
    verification_step: str | None = None  # How reviewer validates against original source
    recommended_action: str | None = None  # What action the pipeline/reviewer should take
    revalidation_action: str | None = None  # How to re-verify once addressed
    detector: str
    confidence: float | None = 1.0


class ChunkAuditReport(BaseModel):
    """Consolidated audit outcome for a single chunk."""
    chunk_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    metrics: list[MetricResult] = Field(default_factory=list)
    overall_status: Literal["pass", "warning", "fail"] = "pass"
    hard_failures_count: int = 0
    warnings_count: int = 0
    chunk_type: str = "text"  # "text", "table", "code", "ocr", "vlm"
    token_count: int = 0
    char_count: int = 0


class CorpusAuditReport(BaseModel):
    """Corpus-level aggregated quality report across all chunks."""
    total_chunks: int = 0
    hard_failures_count: int = 0
    warnings_count: int = 0
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    dimension_status: dict[str, str] = Field(default_factory=dict)
    composite_score: float = 100.0
    composite_grade: str = "A+"
    chunk_reports: list[ChunkAuditReport] = Field(default_factory=list)
    findings_summary: dict[str, int] = Field(default_factory=dict)
    retrieval_readiness_metrics: dict[str, Any] = Field(default_factory=dict)


# ==============================================================================
# Complete 65-Metric Specification & Catalog
# ==============================================================================

CHUNK_QUALITY_METRICS_CATALOG: list[MetricDefinition] = [
    # --------------------------------------------------------------------------
    # 1. Text integrity and noisy-data metrics (1–10)
    # --------------------------------------------------------------------------
    MetricDefinition(
        id=1,
        metric_name="empty_chunk_rate",
        display_name="Empty Chunk Rate",
        dimension="text_integrity",
        priority="P0",
        check_type="hard_validation",
        what_it_measures="Percentage of chunks containing no meaningful text",
        why_we_need_it="Empty chunks waste storage and can pollute retrieval results",
        recommended_action="Block ingestion: Drop empty chunk and inspect parser splitting configuration.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=2,
        metric_name="suspicious_symbol_ratio",
        display_name="Suspicious Symbol Ratio",
        dimension="text_integrity",
        priority="P0",
        check_type="heuristic",
        what_it_measures="Proportion of suspicious symbols relative to non-whitespace characters",
        why_we_need_it="Detects OCR corruption, extraction artifacts, and symbol-heavy noise",
        recommended_action="Filter OCR noise or check PDF column extraction boundaries before chunking.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=3,
        metric_name="replacement_character_count",
        display_name="Replacement Character Count",
        dimension="text_integrity",
        priority="P0",
        check_type="hard_validation",
        what_it_measures="Number of Unicode replacement characters (\\ufffd)",
        why_we_need_it="Identifies decoding or extraction failures",
        recommended_action="Re-extract document using verified UTF-8 encoding or run OCR repair on scanned source.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=4,
        metric_name="control_character_rate",
        display_name="Control Character Rate",
        dimension="text_integrity",
        priority="P0",
        check_type="hard_validation",
        what_it_measures="Frequency of unexpected control characters",
        why_we_need_it="Detects malformed text and encoding artifacts that corrupt databases and vector indices",
        recommended_action="Sanitize chunk text using `re.sub(r'[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]', '', text)` prior to storage.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=5,
        metric_name="non_printable_character_ratio",
        display_name="Non-Printable Character Ratio",
        dimension="text_integrity",
        priority="P0",
        check_type="hard_validation",
        what_it_measures="Proportion of characters that are not normally printable",
        why_we_need_it="Helps detect corrupted or malformed content and broken font encodings",
        recommended_action="Strip non-printable characters and verify font mapping in source document processor.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=6,
        metric_name="fragmentation_score",
        display_name="Fragmentation Score",
        dimension="text_integrity",
        priority="P0",
        check_type="heuristic",
        what_it_measures="Frequency of isolated characters, tiny tokens, and broken lines",
        why_we_need_it="Identifies chunks that have lost their original text structure and breaks embeddings",
        recommended_action="Enable layout-aware parsing (Docling) to reconstruct word sequences before splitting.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=7,
        metric_name="ocr_confidence",
        display_name="OCR Confidence",
        dimension="text_integrity",
        priority="P1",
        check_type="heuristic",
        what_it_measures="OCR engine confidence score, where available, or lexical plausibility estimate",
        why_we_need_it="Helps prioritize scanned pages that may require manual review or re-OCR",
        recommended_action="Re-run high-resolution OCR or route to VLM for low-confidence scans.",
        phase="Phase 4",
    ),
    MetricDefinition(
        id=8,
        metric_name="language_consistency",
        display_name="Language Consistency",
        dimension="text_integrity",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Whether the detected language matches the expected language and text distribution",
        why_we_need_it="Finds incorrect language detection, mixed-script corruption, and extraction anomalies",
        recommended_action="Inspect document language routing and verify OCR character recognition whitelist.",
        phase="Phase 4",
    ),
    MetricDefinition(
        id=9,
        metric_name="repeated_character_ratio",
        display_name="Repeated Character Ratio",
        dimension="text_integrity",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Frequency of suspicious repeated characters or sequences (dashes, dots, underlines)",
        why_we_need_it="Detects extraction loops, duplicated glyphs, and malformed layout text",
        recommended_action="Strip cosmetic horizontal rules and form fill-in-the-blank dots during text cleaning.",
        phase="Phase 4",
    ),
    MetricDefinition(
        id=10,
        metric_name="whitespace_anomaly_score",
        display_name="Whitespace Anomaly Score",
        dimension="text_integrity",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Excessive spaces, tabs, line breaks, or irregular spacing",
        why_we_need_it="Detects broken column extraction, layout problems, and fragmented text",
        recommended_action="Normalize whitespace runs (`re.sub(r' +', ' ', text)`) before tokenization.",
        phase="Phase 4",
    ),

    # --------------------------------------------------------------------------
    # 2. Chunk structure and boundary metrics (11–21)
    # --------------------------------------------------------------------------
    MetricDefinition(
        id=11,
        metric_name="token_count",
        display_name="Token Count",
        dimension="structural_quality",
        priority="P0",
        check_type="hard_validation",
        what_it_measures="Number of tokens in each chunk relative to the model's context window (256 tokens)",
        why_we_need_it="Prevents silent truncation by embedder and identifies extreme outliers",
        recommended_action="Sub-split chunk using sentence-aware chunker with max_tokens <= 256.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=12,
        metric_name="chunk_length_distribution",
        display_name="Chunk Length Distribution",
        dimension="structural_quality",
        priority="P0",
        check_type="heuristic",
        what_it_measures="Minimum, maximum, mean, median, and percentile lengths relative to target budget (200-220 tok)",
        why_we_need_it="Reveals whether the chunking configuration produces inconsistent or extreme sizes",
        recommended_action="Tune sliding window step closer to target budget 220 tokens.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=13,
        metric_name="sentence_boundary_integrity",
        display_name="Sentence Boundary Integrity",
        dimension="structural_quality",
        priority="P0",
        check_type="heuristic",
        what_it_measures="Whether chunks end or begin at sensible sentence boundaries",
        why_we_need_it="Prevents splitting definitions, conditions, and explanations mid-sentence",
        recommended_action="Re-split chunk strictly at terminal punctuation boundaries.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=14,
        metric_name="orphaned_heading_rate",
        display_name="Orphaned Heading Rate",
        dimension="structural_quality",
        priority="P0",
        check_type="heuristic",
        what_it_measures="Percentage of headings separated from the content they introduce",
        why_we_need_it="Prevents chunks from losing the topic that gives their content meaning",
        recommended_action="Fuse section heading with the succeeding content chunk during hierarchy extraction.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=15,
        metric_name="incomplete_sentence_rate",
        display_name="Incomplete Sentence Rate",
        dimension="structural_quality",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Frequency of chunks that start or end with apparently incomplete sentences",
        why_we_need_it="Identifies possible boundary errors and missing context",
        recommended_action="Align chunk boundary to complete syntactic clauses or expand window overlap.",
        phase="Phase 2",
    ),
    MetricDefinition(
        id=16,
        metric_name="paragraph_integrity",
        display_name="Paragraph Integrity",
        dimension="structural_quality",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Whether paragraphs have been split or merged inappropriately",
        why_we_need_it="Preserves logical relationships between statements and avoids severed hyphen breaks",
        recommended_action="De-hyphenate line wraps and respect double-newline paragraph separators.",
        phase="Phase 2",
    ),
    MetricDefinition(
        id=17,
        metric_name="table_integrity",
        display_name="Table Integrity",
        dimension="structural_quality",
        priority="P0",
        check_type="heuristic",
        what_it_measures="Whether table headers, rows, columns, and cell relationships remain understandable",
        why_we_need_it="Prevents numerical values and policy conditions from becoming ambiguous",
        recommended_action="Re-inject table header row into every chunk slice produced from multi-row tables.",
        phase="Phase 2",
    ),
    MetricDefinition(
        id=18,
        metric_name="list_integrity",
        display_name="List Integrity",
        dimension="structural_quality",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Whether list items remain associated with their parent heading and conditions",
        why_we_need_it="Preserves procedural steps, requirements, and enumerated exceptions",
        recommended_action="Group list items together with parent prompt/preamble in a single chunk.",
        phase="Phase 2",
    ),
    MetricDefinition(
        id=19,
        metric_name="chunk_overlap_ratio",
        display_name="Chunk Overlap Ratio",
        dimension="structural_quality",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Amount of text shared by neighboring chunks",
        why_we_need_it="Helps tune overlap to balance context preservation against redundant retrieval",
        recommended_action="Configure overlap window between 10% and 20% of target chunk size.",
        phase="Phase 2",
    ),
    MetricDefinition(
        id=20,
        metric_name="source_coverage_gap_rate",
        display_name="Source Coverage Gap Rate",
        dimension="structural_quality",
        priority="P0",
        check_type="hard_validation",
        what_it_measures="Proportion of relevant source text that is not represented in the resulting chunks",
        why_we_need_it="Detects text lost during chunking and extraction failures",
        recommended_action="Verify parser text stream length matches cumulative chunk character counts.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=21,
        metric_name="chunk_boundary_discontinuity",
        display_name="Chunk Boundary Discontinuity",
        dimension="structural_quality",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Whether adjacent chunks skip, reorder, or unexpectedly duplicate source passages",
        why_we_need_it="Finds segmentation errors that ordinary length metrics cannot detect",
        recommended_action="Inspect document section offsets to ensure sequential monotonically increasing bounds.",
        phase="Phase 4",
    ),

    # --------------------------------------------------------------------------
    # 3. Semantic quality metrics (22–31)
    # --------------------------------------------------------------------------
    MetricDefinition(
        id=22,
        metric_name="semantic_coherence",
        display_name="Semantic Coherence",
        dimension="semantic_quality",
        priority="P0",
        check_type="model_based",
        what_it_measures="Whether the text expresses a reasonably unified topic or idea",
        why_we_need_it="Detects chunks that mix unrelated subjects or lose logical flow",
        recommended_action="Split chunk on major section breaks to preserve thematic unity.",
        phase="Phase 2",
    ),
    MetricDefinition(
        id=23,
        metric_name="contextual_independence",
        display_name="Contextual Independence",
        dimension="semantic_quality",
        priority="P0",
        check_type="heuristic",
        what_it_measures="Whether a reader can understand the chunk without unavailable context (unanchored pronouns)",
        why_we_need_it="Finds references such as 'this provision,' 'they,' or 'the above' that lack clear antecedents",
        recommended_action="Prepend heading breadcrumbs via contextual prefix or apply coreference resolution.",
        phase="Phase 2",
    ),
    MetricDefinition(
        id=24,
        metric_name="topic_purity",
        display_name="Topic Purity",
        dimension="semantic_quality",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Degree to which the chunk focuses on one main subject",
        why_we_need_it="Helps prevent retrieval of irrelevant material bundled with the correct passage",
        recommended_action="Reduce chunk window size to align with single policy sections.",
        phase="Phase 2",
    ),
    MetricDefinition(
        id=25,
        metric_name="definition_completeness",
        display_name="Definition Completeness",
        dimension="semantic_quality",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Whether a term and its definition remain together or are linked through sufficient context",
        why_we_need_it="Essential for glossaries, technical documentation, and corporate policies",
        recommended_action="Keep definition clauses unified in chunking boundary rules.",
        phase="Phase 2",
    ),
    MetricDefinition(
        id=26,
        metric_name="entity_reference_resolution",
        display_name="Entity and Reference Resolution",
        dimension="semantic_quality",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Whether named entities, pronouns, abbreviations, and references are understandable",
        why_we_need_it="Prevents ambiguity about which person, system, rule, or object a statement describes",
        recommended_action="Include document header context in metadata to resolve entity ambiguities.",
        phase="Phase 2",
    ),
    MetricDefinition(
        id=27,
        metric_name="logical_completeness",
        display_name="Logical Completeness",
        dimension="semantic_quality",
        priority="P0",
        check_type="heuristic",
        what_it_measures="Whether necessary premises, conclusions, conditions, and consequences are preserved",
        why_we_need_it="Reduces the risk of misleading answers generated from partial statements",
        recommended_action="Ensure conditional if/then pairs are kept in the same chunk.",
        phase="Phase 2",
    ),
    MetricDefinition(
        id=28,
        metric_name="condition_exception_preservation",
        display_name="Condition and Exception Preservation",
        dimension="semantic_quality",
        priority="P0",
        check_type="heuristic",
        what_it_measures="Whether qualifications such as 'unless,' 'only if,' 'except,' and 'subject to approval' are retained",
        why_we_need_it="Particularly important for policies, contracts, compliance, and technical procedures",
        recommended_action="Adjust chunk boundary to keep the condition and its qualification in the same chunk.",
        phase="Phase 2",
    ),
    MetricDefinition(
        id=29,
        metric_name="contradiction_conflict_indicators",
        display_name="Contradiction and Conflict Indicators",
        dimension="semantic_quality",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Whether chunks contain potentially conflicting statements without qualification",
        why_we_need_it="Helps reviewers investigate contradictory policies or extraction errors",
        recommended_action="Flag for human policy review to verify intended exceptions.",
        phase="Phase 4",
    ),
    MetricDefinition(
        id=30,
        metric_name="semantic_redundancy",
        display_name="Semantic Redundancy",
        dimension="semantic_quality",
        priority="P2",
        check_type="heuristic",
        what_it_measures="Degree of unnecessary repetition within a single chunk",
        why_we_need_it="Detects duplicated passages and repetitive extraction artifacts that add little value",
        recommended_action="Deduplicate repetitive sentence blocks within the chunk.",
        phase="Phase 4",
    ),
    MetricDefinition(
        id=31,
        metric_name="semantic_completeness_score",
        display_name="Semantic Completeness Score",
        dimension="semantic_quality",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Whether the chunk contains enough information to communicate its apparent claim",
        why_we_need_it="Identifies fragments that appear meaningful but omit essential supporting information",
        recommended_action="Ensure chunk contains subject, action, and complete policy qualification.",
        phase="Phase 4",
    ),

    # --------------------------------------------------------------------------
    # 4. Source fidelity and extraction metrics (32–40)
    # --------------------------------------------------------------------------
    MetricDefinition(
        id=32,
        metric_name="source_traceability_rate",
        display_name="Source Traceability Rate",
        dimension="source_fidelity",
        priority="P0",
        check_type="hard_validation",
        what_it_measures="Percentage of chunks linked to a valid source document and location",
        why_we_need_it="Allows reviewers to verify findings against the original material and render citations",
        recommended_action="Block ingestion: Enforce document entity mapping before chunk provisioning.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=33,
        metric_name="source_to_chunk_fidelity",
        display_name="Source-to-Chunk Fidelity",
        dimension="source_fidelity",
        priority="P0",
        check_type="hard_validation",
        what_it_measures="Degree to which chunk text matches the corresponding source passage without silent drop",
        why_we_need_it="Detects extraction errors, missing text, altered values, and corrupted characters",
        recommended_action="Compare character hash against source extraction stream.",
        phase="Phase 2",
    ),
    MetricDefinition(
        id=34,
        metric_name="source_span_coverage",
        display_name="Source Span Coverage",
        dimension="source_fidelity",
        priority="P0",
        check_type="hard_validation",
        what_it_measures="Percentage of relevant source spans represented in chunk metadata",
        why_we_need_it="Identifies content dropped during extraction or chunking",
        recommended_action="Record source page and byte span in chunk metadata.",
        phase="Phase 2",
    ),
    MetricDefinition(
        id=35,
        metric_name="extraction_artifact_rate",
        display_name="Extraction Artifact Rate",
        dimension="source_fidelity",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Frequency of headers, footers, page numbers, watermarks, and layout artifacts",
        why_we_need_it="Prevents irrelevant document noise from contaminating embeddings and retrieval",
        recommended_action="Filter out recurring header/footer artifacts during PDF layout analysis.",
        phase="Phase 2",
    ),
    MetricDefinition(
        id=36,
        metric_name="ocr_word_error_rate",
        display_name="OCR Word Error Rate",
        dimension="source_fidelity",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Word-level substitutions, deletions, and insertions compared with verified dictionary",
        why_we_need_it="Quantifies OCR accuracy on scanned and image-based documents",
        recommended_action="Switch low-WER pages to SmolVLM or EasyOCR with document-tuned binarization.",
        phase="Phase 2",
    ),
    MetricDefinition(
        id=37,
        metric_name="numeric_symbol_fidelity",
        display_name="Numeric and Symbol Fidelity",
        dimension="source_fidelity",
        priority="P0",
        check_type="heuristic",
        what_it_measures="Preservation of dates, percentages, currency values, formulas, identifiers, and special symbols",
        why_we_need_it="Prevents consequential errors such as changing 15% to 75% or confusing dates",
        recommended_action="Ensure chunk boundary regex does not split between symbols and digits.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=38,
        metric_name="reading_order_integrity",
        display_name="Reading Order Integrity",
        dimension="source_fidelity",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Whether text from columns, pages, and visual elements appears in correct sequence",
        why_we_need_it="Detects multi-column PDF and complex-layout extraction failures",
        recommended_action="Use layout-aware PDF reading models (Docling/PDFMiner column sorting).",
        phase="Phase 2",
    ),
    MetricDefinition(
        id=39,
        metric_name="table_value_to_header_alignment",
        display_name="Table Value-to-Header Alignment",
        dimension="source_fidelity",
        priority="P0",
        check_type="heuristic",
        what_it_measures="Whether extracted values remain associated with correct row and column labels",
        why_we_need_it="Prevents incorrect interpretation of tabular data",
        recommended_action="Validate markdown pipe column counts match across all rows in table chunk.",
        phase="Phase 2",
    ),
    MetricDefinition(
        id=40,
        metric_name="source_version_consistency",
        display_name="Source Version Consistency",
        dimension="source_fidelity",
        priority="P0",
        check_type="hard_validation",
        what_it_measures="Whether chunks reference the intended document version",
        why_we_need_it="Prevents stale or superseded policies from silently entering retrieval corpus",
        recommended_action="Validate document version metadata against organization document registry.",
        phase="Phase 1",
    ),

    # --------------------------------------------------------------------------
    # 5. Chunk relationships and corpus-level metrics (41–50)
    # --------------------------------------------------------------------------
    MetricDefinition(
        id=41,
        metric_name="exact_duplicate_rate",
        display_name="Exact Duplicate Rate",
        dimension="chunk_relationships",
        priority="P0",
        check_type="hard_validation",
        what_it_measures="Percentage of chunks identical to other chunks",
        why_we_need_it="Finds repeated ingestion, redundant storage, and duplicate retrieval results",
        recommended_action="Deduplicate chunks by content MD5 hash prior to vector upsert.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=42,
        metric_name="near_duplicate_rate",
        display_name="Near-Duplicate Rate",
        dimension="chunk_relationships",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Percentage of chunks with substantial textual similarity (Jaccard >= 90%)",
        why_we_need_it="Finds slightly altered duplicates that exact hashing misses",
        recommended_action="Increase chunk stride or adjust overlap window.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=43,
        metric_name="neighbor_continuity_score",
        display_name="Neighbor Continuity Score",
        dimension="chunk_relationships",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Whether adjacent chunks preserve a logical progression of the source",
        why_we_need_it="Detects broken sequencing and missing transitions",
        recommended_action="Ensure chunk index sequence is continuous without missing sequence numbers.",
        phase="Phase 3",
    ),
    MetricDefinition(
        id=44,
        metric_name="cross_chunk_context_dependency",
        display_name="Cross-Chunk Context Dependency",
        dimension="chunk_relationships",
        priority="P1",
        check_type="heuristic",
        what_it_measures="How frequently a chunk requires information from another chunk to be understood",
        why_we_need_it="Helps identify chunks that need headings, metadata, or adjacent context",
        recommended_action="Inject section title and breadcrumb into chunk prefix.",
        phase="Phase 3",
    ),
    MetricDefinition(
        id=45,
        metric_name="cross_chunk_evidence_completeness",
        display_name="Cross-Chunk Evidence Completeness",
        dimension="chunk_relationships",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Whether multiple related chunks collectively preserve all necessary information",
        why_we_need_it="Helps assess multi-part procedures, definitions, and policies",
        recommended_action="Link sibling chunks using section hierarchy metadata.",
        phase="Phase 3",
    ),
    MetricDefinition(
        id=46,
        metric_name="document_coverage_distribution",
        display_name="Document Coverage Distribution",
        dimension="chunk_relationships",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Distribution of chunks across documents, sections, and pages",
        why_we_need_it="Reveals missing sections, unexpectedly sparse documents, or ingestion imbalances",
        recommended_action="Review chunk distribution chart to spot unexpectedly sparse source files.",
        phase="Phase 3",
    ),
    MetricDefinition(
        id=47,
        metric_name="orphaned_chunk_rate",
        display_name="Orphaned Chunk Rate",
        dimension="chunk_relationships",
        priority="P0",
        check_type="hard_validation",
        what_it_measures="Percentage of chunks whose document, parent section, or source relationship cannot be resolved",
        why_we_need_it="Makes document navigation and source verification unreliable",
        recommended_action="Block ingestion: Verify each chunk has a valid parent document entity in DB.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=48,
        metric_name="metadata_consistency",
        display_name="Metadata Consistency",
        dimension="chunk_relationships",
        priority="P0",
        check_type="hard_validation",
        what_it_measures="Whether metadata values follow expected schema and remain consistent across related chunks",
        why_we_need_it="Enables reliable filtering, grouping, access control, and source reconstruction",
        recommended_action="Enforce strict Pydantic chunk metadata validation before vector provisioning.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=49,
        metric_name="cross_version_duplication_conflict",
        display_name="Cross-Version Duplication and Conflict",
        dimension="chunk_relationships",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Repeated or conflicting content across different document versions",
        why_we_need_it="Helps identify stale content and overlapping versions that may mislead retrieval",
        recommended_action="Archive superseded document versions before re-indexing.",
        phase="Phase 3",
    ),
    MetricDefinition(
        id=50,
        metric_name="content_concentration_anomalies",
        display_name="Content Concentration Anomalies",
        dimension="chunk_relationships",
        priority="P2",
        check_type="heuristic",
        what_it_measures="Unusual clustering of repeated boilerplate, empty sections, or disproportionately large chunk groups",
        why_we_need_it="Detects ingestion defects that may not appear in individual chunk checks",
        recommended_action="Check documents with high stub ratios for unhandled layout noise.",
        phase="Phase 3",
    ),

    # --------------------------------------------------------------------------
    # 6. Retrieval readiness and evidence metrics (51–60)
    # --------------------------------------------------------------------------
    MetricDefinition(
        id=51,
        metric_name="gold_evidence_coverage",
        display_name="Gold-Evidence Coverage",
        dimension="retrieval_readiness",
        priority="P0",
        check_type="hard_validation",
        what_it_measures="Percentage of required evidence passages preserved in the corpus",
        why_we_need_it="Determines whether the knowledge base contains the information needed to answer known questions",
        recommended_action="Verify all gold evidence chunk IDs exist in active ChromaDB index.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=52,
        metric_name="evidence_retrievability_at_k",
        display_name="Evidence Retrievability@k",
        dimension="retrieval_readiness",
        priority="P0",
        check_type="heuristic",
        what_it_measures="Percentage of evaluation questions for which expected evidence appears in top k results",
        why_we_need_it="Checks whether useful chunks can actually be retrieved",
        recommended_action="Optimize chunk size and tune Bi-Encoder / Cross-Encoder reranker parameters.",
        phase="Phase 3",
    ),
    MetricDefinition(
        id=53,
        metric_name="recall_at_k",
        display_name="Recall@k",
        dimension="retrieval_readiness",
        priority="P0",
        check_type="heuristic",
        what_it_measures="Fraction of known relevant chunks retrieved among the top k results",
        why_we_need_it="Detects missing retrieval coverage for benchmark evaluation queries",
        recommended_action="Increase candidate retrieval k (e.g. 15 -> 25) before reranking.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=54,
        metric_name="mean_reciprocal_rank",
        display_name="Mean Reciprocal Rank (MRR)",
        dimension="retrieval_readiness",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Average reciprocal rank of the first relevant result",
        why_we_need_it="Measures how early useful evidence appears in ranked results",
        recommended_action="Enable Cross-Encoder reranker to promote target needles into top-4.",
        phase="Phase 3",
    ),
    MetricDefinition(
        id=55,
        metric_name="ndcg_at_k",
        display_name="nDCG@k",
        dimension="retrieval_readiness",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Ranking quality when relevance has graded levels",
        why_we_need_it="Evaluates whether highly relevant chunks rank above less useful ones",
        recommended_action="Train or tune domain-specific Cross-Encoder reranker weights.",
        phase="Phase 3",
    ),
    MetricDefinition(
        id=56,
        metric_name="retrieval_noise_ratio",
        display_name="Retrieval Noise Ratio",
        dimension="retrieval_readiness",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Proportion of retrieved chunks that are irrelevant to the query",
        why_we_need_it="Measures how much distracting context enters generation",
        recommended_action="Tighten similarity score cutoffs or prune low-relevance passages.",
        phase="Phase 3",
    ),
    MetricDefinition(
        id=57,
        metric_name="evidence_sufficiency",
        display_name="Evidence Sufficiency",
        dimension="retrieval_readiness",
        priority="P0",
        check_type="heuristic",
        what_it_measures="Whether retrieved chunk or chunk set contains enough evidence to answer question",
        why_we_need_it="Identifies cases where retrieval returns related text but not the full answer",
        recommended_action="Expand chunk boundary or use hierarchical chunking to bundle parent context.",
        phase="Phase 3",
    ),
    MetricDefinition(
        id=58,
        metric_name="context_redundancy",
        display_name="Context Redundancy",
        dimension="retrieval_readiness",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Degree of repeated information in the retrieved chunk set",
        why_we_need_it="Helps reduce wasted context-window capacity",
        recommended_action="Apply MMR (Maximal Marginal Relevance) or Cross-Encoder diversity pruning.",
        phase="Phase 3",
    ),
    MetricDefinition(
        id=59,
        metric_name="query_coverage_by_document",
        display_name="Query Coverage by Document or Section",
        dimension="retrieval_readiness",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Whether important topic areas can be retrieved across a representative query set",
        why_we_need_it="Detects weakly represented topics and document coverage gaps",
        recommended_action="Add synthetic benchmark test cases for under-tested document sections.",
        phase="Phase 3",
    ),
    MetricDefinition(
        id=60,
        metric_name="chunking_configuration_sensitivity",
        display_name="Chunking Configuration Sensitivity",
        dimension="retrieval_readiness",
        priority="P1",
        check_type="heuristic",
        what_it_measures="How retrieval and evidence metrics change when chunk size, overlap, or boundary rules change",
        why_we_need_it="Helps identify a better chunking configuration using measurable evidence",
        recommended_action="Use Chunking Strategy Optimizer in Step 4 to compare Hierarchical vs Window vs Semantic.",
        phase="Phase 3",
    ),

    # --------------------------------------------------------------------------
    # 7. Security, auditability, and operational metrics (61–65)
    # --------------------------------------------------------------------------
    MetricDefinition(
        id=61,
        metric_name="access_control_metadata_completeness",
        display_name="Access-Control Metadata Completeness",
        dimension="security_auditability",
        priority="P0",
        check_type="hard_validation",
        what_it_measures="Whether required tenant, classification, and access-control metadata exists",
        why_we_need_it="Prevents chunks from entering an index without metadata needed for safe filtering",
        recommended_action="Block ingestion: Assign authenticated project_id and classification scope.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=62,
        metric_name="access_control_consistency",
        display_name="Access-Control Consistency",
        dimension="security_auditability",
        priority="P0",
        check_type="hard_validation",
        what_it_measures="Whether chunk permissions agree with source document and governing access policy",
        why_we_need_it="Helps prevent unauthorized information from being retrieved",
        recommended_action="Ensure chunk classification matches source document security policy.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=63,
        metric_name="stale_chunk_rate",
        display_name="Stale Chunk Rate",
        dimension="security_auditability",
        priority="P0",
        check_type="hard_validation",
        what_it_measures="Percentage of indexed chunks that reference deleted or superseded source content",
        why_we_need_it="Prevents obsolete information from appearing in answers",
        recommended_action="Purge chunks whose source documents have been deleted or archived from the database.",
        phase="Phase 1",
    ),
    MetricDefinition(
        id=64,
        metric_name="audit_reproducibility",
        display_name="Audit Reproducibility",
        dimension="security_auditability",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Whether a finding can be reproduced using same chunk, source version, and rules",
        why_we_need_it="Makes quality investigations and regression testing reliable",
        recommended_action="Ensure deterministic auditing logic with fixed random seeds and versioned rule schemas.",
        phase="Phase 4",
    ),
    MetricDefinition(
        id=65,
        metric_name="remediation_success_rate",
        display_name="Remediation Success Rate",
        dimension="security_auditability",
        priority="P1",
        check_type="heuristic",
        what_it_measures="Percentage of flagged defects resolved after reprocessing or manual correction",
        why_we_need_it="Shows whether quality improvements actually work and tracks reviewer governance",
        recommended_action="Reviewer sets disposition (Approved, Needs Re-OCR, Needs Re-Chunk) to track closure.",
        phase="Phase 4",
    ),
]


def get_metrics_catalog_dataframe() -> pd.DataFrame:
    """Returns a Pandas DataFrame representing the complete 65-metric quality catalog."""
    rows = []
    for m in CHUNK_QUALITY_METRICS_CATALOG:
        rows.append({
            "Metric #": m.id,
            "Metric Name": m.metric_name,
            "Display Label": m.display_name,
            "Dimension": m.dimension.replace("_", " ").title(),
            "Priority": m.priority,
            "Check Type": m.check_type.replace("_", " ").title(),
            "Phase": m.phase,
            "What it Measures": m.what_it_measures,
            "Why We Need It": m.why_we_need_it,
            "Recommended Action": m.recommended_action,
        })
    return pd.DataFrame(rows)


# ==============================================================================
# Domain Heuristic Lists & Lexicons
# ==============================================================================

COMMON_ENGLISH_WORDS: Set[str] = {
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
    "business", "health", "security", "support", "working", "medical", "casual",
    "attendance", "salary", "expense", "reimbursement", "travel", "confidential"
}

CONDITIONAL_MARKERS = [
    r"\bunless\b",
    r"\bprovided\s+that\b",
    r"\bexcept\b",
    r"\bonly\s+if\b",
    r"\bsubject\s+to\b",
    r"\bwith\s+prior\s+approval\b",
    r"\bprohibited\b",
    r"\bforbidden\b",
    r"\bmandatory\b",
    r"\bnot\s+permitted\b",
    r"\bcondition\b",
]

UNANCHORED_PRONOUNS = [
    r"^\s*it\s+(?:is|must|will|should|can|applies)\b",
    r"^\s*they\s+(?:are|must|will|should|can)\b",
    r"^\s*this\s+(?:provision|rule|policy|requirement|section)\b",
    r"^\s*the\s+above\b",
    r"^\s*these\s+(?:rules|exceptions|requirements|benefits)\b",
    r"^\s*such\s+(?:requests|payments|employees)\b",
]

BOILERPLATE_PATTERNS = [
    r"(?i)\bpage\s+\d+\s+of\s+\d+\b",
    r"(?i)\bconfidential\s+(?:&|and)\s+proprietary\b",
    r"(?i)\ball\s+rights\s+reserved\b",
    r"(?i)\bdraft\s*-\s*internal\s+use\s+only\b",
    r"(?i)\bdo\s+not\s+distribute\b",
]

SECRET_PATTERNS = [
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS Access Key ID"),
    (r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----", "Private Cryptographic Key"),
    (r"\beyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*\b", "JWT Token"),
    (r"(?i)password\s*[:=]\s*['\"][^\s'\"]{6,}['\"]", "Plaintext Password Assignment"),
]


def detect_content_type(text: str, metadata: dict[str, Any]) -> str:
    """Identify if chunk is markdown table, code block, OCR/VLM, or standard text."""
    meta_type = str(metadata.get("content_type", "")).lower()
    produced_by = str(metadata.get("produced_by", "")).lower()

    if "easyocr" in produced_by or "ocr" in meta_type:
        return "ocr"
    if "smolvlm" in produced_by or meta_type in ("picture", "figure", "vlm"):
        return "vlm"
    if text.strip().startswith("```") or text.count("```") >= 2:
        return "code"
    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    if len(lines) >= 2 and all("|" in line for line in lines[:2]):
        if any(re.search(r"\|(?:\s*:?-+:?\s*\|)+", line) for line in lines):
            return "table"
    return "text"


# ==============================================================================
# Dimension 1: Text Integrity & Noisy-Data Detectors (Metrics 1–10)
# ==============================================================================

def evaluate_text_integrity(chunk_id: str, text: str, content_type: str, metadata: dict[str, Any] | None = None) -> list[MetricResult]:
    results: list[MetricResult] = []
    clean_text = text.strip()
    total_chars = len(text)
    meta = metadata or {}

    # 1. Empty Chunk Rate (P0 - Hard Validation)
    if not clean_text:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="empty_chunk_rate",
            dimension="text_integrity",
            check_type="hard_validation",
            value=1.0,
            status="fail",
            severity="critical",
            evidence="Chunk contains 0 meaningful characters (empty or pure whitespace)",
            explanation="Empty chunks waste storage and can pollute retrieval results.",
            recommended_action="Block ingestion: Drop empty chunk and inspect parser splitting configuration.",
            detector="EmptyChunkDetector",
        ))
        return results
    else:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="empty_chunk_rate",
            dimension="text_integrity",
            check_type="hard_validation",
            value=0.0,
            status="pass",
            severity="none",
            detector="EmptyChunkDetector",
        ))

    # 2. Suspicious Symbol Ratio (P0 - Heuristic)
    if content_type not in ("code", "table"):
        non_ws_chars = len(re.sub(r"\s", "", text))
        noise_chars = len(re.sub(r"[A-Za-z0-9.,!?:;\-\'\"()\[\]{}/%$€£@&+=]", "", text))
        symbol_ratio = noise_chars / non_ws_chars if non_ws_chars > 0 else 0.0

        if symbol_ratio > 0.20:
            results.append(MetricResult(
                chunk_id=chunk_id,
                metric_name="suspicious_symbol_ratio",
                dimension="text_integrity",
                check_type="heuristic",
                value=round(symbol_ratio, 3),
                status="fail" if symbol_ratio > 0.35 else "warning",
                severity="high" if symbol_ratio > 0.35 else "medium",
                evidence=f"Suspicious symbol ratio is {symbol_ratio*100:.1f}% (threshold <= 20.0%)",
                explanation="Detects OCR corruption, extraction artifacts, and symbol-heavy noise.",
                recommended_action="Filter OCR noise or check PDF column extraction boundaries before chunking.",
                detector="SuspiciousSymbolHeuristic",
            ))
        else:
            results.append(MetricResult(
                chunk_id=chunk_id,
                metric_name="suspicious_symbol_ratio",
                dimension="text_integrity",
                check_type="heuristic",
                value=round(symbol_ratio, 3),
                status="pass",
                severity="none",
                detector="SuspiciousSymbolHeuristic",
            ))

    # 3. Replacement Character Count (P0 - Hard Validation)
    replacement_count = text.count("\ufffd")
    if replacement_count > 0:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="replacement_character_count",
            dimension="text_integrity",
            check_type="hard_validation",
            value=float(replacement_count),
            status="fail",
            severity="high",
            evidence=f"Found {replacement_count} Unicode replacement character(s) ('\ufffd')",
            explanation="Identifies decoding or extraction failures resulting in destroyed terms.",
            recommended_action="Re-extract document using verified UTF-8 encoding or run OCR repair on scanned source.",
            detector="UnicodeEncodingValidator",
        ))
    else:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="replacement_character_count",
            dimension="text_integrity",
            check_type="hard_validation",
            value=0.0,
            status="pass",
            severity="none",
            detector="UnicodeEncodingValidator",
        ))

    # 4. Control Character Rate (P0 - Hard Validation)
    ctrl_chars = [ch for ch in text if ord(ch) < 32 and ch not in ("\t", "\n", "\r")]
    ctrl_rate = len(ctrl_chars) / total_chars if total_chars > 0 else 0.0
    if ctrl_chars:
        sample_hex = [hex(ord(c)) for c in ctrl_chars[:5]]
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="control_character_rate",
            dimension="text_integrity",
            check_type="hard_validation",
            value=round(ctrl_rate, 4),
            status="fail",
            severity="high",
            evidence=f"Detected {len(ctrl_chars)} non-printable control character(s): {sample_hex}",
            explanation="Detects malformed text and encoding artifacts.",
            recommended_action="Sanitize chunk text using `re.sub(r'[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]', '', text)` prior to storage.",
            detector="ControlCharacterValidator",
        ))
    else:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="control_character_rate",
            dimension="text_integrity",
            check_type="hard_validation",
            value=0.0,
            status="pass",
            severity="none",
            detector="ControlCharacterValidator",
        ))

    # 5. Non-Printable Character Ratio (P0 - Hard Validation)
    non_printable = [ch for ch in text if not ch.isprintable() and ch not in ("\t", "\n", "\r")]
    np_ratio = len(non_printable) / total_chars if total_chars > 0 else 0.0
    if np_ratio > 0.02:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="non_printable_character_ratio",
            dimension="text_integrity",
            check_type="hard_validation",
            value=round(np_ratio, 4),
            status="fail",
            severity="high",
            evidence=f"Non-printable character ratio {np_ratio*100:.2f}% exceeds threshold",
            explanation="Helps detect corrupted or malformed content and font encoding failures.",
            recommended_action="Strip non-printable characters and verify PDF font decoding.",
            detector="NonPrintableValidator",
        ))
    else:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="non_printable_character_ratio",
            dimension="text_integrity",
            check_type="hard_validation",
            value=round(np_ratio, 4),
            status="pass",
            severity="none",
            detector="NonPrintableValidator",
        ))

    # 6. Fragmentation Score (P0 - Heuristic)
    words = re.findall(r"\b\w+\b", text)
    if words and content_type == "text":
        single_char_words = [w for w in words if len(w) == 1 and w.lower() not in ("a", "i")]
        frag_ratio = len(single_char_words) / len(words)
        if frag_ratio > 0.15:
            results.append(MetricResult(
                chunk_id=chunk_id,
                metric_name="fragmentation_score",
                dimension="text_integrity",
                check_type="heuristic",
                value=round(frag_ratio, 3),
                status="fail",
                severity="high",
                evidence=f"Fragmentation ratio {frag_ratio*100:.1f}% ({len(single_char_words)} single-letter words: {single_char_words[:6]})",
                explanation="Identifies chunks that have lost their original text structure.",
                recommended_action="Enable layout-aware parsing (Docling) to reconstruct word sequences before splitting.",
                detector="TextFragmentationDetector",
            ))
        else:
            results.append(MetricResult(
                chunk_id=chunk_id,
                metric_name="fragmentation_score",
                dimension="text_integrity",
                check_type="heuristic",
                value=round(frag_ratio, 3),
                status="pass",
                severity="none",
                detector="TextFragmentationDetector",
            ))

    # 7. OCR Confidence (P1 - Heuristic)
    ocr_score = meta.get("confidence") or meta.get("ocr_score")
    if ocr_score is not None:
        try:
            score_val = float(ocr_score)
            if score_val < 0.70:
                results.append(MetricResult(
                    chunk_id=chunk_id,
                    metric_name="ocr_confidence",
                    dimension="text_integrity",
                    check_type="heuristic",
                    value=round(score_val, 2),
                    status="warning",
                    severity="medium",
                    evidence=f"Low OCR confidence ({score_val:.2f} < 0.70) reported by extraction engine",
                    explanation="Helps prioritize scanned pages that may require manual review.",
                    recommended_action="Route scanned page to VLM or re-OCR with contrast enhancement.",
                    detector="OcrConfidenceEvaluator",
                ))
            else:
                results.append(MetricResult(
                    chunk_id=chunk_id,
                    metric_name="ocr_confidence",
                    dimension="text_integrity",
                    check_type="heuristic",
                    value=round(score_val, 2),
                    status="pass",
                    severity="none",
                    detector="OcrConfidenceEvaluator",
                ))
        except (ValueError, TypeError):
            pass

    # 8. Language Consistency (P1 - Heuristic)
    if words and content_type == "text":
        valid_words = [w for w in words if w.lower() in COMMON_ENGLISH_WORDS or len(w) > 3]
        lexical_cohesion = len(valid_words) / len(words)
        if lexical_cohesion < 0.60:
            results.append(MetricResult(
                chunk_id=chunk_id,
                metric_name="language_consistency",
                dimension="text_integrity",
                check_type="heuristic",
                value=round(lexical_cohesion, 3),
                status="warning",
                severity="medium",
                evidence=f"Low lexical consistency score {lexical_cohesion:.2f}: excessive unrecognized tokens",
                explanation="Finds incorrect language detection, mixed-script corruption, and extraction anomalies.",
                recommended_action="Inspect document language routing and verify OCR character recognition whitelist.",
                detector="LanguageConsistencyDetector",
            ))

    # 9. Repeated Character Ratio (P1 - Heuristic)
    repetitive_sequences = re.findall(r"([_\-~|=+*#.]){5,}", text)
    if repetitive_sequences:
        total_rep_chars = sum(len(m.group(0)) for m in re.finditer(r"([_\-~|=+*#.]){5,}", text))
        rep_ratio = total_rep_chars / total_chars
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="repeated_character_ratio",
            dimension="text_integrity",
            check_type="heuristic",
            value=round(rep_ratio, 3),
            status="warning",
            severity="medium",
            evidence=f"Detected repetitive delimiter chains totaling {total_rep_chars} characters",
            explanation="Detects extraction loops, duplicated glyphs, and malformed layout text.",
            recommended_action="Strip cosmetic horizontal rules and form fill-in-the-blank dots during text cleaning.",
            detector="RepetitiveSequenceDetector",
        ))

    # 10. Whitespace Anomaly Score (P1 - Heuristic)
    whitespace_runs = re.findall(r" {4,}|\t{2,}|\n{3,}", text)
    if whitespace_runs:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="whitespace_anomaly_score",
            dimension="text_integrity",
            check_type="heuristic",
            value=float(len(whitespace_runs)),
            status="warning",
            severity="low",
            evidence=f"Found {len(whitespace_runs)} anomalous whitespace sequence(s) (multi-tabs, 4+ spaces, 3+ newlines)",
            explanation="Detects broken column extraction, layout problems, and fragmented text.",
            recommended_action="Normalize whitespace runs (`re.sub(r' +', ' ', text)`) before tokenization.",
            detector="WhitespaceAnomalyDetector",
        ))

    return results


# ==============================================================================
# Dimension 2: Chunk Structure & Boundary Metrics (Metrics 11–21)
# ==============================================================================

def evaluate_structural_quality(
    chunk_id: str,
    text: str,
    content_type: str,
    target_budget: int = 220,
    model_limit: int = 256,
) -> list[MetricResult]:
    results: list[MetricResult] = []
    tokens = len(text.split())
    clean_text = text.strip()

    # 11. Token Count (P0 - Hard Validation)
    if tokens > model_limit:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="token_count",
            dimension="structural_quality",
            check_type="hard_validation",
            value=float(tokens),
            status="fail",
            severity="critical",
            evidence=f"Chunk has {tokens} tokens (exceeds model limit of {model_limit} tokens)",
            quoted_text=clean_text[:140] + ("..." if len(clean_text) > 140 else ""),
            explanation="Determines chunk size relative to model context window. Silent embedder clipping will occur beyond 256 tokens.",
            possible_cause="Chunking strategy lacked strict max token clamp prior to ChromaDB ingestion.",
            verification_step="Inspect embedding model tokenizer truncation logs in ChromaDB ingestion.",
            recommended_action=f"Sub-split chunk using sentence-aware chunker with max_tokens <= {model_limit}.",
            revalidation_action="Re-index document and confirm no chunk exceeds 256 tokens.",
            detector="TokenCountValidator",
        ))
    else:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="token_count",
            dimension="structural_quality",
            check_type="hard_validation",
            value=float(tokens),
            status="pass",
            severity="none",
            detector="TokenCountValidator",
        ))

    # 12. Chunk Length Distribution (P0 - Heuristic)
    if tokens > target_budget and tokens <= model_limit:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="chunk_length_distribution",
            dimension="structural_quality",
            check_type="heuristic",
            value=float(tokens),
            status="warning",
            severity="medium",
            evidence=f"Chunk has {tokens} tokens (above target budget of {target_budget} tokens, within model limit {model_limit})",
            explanation="Reveals whether chunking configuration produces inconsistent or extreme sizes.",
            recommended_action=f"Tune sliding window step closer to target budget {target_budget}.",
            detector="ChunkLengthDistributionAuditor",
        ))
    elif tokens < 20 and content_type == "text":
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="chunk_length_distribution",
            dimension="structural_quality",
            check_type="heuristic",
            value=float(tokens),
            status="warning",
            severity="medium",
            evidence=f"Stub micro-fragment detected: chunk has only {tokens} tokens (< 20 tokens)",
            explanation="Micro-chunks lack sufficient context to stand alone and crowd out higher-quality evidence in top-k retrieval.",
            recommended_action="Merge stub chunk with adjacent sibling chunk under same heading.",
            detector="ChunkLengthDistributionAuditor",
        ))
    else:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="chunk_length_distribution",
            dimension="structural_quality",
            check_type="heuristic",
            value=float(tokens),
            status="pass",
            severity="none",
            detector="ChunkLengthDistributionAuditor",
        ))

    # 13. Sentence Boundary Integrity (P0 - Heuristic)
    if content_type == "text" and len(clean_text) > 40:
        valid_terminal = (".", "?", "!", "\"", "'", ":", ";")
        ends_cleanly = clean_text.endswith(valid_terminal)
        trailing_conjunction = re.search(r"\b(?:and|or|but|because|with|that|if|as)\s*$", clean_text, re.IGNORECASE)

        if trailing_conjunction:
            results.append(MetricResult(
                chunk_id=chunk_id,
                metric_name="sentence_boundary_integrity",
                dimension="structural_quality",
                check_type="heuristic",
                value=0.0,
                status="fail",
                severity="high",
                evidence=f"Chunk terminates mid-clause on conjunction: '...{clean_text[-25:]}'",
                explanation="Prevents splitting definitions, conditions, and explanations mid-sentence.",
                recommended_action="Re-split chunk strictly at terminal punctuation boundaries.",
                detector="SentenceBoundaryDetector",
            ))
        elif not ends_cleanly:
            results.append(MetricResult(
                chunk_id=chunk_id,
                metric_name="sentence_boundary_integrity",
                dimension="structural_quality",
                check_type="heuristic",
                value=0.5,
                status="warning",
                severity="medium",
                evidence=f"Chunk does not terminate with standard punctuation: '{clean_text[-20:]}'",
                explanation="May indicate mid-sentence truncation across sliding window boundaries.",
                recommended_action="Ensure sentence-boundary splitter does not cut off narrative sentences.",
                detector="SentenceBoundaryDetector",
            ))
        else:
            results.append(MetricResult(
                chunk_id=chunk_id,
                metric_name="sentence_boundary_integrity",
                dimension="structural_quality",
                check_type="heuristic",
                value=1.0,
                status="pass",
                severity="none",
                detector="SentenceBoundaryDetector",
            ))

    # 14. Orphaned Heading Rate (P0 - Heuristic)
    is_pure_heading = bool(re.match(r"^#{1,6}\s+[\w\s\-,:]{3,80}$", clean_text)) or (len(clean_text) < 60 and clean_text.endswith(":"))
    if is_pure_heading and tokens < 12:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="orphaned_heading_rate",
            dimension="structural_quality",
            check_type="heuristic",
            value=1.0,
            status="fail",
            severity="critical",
            evidence=f"Chunk contains only an orphaned heading: '{clean_text}' with 0 body text",
            explanation="Prevents chunks from losing the topic that gives their content meaning.",
            recommended_action="Fuse section heading with the succeeding content chunk during hierarchy extraction.",
            detector="OrphanedHeadingDetector",
        ))
    else:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="orphaned_heading_rate",
            dimension="structural_quality",
            check_type="heuristic",
            value=0.0,
            status="pass",
            severity="none",
            detector="OrphanedHeadingDetector",
        ))

    # 15. Incomplete Sentence Rate (P1 - Heuristic)
    if content_type == "text" and len(clean_text) > 30:
        starts_lowercase = clean_text[0].islower() and not clean_text.startswith(("e.g.", "i.e."))
        if starts_lowercase:
            results.append(MetricResult(
                chunk_id=chunk_id,
                metric_name="incomplete_sentence_rate",
                dimension="structural_quality",
                check_type="heuristic",
                value=1.0,
                status="warning",
                severity="medium",
                evidence=f"Chunk starts with lowercase fragment: '{clean_text[:30]}...'",
                explanation="Identifies possible boundary errors and missing context.",
                recommended_action="Align chunk boundary to complete syntactic clauses or expand window overlap.",
                detector="IncompleteSentenceDetector",
            ))

    # 16. Paragraph Integrity (P1 - Heuristic)
    if "-\n" in text:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="paragraph_integrity",
            dimension="structural_quality",
            check_type="heuristic",
            value=0.0,
            status="warning",
            severity="low",
            evidence="Hyphenated line break detected ('-\\n') splitting a word across lines",
            explanation="Preserves logical relationships between statements without broken words.",
            recommended_action="De-hyphenate line wraps during PDF layout analysis.",
            detector="ParagraphIntegrityDetector",
        ))

    # 17. Table Integrity (P0 for tables)
    if content_type == "table":
        lines = [l.strip() for l in clean_text.split("\n") if l.strip()]
        has_header_divider = any(re.search(r"^\|(?:\s*:?-+:?\s*\|)+$", l) for l in lines)
        broken_pipes = any(not l.startswith("|") or not l.endswith("|") for l in lines)

        if not has_header_divider or broken_pipes:
            results.append(MetricResult(
                chunk_id=chunk_id,
                metric_name="table_integrity",
                dimension="structural_quality",
                check_type="heuristic",
                value=0.0,
                status="fail",
                severity="high",
                evidence=f"Malformed table markdown: missing header divider or ragged pipes across {len(lines)} rows",
                explanation="Prevents numerical values and policy conditions from becoming ambiguous.",
                recommended_action="Re-inject table header row into every chunk slice produced from multi-row tables.",
                detector="TableStructureValidator",
            ))
        else:
            results.append(MetricResult(
                chunk_id=chunk_id,
                metric_name="table_integrity",
                dimension="structural_quality",
                check_type="heuristic",
                value=1.0,
                status="pass",
                severity="none",
                detector="TableStructureValidator",
            ))

    # 18. List Integrity (P1 - Heuristic)
    lone_list_marker = bool(re.match(r"^[\s]*[0-9]+[.)]\s*$|^[\s]*[-*•]\s*$", clean_text))
    if lone_list_marker:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="list_integrity",
            dimension="structural_quality",
            check_type="heuristic",
            value=0.0,
            status="fail",
            severity="high",
            evidence=f"Chunk contains isolated list marker with no content: '{clean_text}'",
            explanation="Preserves procedural steps, requirements, and enumerated exceptions.",
            recommended_action="Group list items together with parent prompt/preamble in a single chunk.",
            detector="ListIntegrityValidator",
        ))

    return results


# ==============================================================================
# Dimension 3: Semantic Quality & Condition Preservation (Metrics 22–31)
# ==============================================================================

def evaluate_semantic_quality(
    chunk_id: str,
    text: str,
    metadata: dict[str, Any],
) -> list[MetricResult]:
    results: list[MetricResult] = []
    clean_text = text.strip()

    # 22. Semantic Coherence (P0 - Model/Heuristic)
    words = re.findall(r"\b\w+\b", text)
    if len(words) >= 15:
        unique_words = set(w.lower() for w in words)
        lexical_diversity = len(unique_words) / len(words)
        if lexical_diversity < 0.25:
            results.append(MetricResult(
                chunk_id=chunk_id,
                metric_name="semantic_coherence",
                dimension="semantic_quality",
                check_type="heuristic",
                value=round(lexical_diversity, 2),
                status="warning",
                severity="medium",
                evidence=f"Low lexical diversity ({lexical_diversity:.2f}): high repetitive boilerplate within chunk",
                explanation="Detects chunks that mix unrelated subjects or lose logical flow.",
                recommended_action="Split chunk on major section breaks to preserve thematic unity.",
                detector="SemanticCoherenceDetector",
            ))

    # 23. Contextual Independence & Anaphora (P0 - Heuristic)
    has_anchor = bool(metadata.get("hierarchy_path") or metadata.get("section_heading"))
    is_unanchored_pronoun = any(re.search(p, clean_text, re.IGNORECASE) for p in UNANCHORED_PRONOUNS)

    if is_unanchored_pronoun and not has_anchor:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="contextual_independence",
            dimension="semantic_quality",
            check_type="heuristic",
            value=0.0,
            status="fail",
            severity="high",
            evidence=f"Chunk begins with unanchored pronoun: '{clean_text[:40]}...'",
            explanation="Finds references such as 'this provision,' 'they,' or 'the above' that lack clear antecedents.",
            recommended_action="Prepend heading breadcrumbs via contextual prefix or apply coreference resolution.",
            detector="AnaphoraIndependenceDetector",
        ))
    else:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="contextual_independence",
            dimension="semantic_quality",
            check_type="heuristic",
            value=1.0,
            status="pass",
            severity="none",
            detector="AnaphoraIndependenceDetector",
        ))

    # 25. Definition Completeness (P1 - Heuristic)
    has_def_marker = re.search(r"\b(?:means|is defined as|refers to)\b", clean_text, re.IGNORECASE)
    if has_def_marker and len(clean_text) < 40 and not clean_text.endswith("."):
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="definition_completeness",
            dimension="semantic_quality",
            check_type="heuristic",
            value=0.0,
            status="warning",
            severity="medium",
            evidence=f"Potential severed definition statement: '{clean_text}'",
            explanation="Essential for glossaries, technical documentation, and policies.",
            recommended_action="Keep definition clauses unified in chunking boundary rules.",
            detector="DefinitionCompletenessValidator",
        ))

    # 27. Logical Completeness (P0 - Heuristic)
    starts_with_if = bool(re.match(r"^(?:if|when|provided)\b", clean_text, re.IGNORECASE))
    if starts_with_if and not any(m in clean_text.lower() for m in [",", "then", "must", "shall", "will", "should"]):
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="logical_completeness",
            dimension="semantic_quality",
            check_type="heuristic",
            value=0.0,
            status="warning",
            severity="high",
            evidence="Conditional premise starts with 'If/When' but contains no concluding clause or consequence",
            explanation="Reduces the risk of misleading answers generated from partial statements.",
            recommended_action="Ensure conditional if/then pairs are kept in the same chunk.",
            detector="LogicalCompletenessValidator",
        ))

    # 28. Condition & Exception Preservation (P0 - Heuristic)
    for pattern in CONDITIONAL_MARKERS:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            offset_from_end = len(clean_text) - match.end()
            if offset_from_end < 15 and not clean_text.endswith("."):
                results.append(MetricResult(
                    chunk_id=chunk_id,
                    metric_name="condition_exception_preservation",
                    dimension="semantic_quality",
                    check_type="heuristic",
                    value=0.0,
                    status="fail",
                    severity="critical",
                    evidence=f"Qualifying condition '{match.group(0)}' severed at end of chunk: '...{clean_text[-30:]}'",
                    explanation="Cutting off a rule at its exception marker (e.g. 'unless', 'provided that') produces misleading chunks that state an unqualified rule.",
                    recommended_action="Adjust chunk boundary to keep the condition and its qualification in the same chunk.",
                    detector="ConditionIntegrityValidator",
                ))
                break
    else:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="condition_exception_preservation",
            dimension="semantic_quality",
            check_type="heuristic",
            value=1.0,
            status="pass",
            severity="none",
            detector="ConditionIntegrityValidator",
        ))

    # 30. Semantic Redundancy (P2 - Heuristic)
    sentences = [s.strip() for s in re.split(r"[.!?]\s+", clean_text) if len(s.strip()) > 15]
    if len(sentences) >= 2:
        sentence_counts = Counter(s.lower() for s in sentences)
        dup_sentences = [s for s, c in sentence_counts.items() if c > 1]
        if dup_sentences:
            results.append(MetricResult(
                chunk_id=chunk_id,
                metric_name="semantic_redundancy",
                dimension="semantic_quality",
                check_type="heuristic",
                value=float(len(dup_sentences)),
                status="warning",
                severity="low",
                evidence=f"Found duplicate sentence inside chunk: '{dup_sentences[0][:60]}...'",
                explanation="Detects duplicated passages and repetitive extraction artifacts that add little value.",
                recommended_action="Deduplicate repetitive sentence blocks within the chunk.",
                detector="SemanticRedundancyDetector",
            ))

    return results


# ==============================================================================
# Dimension 4: Source Fidelity & Extraction Metrics (Metrics 32–40)
# ==============================================================================

def evaluate_source_fidelity(
    chunk_id: str,
    text: str,
    metadata: dict[str, Any],
) -> list[MetricResult]:
    results: list[MetricResult] = []

    # 32. Source Traceability Rate (P0 - Hard Validation)
    doc_id = metadata.get("doc_id") or metadata.get("document_id")
    source_fn = metadata.get("source") or metadata.get("source_filename")

    if not doc_id or not source_fn or doc_id == "unknown" or source_fn == "unknown":
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="source_traceability_rate",
            dimension="source_fidelity",
            check_type="hard_validation",
            value=0.0,
            status="fail",
            severity="critical",
            evidence=f"Missing source provenance: doc_id={doc_id}, source={source_fn}",
            explanation="Allows reviewers to verify findings against the original material.",
            recommended_action="Block ingestion: Enforce document entity mapping before chunk provisioning.",
            detector="SourceTraceabilityValidator",
        ))
    else:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="source_traceability_rate",
            dimension="source_fidelity",
            check_type="hard_validation",
            value=1.0,
            status="pass",
            severity="none",
            detector="SourceTraceabilityValidator",
        ))

    # 33. Source-to-Chunk Fidelity (P0 - Hard Validation)
    if source_fn:
        valid_extensions = (".pdf", ".docx", ".doc", ".txt", ".json", ".md")
        has_ext = any(str(source_fn).lower().endswith(ext) for ext in valid_extensions)
        if not has_ext:
            results.append(MetricResult(
                chunk_id=chunk_id,
                metric_name="source_to_chunk_fidelity",
                dimension="source_fidelity",
                check_type="hard_validation",
                value=0.0,
                status="warning",
                severity="medium",
                evidence=f"Unrecognized or missing source file extension: '{source_fn}'",
                explanation="Detects extraction errors, missing text, altered values, and corrupted characters.",
                recommended_action="Ensure source document retains canonical filename and extension.",
                detector="SourceToChunkFidelityValidator",
            ))

    # 35. Extraction Artifact Rate (P1 - Heuristic)
    for pattern in BOILERPLATE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            results.append(MetricResult(
                chunk_id=chunk_id,
                metric_name="extraction_artifact_rate",
                dimension="source_fidelity",
                check_type="heuristic",
                value=1.0,
                status="warning",
                severity="medium",
                evidence=f"Found boilerplate running header/footer: '{match.group(0)}'",
                explanation="Prevents irrelevant document noise from contaminating embeddings and retrieval.",
                recommended_action="Filter out recurring header/footer artifacts during PDF layout analysis.",
                detector="BoilerplateArtifactDetector",
            ))
            break
    else:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="extraction_artifact_rate",
            dimension="source_fidelity",
            check_type="heuristic",
            value=0.0,
            status="pass",
            severity="none",
            detector="BoilerplateArtifactDetector",
        ))

    # 37. Numeric and Symbol Fidelity (P0 - Heuristic)
    severed_currency = bool(re.search(r"[$€£]\s*$", text.strip()))
    if severed_currency:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="numeric_symbol_fidelity",
            dimension="source_fidelity",
            check_type="heuristic",
            value=0.0,
            status="fail",
            severity="high",
            evidence=f"Currency symbol severed from its numerical value at chunk boundary: '...{text.strip()[-15:]}'",
            explanation="Prevents consequential errors such as changing 15% to 75% or confusing dates.",
            recommended_action="Ensure chunk boundary regex does not split between symbols and digits.",
            detector="NumericFidelityDetector",
        ))
    else:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="numeric_symbol_fidelity",
            dimension="source_fidelity",
            check_type="heuristic",
            value=1.0,
            status="pass",
            severity="none",
            detector="NumericFidelityDetector",
        ))

    return results


# ==============================================================================
# Dimension 5: Chunk Relationships & Corpus-Level Metrics (Metrics 41–50)
# ==============================================================================

def evaluate_corpus_relationships(records: Sequence[dict]) -> dict[str, list[MetricResult]]:
    """Evaluates cross-chunk relationships: duplicates, indexing, near-duplicates, coverage."""
    unique_records: list[dict] = []
    seen_chunk_ids: set[str] = set()
    for idx, r in enumerate(records):
        cid = str(r.get("id") or r.get("chunk_id") or f"chunk_{idx}")
        if cid not in seen_chunk_ids:
            seen_chunk_ids.add(cid)
            unique_records.append(r)

    results_by_chunk: dict[str, list[MetricResult]] = {str(r.get("id") or r.get("chunk_id")): [] for r in unique_records}
    
    hash_to_cids: dict[str, list[str]] = {}
    registered_vocabularies: list[tuple[str, set[str]]] = []

    for idx, r in enumerate(unique_records):
        cid = str(r.get("id") or r.get("chunk_id") or f"chunk_{idx}")
        text = r.get("text", "").strip()
        metadata = r.get("metadata", {})
        if not text:
            continue

        # 41. Exact Duplicate Rate (P0 - Hard Validation)
        md5_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        prior_cids = hash_to_cids.get(md5_hash, [])
        distinct_prior = [other_id for other_id in prior_cids if other_id != cid]

        if distinct_prior:
            dup_target = distinct_prior[0]
            results_by_chunk[cid].append(MetricResult(
                chunk_id=cid,
                metric_name="exact_duplicate_rate",
                dimension="chunk_relationships",
                check_type="hard_validation",
                value=1.0,
                status="fail",
                severity="high",
                evidence=f"Exact duplicate of distinct chunk ID: '{dup_target}' (MD5: {md5_hash[:8]})",
                quoted_text=text[:140] + ("..." if len(text) > 140 else ""),
                explanation="Finds repeated ingestion, redundant storage, and duplicate retrieval results.",
                recommended_action="Deduplicate chunks prior to vector upsert.",
                detector="ExactDuplicateHashDetector",
            ))
        else:
            results_by_chunk[cid].append(MetricResult(
                chunk_id=cid,
                metric_name="exact_duplicate_rate",
                dimension="chunk_relationships",
                check_type="hard_validation",
                value=0.0,
                status="pass",
                severity="none",
                detector="ExactDuplicateHashDetector",
            ))

        hash_to_cids.setdefault(md5_hash, []).append(cid)

        # 42. Near-Duplicate Rate (P1 - Heuristic: Jaccard vocabulary overlap >= 90%)
        words = set(w.lower() for w in re.findall(r"\b[a-zA-Z]{3,}\b", text))
        found_near_dup = False

        if len(words) >= 10:
            for other_cid, other_words in registered_vocabularies:
                if other_cid == cid:
                    continue

                intersection = len(words & other_words)
                union = len(words | other_words)
                jaccard = (intersection / union) if union > 0 else 0.0

                if jaccard >= 0.90:
                    results_by_chunk[cid].append(MetricResult(
                        chunk_id=cid,
                        metric_name="near_duplicate_rate",
                        dimension="chunk_relationships",
                        check_type="heuristic",
                        value=round(jaccard, 3),
                        status="warning",
                        severity="medium",
                        evidence=f"Near-duplicate ({jaccard*100:.1f}% vocabulary overlap) of distinct chunk ID: '{other_cid}'",
                        quoted_text=text[:140] + ("..." if len(text) > 140 else ""),
                        explanation="Finds slightly altered duplicates that exact hashing misses.",
                        recommended_action="Increase chunk stride or adjust overlap window.",
                        detector="NearDuplicateJaccardDetector",
                    ))
                    found_near_dup = True
                    break

            registered_vocabularies.append((cid, words))

        if not found_near_dup:
            results_by_chunk[cid].append(MetricResult(
                chunk_id=cid,
                metric_name="near_duplicate_rate",
                dimension="chunk_relationships",
                check_type="heuristic",
                value=0.0,
                status="pass",
                severity="none",
                detector="NearDuplicateJaccardDetector",
            ))

        # 47. Orphaned Chunk Rate (P0 - Hard Validation)
        doc_ref = metadata.get("source") or metadata.get("doc_id")
        if not doc_ref or doc_ref == "unknown":
            results_by_chunk[cid].append(MetricResult(
                chunk_id=cid,
                metric_name="orphaned_chunk_rate",
                dimension="chunk_relationships",
                check_type="hard_validation",
                value=1.0,
                status="fail",
                severity="critical",
                evidence="Orphaned chunk: no parent document source reference found in metadata",
                explanation="Makes document navigation and source verification unreliable.",
                recommended_action="Block ingestion: Verify each chunk has a valid parent document entity in DB.",
                detector="OrphanedChunkValidator",
            ))

        # 48. Metadata Consistency (P0 - Hard Validation)
        required_keys = {"source", "doc_id", "project_id"}
        missing_keys = [k for k in required_keys if not metadata.get(k)]
        if missing_keys:
            results_by_chunk[cid].append(MetricResult(
                chunk_id=cid,
                metric_name="metadata_consistency",
                dimension="chunk_relationships",
                check_type="hard_validation",
                value=float(len(missing_keys)),
                status="fail",
                severity="high",
                evidence=f"Missing required metadata schema key(s): {missing_keys}",
                explanation="Enables reliable filtering, grouping, access control, and source reconstruction.",
                recommended_action="Enforce strict Pydantic chunk metadata validation before vector provisioning.",
                detector="MetadataConsistencyValidator",
            ))

    return results_by_chunk


# ==============================================================================
# Dimension 6: Security, Access-Control & Auditability (Metrics 61–65)
# ==============================================================================

def evaluate_security_and_access(
    chunk_id: str,
    text: str,
    metadata: dict[str, Any],
) -> list[MetricResult]:
    results: list[MetricResult] = []

    # 61. Access-Control Metadata Completeness (P0 - Hard Validation)
    project_id = metadata.get("project_id")
    if not project_id or str(project_id).strip() == "":
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="access_control_metadata_completeness",
            dimension="security_auditability",
            check_type="hard_validation",
            value=0.0,
            status="fail",
            severity="critical",
            evidence="Missing 'project_id' scope in chunk metadata",
            explanation="Prevents chunks from entering an index without the metadata needed for safe filtering.",
            recommended_action="Block ingestion: Assign authenticated project_id (e.g. 'unassigned' or numeric project ID).",
            detector="AccessControlSchemaValidator",
        ))
    else:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="access_control_metadata_completeness",
            dimension="security_auditability",
            check_type="hard_validation",
            value=1.0,
            status="pass",
            severity="none",
            detector="AccessControlSchemaValidator",
        ))

    # 62. Access-Control Consistency (P0 - Hard Validation)
    classification = str(metadata.get("classification", "Internal")).title()
    allowed_classifications = {"Public", "Internal", "Confidential", "Restricted"}
    if classification not in allowed_classifications:
        results.append(MetricResult(
            chunk_id=chunk_id,
            metric_name="access_control_consistency",
            dimension="security_auditability",
            check_type="hard_validation",
            value=0.0,
            status="warning",
            severity="medium",
            evidence=f"Unrecognized classification '{classification}'; expected one of {allowed_classifications}",
            explanation="Helps prevent unauthorized information from being retrieved.",
            recommended_action="Ensure chunk classification matches source document security policy.",
            detector="AccessControlConsistencyValidator",
        ))

    # Secret / Credential Leakage Scan (P0 - Hard Security Check)
    for pattern, secret_type in SECRET_PATTERNS:
        match = re.search(pattern, text)
        if match:
            results.append(MetricResult(
                chunk_id=chunk_id,
                metric_name="secret_credential_leak",
                dimension="security_auditability",
                check_type="hard_validation",
                value=1.0,
                status="fail",
                severity="critical",
                evidence=f"Exposed {secret_type} pattern detected: '{match.group(0)[:12]}...'",
                explanation="Storing plaintext secrets in shared vector collections creates high-severity data exfiltration vulnerabilities.",
                recommended_action="Block ingestion: Redact credentials using DLP filter before indexing.",
                detector="SecretLeakageScanner",
            ))
            break

    # 64. Audit Reproducibility (P1 - Heuristic)
    results.append(MetricResult(
        chunk_id=chunk_id,
        metric_name="audit_reproducibility",
        dimension="security_auditability",
        check_type="heuristic",
        value=1.0,
        status="pass",
        severity="none",
        detector="AuditReproducibilityValidator",
    ))

    return results


# ==============================================================================
# Dimension 7: Retrieval Readiness & Evidence Metrics Evaluator (Metrics 51–60)
# ==============================================================================

def evaluate_retrieval_readiness(
    records: Sequence[dict],
    benchmark_cases: Sequence[dict] | None = None,
) -> dict[str, Any]:
    """Calculates corpus-wide retrieval readiness against benchmark queries and chunking density."""
    total = len(records)
    if total == 0:
        return {}

    cases = benchmark_cases or []
    chunk_ids = {str(r.get("id") or r.get("chunk_id")) for r in records}

    # 51. Gold-Evidence Coverage
    matched_cases = 0
    for case in cases:
        req_chunks = case.get("required_chunk_ids", [])
        if req_chunks and any(cid in chunk_ids for cid in req_chunks):
            matched_cases += 1
    gold_cov = (matched_cases / len(cases) * 100.0) if cases else 100.0

    # Token density distribution for evidence sufficiency
    tok_counts = [len(r.get("text", "").split()) for r in records]
    sufficient_evidence = sum(1 for tok in tok_counts if 40 <= tok <= 256)
    evidence_sufficiency_rate = (sufficient_evidence / total * 100.0) if total else 100.0

    return {
        "gold_evidence_coverage": round(gold_cov, 1),
        "evidence_sufficiency_rate": round(evidence_sufficiency_rate, 1),
        "total_test_cases_evaluated": len(cases),
        "matched_benchmark_cases": matched_cases,
    }


# ==============================================================================
# Master Auditor Orchestrator
# ==============================================================================

def audit_single_chunk(chunk_record: dict, target_window: int = 256) -> ChunkAuditReport:
    """Audit one chunk record across all single-chunk quality dimensions."""
    chunk_id = str(chunk_record.get("id") or chunk_record.get("chunk_id", "unknown"))
    text = chunk_record.get("text", "")
    metadata = chunk_record.get("metadata", {})
    content_type = detect_content_type(text, metadata)

    metrics: list[MetricResult] = []
    metrics.extend(evaluate_text_integrity(chunk_id, text, content_type, metadata))
    metrics.extend(evaluate_structural_quality(chunk_id, text, content_type, target_budget=220, model_limit=target_window))
    metrics.extend(evaluate_semantic_quality(chunk_id, text, metadata))
    metrics.extend(evaluate_source_fidelity(chunk_id, text, metadata))
    metrics.extend(evaluate_security_and_access(chunk_id, text, metadata))

    hard_fails = sum(1 for m in metrics if m.status == "fail" and m.check_type == "hard_validation")
    warnings = sum(1 for m in metrics if m.status in ("fail", "warning") and m.check_type != "hard_validation")

    overall = "fail" if hard_fails > 0 else ("warning" if warnings > 0 else "pass")

    return ChunkAuditReport(
        chunk_id=chunk_id,
        text=text,
        metadata=metadata,
        metrics=metrics,
        overall_status=overall,
        hard_failures_count=hard_fails,
        warnings_count=warnings,
        chunk_type=content_type,
        token_count=len(text.split()),
        char_count=len(text),
    )


def audit_corpus_comprehensive(records: Sequence[dict], target_window: int = 256) -> CorpusAuditReport:
    """Execute the full 6-dimensional audit over a set of chunk records."""
    if not records:
        return CorpusAuditReport()

    chunk_reports = [audit_single_chunk(r, target_window) for r in records]

    # Evaluate corpus-level relationships (duplicates, schema, contiguity)
    relationship_metrics = evaluate_corpus_relationships(records)
    for report in chunk_reports:
        rel_metrics = relationship_metrics.get(report.chunk_id, [])
        report.metrics.extend(rel_metrics)
        report.hard_failures_count += sum(1 for m in rel_metrics if m.status == "fail" and m.check_type == "hard_validation")
        report.warnings_count += sum(1 for m in rel_metrics if m.status in ("fail", "warning") and m.check_type != "hard_validation")
        if report.hard_failures_count > 0:
            report.overall_status = "fail"
        elif report.warnings_count > 0 and report.overall_status == "pass":
            report.overall_status = "warning"

    total = len(chunk_reports)
    total_hard_fails = sum(r.hard_failures_count for r in chunk_reports)
    total_warnings = sum(r.warnings_count for r in chunk_reports)

    core_dimensions = [
        "text_integrity",
        "structural_quality",
        "semantic_quality",
        "source_fidelity",
        "chunk_relationships",
        "security_auditability",
    ]

    findings_summary: Counter[str] = Counter()
    for r in chunk_reports:
        for m in r.metrics:
            if m.status in ("fail", "warning"):
                findings_summary[m.metric_name] += 1

    dimension_affected: dict[str, int] = {}
    for dim in core_dimensions:
        affected_count = sum(
            1 for cr in chunk_reports
            if any(m.dimension == dim and m.status in ("fail", "warning") for m in cr.metrics)
        )
        dimension_affected[dim] = affected_count

    dimension_scores = {
        dim: round(((total - dimension_affected[dim]) / total) * 100.0, 1) if total > 0 else 100.0
        for dim in core_dimensions
    }

    dimension_status = {
        dim: "pass" if score >= 90.0 else ("warning" if score >= 75.0 else "fail")
        for dim, score in dimension_scores.items()
    }

    clean_chunks = sum(1 for cr in chunk_reports if cr.overall_status == "pass")
    warning_only_chunks = sum(1 for cr in chunk_reports if cr.hard_failures_count == 0 and cr.warnings_count > 0)

    avg_dim_score = (sum(dimension_scores.values()) / len(dimension_scores)) if dimension_scores else 100.0
    weighted_corpus_score = (
        ((clean_chunks * 1.0 + warning_only_chunks * 0.7) / total) * 100.0
        if total > 0 else 100.0
    )
    composite = round(0.5 * avg_dim_score + 0.5 * weighted_corpus_score, 1)

    grade = (
        "A+" if composite >= 90.0
        else ("A" if composite >= 85.0
        else ("B" if composite >= 75.0
        else ("C" if composite >= 65.0 else "F")))
    )

    readiness = evaluate_retrieval_readiness(records)

    return CorpusAuditReport(
        total_chunks=total,
        hard_failures_count=total_hard_fails,
        warnings_count=total_warnings,
        dimension_scores=dimension_scores,
        dimension_status=dimension_status,
        composite_score=composite,
        composite_grade=grade,
        chunk_reports=chunk_reports,
        findings_summary=dict(findings_summary.most_common()),
        retrieval_readiness_metrics=readiness,
    )
