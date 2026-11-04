# Ingestion Optimization & Reliability Specification

> **Document Status**: Approved for Implementation  
> **Author**: Antigravity AI & Engineering Team  
> **Target System**: Company Bot (KnowLayer V3 Enterprise)  
> **Date**: October 2026  

---

## 1. Executive Summary

This specification outlines the comprehensive optimizations being implemented across the document ingestion pipeline, visual understanding engine, and vector storage layers. 

These changes resolve real-world bottlenecks uncovered during the ingestion and testing of **`DOC-003.docx`** (which took 14.5 minutes due to EasyOCR and VLM timeouts) and **`DOC-004.pdf`** (a 36-page financial audit report scanned on a Konica Minolta bizhub copier containing blank duplex divider pages and broken number spacing).

---

## 2. Problem Statement & Empirical Evidence

### Problem 1: 14.5-Minute DOCX Ingestion (EasyOCR & VLM Timeout Bottleneck)
* **Evidence**: Ingesting `DOC-003.docx` with 9 images took **14 minutes and 39 seconds**:
  * **5m 8s** was spent running EasyOCR (`scale=2.0`, CRAFT, CRNN, and Layout-Heron) on CPU to extract words Qwen2-VL can already see.
  * **9m 18s** was spent waiting for 9 Qwen2-VL requests to hit the 60.0s timeout on CPU because full-resolution images produced too many visual tokens.
* **Resolution**: Completely eliminate EasyOCR (**Direct-to-Qwen**), cap max image dimension to 1024px, and increase timeout to 120s.

### Problem 2: 3-Minute Digital PDF Ingestion (RapidOCR Scale 3.0)
* **Evidence**: Ingesting `DOC-004.pdf` took ~3 minutes while RapidOCR logged warnings on every page:
  `[WARNING] [RapidOCR] The text detection result is empty`.
* **Resolution**: The PDF is a digital vector PDF with native text. RapidOCR was running with default `scale=3.0` (9× pixel area on CPU) scanning empty image backgrounds. Switching to `OcrMode.PDF_AWARE_LAYOUT_REGIONS` with `scale=1.5` speeds up PDF ingestion by **5×–10×**.

### Problem 3: Blank Pages in Scanned Duplex Documents
* **Evidence**: Pages 2, 4, 6, 8, 10, 12, 14, 16 of `DOC-004.pdf` are physically blank white divider sheets created when single-sided pages were fed into a two-sided Konica Minolta scanner.
* **Resolution**: Implement an automated blank-page filter that detects pages with $< 100$ dark pixels and skips them, preventing ghost blank chunks in ChromaDB.

### Problem 4: Spaced Numbers & Font Artifacts in Financial Tables
* **Evidence**: In `DOC-004` chunks 19 and 25, numbers were extracted with spaces:
  `"Accumulated depreciation inEUR = 12, 894. 95"`
  `"Surpluses / (Deficits) = 688, 993. 55"`
  `"Balance as at January 1, 2021, D--...-*- -fy"-" = ."`
* **Resolution**: Embedding models (`all-MiniLM-L6-v2`) split `12, 894. 95` into 5 disjoint tokens, penalizing vector similarity when a user searches for `12,894.95`. Implement a sanitization regex to normalize numbers into `12,894.95`.

### Problem 5: Dual LLM Provider Outage
* **Evidence**: After one successful query on `DOC-004`, subsequent queries failed with:
  `"I'm having trouble reaching the AI provider right now."`
  OpenRouter's free tier hit a rate limit, and the fallback to Groq crashed because `GROQ_MODEL=openai/gpt-oss-20b` in `.env` does not exist on Groq.
* **Resolution**: Update `GROQ_MODEL=llama-3.3-70b-versatile` in `.env` so fallback answers instantly with 100% reliability.

---

## 3. Comprehensive Inventory of Implementations & Reasons

