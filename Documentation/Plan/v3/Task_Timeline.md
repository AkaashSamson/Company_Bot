# KnowLayer V3 Phase-Wise Task Timeline & Execution Roadmap

**Target Version:** KnowLayer V3 Enterprise  
**Generated Date:** September 2026  
**Status:** Active Execution Baseline  
**Location:** `Documentation/Plan/v3/Task_Timeline.md`  

---

## 1. Overview & Execution Principles

This document defines the phase-by-phase execution timeline for KnowLayer V3. It translates the architectural requirements and individual proposals into an actionable, dependency-aware work breakdown structure across four contributors: **Abhinav**, **Akaash Samson**, **Neha**, and **Roshan**.

### Key Rules Followed:
1. **Parallel vs. Dependent Tagging:** Each teammate's section explicitly states whether their tasks run in parallel (`[Parallel]`) or depend on prerequisite tasks (`[Sequential / Dependent]`).
2. **Explicit Upstream Dependencies:** When a task relies on another teammate's deliverable, the prerequisite task is placed at the top of that task block with the dependency ID, description, and owner in brackets: `[Dependency: Task ID - Task Name (Owner)]`.
3. **Hot File Protection:** Changes to shared pipeline files (especially `app/use_cases/chat/query_orchestrator.py` and `app/use_cases/chat/retrieval_service.py`) are strictly partitioned into ordered, non-conflicting merge gates.
4. **Adaptive Architecture:** Every external dependency (Langfuse, Tesseract OCR, Cohere Reranker) includes an in-tree mock/fallback provider so teammates are never blocked by environment or infrastructure delays.
5. **Interactive Checklists:** Every unit task and sub-task is formatted as a checkbox (`- [ ]`) to track granular execution progress.

---

## 2. Phase-Wise Implementation Roadmap

```
+---------------------------------------------------------------------------------------------------+
| PHASE 1: Foundations, Isolated Subsystems & Schema Contracts                                     |
| Execution Mode: 100% Parallel across all 4 contributors (Zero file collision risk)               |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
| PHASE 2: Domain Services & Standalone Component Construction                                      |
| Execution Mode: Parallel feature development along modular interface boundaries                   |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
| PHASE 3: Subsystem Handshakes & Cross-Teammate Pairwise Merges                                    |
| Execution Mode: Pairwise integration (Roshan + Neha, Neha + Abhinav + Akaash, Akaash + Abhinav)   |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
| PHASE 4: Core Pipeline Orchestration Consolidation (Hot File Gate)                                |
| Execution Mode: Strict single-owner sequential edits on query_orchestrator.py                     |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
| PHASE 5: UI Polish, Lifespan Integration, Containerization & E2E Validation                       |
| Execution Mode: Parallel UI & DevOps completion followed by coordinated team sign-off             |
+---------------------------------------------------------------------------------------------------+
```

---

### PHASE 1: Foundations, Isolated Subsystems & Schema Contracts

**Objective:** Build base protocols, standalone entity models, schema definitions, and settings without touching shared pipeline logic. All contributors work in parallel with zero merge conflict risk.

#### 1. Akaash Samson [Parallel]
- [ ] **Task AK-1.1 (Domain Service Foundation):** Implement stateful foundation of `app/domain/services/session_memory_service.py`:
  - [ ] Create thread-safe in-memory session store keyed by `session_id`.
  - [ ] Implement sliding history buffer ($k=6$ turns).
  - [ ] Implement inactivity TTL check (default 12 hours) and programmatic `clear_session(session_id)` hook.
- [ ] **Task AK-1.2 (Settings Configuration):** Add `SESSION_INACTIVITY_TIMEOUT_HOURS = 12.0` and `SESSION_MAX_HISTORY_TURNS = 6` to `app/core/settings.py`.
- [ ] **Task AK-3.1 (Observability Protocol & Entities):** Create `app/infrastructure/observability/provider.py`:
  - [ ] Define `BaseObservabilityProvider` protocol with `record_llm_call()`, `create_trace()`, `end_trace()`.
  - [ ] Define standardized `TokenUsage` dataclass (`prompt_tokens`, `completion_tokens`, `total_tokens`).
- [ ] **Task AK-2.1 (Channel Interfaces):** Create `app/infrastructure/channels/base.py`:
  - [ ] Define `BaseChannelAdapter` abstract base class.
  - [ ] Define `ChannelMessage` and `ChannelResponse` unified dataclasses.

#### 2. Abhinav [Parallel]
- [x] **Task AB-2 (LLM Response Standard Contract):** Implement `app/infrastructure/llm/llm_response.py`:
  - [x] Define `LLMResponse` standard dataclass.
  - [x] Define enums `LLMProviderName` (`OPENROUTER`, `GROQ`, `UNKNOWN`) and `LLMResponseStatus` (`SUCCESS`, `PARTIAL`, `CACHED`, `FAILED`).
  - [x] Implement `LLMResponseBuilder` factory and `ResponseAggregator`.
- [x] **Task AB-1.1 (Circuit Breaker & Provider Health Monitoring):** Implement `app/infrastructure/llm/provider_health.py` and `provider_error_tracker.py`:
  - [x] Build `ProviderHealthMonitor` with circuit breaker pattern (consecutive failure tracking).
  - [x] Implement intelligent retry categorization (retry on 429/5xx, fail-fast on 401/403).
