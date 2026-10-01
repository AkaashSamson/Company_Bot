# Docling POC: Implementation, Limitations, and Remediation Plan

## Purpose

This document explains:

1. How the current `docling-poc` implementation works.
2. What limitations exist today.
3. Which options can address each limitation.
4. Which option this project should choose.
5. How to implement the improvements efficiently.
6. How to verify that each improvement works.

The POC is an experiment. It is not yet a production ingestion service.

## 1. Current implementation

Entry point:

```text
python -m src.main
```

Main source directory:

```text
docling-poc/src/
```

Default input directory:

```text
docling-poc/input/
```

Default output directory:

```text
docling-poc/output/
```

### Stage 1: Docling parses documents

`stage1_docling.py` creates one `DocumentConverter` and gives it DOCX and PDF input.

Docling extracts:

- Headings.
- Paragraphs.
- List items.
- Tables.
- Pictures.
- Reading order.
- Page provenance when available.
- Heading hierarchy.
- Raw picture bytes.
- Picture classification annotations when the pipeline provides them.

The parser maps Docling labels into POC content types:

```text
section_header -> heading
text           -> paragraph
list_item      -> list
table          -> table
picture        -> image
```

The parser saves Docling's native structure to:

```text
output/docling/<document-stem>.json
```

### DOCX picture classification

Docling's PDF pipeline can run picture classification. The DOCX backend can extract pictures but does not automatically run that classifier.

The code therefore has `PictureClassifier` in `stage1_docling.py`. It attempts to run Docling's picture classifier over pictures that have no classification annotation.

`main.py` creates one classifier for the run and passes it into `parse_document()`.

This path must be tested on the current corpus. Old output files may not represent current code behavior.

### Stage 2: OCR reads text inside pictures

`stage2_ocr.py` builds a second Docling converter for standalone images.

For each extracted picture:

1. Picture bytes are written to `output/_ocr_work/`.
2. Picture bytes are sent to Docling as `InputFormat.IMAGE`.
3. EasyOCR reads text.
4. OCR lines and confidence values are collected.
5. Character count is calculated.

OCR results are stored in:

```text
output/ocr_results.json
```

OCR is currently run for every picture before routing. This means decorative images can consume OCR time even when the final route is `IGNORE`.

### Stage 4: Router decides picture treatment

The code labels this as stage 4, although it runs before stage 3 in `main.py`.

`stage4_router.py` uses two signals:

1. Docling picture classification.
2. OCR character count.

Routes:

```text
OCR    text-heavy content
VLM    diagrams, charts, and structural visual content
IGNORE decorative or empty content
```

Routing rules include:

- Logos, icons, barcodes, QR codes, stamps, signatures, and photographs can route to `IGNORE`.
- Charts route to `VLM`.
- Diagrams and flowcharts route to `VLM`.
- Tables route to `OCR`.
- Text-heavy screenshots route to `OCR`.
- Unclassified pictures with text route to `OCR`.
- Unclassified pictures without text route to `IGNORE`.

The unclassified text threshold is 40 characters.

Routing decisions are stored in:

```text
output/routing.json
```

### Stage 3: VLM describes routed pictures

`stage3_vlm.py` defines a common `VlmBackend` interface.

Current backend options:

```text
local  SmolVLM-256M-Instruct
Gemini Gemini REST API
```

The default backend is local SmolVLM.

The VLM prompt asks for:

- Exact visible labels.
- Components.
- Relationships.
- Arrow direction.
- Process sequence.
- Chart titles.
- Axis labels.
- Categories.
- Numeric values.

The prompt also tells the model not to speculate.

The local backend runs Transformers and PyTorch in the same process.

The Gemini backend sends a PNG image and prompt to Google's Generative Language API. It requires:

```text
POC_GEMINI_API_KEY
```

VLM results are stored in:

```text
output/vlm_results.json
```

Run Gemini with:

```text
python -m src.main --vlm gemini
```

Only pictures routed to `VLM` reach this stage.

### Stage 5: Normalisation

`stage5_normalize.py` combines three knowledge sources:

```text
Docling text       text present in document
EasyOCR text       text read from picture pixels
VLM description   model-written picture description
```

It emits one ordered list of elements.

Element types:

```text
heading
paragraph
list
table
image_ocr
image_description
image_skipped
```

