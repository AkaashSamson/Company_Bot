# KnowLayer V3: Phase 1 & Phase 2 PR Cross-Check, Audit & Merge Strategy

**Document Status:** Approved Merge Baseline  
**Target Baseline Branch:** `dev`  
**Integration Branch:** `feature/consolidate-p1-p2`  
**Associated Guide:** [Task_Timeline.md](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/Documentation/Plan/v3/Task_Timeline.md)  
**Date:** September 2026  

---

## 1. Executive Summary & Core Strategy

The KnowLayer team has reached the end of Phase 1 and Phase 2 implementation. Pull requests are open across all contributors targeting `dev`.

### Key Strategic Decisions:
1. **Defer Teams Integration Until After Core Merge (Akaash):**
   - Microsoft Teams is an **inbound driving channel adapter** (`app/infrastructure/channels/teams/`). It invokes `POST /api/chat` or `QueryOrchestrator.answer()`.
   - The core domain and application services never depend on Teams. No teammate in Phase 1, 2, 3, or 4 has an upstream dependency on Teams.
   - Deferring Teams allows Akaash to merge `SessionMemoryService` (AK-1.1) and `ObservabilityManager` (AK-3.2/3.4) immediately so Neha and Abhinav are not blocked.
   - Building Teams after merging auth/user contracts (Roshan) guarantees the Teams identity bridge connects to final, verified user and JWT schemas.
2. **"Merge Now, Record Fixes into Future Phase Tasks":**
   - The team is in an intermediate state of learning the codebase. Perfect alignment across 4 parallel branches is unrealistic.
   - Rather than blocking on perfection, we merge Phase 1 & Phase 2 into a single consolidated baseline branch, test it thoroughly, and document any known friction points as explicit "Fix-up" line items inside Phase 3 and Phase 4.