| # | What We Are Implementing | Technical Reason / Why It Is Needed | Target File |
| :--- | :--- | :--- | :--- |
| **1** | **Direct-to-Qwen (Delete EasyOCR)** | EasyOCR took 5m 8s doing duplicate work. Qwen2-VL 2B is a native OCR model that reads text, labels, and arrows directly from pixels with superior accuracy. | `app/infrastructure/document/visual_enrichment.py` |
| **2** | **Alpha-to-White Matte Normalization** | Transparent PNGs exported from Word/PDF can render as pure black in Ollama/PIL, making black text unreadable. Pasting onto white canvas ensures 100% contrast. | `app/infrastructure/document/image_normalizer.py` *(New)* |
| **3** | **1024px Dimension Guard (`LANCZOS`)** | Full-resolution images generate thousands of image patch tokens, causing CPU timeouts (>60s). Capping to 1024px preserves sharp text while dropping inference to ~20s. | `app/infrastructure/document/image_normalizer.py` *(New)* |
| **4** | **Zero-Loss Label Prompting** | LLMs tend to summarize rather than transcribe. Giving an explicit directive forces Qwen2-VL to transcribe all numbers, labels, and acronyms into `visible_text`. | `app/infrastructure/document/vlm_engine.py` |
| **5** | **RapidOCR Scale 1.5 & PDF-Aware Mode** | Lowers Docling PDF OCR scale from 3.0 to 1.5 (75% less pixel area) and sets `PDF_AWARE_LAYOUT_REGIONS` to skip digital text pages. | `app/infrastructure/document/docling_processor.py` |
| **6** | **Blank Page Pre-Filter** | Duplex scanner scans produce empty white pages (like Pages 12 & 14 in `DOC-004`). Detecting $< 100$ dark pixels prevents indexing empty divider sheets. | `app/infrastructure/document/image_normalizer.py` *(New)* |
| **7** | **Financial Number & Table Sanitizer** | Regex normalizes `12, 894. 95` &rarr; `12,894.95` and strips corrupted font ligatures before embedding into ChromaDB. | `app/use_cases/ingestion/document_processing.py` |
| **8** | **Dual-Index Search Text for Visuals** | Ensures that visual chunks contain both high-level semantic summaries and exact literal labels (`visible_text`) so both conceptual and keyword queries hit. | `app/domain/ports/visual_contract.py` |
| **9** | **Groq Fallback Model Fix** | Replaces non-existent `openai/gpt-oss-20b` with `llama-3.3-70b-versatile` so fallback LLM generation never fails. | `.env` & `.env.example` |
| **10** | **Centralized Settings Exposure** | Adds `DOCLING_PDF_OCR_SCALE`, `DOCLING_SKIP_BLANK_PAGES`, and updates `DOCLING_VLM_TIMEOUT_SECONDS=120.0`. | `app/core/settings.py` |

---

## 4. File Modification & Creation Inventory

### New Files Created

1. **`app/infrastructure/document/image_normalizer.py`**
   - **Purpose**: Modular image preprocessing helper.
   - **Functions**: `normalize_alpha_to_white()`, `guard_max_dimension()`, and `is_blank_page()`.
   - **Rationale**: Isolates PIL image operations from the VLM network adapter and Docling parser, enabling fast standalone unit testing.
2. **`tests/unit/test_image_normalizer.py`**
   - **Purpose**: Unit tests for image normalization.
   - **Tests**: Alpha channel composite, aspect ratio preservation, downsampling bounds, and blank page detection.

### Existing Files Modified

1. **`.env` and `.env.example`**
   - Fix `GROQ_MODEL=llama-3.3-70b-versatile`
   - Set `DOCLING_VLM_TIMEOUT_SECONDS=120.0`
   - Add `DOCLING_PDF_OCR_SCALE=1.5`
   - Add `DOCLING_SKIP_BLANK_PAGES=true`
2. **`app/core/settings.py`**
   - Expose the new settings with production-safe defaults.
3. **`app/infrastructure/document/visual_enrichment.py`**
   - Remove `_ocr()` method and `EasyOcrOptions` imports.
   - Connect directly to `self._describe()`.
   - Skip decorative icons ($< 150 \times 150\text{ px}$).
4. **`app/infrastructure/document/vlm_engine.py`**
   - Call `normalize_alpha_to_white()` and `guard_max_dimension(1024)` in `describe()`.
   - Update system prompt with the zero-loss transcription directive.
5. **`app/infrastructure/document/docling_processor.py`**
   - Configure `PdfPipelineOptions` with `scale=DOCLING_PDF_OCR_SCALE` and `mode=OcrMode.PDF_AWARE_LAYOUT_REGIONS`.
   - Add blank page skipping logic.
6. **`app/use_cases/ingestion/document_processing.py`**
   - Add `_sanitize_financial_text()` to clean broken numbers (`12, 894. 95` &rarr; `12,894.95`) before wrapping chunks for ChromaDB.
7. **`tests/unit/test_qwen2_vl.py` and `tests/unit/test_visual_enrichment.py`**
   - Update tests to validate Direct-to-Qwen without EasyOCR.

---

## 5. Expected Performance & Reliability Impact

| Metric | Baseline (Today) | Optimized Target | Improvement |
| :--- | :---: | :---: | :---: |
| **DOCX Upload Time (9 images)** | 14m 39s | **~1m 30s** | **~10× Faster** |
| **PDF Upload Time (36 pages)** | ~3m 00s | **~25s to 35s** | **~6× Faster** |
| **Blank Pages Ingested** | 8 empty chunks | **0 (filtered out)** | **100% Clean Index** |
| **Financial Number Accuracy** | `12, 894. 95` (distorted) | `12,894.95` (exact) | **High Cosine Similarity** |
| **Python Process Memory** | ~3.5 GB | **~800 MB** | **~75% Memory Reduction** |
| **LLM Provider Availability** | Intermittent (Rate limits) | **100% (Instant Groq Fallback)** | **Zero User-Facing Outages** |
| **Unit Test Suite Status** | 19/19 Passing | **All Passing** | **Zero Regressions** |