Each element includes provenance fields such as:

- Source document.
- Page when available.
- Section.
- Producer.
- Docling label.
- Picture reference.
- Route.
- OCR confidence.
- VLM model.

The unified document is stored in:

```text
output/final_document.json
```

### Stage 6: Reporting

`main.py` writes:

```text
output/ocr_results.json
output/vlm_results.json
output/routing.json
output/final_document.json
output/run_report.json
```

`run_report.json` records:

- Runtime.
- Python and platform.
- Docling version.
- OCR engine.
- VLM backend and model.
- Per-document status.
- Page count.
- Picture count.
- Element counts.
- Warnings.

## 2. Current limitations

### L1. Small local VLM produces unreliable descriptions

SmolVLM-256M is too weak for important visual reasoning.

Observed failure patterns:

- Chart description can contain only one number instead of all values.
- Architecture diagrams can become a simple linear chain.
- Branches, loops, and arrow direction can be lost.
- Wording can be repetitive.
- Output can look factual even when it is wrong.

Impact: high. Wrong visual descriptions can enter search and answer generation as if they were document facts.

### L2. VLM output is not verified

The output records `produced_by: "vlm"`, but downstream behavior does not yet enforce that this content is unverified.

No current control:

- Blocks VLM text from direct citation.
- Compares VLM numbers with OCR numbers.
- Requires review for high-risk visual facts.
- Assigns lower retrieval weight to generated descriptions.

Impact: high.

### L3. Current output can become stale or misleading

JSON output files remain from prior runs. Opening an old `routing.json` or `vlm_results.json` does not prove what the current source code would produce today.

Impact: medium.

### L4. DOCX picture classification depends on a fragile internal model path

`PictureClassifier` uses Docling's internal `DocumentPictureClassifier` class. Internal library APIs can change between Docling versions.

The classifier catches exceptions and reports a failure, but the run can continue with unclassified pictures. That fallback can silently reduce routing quality.

Impact: high for DOCX documents.

### L5. OCR runs before routing

The router uses OCR character count, so the current pipeline OCRs every picture first.

Decorative pictures can therefore consume OCR time before routing sends them to `IGNORE`.

Impact: medium for performance. Larger impact on image-heavy documents.

### L6. Router has only three coarse routes

The router chooses `OCR`, `VLM`, or `IGNORE`.

It cannot express:

- OCR plus VLM.
- OCR with low confidence.
- VLM requiring review.
- VLM blocked by privacy policy.
- Classification uncertain.
- Processing failed and needs retry.

Impact: medium. Coarse routes make later quality policy difficult.

### L7. Text-heavy screenshots lose layout meaning

A screenshot with many words usually routes to OCR. OCR preserves words but not reliable relationships such as:

- Which label belongs to which field.
- Which navigation item is selected.
- Which button is enabled.
- Which values appear in the same panel.

Impact: medium.

### L8. Misclassification can send charts or diagrams to OCR

If a chart or diagram receives a textual or table label, routing can choose OCR. OCR finds visible words but cannot reliably express chart trends or diagram topology.

Impact: high for affected images.

### L9. OCR is not exact transcription

OCR can make character errors, especially with:

- Small fonts.
- Low resolution.
- Unusual fonts.
- Compression.
- Skew.
- Low contrast.
- Dense screenshots.

OCR text must not be treated as a guaranteed verbatim quote.

Impact: medium.

### L10. DOCX page numbers are unavailable

Docling normally reports no page number for DOCX content. The implementation correctly keeps `page: null` instead of inventing a page.

Impact: low for search, medium for citation UX.

### L11. No real confidence policy

The implementation records OCR confidence and classifier confidence, but no policy uses those values to decide:

- Keep.
- Retry.
- Review.
- Reject.
- Lower retrieval weight.

Impact: high for production trust.

### L12. No retry, timeout policy, or rate-limit strategy for Gemini

The Gemini call has a request timeout and checks non-200 responses. It does not yet provide a robust production policy for:

- Exponential backoff.
- Retryable versus permanent errors.
- API quota exhaustion.
- Request throttling.
- Circuit breaking.
- Per-document failure isolation beyond recording an error.

Impact: high when using an external API.

### L13. Gemini privacy and compliance risk

