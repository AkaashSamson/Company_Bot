# KnowLayer Chunk Quality Tester: Master Architecture & Implementation Plan

A comprehensive, production-grade quality testing framework for document chunks across KnowLayer / Company-Bot.

---

## 1. Architectural Philosophy: The Three Critical Questions

The goal of the Chunk Quality Tester is **not merely to assign a score and stop there**. Every evaluated metric must answer three fundamental questions:

1. **What is wrong with this chunk?**  
   *Exact evidence, offending token offsets, or rule violations.*
2. **Why does the issue matter for RAG retrieval or answer generation?**  
   *The precise downstream impact on embeddings, BM25 ranks, context budget, or LLM factual fidelity.*
3. **What action should the reviewer or ingestion pipeline take?**  
   *Actionable remediation: drop chunk, sub-split, re-inject headers, anchor breadcrumbs, or block ingestion.*

---

## 2. Category Distinction: Reliability & Severity

We distinguish three fundamentally different types of quality checks:

| Check Type | Nature | Certainty | Pipeline Action | Example |
| :--- | :--- | :---: | :--- | :--- |
| **Hard Validation** | Deterministic / Contractual | 100% | **Release-Blocking**: Rejects chunk or blocks ingestion | Missing `project_id`, `doc_id`, null bytes (`\x00`), severed conditions |
| **Heuristic Metrics** | Statistical / Rule-Based | High (~85–95%) | **Warning / Automated Healing**: Re-splits, trims, merges | Symbol noise ratio, fragmentation, stub chunks, unclosed pipes |
| **Model-Based Judgments** | Semantic / LLM Evaluation | Graded (~75–90%) | **Reviewer Advisory**: Flags for qualitative inspection | Semantic coherence, topic purity, nuanced policy contradictions |

---

## 3. The 6 Core Quality Dimensions & 65 Candidate Metrics

```
┌────────────────────────────────────────────────────────────────────────┐
│                      SIX CHUNK QUALITY DIMENSIONS                      │
├────────────────────────────────────────────────────────────────────────┤
│ 1. Text Integrity & Noisy Data  │ Empty chunks, symbols, replacement,  │
│                                 │ control chars, OCR noise, fragments  │
├─────────────────────────────────┼──────────────────────────────────────┤
│ 2. Chunk Structure & Boundaries │ Token limits, sentence integrity,    │
│                                 │ orphaned headings, tables, lists     │
├─────────────────────────────────┼──────────────────────────────────────┤
│ 3. Semantic Quality & Logic     │ Coherence, anaphora, exceptions,     │
│                                 │ definition completeness, numbers     │
├─────────────────────────────────┼──────────────────────────────────────┤
│ 4. Source Fidelity & Extraction │ Traceability, OCR WER, table schema, │
│                                 │ boilerplate leakage, versioning      │
├─────────────────────────────────┼──────────────────────────────────────┤
│ 5. Chunk Relationships & Corpus │ Exact & near duplicates, continuity, │
│                                 │ coverage gaps, metadata consistency  │
├─────────────────────────────────┼──────────────────────────────────────┤
│ 6. Retrieval Readiness & Evidence│ Gold evidence coverage, Recall@k,   │
│                                 │ sufficiency, noise ratio, MRR/nDCG   │
├─────────────────────────────────┼──────────────────────────────────────┤
│ 7. Security & Access Control    │ RBAC metadata, secret leaks, stale   │
│                                 │ chunks, audit reproducibility        │
└────────────────────────────────────────────────────────────────────────┘
```

### Dimension 1: Text Integrity & Noisy Data (P0 Priority)
- **Metric 1: Empty Chunk Rate** (P0 - Hard): Chunks with 0 characters or pure whitespace.
- **Metric 2: Suspicious Symbol Ratio** (P0 - Heuristic): Proportion of suspicious symbols relative to text (math/code aware).
- **Metric 3: Replacement Character Count** (P0 - Hard): Count of `\ufffd` indicating decoding failures.
- **Metric 4: Control Character Rate** (P0 - Hard): Unexpected control characters (`\x00-\x1f` except `\t`, `\n`).
- **Metric 5: Non-Printable Character Ratio** (P0 - Heuristic): Corrupted non-printable glyphs.
- **Metric 6: Fragmentation Score** (P0 - Heuristic): Isolated letters and broken words (`c o n t r a c t`).
- **Metric 7: OCR Confidence** (P1 - Heuristic): Confidence score from EasyOCR/Docling.
- **Metric 8: Language Consistency** (P1 - Hard): Script mismatch or non-English rejection.
- **Metric 9: Repeated Character Ratio** (P1 - Heuristic): Uncontrolled repetitive delimiters (`-------`, `......`).
- **Metric 10: Whitespace Anomaly Score** (P1 - Heuristic): Broken column whitespace and irregular tabs.