- [x] **Task AB-3.1 (Query Normalizer Core):** Implement `app/use_cases/chat/query_normalizer.py`:
  - [x] Build domain vocabulary dictionary and typo detection.
  - [x] Implement whitespace/casing normalization and word boundary fixing (e.g., `"leavesavailable"` -> `"leaves available"`).
  - [x] Implement normalized cache key generator.

#### 3. Neha [Parallel]
- [ ] **Task NE-3.1 (YAML Prompt Externalization):** Externalize system prompts and QA rules:
  - [ ] Populate `config/prompts.yaml` with production system and user prompts.
  - [ ] Update `app/core/prompt_config.py` and test `load_prompt()` LRU caching.
- [ ] **Task NE-1.1 (Append-Mode Logging Core):** Upgrade `app/infrastructure/logging/conversation_logger.py`:
  - [ ] Implement session-to-filepath in-memory registry to append turns to active JSON files instead of creating new files per turn.
  - [ ] Eliminate quadratic log file duplication.
- [ ] **Task NE-1.2 (Identity Provider Robustness):** Update `app/infrastructure/logging/database_employee_id_provider.py` as default provider; fall back to `"anonymous"` with high-severity logger warning on unauthenticated access.
- [ ] **Task NE-2.1 (Background Cleanup Routine):** Create `app/infrastructure/logging/conversation_log_cleanup.py`:
  - [ ] Build async file cleanup utility based on file `mtime` and `CONVERSATION_LOG_RETENTION_DAYS`.

#### 4. Roshan [Parallel]
- [ ] **Task RO-2.1 (Streamlit Session Store Utility):** Create `streamlit_app/services/session_store.py`:
  - [ ] Implement helper functions to read, write, and clear JWT `access_token` and `uid` from `st.query_params` and sync with `st.session_state["auth"]`.
- [ ] **Task RO-5.1 (User Auto-ID Schema & Service):**
  - [ ] Make `UserCreate.uid` optional (`str | None = None`) in `app/api/schemas/organization.py`.
  - [ ] In `app/use_cases/organization/user_management.py`, auto-generate `MSS-###` via `business_id_generator.next(uow, "user")` when `uid` is blank.
- [ ] **Task RO-5.2 (Department Auto-ID Support):** Update `create_department` in `user_management.py` to auto-generate `DEPT-###` when empty string or whitespace is received.
- [ ] **Task RO-1.1 (Directory Schema Contract):** Add `PeopleDirectoryEntry` model and `people: list[PeopleDirectoryEntry]` field to `app/api/schemas/explorer.py`.
- [ ] **Task RO-3.1 (Project Management Scope Schema):** Add `can_manage: bool = False` to `ProjectResponse` in `app/api/schemas/organization.py`.
- [ ] **Task RO-4.1 (Document Update Schema):** Add `DocumentUpdate` Pydantic model (`document_name`, `description`, `version`, `file_type`, `project_id`) in `app/api/schemas/documents.py`.
- [ ] **Task RO-7.1 (OCR Dependencies & Environment Config):**
  - [ ] Add `pytesseract` and `Pillow` to `requirements.txt`.
  - [ ] Add `TESSERACT_CMD`, `OCR_LANGUAGES`, and `IMAGE_CAPTIONING_ENABLED` to `app/core/settings.py` and `.env.example`.

---

### PHASE 2: Domain Services & Standalone Component Construction

**Objective:** Build out domain logic, client adapters, cache layers, and feature modules. Work remains decoupled along modular interface boundaries.

#### 1. Akaash Samson [Parallel]
- [ ] **Task AK-2.2 (Channel Identity & JWT Bridge):** Create `app/infrastructure/channels/identity_bridge.py`:
  - [ ] Extract corporate email / User Principal Name (UPN) from incoming webhook payload.
  - [ ] Look up active user in SQLite database (`uow.users.get_by_email(email)`).
  - [ ] Issue short-lived internal JWT bearer token for valid users; return unauthorized card for unknown users.
- [ ] **Task AK-2.3 (Stateless Teams Adapter & Adaptive Card Formatter):**
  - [ ] Create `app/infrastructure/channels/teams/adapter.py`: Mount Teams webhook route, resolve identity via `ChannelIdentityBridge`, dispatch in-memory ASGI request to `POST /api/chat`, and return response.
  - [ ] Create `app/infrastructure/channels/teams/formatter.py`: Convert chat answer and citation records into Teams Adaptive Cards.
- [ ] **Task AK-2.4 (Channel Registry):** Create `app/infrastructure/channels/registry.py`: Discover and load enabled channel adapters based on environment flags (`TEAMS_ENABLED=true`).
- [ ] **Task AK-3.2 (Observability Providers & Manager):** Implement observability dispatch in `app/infrastructure/observability/`:
  - [ ] `langfuse_provider.py`: REST client integration with self-hosted Langfuse server.
  - [ ] `langsmith_provider.py`: Configurable LangSmith provider.
  - [ ] `manager.py`: `ObservabilityManager` dispatching spans and tokens according to `OBSERVABILITY_PROVIDER`.
