# Pending Tasks - KnowLayer V3

Based on a comparison between the `Task_Timeline.md` and the current implementation, the following tasks are currently pending and need to be implemented.

*(Note: Tasks NE-5.1, NE-5.2, and AB-5.2 are marked as Pending in the timeline document, but have been verified as already implemented in the code and are therefore omitted from this list.)*

## Subsystem 1: Multimodal Ingestion Pipeline
- [ ] **Task RO-7.1b (OCR Settings Configuration - Roshan):** Add `TESSERACT_CMD`, `OCR_LANGUAGES`, and `IMAGE_CAPTIONING_ENABLED` to `app/core/settings.py` and `.env.example`.
- [ ] **Task RO-7.2 (OCR Wrapper & Media Extractor - Roshan):** Create image ingestion modules:
  - `app/infrastructure/ingestion/ocr.py`: Mockable Tesseract OCR wrapper.
  - `app/infrastructure/ingestion/image_extractor.py`: Extract embedded raster media from `.docx` and decode direct image uploads.
  - `app/infrastructure/ingestion/captioner.py`: Optional visual captioning seam for charts/graphs.
- [ ] **Task RO-7.3 (Provisioner Image Wire-Up - Roshan):**
  - Update `app/infrastructure/ingestion/provisioner.py`: Recognize image file extensions and magic bytes.
  - Pass extracted images from `.docx` and direct uploads through `ocr.py` to generate text.
  - Tag generated chunks with `asset_type="image"` and `asset_index`.
- [ ] **Task NE-6.1 (Sliding Window Chunk Overlap - Neha):** Update chunking logic in ingestion pipeline:
  - Implement sliding sentence overlap (retain 1-2 trailing sentences from previous chunk into beginning of next chunk) to eliminate context splitting.
- [ ] **Task NE-6.2 (Dynamic Structural Header Tracking - Neha):** Update document ingestion logic:
  - Detect Word heading styles and Markdown `#` tags during text extraction.
  - Track the active structural section and dynamically assign it to chunk `section` metadata.
- [ ] **Task NE-6.3 (Structural Chunking Handshake - Neha):**
  - Handshake with Roshan's chunk generator in ingestion.
  - Apply sliding window overlap and dynamic structural headers cleanly across both regular text chunks and OCR-derived image text chunks.

## Subsystem 2: Contextual Retrieval & Evidence Quality Funnel
- [ ] **Task AK-5.1 (Distance Cutoff Gate Hook - Akaash):**
  - Hook distance threshold check (`RAG_DISTANCE_THRESHOLD`) into `RetrievalService` output.
  - If top chunk distance exceeds threshold or quality is `INVALID`, return empty evidence list to trigger early negative exit.

## Subsystem 4: Document Governance & Auto-ID Handshake
- [ ] **Task RO-4.1 (Document Update Schema - Roshan):** Add `DocumentUpdate` Pydantic model (`document_name`, `description`, `version`, `file_type`, `project_id`) in `app/api/schemas/documents.py`.
- [ ] **Task RO-4.3 (Document Update Route & Service - Roshan):**
  - Implement `update_document(principal, document_id, changes)` in `app/use_cases/organization/document_management.py`.
  - Add `PATCH /api/documents/{document_id}` in `app/api/routes/documents.py`.
- [ ] **Task RO-5.3 (Auto-Generated DOC IDs & Ingestion Guard - Roshan):** In `app/use_cases/organization/document_management.py`:
  - Enforce non-empty content: reject metadata-only registration if both `content` and `source_path` are missing.

## Core Pipeline Orchestration Consolidation
- [ ] **Task AK-5.2 (Two-Stage Citation Guardrail Finalization - Akaash):**
  - Stage 1 Gate: Check if retrieval returned empty evidence due to distance cutoff; if so, immediately return negative response without invoking LLM or caching.
  - Stage 2 Post-LLM Inspection: Inspect LLM output with `_NO_INFO_PATTERN` regex (`"could not find that information"`, `"not mentioned in the documents"`):
    - Wipe citations array (`citations = []`).
    - Clear pending citations (`_pending_citations.pop(session_id, None)`).
    - Strip trailing reference prompts (*"Would you like to see the references for this?"*).

## UI Polish, Lifespan Integration, Containerization & E2E Validation
- [ ] **Task RO-3.2 (Projects Page Fixes & Polish - Roshan):** In `streamlit_app/pages/projects.py`:
  - Conditionally fetch project members/documents only when `project.get("can_manage")` is True.
  - Guard against KeyError on empty departments; remove manual "Project ID" text input.
- [ ] **Task RO-4.4a (User Delete UI - Roshan):**
  - Add "Delete User" button with confirmation modal in `streamlit_app/pages/users.py`.
- [ ] **Task RO-4.4b (Document Edit UI - Roshan):**
  - Add "Edit Document" metadata form in `streamlit_app/pages/documents.py`.
- [ ] **Task RO-6.2 (Unassigned Document Access UI - Roshan):** Display and enable access configuration grants for unassigned documents in `streamlit_app/pages/documents.py`.
- [ ] **Task RO-7.4 (Direct Image Upload UI - Roshan):** Add `"png", "jpg", "jpeg"` file types to `st.file_uploader` in `streamlit_app/pages/documents.py`.
- [ ] **Task AK-6.1 (UI Token Privacy Separation - Akaash):** In `streamlit_app/app.py`:
  - Remove technical token metric strings from user chat bubbles.
  - Move sidebar token usage metrics behind administrator role check (`if st.session_state.get("is_admin"): ...`).
- [ ] **Task AK-6.2 (API Token Masking - Akaash):** In `app/api/routes/chat.py`: Suppress `tokens` in `ChatResponse` (return `None`) for non-admin principals.
- [ ] **Task AK-7.1 (Production Dockerfile - Akaash):** Create root `Dockerfile` (Python 3.12-slim, layer-cached dependencies, ports 8000 and 8501) and `.dockerignore`.
- [ ] **Task AK-7.2 (Docker Compose Full Stack - Akaash):** Create `docker-compose.yml` orchestrating `knowlayer-api` (port 8000), `knowlayer-ui` (port 8501), `langfuse-server` (port 3000), and `langfuse-db` (port 5432).

## Coordinated Team Verification & Validation
- [ ] **Task AB-7 (Cache & Tracing Evaluation - Abhinav):** Run evaluation suite (`test_quality_aware_cache.py`, `test_pipeline_tracing.py`, `test_dual_cache.py`).
- [ ] **Task AK-VERIFY (Channel & Container Validation - Akaash):** Execute Teams ASGI channel simulation tests (`test_teams_channel_adapter.py`) and verify container stack health (`docker compose up -d`).
- [ ] **Task NE-VERIFY (Logging & Retention Audit - Neha):** Run conversation logging and retention tests (`test_conversation_logger.py`, append-mode verification).
- [ ] **Task RO-VERIFY (Session, Directory & OCR Audit - Roshan):** Run session persistence contract test (`test_session_persistence.py`), directory tests, and OCR ingestion verification (`test_ocr_wrapper.py`).
- [ ] **Task ALL-TEST (Full Regression Gate - All Team):** Run repository-wide test suite.