Gemini sends image content outside the machine.

The POC documentation restricts Gemini to synthetic data. Real HR and policy documents require explicit organizational approval, retention review, provider configuration, and contract review before external processing.

Impact: blocking for unapproved sensitive data.

### L14. Gemini implementation is untested in this POC

The backend exists, but no measured comparison exists until a valid API key is used on synthetic data.

Claims that Gemini is better remain hypotheses until tested against the same images.

Impact: high for model selection.

### L15. Small synthetic evaluation set

The corpus contains only a few documents and a small set of clean generated images.

It does not represent:

- Real scans.
- Multi-column documents.
- Complex tables.
- Handwriting.
- Rotated pages.
- Poor contrast.
- Multiple languages.
- Large documents.
- Dense technical diagrams.
- Sensitive documents.

Impact: high for general accuracy claims.

### L16. Synchronous single-process execution

The complete run is sequential and in-process.

It has no:

- Work queue.
- Parallel picture processing.
- Persistent job state.
- Idempotency key.
- Cache.
- Resume after failure.
- Resource limits per document.

Impact: medium for POC, high for production throughput.

### L17. No production storage or indexing integration

The POC stops at JSON files. It does not:

- Chunk content for retrieval.
- Generate embeddings.
- Store vectors.
- Store document versions.
- Enforce document access control.
- Track deletion or retention.
- Expose an ingestion API.

Impact: expected POC scope, blocking for platform integration.

### L18. Model-generated descriptions can be overconfident

The prompt says not to speculate, but prompt instructions do not guarantee compliance. A stronger Gemini response can sound more credible while still being wrong.

Impact: high unless downstream provenance and review policy exists.

## 3. Options and decisions

### Option A: Keep local SmolVLM only

Advantages:

- No external data transfer.
- No API cost.
- Works offline after model download.
- Existing code already supports it.

Disadvantages:

- Known chart and diagram failures.
- Slow CPU inference.
- Weak visual reasoning.

Decision: keep as privacy-safe fallback and development backend. Do not use as sole production visual reasoner.

### Option B: Use Gemini only

Advantages:

- Likely stronger chart and diagram understanding.
- Likely faster than CPU inference.
- No local VLM model management.

Disadvantages:

- Sends content outside machine.
- Requires network and API key.
- Adds usage cost and quota limits.
- Untested in this POC.
- Does not fix routing, OCR, provenance, or storage problems.

Decision: do not make Gemini the only backend. Permit it only under an explicit data policy and synthetic or approved data mode.

### Option C: Keep local backend and add Gemini as a selectable backend

Advantages:

- Preserves privacy-safe local path.
- Enables measured model comparison.
- Uses existing `VlmBackend` abstraction.
- Supports different policies by environment.

Disadvantages:

- Two backends to maintain.
- Different output quality and latency.
- Need model selection policy.

Decision: choose this option.

### Option D: Replace VLM with a stronger local model

Advantages:

- Better privacy than Gemini.
- No per-image API cost.
- No external network dependency.

Disadvantages:

- Hardware requirements.
- Model download and memory cost.
- CPU latency may remain high.
- Must test model license and accuracy.

Decision: evaluate after routing and verification fixes. Prefer this path for sensitive production data if hardware supports it.

### Option E: Use a specialized chart or diagram pipeline

Advantages:

- More deterministic numeric extraction.
- Can validate chart values against OCR.
- Can represent diagram edges explicitly.

Disadvantages:

- More components.
- More maintenance.
- Less general than a VLM.

Decision: use targeted validation, not a full replacement initially. Add specialized extraction only when evaluation shows VLM errors remain unacceptable.

## 4. Recommended target design

Keep Docling as parser. Keep OCR. Keep local VLM. Keep Gemini as optional backend.

Add policy around those components.

Target flow:

```text
Input document
    |
    v
Docling parse
    |
    v
Extract pictures and native text
    |
    v
Cheap picture classification
    |
    +--> decorative      -> IGNORE
    |
    +--> chart/diagram   -> OCR probe + selected VLM
    |
    +--> screenshot      -> OCR + VLM when layout matters
    |
    +--> text/table      -> OCR
    |
    v
Validate OCR and VLM outputs
    |
    v
Mark provenance, confidence, verification, and review state
    |
    v
Normalize to searchable elements
    |
    v
Persist JSON and later integrate with indexing
```