- [ ] **Task AK-3.3 (Groq Token Standardization):** Update `app/infrastructure/llm/groq_client.py` to parse OpenAI-compatible `usage` blocks (`prompt_tokens`, `completion_tokens`, `total_tokens`) and populate `TokenUsage`.

#### 2. Abhinav [Parallel]
- [ ] **Task AB-4 (Quality-Aware Semantic Cache):** Implement `app/infrastructure/cache/quality_aware_cache.py`:
  - [ ] Implement `InMemoryQualityAwareCache` with thread-safe LRU eviction and TTL expiration.
  - [ ] Create `QualityAwareCacheEntry` and `CacheEntryMetadata` (tracking source, confidence score, evidence count, and timestamp).
  - [ ] Implement `CacheQualityValidator` ensuring only verified answers meeting quality thresholds are stored.
- [ ] **Task AB-5.1 (Multi-Dimensional Retrieval Quality Gate Core):** Implement `app/use_cases/chat/retrieval_quality.py`:
  - [ ] Create `RetrievalQualityGate` evaluating lexical grounding, distance score, and separation gap.
  - [ ] Define `EvidenceQualityLevel` enum (`STRONG`, `BORDERLINE`, `WEAK`, `INVALID`).
  - [ ] Implement adaptive confidence scoring ($0.0$ to $1.0$).
- [ ] **Task AB-6.1 (Pipeline Tracing Engine):** Implement `app/infrastructure/observability/pipeline_tracer.py`:
  - [ ] Define `PipelineStage` enum with 8 stages (Context Rewrite, Normalization, Cache Lookup, Vector Retrieval, Reranking, Quality Gate, LLM Generation, Post Guardrails).
  - [ ] Implement `TraceContext` context manager for measuring stage durations and token metrics.
- [ ] **Task AB-1.2 (Client Health Integration):** Update `openrouter_client.py` and `groq_client.py` to report status to `ProviderHealthMonitor` and utilize `LLMResponseBuilder`.

#### 3. Neha [Parallel]
- [ ] **Task NE-4.1 (Contextual Query Rewriter):** Implement `app/use_cases/chat/conversation_query_resolver.py`:
  - [ ] Create lightweight LLM rewriter instructing model to resolve pronouns (*"it"*, *"they"*, *"that policy"*) using the last 2-3 chat turns from session memory into a standalone semantic query.
- [ ] **Task NE-5.1 (Cross-Encoder Reranker Module):** Implement cross-encoder reranking helper in `app/use_cases/chat/retrieval_service.py`:
  - [ ] Fetch top-15 nearest chunks from ChromaDB vector search.
  - [ ] Pass candidate chunks and rewritten query through Reranker model (e.g. Cohere or local cross-encoder) to select the top 3-4 chunks with deep semantic relevance.
- [ ] **Task NE-6.1 (Sliding Window Chunk Overlap):** Update `chunk_text()` in `app/use_cases/ingestion/document_processing.py`:
  - [ ] Implement sliding sentence overlap (retain 1-2 trailing sentences from previous chunk into beginning of next chunk) to eliminate context splitting.
- [ ] **Task NE-6.2 (Dynamic Structural Header Tracking):** Update document ingestion in `app/use_cases/ingestion/document_processing.py`:
  - [ ] Detect Word heading styles and Markdown `#` tags during text extraction.
  - [ ] Track the active structural section and dynamically assign it to chunk `section` metadata.
- [ ] **Task NE-3.2 (Prompt Injection XML Delimiters):** Update `app/use_cases/chat/rag_context_builder.py`:
  - [ ] Wrap user input in `<user_question>{question}</user_question>` delimiters.
  - [ ] Bind prompt templates dynamically via `load_prompt()`.

#### 4. Roshan [Parallel]
- [ ] **Task RO-1.2 (Company-Wide Directory Service):** Update `OrganizationExplorerService.get_organization` in `app/use_cases/organization/organization_explorer.py`:
  - [ ] Query all active employees across all departments (`uow.users.list()`) and populate the `people` list in `OrganizationExplorerResponse`.
- [ ] **Task RO-4.2 (User Hard Delete & Cleanup):** Update `app/use_cases/organization/user_management.py` and `app/api/routes/organization.py`:
  - [ ] Gate `update_user` and `deactivate_user` behind `USER_UPDATE` and `USER_DELETE` permissions.
  - [ ] Implement `delete_user(actor_uid, uid)` to hard delete user record and clean up associated department memberships, project memberships, and document grants.
  - [ ] Update `DELETE /api/users/{uid}` to invoke hard delete.
- [ ] **Task RO-4.3 (Document Update Route & Service):**
  - [ ] Implement `update_document(principal, document_id, changes)` in `app/use_cases/organization/document_management.py`.
  - [ ] Add `PATCH /api/documents/{document_id}` in `app/api/routes/documents.py`.
- [ ] **Task RO-5.3 (Auto-Generated DOC IDs & Ingestion Guard):** In `app/use_cases/organization/document_management.py`:
  - [ ] Normalize empty `document_id` to generate `DOC-###`.
  - [ ] Enforce non-empty content: reject metadata-only registration if both `content` and `source_path` are missing.