3. **Repository Cleanup PR (#24) Merged LAST:**
   - PR #24 deletes obsolete runtime caches (`data/response_cache.json`, `data/faqs_cache.json`).
   - PR #22 (Abhinav) modified `data/response_cache.json`.
   - Merging PR #24 before PR #22 causes a Git delete/modify collision. Merging PR #24 last cleanly wipes runtime cache files without conflict.
4. **Isolated Integration Branch Workflow:**
   - Instead of merging directly into `dev` via GitHub UI, we check out `dev`, branch `feature/consolidate-p1-p2`, perform sequential merges locally, resolve conflicts, run unit tests, and fast-forward `dev`.

---

## 2. PR-to-Task-Timeline Cross-Check Matrix

| Contributor | PR # & Branch | Planned Tasks in Phase 1 & 2 | Implementation Status | Scope Drift / Ahead-of-Time Work |
|:---|:---|:---|:---|:---|
| **Akaash** | **#26** (`p1-akaash`) | **AK-1.1**: Session memory service<br>**AK-1.2**: Settings config<br>**AK-3.1**: Observability protocols<br>**AK-3.2**: Langfuse/Phoenix providers<br>**AK-2.1-2.4**: Channel & Teams | • **AK-1.1**: Complete (`session_memory_service.py`)<br>• **AK-1.2**: Complete (`settings.py`)<br>• **AK-3.1**: Complete (`ports/observability.py`)<br>• **AK-3.2**: Complete (`langfuse_provider.py`, etc.)<br>• **AK-3.4**: Complete (`manager.py` singleton)<br>• **AK-2.1 - 2.4**: Deferred to Post-Merge | Zero unwanted drift. Clean boundary adherence. |
| **Roshan** | **#25** (`p1-roshan`) | **RO-1.1**: Directory schema<br>**RO-1.2**: Directory service<br>**RO-2.1**: Streamlit session store<br>**RO-3.1**: Project scope schema<br>**RO-4.1 - 4.3**: Doc update & hard delete<br>**RO-5.1 - 5.3**: Auto IDs (User, Dept, Doc)<br>**RO-6.1**: Unassigned doc access<br>**RO-7.1 - 7.2**: OCR deps & wrapper | • **RO-1.1 & 1.2**: Complete (`explorer.py`)<br>• **RO-2.1**: Complete (`session_auth.py`)<br>• **RO-3.1**: Complete (`can_manage: bool`)<br>• **RO-4.2**: Complete (hard delete user)<br>• **RO-5.1 - 5.3**: Complete (auto IDs)<br>• **RO-6.1**: Complete (`authorization_engine.py`)<br>• **RO-7.1**: Complete (`requirements.txt`)<br>• **RO-7.2**: Incomplete (`ocr.py` deferred) | Completed several Phase 5 UI tasks early (`pages/explorer.py`, `pages/roles.py`, `pages/users.py`, login refresh persistence). |
| **Neha** | **#23** (`feature/Neha`) | **NE-1.1**: Append-mode logging<br>**NE-1.2**: Database employee ID<br>**NE-2.1**: Background cleanup<br>**NE-3.1**: Externalize YAML prompts<br>**NE-3.2**: XML prompt defense<br>**NE-4.1**: Query rewriter<br>**NE-5.1**: Cross-encoder reranker<br>**NE-6.1 - 6.2**: Chunking overlap/headers | • **NE-1.1**: Complete (`conversation_logger.py`)<br>• **NE-1.2**: Complete (enforce DB ID)<br>• **NE-2.1**: Complete (background cleanup)<br>• **NE-3.1**: Complete (`prompts.yaml`, loader)<br>• **NE-3.2**: Complete (`rag_context_builder.py`)<br>• **NE-4.1, 5.1, 6.1**: Incomplete / Deferred to Phase 3 | Completed Phase 5 tasks early: Streamlit session UUID & timestamps (`app.py`, `chat_service.py`), lifespan cleanup task (`main.py`). Modifies `query_orchestrator.py` logging hook. |
| **Abhinav** | **#22** (`Abhinav`) | **AB-1.1 - 1.2**: Provider health & circuit breaker<br>**AB-2**: LLMResponse contract<br>**AB-3.1**: Query normalizer<br>**AB-4**: Quality-aware cache<br>**AB-5.1**: Retrieval quality gate<br>**AB-6.1**: Pipeline tracing engine | • **AB-1.1 & 1.2**: Complete (`provider_health.py`, client health)<br>• **AB-2**: Complete (`llm_response.py`)<br>• **AB-3.1**: Complete (`query_normalizer.py`)<br>• **AB-4**: Complete (`quality_aware_cache.py`, `dual_cache.py`)<br>• **AB-5.1**: Complete (`retrieval_quality.py`)<br>• **AB-6.1**: Complete (`pipeline_tracer.py`) | Heavy drift into Phase 4: Edited `query_orchestrator.py` (+444 lines) and `streamlit_app/app.py` (+203 lines) ahead of the sequential Hot File Gate schedule. |
| **Akaash** | **#24** (`chore/cleanup-repo`) | Repository hygiene | • Deleted legacy V2 documentation<br>• Deleted bloated runtime cache JSON files<br>• Updated `.gitignore` to ignore runtime caches | Must merge last after Abhinav's branch. |

---

## 3. High-Collision Hotspots & Resolution Strategy

When merging these PRs, conflicts will arise in 4 specific locations. Here is how each must be resolved:

### 1. `app/core/settings.py` (4-Way Collision)
- **Akaash:** Adds `SESSION_INACTIVITY_TIMEOUT_HOURS`, `SESSION_MAX_HISTORY_TURNS`, Observability settings (`OBSERVABILITY_PROVIDER`, `LANGFUSE_*`, `PHOENIX_*`).
- **Roshan:** Adds Tesseract/OCR settings and authentication configurations.
- **Neha:** Adds conversation log retention days.
- **Abhinav:** Adds cache thresholds, provider health parameters, circuit breaker settings.
- **Resolution:** Combine all additions into clearly commented sections. Ensure no duplicate variable names or conflicting defaults.

### 2. `app/use_cases/chat/query_orchestrator.py` (Critical Conflict)
- **Neha:** Updated `_safe_log_conversation()` to send only active turns (preventing quadratic log explosion) and accept `question_timestamp`.
- **Abhinav:** Wrapped `answer()` with `PipelineTracer`, inserted `QueryNormalizer`, integrated `QualityAwareCache`, and added fallback error handling.
- **Resolution:** 
  1. Keep Abhinav's pipeline tracing and caching structure.
  2. Preserve Neha's non-duplicating append-mode log call inside `_finish()`/`_safe_log_conversation()`.
  3. Wire in Akaash's `SessionMemoryService` when session history is not provided by the caller.

### 3. `streamlit_app/app.py` (3-Way Collision)
- **Roshan:** Added session query params token restoration (`session_auth.py`), user profile verification.
- **Neha:** Added frontend UTC timestamp tagging and session UUID generation.
- **Abhinav:** Added cache bypass toggles, provider health badges, and latency tracking.
- **Resolution:** Combine sequentially: Roshan's authentication session check at the top $\rightarrow$ Neha's session UUID & timestamp generation on message send $\rightarrow$ Abhinav's cache bypass and debug controls in the sidebar.

### 4. `data/response_cache.json` (PR #24 vs PR #22)
- Abhinav modified cached responses; PR #24 deletes the file from git tracking.
- **Resolution:** Merge PR #22 first, verify cache functionality, then apply PR #24 to delete runtime JSON files and commit `.gitignore`.

---

## 4. Phase 3 & Phase 4 Future Task Adjustments (Fix Ledger)

Because several tasks were either deferred or built ahead of schedule, update the execution plan as follows:

### Adjustments for Phase 3:
1. **Task RO-7.2 (OCR Wrapper):** Roshan needs to complete `app/infrastructure/ingestion/ocr.py` so Phase 3 multimodal ingestion can proceed.
2. **Task NE-4.1 & NE-5.1 (Rewriter & Reranker):** Neha's standalone rewriter class and Cohere/cross-encoder reranker remain to be wired into `retrieval_service.py`.
3. **Task AB-6.3 (Pipeline Tracer -> ObservabilityManager Bridge):** Abhinav's `PipelineTracer` must dispatch traces to Akaash's `ObservabilityManager.dispatch_trace()` using the singleton `get_observability_manager()`.

### Adjustments for Phase 4:
1. **Orchestrator Consolidation Check:** Because Abhinav already placed cache and tracer hooks into `query_orchestrator.py`, Phase 4 Step 4.2 is largely complete.
2. **Phase 4 Step 4.1 (Akaash):** Connect `SessionMemoryService` into `QueryOrchestrator.answer()`.
3. **Phase 4 Step 4.4 (Akaash):** Implement two-stage citation guardrail (`_NO_INFO_PATTERN` and empty retrieval cutoff).

---

## 5. Step-by-Step Merge Execution Procedure

Execute these steps strictly from the root of the repository:

### Step 1: Switch to `dev` and Branch
```powershell
git checkout dev
git pull origin dev
git checkout -b feature/consolidate-p1-p2
```

### Step 2: Merge PR #26 (`p1-akaash`)
```powershell
git merge origin/p1-akaash -m "merge: Phase 1 & 2 Akaash (Session Memory & Observability)"
```
*(Clean merge expected with zero conflicts.)*

### Step 3: Merge PR #25 (`p1-roshan`)
```powershell
git merge origin/p1-roshan -m "merge: Phase 1 & 2 Roshan (Identity, DB, Admin UI)"
```
*(Resolve any small overlaps in `settings.py` or `.gitignore`.)*

### Step 4: Merge PR #23 (`feature/Neha`)
```powershell
git merge origin/feature/Neha -m "merge: Phase 1 Neha (Logging, Prompts, Lifespan)"
```
*(Resolve `settings.py` and `app/main.py` lifespan cleanly.)*

### Step 5: Merge PR #22 (`Abhinav`)
```powershell
git merge origin/Abhinav -m "merge: Phase 1 & 2 Abhinav (Cache, Health, Tracer, Normalizer)"
```
*(Resolve `query_orchestrator.py`, `settings.py`, and `streamlit_app/app.py`.)*

### Step 6: Validate Consolidated Baseline
```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit -q
python -m compileall -q app streamlit_app tests
```

### Step 7: Merge PR #24 (`chore/cleanup-repo`) & Finalize
```powershell
git merge origin/chore/cleanup-repo -m "chore: cleanup cache files and update gitignore"
```

### Step 8: Fast-Forward `dev` & Push
```powershell
git checkout dev
git merge feature/consolidate-p1-p2
git push origin dev
```
All teammates then run `git checkout dev && git pull origin dev` to base their Phase 3 work on the unified baseline.