### Dimension 2: Chunk Structure & Boundary Metrics
- **Metric 11: Token Count & Budget** (P0 - Hard): Chunk token count relative to 256 embedding limit.
- **Metric 12: Chunk Length Distribution** (P0 - Heuristic): Percentiles, stubs (<15 tokens), overflows (>256).
- **Metric 13: Sentence Boundary Integrity** (P0 - Heuristic): Chunks ending on trailing conjunctions (`and`, `or`, `because`).
- **Metric 14: Orphaned Heading Rate** (P0 - Heuristic): Standalone `# Heading` with zero body content.
- **Metric 15: Incomplete Sentence Rate** (P1 - Heuristic): Sentences starting mid-clause without capital letters.
- **Metric 16: Paragraph Integrity** (P1 - Heuristic): Logical paragraph unit preservation.
- **Metric 17: Table Integrity** (P0 for tables): Markdown header dividers and pipe consistency across slices.
- **Metric 18: List Integrity** (P1 - Heuristic): Preservation of numbered steps and sub-items.
- **Metric 19: Chunk Overlap Ratio** (P1 - Heuristic): Stride overlap percentage between neighboring chunks.
- **Metric 20: Source Coverage Gap Rate** (P0 - Hard): Missing text spans from original document.
- **Metric 21: Boundary Discontinuity** (P1 - Heuristic): Skips or re-orderings across adjacent chunks.

### Dimension 3: Semantic Quality & Condition Preservation
- **Metric 22: Semantic Coherence** (P0 - Model): Focus on unified topic.
- **Metric 23: Contextual Independence & Anaphora** (P0 - Heuristic): Pronouns (`it`, `they`) anchored via breadcrumbs.
- **Metric 24: Topic Purity** (P1 - Heuristic): Single-topic vs disjointed multi-topic chunks.
- **Metric 25: Definition Completeness** (P1 - Heuristic): Term and definition kept together.
- **Metric 26: Entity & Reference Resolution** (P1 - Heuristic): Clear referents for corporate entities.
- **Metric 27: Logical Completeness** (P0 - Heuristic): Premise and conclusion kept in single unit.
- **Metric 28: Condition & Exception Preservation** (P0 - Critical): Retaining `unless`, `provided that`, `except`.
- **Metric 29: Contradiction Indicators** (P1 - Model): Contradictory policy statements across versions.
- **Metric 30: Semantic Redundancy** (P2 - Heuristic): Internal repetitive loops (especially in VLM captions).
- **Metric 31: Semantic Completeness Score** (P1 - Model): Sufficient supporting facts for claims.

### Dimension 4: Source Fidelity & Extraction Metrics
- **Metric 32: Source Traceability Rate** (P0 - Hard): Mandatory `doc_id`, `source_filename`, and valid `page_number`.
- **Metric 33: Source-to-Chunk Fidelity** (P0 - Hard): Match between chunk text and source file span.
- **Metric 34: Source Span Coverage** (P0 - Hard): Percentage of document text represented in chunks.
- **Metric 35: Extraction Artifact Rate** (P1 - Heuristic): Running headers, footers ("Page X of Y"), watermarks.
- **Metric 36: OCR Word Error Rate** (P1 - Benchmark): Word error rate against verified transcription.
- **Metric 37: Numeric and Symbol Fidelity** (P0 - Hard): Currency symbols, percentages, and metrics preserved.
- **Metric 38: Reading Order Integrity** (P1 - Heuristic): Column order sequence in multi-column documents.
- **Metric 39: Table Value-to-Header Alignment** (P0 - Hard): Value-to-column header fidelity.
- **Metric 40: Source Version Consistency** (P0 - Hard): Alignment with current active document version.

### Dimension 5: Chunk Relationships & Corpus-Level Metrics
- **Metric 41: Exact Duplicate Rate** (P0 - Hard): Identical chunks identified via MD5/SHA256 hashes.
- **Metric 42: Near-Duplicate Rate** (P1 - Heuristic): Vocabulary overlap > 90% via shingling.
- **Metric 43: Neighbor Continuity Score** (P1 - Heuristic): Logical transition between adjacent chunks.
- **Metric 44: Cross-Chunk Context Dependency** (P1 - Heuristic): Chunks requiring neighbor context.
- **Metric 45: Cross-Chunk Evidence Completeness** (P1 - Model): Multi-chunk procedure aggregation.
- **Metric 46: Document Coverage Distribution** (P1 - Heuristic): Balanced chunking across document sections.
- **Metric 47: Orphaned Chunk Rate** (P0 - Hard): Chunks with unresolved document/source relationships.
- **Metric 48: Metadata Schema Consistency** (P0 - Hard): Conformance to canonical metadata schema.
- **Metric 49: Cross-Version Conflict** (P1 - Model): Superseded document chunks clashing with active ones.
- **Metric 50: Content Concentration Anomalies** (P2 - Heuristic): Unusual clustering of boilerplate chunks.