- [ ] **Task RO-6.1 (Unassigned Document Access Governance):** Update `can_manage_document` in `app/domain/services/authorization_engine.py`:
  - [ ] Allow admin and department managers to manage and configure access on unassigned documents (`project_id is None`).
- [ ] **Task RO-7.2 (OCR Wrapper & Media Extractor):** Create image ingestion modules:
  - [ ] `app/infrastructure/ingestion/ocr.py`: Mockable Tesseract OCR wrapper.
  - [ ] `app/infrastructure/ingestion/image_extractor.py`: Extract embedded raster media (`word/media/*`) from `.docx` and decode direct image uploads (`.png`, `.jpg`, `.jpeg`).
  - [ ] `app/infrastructure/ingestion/captioner.py`: Optional visual captioning seam for charts/graphs.

---

### PHASE 3: Subsystem Handshakes & Cross-Teammate Pairwise Merges

**Objective:** Wire independently developed modules together in pairwise handshakes before touching the main query orchestrator. Dependencies are strictly defined.

#### Subsystem 1: Multimodal Ingestion Pipeline (Roshan + Neha)
- **Top Dependency:** `[Dependency: Task RO-7.2 - Image Extractor & OCR Wrapper (Roshan)]`
- [ ] **Task RO-7.3 (Provisioner Image Wire-Up - Roshan [Sequential Step 1]):**
  - [ ] Update `app/infrastructure/ingestion/provisioner.py`: Recognize image file extensions and magic bytes (`\x89PNG`, `\xff\xd8\xff`).
  - [ ] Pass extracted images from `.docx` and direct uploads through `ocr.py` to generate text.
  - [ ] Tag generated chunks with `asset_type="image"` and `asset_index`.