Recommended backend policy:

```text
Development synthetic data       local or Gemini
Sensitive data, no approval      local only
Approved external processing     Gemini allowed
High-risk visual facts           VLM output requires validation or review
```

## 5. Efficient implementation plan

Implement in dependency order. Each step has a narrow change and a focused check.

### Step 1: Establish a fresh baseline

Run current code and record outputs from one command.

```text
python -m src.main --regen --quiet
```

Record:

- `run_report.json`.
- `routing.json`.
- `vlm_results.json`.
- Runtime.
- Picture counts.
- Route counts.
- Classification failures.

Do not diagnose from stale JSON files.

### Step 2: Add explicit classification diagnostics

Improve classification reporting in `stage1_docling.py`.

Record per picture:

- Picture reference.
- Initial classification count.
- Whether classifier ran.
- Classifier exception type.
- Final classification count.
- Final top label.

Do not swallow the useful cause inside a generic failure line. Keep secrets out of errors.

Acceptance check:

```text
Every DOCX picture has either a final label or an explicit classification failure reason.
```

### Step 3: Make DOCX classification reliable

Preferred order:

1. Keep Docling's native PDF classification.
2. Keep the existing `PictureClassifier` for DOCX.
3. Add a standalone image classification fallback only if the current classifier fails.
4. Record `classification_source` as `docling_pipeline`, `docling_picture_pass`, or `unclassified`.

Do not silently treat a failed classifier as a successful unclassified result.

Add regression test:

```text
DOCX chart image -> chart label or explicit fallback label -> VLM route
DOCX logo image  -> decorative label or explicit ignore decision
```

### Step 4: Add explicit trust metadata

Update `stage5_normalize.py`.

Add fields to `Element`:

```text
verified: bool
review_required: bool
confidence: float | null
```

Recommended defaults:

```text
Docling native text       verified=true, review_required=false
OCR text                  verified=false, review_required=false
VLM description           verified=false, review_required=true
```

OCR is machine output, so `verified=false` is more honest than treating OCR as exact text.

Add a separate `evidence_type` or retain `produced_by` with clear semantics.

Acceptance check:

```text
No VLM element can appear without verified=false and review_required=true.
```

### Step 5: Validate VLM numeric claims against OCR

For chart and table-like pictures:

1. Extract numeric tokens from OCR text.
2. Extract numeric tokens from VLM description.
3. Compare sets with normalization for commas, decimals, and percentages.
4. Add warning when VLM claims a number absent from OCR.
5. Set `review_required=true` on mismatch.

This does not prove a VLM description is correct. It catches obvious numeric disagreement.

Acceptance check:

```text
A VLM description claiming unseen chart values receives a warning and review_required=true.
```

### Step 6: Improve routing without breaking the current route API

Keep existing routes for compatibility. Add a second route field or route list for multi-processing.

Preferred model:

```text
processing_actions: ["OCR"]
processing_actions: ["VLM"]
processing_actions: ["OCR", "VLM"]
processing_actions: []
```

Use actions for decisions:

- Decorative image: `[]`.
- Text card: `["OCR"]`.
- Chart: `["OCR", "VLM"]`.
- Architecture diagram: `["OCR", "VLM"]`.
- Text-heavy screenshot: `["OCR", "VLM"]`.

Keep `route` as the primary route for backward compatibility.

### Step 7: Reduce wasted OCR work

Do not blindly OCR images with a high-confidence decorative label.

Use this rule:

```text
High-confidence decorative label -> IGNORE without OCR
Other image -> OCR probe
```

Do not skip OCR for uncertain labels. OCR helps recover from bad classification.

This gives performance improvement without making uncertain images invisible.

### Step 8: Add Gemini safely

Keep `GeminiBackend` behind `VlmBackend`.

Add configuration:

```text
POC_VLM_BACKEND=local|gemini
POC_VLM_DATA_POLICY=synthetic_only|approved_external|local_only
```

Enforce policy before processing:

- `local_only` rejects Gemini.
- `synthetic_only` permits Gemini only for the synthetic input directory.
- `approved_external` permits Gemini after explicit deployment configuration.

Add Gemini controls:

- Request timeout.
- Exponential backoff for transient HTTP failures.
- No retry for authentication and invalid-request failures.
- Rate limit handling.
- Response schema validation.
- Maximum response length.
- Redacted error logging.

Do not include raw document content in logs.

### Step 9: Compare models using same images

Run local and Gemini on identical extracted PNGs.

Compare:

- Chart value accuracy.
- Diagram relationship accuracy.
- Label recall.
- Unsupported claim count.
- Latency.
- Cost.
- Failure rate.

Use a hand-checked expected result file. Do not select Gemini based only on prose quality.

Required test categories:

```text
text card
screenshot
architecture diagram
flowchart
bar chart
logo
scanned page
```

### Step 10: Expand evaluation corpus

Add documents with known expected outputs.

Minimum useful evaluation set:

- 20 to 50 documents.
- DOCX and PDF.
- Born-digital and scanned.
- Clean and degraded images.
- Charts, diagrams, tables, screenshots, logos.
- At least two languages if multilingual support matters.

Measure separately:

- Parser extraction accuracy.
- OCR character and field accuracy.
- Classification accuracy.
- Routing accuracy.
- VLM label recall.
- VLM relationship accuracy.
- Numeric accuracy.
- End-to-end retrieval accuracy.

### Step 11: Add production execution controls

Only after quality is measured, add:

- Persistent job records.
- Idempotency.
- Retry queue.
- Parallel picture processing with resource limits.
- Cache keyed by image hash, model, and prompt version.
- Resume after failure.
- Metrics.
- Document deletion and retention handling.
- Versioned output schema.

Do not build these before routing and model quality have acceptance tests.

## 6. Exact option selected

Choose this implementation:

1. Keep Docling as only document parser.
2. Keep EasyOCR through Docling for OCR.
3. Keep local SmolVLM as privacy-safe fallback, not trusted production reasoner.
4. Keep Gemini as optional selectable backend, not unconditional replacement.
5. Fix and test DOCX picture classification first.
6. Add multi-action routing for OCR plus VLM.
7. Add explicit verification and review metadata.
8. Cross-check VLM numbers against OCR.
9. Skip OCR only for high-confidence decorative pictures.
10. Add data-policy enforcement before Gemini calls.
11. Compare local and Gemini on identical ground-truth images.
12. Expand evaluation before production claims.

This option preserves privacy and existing architecture while allowing stronger visual reasoning where policy permits it.

## 7. Expected result after improvements

### Accuracy

- DOCX pictures receive reliable classification or explicit failure state.
- Charts and diagrams reach a stronger VLM.
- OCR text remains available for exact visible labels.
- VLM descriptions include review metadata.
- Numeric disagreements become visible instead of silently entering retrieval.

### Privacy

- Local-only environments cannot accidentally call Gemini.
- Gemini processing requires explicit policy configuration.
- Synthetic test mode remains safe for model comparison.

### Performance

- High-confidence decorative images skip OCR.
- Repeated images can use cache after production controls are added.
- Gemini can reduce local CPU latency when external processing is approved.

### Reliability

- Classification failures become visible.
- Gemini transient failures retry safely.
- Permanent failures remain attached to the affected picture.
- Runs remain inspectable through JSON reports.

### Trust

- Native text, OCR text, and VLM prose remain distinguishable.
- VLM output cannot be mistaken for verified source text.
- Review requirements become machine-readable.

## 8. Stop conditions

Do not call this production-ready until all conditions pass:

- DOCX classification regression test passes.
- Routing tests cover chart, diagram, screenshot, text card, and logo.
- VLM output always carries `verified=false`.
- Numeric mismatch warning test passes.
- Gemini policy prevents calls in `local_only` mode.
- Gemini retry behavior has tests.
- Model comparison uses ground truth.
- Realistic evaluation corpus meets agreed accuracy thresholds.
- Sensitive-data handling receives organizational approval.
- Output schema is versioned.

## Final recommendation

Do not replace current implementation wholesale with Gemini.

Keep current pipeline structure. Fix routing and trust controls first. Add Gemini as an optional backend behind existing interface. Measure Gemini against local SmolVLM on identical images. Use Gemini only when data policy permits external processing. Use a stronger local model for sensitive production documents when hardware allows it.

This gives highest improvement with lowest architectural risk.