### Dimension 6: Retrieval Readiness & Evidence Metrics
- **Metric 51: Gold-Evidence Coverage** (P0): Necessary evidence passages present in corpus.
- **Metric 52: Evidence Retrievability@k** (P0): Fraction of queries retrieving required evidence in top-k.
- **Metric 53: Recall@k (Chunk & Evidence)** (P0): Chunk ID retrieval vs Information retrieval.
- **Metric 54: Mean Reciprocal Rank (MRR)** (P1): Rank of first relevant chunk.
- **Metric 55: nDCG@k** (P1): Graded relevance ranking quality.
- **Metric 56: Retrieval Noise Ratio** (P1): Irrelevant chunks entering top-k context.
- **Metric 57: Evidence Sufficiency** (P0): Retrieved context contains enough evidence to answer query.
- **Metric 58: Context Redundancy** (P1): Repeated information in top-k context window.
- **Metric 59: Topic Query Coverage** (P1): Retrieval reachability across all company topics.
- **Metric 60: Chunking Sensitivity** (P1): Retrieval impact when tuning chunk size or stride.

### Dimension 7: Security & Access Control Metrics
- **Metric 61: Access-Control Completeness** (P0 - Hard): Presence of `project_id`, classification, tenant scope.
- **Metric 62: Access-Control Consistency** (P0 - Hard): RBAC agreement between chunk and document policy.
- **Metric 63: Stale Chunk Rate** (P0 - Hard): Indexed chunks referencing deleted documents.
- **Metric 64: Secret & Credential Redaction** (P0 - Hard): Detection of AWS keys, JWTs, and passwords.
- **Metric 65: Audit Reproducibility** (P1): Findings reproducible across runs.

---

## 4. The Canonical Pydantic Schema

Implemented in `sandbox/engine/chunk_quality_framework.py`:

```python
from pydantic import BaseModel
from typing import Literal

class MetricResult(BaseModel):
    chunk_id: str
    metric_name: str
    metric_version: str = "1.0"
    dimension: Literal[
        "text_integrity",
        "structural_quality",
        "semantic_quality",
        "source_fidelity",
        "chunk_relationships",
        "security_auditability",
    ]
    check_type: Literal["hard_validation", "heuristic", "model_based"]
    value: float | None = None
    status: Literal["pass", "warning", "fail", "not_applicable", "not_evaluated"]
    severity: Literal["critical", "high", "medium", "low", "none"] = "none"
    evidence: str | None = None
    explanation: str | None = None       # Why this issue matters for RAG
    recommended_action: str | None = None # Actionable remediation step
    detector: str
    confidence: float | None = 1.0
```

---

## 5. Phased Implementation Roadmap

### Phase 1 — Essential Validators (Active in Sandbox)
*Focus: Blocking failures, noisy data, boundaries, and security.*
- Empty chunks (1), replacement chars (3), control characters (4), suspicious symbols (2).
- Token window overflow (11), sentence boundaries (13), orphaned headings (14).
- Source traceability (32), numeric fidelity (37), exact duplicates (41).
- Access control metadata (61), secret leakage (64).

### Phase 2 — Qualitative & Semantic Inspection (Active in Sandbox)
*Focus: Condition preservation, anaphora, OCR/VLM quality, and tables.*
- Condition and exception preservation (28): detects trailing `unless`, `provided that`.
- Contextual independence (23): anchors leading pronouns (`it`, `they`).
- Table integrity (17): header divider and pipe validation.
- OCR/VLM Quality: lexical validity, repetition loops, generic boilerplate.

### Phase 3 — Corpus & Retrieval Evaluation
*Focus: Test studio benchmarks, Gold-Evidence Coverage, Recall@k, and MRR.*
- Integration with Sandbox Tab 5 (🧪 Test Studio & Benchmarks).
- Chunk Recall@k vs Evidence Recall@k.

### Phase 4 — Calibration & Ingestion Gates
- Pre-Chroma blocking hook in `provisioner.py`.
- Automated remediation (merging stubs, de-hyphenation, header re-injection).

---

## 6. Live Sandbox Inspection Experience

Available at `http://localhost:8502`:
- **Step 1 (Ingestion & Chunking)**:
  - 6-Dimension Scorecard with health scores.
  - Interactive Actionable Findings Table (filtered by `🔴 Hard Blockers`, `🟡 Warnings`, `All`).
  - Chunk Inspector displaying the 3-question defect analysis for any selected chunk.
- **Step 2 (Chunk Quality Diagnostics - CQI)**:
  - Full collection audit across all 6 dimensions.
  - Defect breakdown across all active ChromaDB vectors.