- [ ] **Task NE-6.3 (Structural Chunking Handshake - Neha [Sequential Step 2 - Depends on Roshan's Chunks]):**
  - [ ] Handshake with Roshan's chunk generator in `app/use_cases/ingestion/document_processing.py`.
  - [ ] Apply sliding window overlap (Task `NE-6.1`) and dynamic structural headers (Task `NE-6.2`) cleanly across both regular text chunks and OCR-derived image text chunks.

#### Subsystem 2: Contextual Retrieval & Evidence Quality Funnel (Neha + Abhinav + Akaash)
- **Top Dependency:** `[Dependency: Task NE-4.1 & NE-5.1 - Query Resolver & Cross-Encoder Reranker (Neha)]`
- [ ] **Task NE-5.2 (Reranker Pipeline Hook - Neha [Sequential Step 1]):**
  - [ ] Deprecate hardcoded `_query_parts` regex in `app/use_cases/chat/retrieval_service.py`.
  - [ ] Connect Cross-Encoder Reranker to filter ChromaDB top-15 candidates down to top-4 semantic chunks.
- **Top Dependency:** `[Dependency: Task AB-5.1 - RetrievalQualityGate Engine (Abhinav)]`
- [ ] **Task AB-5.2 (Quality Gate Integration - Abhinav [Sequential Step 2 - Depends on Neha's Reranked Chunks]):**
  - [ ] In `app/use_cases/chat/retrieval_service.py`, pass reranked top-4 chunks through `RetrievalQualityGate.evaluate()`.
  - [ ] Attach evidence quality metrics (`level`, `grounding_score`, `confidence`) to candidate evidence.
- **Top Dependency:** `[Dependency: Task AK-5.1 - Pre-LLM Distance Cutoff Specification (Akaash)]`
- [ ] **Task AK-5.1 (Distance Cutoff Gate Hook - Akaash Samson [Sequential Step 3 - Depends on Abhinav's Quality Gate]):**
  - [ ] Hook distance threshold check (`RAG_DISTANCE_THRESHOLD`) into `RetrievalService` output.
  - [ ] If top chunk distance exceeds threshold or quality is `INVALID`, return empty evidence list to trigger early negative exit.

#### Subsystem 3: Observability Bridge (Akaash + Abhinav)
- **Top Dependency:** `[Dependency: Task AK-3.2 - ObservabilityManager & LangfuseProvider (Akaash)]`
- [ ] **Task AK-3.4 (Observability Manager Singleton - Akaash Samson [Sequential Step 1]):**
  - [ ] Expose singleton `get_observability_manager()` in `app/infrastructure/observability/manager.py`.
- **Top Dependency:** `[Dependency: Task AB-6.1 - PipelineTracer Engine (Abhinav)]`
- [ ] **Task AB-6.3 (Pipeline Tracer Dispatch Hook - Abhinav [Sequential Step 2 - Depends on Akaash's ObservabilityManager]):**
  - [ ] In `app/infrastructure/observability/pipeline_tracer.py`, bind completed `PipelineTrace` execution records and stage spans to `ObservabilityManager.dispatch_trace()`.

---

### PHASE 4: Core Pipeline Orchestration Consolidation (Hot File Gate)

**Objective:** Consolidate all subsystems into `app/use_cases/chat/query_orchestrator.py`. To eliminate all Git merge conflicts, team members apply their edits in a strict, single-owner sequential sequence.

```
Execution Sequence for app/use_cases/chat/query_orchestrator.py:
Step 4.1 (Akaash) -> Step 4.2 (Abhinav) -> Step 4.3 (Neha) -> Step 4.4 (Akaash)
```

#### Step 4.1: Akaash Samson [Sequential Owner 1 - Session Memory & Outage Fallback]
- [ ] **Task AK-1.3 (Session Memory Wiring):**
  - [ ] In `QueryOrchestrator.answer()`, check if `conversation_history` is provided by caller; if absent, load history from `SessionMemoryService.get_history(session_id)`.
  - [ ] On turn completion, append user query and assistant response via `SessionMemoryService.add_turn(session_id, question, answer)`.
- [ ] **Task AK-4 (Resilient Outage Fallback):**
  - [ ] Wrap LLM generation in `try...except (LLMProviderError, Exception)`.
  - [ ] If LLM call fails but `selected_evidence` exists from ChromaDB, preserve evidence, format citations immediately, and return response with outage advisory note.

#### Step 4.2: Abhinav [Sequential Owner 2 - Query Normalization, Cache & Tracing]
- **[Dependency: Step 4.1 completed by Akaash (Session memory and error handling active)]**
- [ ] **Task AB-3.2 (Query Normalization Hook):**
  - [ ] Pass incoming query through `QueryNormalizer.normalize()` to standardize casing and typos before cache evaluation.
- [ ] **Task AB-4.2 (Semantic Cache Hook):**
  - [ ] Check `QualityAwareCache.get(normalized_query)` before triggering vector search.
  - [ ] On cache hit: return cached answer with `cache_hit=True` and provenance metadata.
  - [ ] On cache miss: proceed to retrieval; write response to cache *only if* `RetrievalQualityGate` validated answer as verified (`STRONG` or high confidence).
- [ ] **Task AB-6.2 (Telemetry Span Instrumentation):**
  - [ ] Wrap each stage of `QueryOrchestrator.answer()` in `PipelineTracer.trace_stage(PipelineStage)` context blocks.

#### Step 4.3: Neha [Sequential Owner 3 - Contextual Rewriting & Append Logging]
- **[Dependency: Step 4.2 completed by Abhinav (Query normalization and cache hooks active)]**
- [ ] **Task NE-4.2 (Contextual Query Rewriting Integration):**
  - [ ] In `QueryOrchestrator.answer()`, invoke `ConversationQueryResolver` *before* normalization when multi-turn session history exists, rewriting pronouns into standalone query terms.
- [ ] **Task NE-1.3 (Single-Turn Append Logging Hook):**
  - [ ] Update `_safe_log_conversation()` in `QueryOrchestrator`: pass only active turn (user question and assistant answer) to `ConversationLogger`, using session ID to append to active file.

#### Step 4.4: Akaash Samson [Sequential Owner 4 - Citation Guardrails & Suppression]
- **[Dependency: Step 4.3 completed by Neha (Prompting, rewriting, and logging hooks active)]**
- [ ] **Task AK-5.2 (Two-Stage Citation Guardrail Finalization):**
  - [ ] Stage 1 Gate: Check if retrieval returned empty evidence due to distance cutoff; if so, immediately return negative response without invoking LLM or caching.
  - [ ] Stage 2 Post-LLM Inspection: Inspect LLM output with `_NO_INFO_PATTERN` regex (`"could not find that information"`, `"not mentioned in the documents"`):
    - [ ] Wipe citations array (`citations = []`).
    - [ ] Clear pending citations (`_pending_citations.pop(session_id, None)`).
    - [ ] Strip trailing reference prompts (*"Would you like to see the references for this?"*).

---

### PHASE 5: UI Polish, Lifespan Integration, Containerization & E2E Validation

**Objective:** Complete frontend views, wire FastAPI startup lifespan hooks, build Docker infrastructure, and run comprehensive end-to-end regression tests.

#### 1. Roshan [Parallel - UI Governance & Explorer Views]
- [ ] **Task RO-1.3 (Company Directory UI):** Add "Company Directory" view in `streamlit_app/pages/explorer.py` rendering table of all active employees (name, UID, department, role, email).
- [ ] **Task RO-2.2 (Refresh Session Persistence Wiring):** Update `streamlit_app/app.py` and `authentication_service.py` to restore session state from `st.query_params` on browser refresh and validate token against `/api/users/me/profile`.
- [ ] **Task RO-3.2 (Projects Page Fixes & Polish):** In `streamlit_app/pages/projects.py`:
  - [ ] Conditionally fetch project members/documents only when `project.get("can_manage")` is True.
  - [ ] Guard against KeyError on empty departments; remove manual "Project ID" text input.
- [ ] **Task RO-4.4 (User Delete & Document Edit UI):**
  - [ ] Add "Delete User" button with confirmation modal in `streamlit_app/pages/users.py`.
  - [ ] Add "Edit Document" metadata form in `streamlit_app/pages/documents.py`.
- [ ] **Task RO-5.4 (UI Auto-ID Cleanups):** Remove manual ID text inputs from `pages/users.py`, `pages/departments.py`, and `pages/documents.py`. Delete metadata-only registration form.
- [ ] **Task RO-6.2 (Unassigned Document Access UI):** Display and enable access configuration grants for unassigned documents in `streamlit_app/pages/documents.py`.
- [ ] **Task RO-7.4 (Direct Image Upload UI):** Add `"png", "jpg", "jpeg"` file types to `st.file_uploader` in `streamlit_app/pages/documents.py`.

#### 2. Neha [Parallel - Streamlit Session Identification & Lifespan Task]
- [ ] **Task NE-1.4 (Streamlit UUID Session & Timestamps):** In `streamlit_app/app.py`:
  - [ ] Initialize unique `uuid.uuid4()` as `session_id` in `st.session_state` upon login/start.
  - [ ] Attach frontend UTC ISO timestamps to user chat messages upon sending.
- [ ] **Task NE-2.2 (Lifespan Periodic Cleanup Hook):** In `app/main.py`:
  - [ ] Register 24-hour periodic log cleanup `asyncio` background task inside FastAPI `lifespan` context manager.

#### 3. Akaash Samson [Parallel - DevOps, Lifespan Registry & Token Privacy]
- [ ] **Task AK-6.1 (UI Token Privacy Separation):** In `streamlit_app/app.py`:
  - [ ] Remove technical token metric strings from user chat bubbles.
  - [ ] Move sidebar token usage metrics behind administrator role check (`if st.session_state.get("is_admin"): ...`).
- [ ] **Task AK-6.2 (API Token Masking):** In `app/api/routes/chat.py`: Suppress `tokens` in `ChatResponse` (return `None`) for non-admin principals.
- [ ] **Task AK-2.5 (Channel Lifespan Startup):** In `app/main.py`: Mount `ChannelRegistry.initialize_channels(app)` in FastAPI lifespan context manager to initialize active driving adapters (e.g. Teams).
- [ ] **Task AK-7.1 (Production Dockerfile):** Create root `Dockerfile` (Python 3.12-slim, layer-cached dependencies, ports 8000 and 8501) and `.dockerignore`.
- [ ] **Task AK-7.2 (Docker Compose Full Stack):** Create `docker-compose.yml` orchestrating `knowlayer-api` (port 8000), `knowlayer-ui` (port 8501), `langfuse-server` (port 3000), and `langfuse-db` (port 5432).

#### 4. Coordinated Team Verification & Validation [All Teammates]
- [ ] **Task AB-7 (Cache & Tracing Evaluation - Abhinav):** Run evaluation suite (`test_quality_aware_cache.py`, `test_pipeline_tracing.py`, `test_dual_cache.py`).
- [ ] **Task AK-VERIFY (Channel & Container Validation - Akaash):** Execute Teams ASGI channel simulation tests (`test_teams_channel_adapter.py`) and verify container stack health (`docker compose up -d`).
- [ ] **Task NE-VERIFY (Logging & Retention Audit - Neha):** Run conversation logging and retention tests (`test_conversation_logger.py`, append-mode verification).
- [ ] **Task RO-VERIFY (Session, Directory & OCR Audit - Roshan):** Run session persistence contract test (`test_session_persistence.py`), directory tests, and OCR ingestion verification (`test_ocr_wrapper.py`).
- [ ] **Task ALL-TEST (Full Regression Gate - All Team):** Run repository-wide test suite:
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\unit tests\contract tests\integration -q -p no:cacheprovider
  python -m compileall -q app streamlit_app tests
  ```

---

## 3. Flexibility, Adaptation & De-Risking Strategy

To guarantee smooth development and absorb unexpected changes during implementation, the team adheres to four adaptive protocols:

### 3.1. Pluggable Fallbacks & Decoupled Stubs (Zero-Block Policy)
If an external tool, binary, or third-party service is delayed, the dependent teammate must not block. Use the following pre-built seams:

| Subsystem | Primary Target | Fallback Stub (Zero Blocker) | Protocol |
|:---|:---|:---|:---|
| **Observability** | Self-hosted Langfuse Docker container | `NoOpObservabilityProvider` | If Langfuse setup is delayed, the system logs spans locally to stdout with zero errors. |
| **Multimodal OCR** | Tesseract OCR engine binary (`tesseract.exe`) | Mock OCR Seam (`app/infrastructure/ingestion/ocr.py`) | Tests mock OCR outputs using canned text fixtures; developers without Tesseract installed can run full ingestion tests. |
| **Query Reranking** | Cloud Cross-Encoder API (Cohere / HuggingFace) | ChromaDB Cosine Distance Fallback | If API keys or external networks are unavailable, reranking gracefully falls back to raw vector similarity ranks. |
| **Teams Channel** | Live Microsoft Bot Framework Endpoint | In-Memory ASGI Test Client | Teams adapter is fully verified via synthetic in-process HTTP requests without requiring an Azure Bot registration. |

### 3.2. Phase Gate Quality Checkpoints
At the conclusion of each phase, team leads conduct an automated sync before opening the next phase:

1. **Gate 1 (Post-Phase 1):** All schema models, Pydantic contracts, and isolated service files must pass `python -m compileall app streamlit_app` and isolated unit tests.
2. **Gate 2 (Post-Phase 2):** Domain logic modules merged to individual feature branches. Zero overlap in `query_orchestrator.py`.
3. **Gate 3 (Post-Phase 3):** Pairwise test fixtures pass for Ingestion (`test_image_extractor.py`), Retrieval (`test_retrieval_quality.py`), and Tracing.
4. **Gate 4 (Post-Phase 4):** Sequential gate on `query_orchestrator.py` executed strictly in order (Akaash -> Abhinav -> Neha -> Akaash). Merge into `dev` requires all existing unit/contract tests to pass.
5. **Gate 5 (Post-Phase 5):** Complete end-to-end integration and smoke test passing across Streamlit UI, API, and Teams channel.

### 3.3. Change Control & Scope Adjustment Protocol
If scope needs adjustment during execution:
- **Phase B Vision Ingestion:** Genuine multimodal vision models (passing raw images to Claude/GPT-4o) remain explicitly deferred to Phase B. Phase A (OCR text extraction at ingest) fulfills all requirements with zero vector store schema changes.
- **Cache Backend Migration:** If Redis LangCache is prioritized over in-memory LRU cache, Abhinav swaps the storage backend inside `QualityAwareCache` without altering the `QueryOrchestrator` interface.
- **Git Branch Recovery:** If merge conflicts arise on any branch, developers rebase against `dev` instead of merging, preserving linear commit history.

---

## 4. Master Task-to-Owner Cross-Reference Table

| Task ID | Owner | Phase | Nature | Primary Files Impacted |
|:---|:---|:---:|:---:|:---|
| **AK-1.1** | Akaash | Phase 1 | Parallel | `app/domain/services/session_memory_service.py` |
| **AK-1.2** | Akaash | Phase 1 | Parallel | `app/core/settings.py` |
| **AK-3.1** | Akaash | Phase 1 | Parallel | `app/infrastructure/observability/provider.py` |
| **AK-2.1** | Akaash | Phase 1 | Parallel | `app/infrastructure/channels/base.py` |
| **AB-2** | Abhinav | Phase 1 | Parallel | `app/infrastructure/llm/llm_response.py` |
| **AB-1.1** | Abhinav | Phase 1 | Parallel | `app/infrastructure/llm/provider_health.py`, `provider_error_tracker.py` |
| **AB-3.1** | Abhinav | Phase 1 | Parallel | `app/use_cases/chat/query_normalizer.py` |
| **NE-3.1** | Neha | Phase 1 | Parallel | `config/prompts.yaml`, `app/core/prompt_config.py` |
| **NE-1.1** | Neha | Phase 1 | Parallel | `app/infrastructure/logging/conversation_logger.py` |
| **NE-1.2** | Neha | Phase 1 | Parallel | `app/infrastructure/logging/database_employee_id_provider.py` |
| **NE-2.1** | Neha | Phase 1 | Parallel | `app/infrastructure/logging/conversation_log_cleanup.py` |
| **RO-2.1** | Roshan | Phase 1 | Parallel | `streamlit_app/services/session_store.py` |
| **RO-5.1** | Roshan | Phase 1 | Parallel | `app/api/schemas/organization.py`, `app/use_cases/organization/user_management.py` |
| **RO-5.2** | Roshan | Phase 1 | Parallel | `app/use_cases/organization/user_management.py` |
| **RO-1.1** | Roshan | Phase 1 | Parallel | `app/api/schemas/explorer.py` |
| **RO-3.1** | Roshan | Phase 1 | Parallel | `app/api/schemas/organization.py` |
| **RO-4.1** | Roshan | Phase 1 | Parallel | `app/api/schemas/documents.py` |
| **RO-7.1** | Roshan | Phase 1 | Parallel | `requirements.txt`, `app/core/settings.py`, `.env.example` |
| **AK-2.2** | Akaash | Phase 2 | Parallel | `app/infrastructure/channels/identity_bridge.py` |
| **AK-2.3** | Akaash | Phase 2 | Parallel | `app/infrastructure/channels/teams/adapter.py`, `formatter.py` |
| **AK-2.4** | Akaash | Phase 2 | Parallel | `app/infrastructure/channels/registry.py` |
| **AK-3.2** | Akaash | Phase 2 | Parallel | `app/infrastructure/observability/langfuse_provider.py`, `manager.py` |
| **AK-3.3** | Akaash | Phase 2 | Parallel | `app/infrastructure/llm/groq_client.py` |
| **AB-4** | Abhinav | Phase 2 | Parallel | `app/infrastructure/cache/quality_aware_cache.py` |
| **AB-5.1** | Abhinav | Phase 2 | Parallel | `app/use_cases/chat/retrieval_quality.py` |
| **AB-6.1** | Abhinav | Phase 2 | Parallel | `app/infrastructure/observability/pipeline_tracer.py` |
| **AB-1.2** | Abhinav | Phase 2 | Parallel | `app/infrastructure/llm/openrouter_client.py`, `groq_client.py` |
| **NE-4.1** | Neha | Phase 2 | Parallel | `app/use_cases/chat/conversation_query_resolver.py` |
| **NE-5.1** | Neha | Phase 2 | Parallel | `app/use_cases/chat/retrieval_service.py` |
| **NE-6.1** | Neha | Phase 2 | Parallel | `app/use_cases/ingestion/document_processing.py` |
| **NE-6.2** | Neha | Phase 2 | Parallel | `app/use_cases/ingestion/document_processing.py` |
| **NE-3.2** | Neha | Phase 2 | Parallel | `app/use_cases/chat/rag_context_builder.py` |
| **RO-1.2** | Roshan | Phase 2 | Parallel | `app/use_cases/organization/organization_explorer.py` |
| **RO-4.2** | Roshan | Phase 2 | Parallel | `app/use_cases/organization/user_management.py`, `app/api/routes/organization.py` |
| **RO-4.3** | Roshan | Phase 2 | Parallel | `app/use_cases/organization/document_management.py`, `app/api/routes/documents.py` |
| **RO-5.3** | Roshan | Phase 2 | Parallel | `app/use_cases/organization/document_management.py` |
| **RO-6.1** | Roshan | Phase 2 | Parallel | `app/domain/services/authorization_engine.py` |
| **RO-7.2** | Roshan | Phase 2 | Parallel | `app/infrastructure/ingestion/ocr.py`, `image_extractor.py`, `captioner.py` |
| **RO-7.3** | Roshan | Phase 3 | Sequential (Lead) | `app/infrastructure/ingestion/provisioner.py` |
| **NE-6.3** | Neha | Phase 3 | Dependent [Roshan] | `app/use_cases/ingestion/document_processing.py` |
| **NE-5.2** | Neha | Phase 3 | Sequential (Lead) | `app/use_cases/chat/retrieval_service.py` |
| **AB-5.2** | Abhinav | Phase 3 | Dependent [Neha] | `app/use_cases/chat/retrieval_service.py` |
| **AK-5.1** | Akaash | Phase 3 | Dependent [Abhinav] | `app/use_cases/chat/retrieval_service.py` |
| **AK-3.4** | Akaash | Phase 3 | Sequential (Lead) | `app/infrastructure/observability/manager.py` |
| **AB-6.3** | Abhinav | Phase 3 | Dependent [Akaash] | `app/infrastructure/observability/pipeline_tracer.py` |
| **AK-1.3** | Akaash | Phase 4 | Sequential (Step 4.1) | `app/use_cases/chat/query_orchestrator.py` |
| **AK-4** | Akaash | Phase 4 | Sequential (Step 4.1) | `app/use_cases/chat/query_orchestrator.py` |
| **AB-3.2** | Abhinav | Phase 4 | Sequential (Step 4.2) [Akaash] | `app/use_cases/chat/query_orchestrator.py` |
| **AB-4.2** | Abhinav | Phase 4 | Sequential (Step 4.2) [Akaash] | `app/use_cases/chat/query_orchestrator.py` |
| **AB-6.2** | Abhinav | Phase 4 | Sequential (Step 4.2) [Akaash] | `app/use_cases/chat/query_orchestrator.py` |
| **NE-4.2** | Neha | Phase 4 | Sequential (Step 4.3) [Abhinav] | `app/use_cases/chat/query_orchestrator.py` |
| **NE-1.3** | Neha | Phase 4 | Sequential (Step 4.3) [Abhinav] | `app/use_cases/chat/query_orchestrator.py` |
| **AK-5.2** | Akaash | Phase 4 | Sequential (Step 4.4) [Neha] | `app/use_cases/chat/query_orchestrator.py` |
| **RO-1.3** | Roshan | Phase 5 | Parallel | `streamlit_app/pages/explorer.py` |
| **RO-2.2** | Roshan | Phase 5 | Parallel | `streamlit_app/app.py`, `authentication_service.py` |
| **RO-3.2** | Roshan | Phase 5 | Parallel | `streamlit_app/pages/projects.py` |
| **RO-4.4** | Roshan | Phase 5 | Parallel | `streamlit_app/pages/users.py`, `streamlit_app/pages/documents.py` |
| **RO-5.4** | Roshan | Phase 5 | Parallel | `streamlit_app/pages/users.py`, `departments.py`, `documents.py` |
| **RO-6.2** | Roshan | Phase 5 | Parallel | `streamlit_app/pages/documents.py` |
| **RO-7.4** | Roshan | Phase 5 | Parallel | `streamlit_app/pages/documents.py` |
| **NE-1.4** | Neha | Phase 5 | Parallel | `streamlit_app/app.py` |
| **NE-2.2** | Neha | Phase 5 | Parallel | `app/main.py` |
| **AK-6.1** | Akaash | Phase 5 | Parallel | `streamlit_app/app.py` |
| **AK-6.2** | Akaash | Phase 5 | Parallel | `app/api/routes/chat.py` |
| **AK-2.5** | Akaash | Phase 5 | Parallel | `app/main.py` |
| **AK-7.1** | Akaash | Phase 5 | Parallel | `Dockerfile`, `.dockerignore` |
| **AK-7.2** | Akaash | Phase 5 | Parallel | `docker-compose.yml` |
| **AB-7** | Abhinav | Phase 5 | Coordinated | `tests/unit/test_quality_aware_cache.py`, `test_pipeline_tracing.py` |
| **AK-VERIFY** | Akaash | Phase 5 | Coordinated | `test_teams_channel_adapter.py`, `docker compose up -d` |
| **NE-VERIFY** | Neha | Phase 5 | Coordinated | `test_conversation_logger.py`, append-mode verification |
| **RO-VERIFY** | Roshan | Phase 5 | Coordinated | `test_session_persistence.py`, `test_ocr_wrapper.py` |
| **ALL-TEST** | All | Phase 5 | Coordinated | Full repository test suite (`pytest`) |
