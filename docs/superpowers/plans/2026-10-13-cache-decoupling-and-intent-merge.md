# Cache Decoupling and Intent Classifier Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cherry-pick Abhinav's cache-only enhancements (10-category intent classifier, lexical overlap gate, personal data cache bypass) into current branch without touching tracer/observability code, and detach cache from the active pipeline via environment variable switches so the branch is ready to push to `dev`.

**Architecture:** Integrate the updated `QueryIntentClassifier` and `cache_quality.py` gates directly into `InMemoryQualityAwareCache`. Guard all cache lookups and writes in `chat.py` and `QueryOrchestrator` behind `SEMANTIC_CACHE_ENABLED` and `FAQ_SIMILARITY_CACHE_ENABLED` flags (defaulted to `false`), allowing zero-overhead detachment in production while keeping cache code verified and pluggable.

**Tech Stack:** Python 3.11+, FastAPI, Pytest, Regex, Difflib, SentenceTransformers.

**Spec:** User directive for cache detachment, Abhinav branch (`origin/Abhinav`) cache commit `7d9a8cf`.

## Global Constraints

- Do NOT touch `app/infrastructure/observability/pipeline_tracer.py` or `tracer.py`. Preserve ContextVar concurrency tracing.
- Do NOT delete `uv.lock`, `pyproject.toml`, or input documents in `input/`.
- Minimal diff principle (/ponytail): reuse existing `SEMANTIC_CACHE_ENABLED` and `FAQ_SIMILARITY_CACHE_ENABLED` settings in `app/core/settings.py`.
- Default behavior when running pipeline: cache is detached (`SEMANTIC_CACHE_ENABLED=false`, `FAQ_SIMILARITY_CACHE_ENABLED=false`).

## Review Focus

1. `SEMANTIC_CACHE_ENABLED=false`: `QueryOrchestrator.answer()` must never perform cache lookups or writes.
2. `SEMANTIC_CACHE_ENABLED=true`: `QueryIntent.PERSONAL_STATUS` queries must bypass shared cache on read and write.
3. Cache intent compatibility: queries matching semantically but differing in intent category (e.g. procedure vs entitlement) must reject cache reuse.
4. Concurrency & observability: pipeline tracer spans must remain unaffected and report `cache_hit=False` cleanly when disabled.
5. Invalidation: `invalidate_document()` must cleanly purge affected cache entries without throwing errors.

---

### Task 1: Merge Abhinav Intent Classifier & Cache Quality Gates

**Files:**
- Modify: `app/use_cases/chat/query_intent_classifier.py`
- Modify: `app/core/cache_quality.py`
- Modify: `app/infrastructure/cache/quality_aware_cache.py`
- Create: `tests/unit/test_cache_consistency.py`

**Interfaces:**
- Consumes: `QueryIntentClassifier.classify(query: str) -> IntentClassificationResult`
- Produces:
  - `check_cache_intent_compatibility(q1: str, q2: str) -> bool`
  - `calculate_content_token_overlap(q1: str, q2: str) -> float`
  - `QualityAwareCache._check_rbac_access(...)` + lexical overlap gating

- [x] **Step 1: Copy test suite `test_cache_consistency.py` from `origin/Abhinav`**

Create `tests/unit/test_cache_consistency.py` with tests covering:
- 10-category intent classification.
- Intent vs topic extraction.
- Personal data isolation (`NO_SHARED_CACHE`).
- Paraphrase hits for matching intent.
- Refusal response filtering.

- [x] **Step 2: Run test to verify it fails on missing helper functions**

Run: `pytest tests/unit/test_cache_consistency.py -v`
Expected: FAIL on `classify_query_intent`, `check_cache_intent_compatibility`, etc.

- [x] **Step 3: Update `app/core/cache_quality.py` with intent compatibility helpers**

Add `classify_query_intent`, `check_cache_intent_compatibility`, and `calculate_content_token_overlap`.

- [x] **Step 4: Update `app/use_cases/chat/query_intent_classifier.py` from Abhinav's implementation**

Incorporate 10-category classification (`GREETING`, `PERSONAL_STATUS`, `CONTACT_LOOKUP`, `CHANGE_REQUEST`, `LIST_REQUEST`, `PROCEDURE_HOW_TO`, `ROLE_OR_RESPONSIBILITY`, `POLICY_LOOKUP`, `OUT_OF_SCOPE`, `GENERAL_QA`), `QueryTopic`, and `CachePolicy`.

- [x] **Step 5: Update `app/infrastructure/cache/quality_aware_cache.py` with intent & lexical gates**

Add:
- `NO_SHARED_CACHE` read and write bypass.
- Intent compatibility and `difflib.SequenceMatcher` / `calculate_content_token_overlap` checks during semantic cache hit candidate evaluation.
- `invalidate_document(doc_id)` on stale document detection.

- [x] **Step 6: Run consistency test suite to verify all pass**

Run: `pytest tests/unit/test_cache_consistency.py tests/unit/test_query_intent_classifier.py -v`
Expected: PASS

- [x] **Step 7: Commit Task 1**

```bash
git add app/core/cache_quality.py app/use_cases/chat/query_intent_classifier.py app/infrastructure/cache/quality_aware_cache.py tests/unit/test_cache_consistency.py
git commit -m "feat(cache): merge intent classifier, lexical gate, and personal cache isolation"
```

---

### Task 2: Detach All Cache Layers from Pipeline via Environment Toggle

**Files:**
- Modify: `app/core/settings.py`
- Modify: `app/api/routes/chat.py`
- Modify: `app/use_cases/chat/query_orchestrator.py`
- Create: `tests/unit/test_cache_toggle.py`

**Interfaces:**
- Consumes:
  - `SEMANTIC_CACHE_ENABLED: bool`
  - `FAQ_SIMILARITY_CACHE_ENABLED: bool`
  - `LLM_CACHE_ENABLED: bool`
  - `LLM_CACHE_SIZE: int` from `app.core.settings`
- Produces:
  - `init_orchestrator()` passing `response_cache=None` when `SEMANTIC_CACHE_ENABLED=False`
  - `FallbackLLMProvider` using `PromptLRUCache(maxsize=0)` when `LLM_CACHE_ENABLED=False`

- [x] **Step 1: Write test `tests/unit/test_cache_toggle.py`**

```python
import pytest
from app.use_cases.chat.query_orchestrator import QueryOrchestrator
from app.infrastructure.llm.fallback_llm_provider import FallbackLLMProvider
from unittest.mock import MagicMock

def test_orchestrator_skips_response_and_faq_cache_when_disabled(monkeypatch):
    monkeypatch.setattr("app.core.settings.SEMANTIC_CACHE_ENABLED", False)
    monkeypatch.setattr("app.core.settings.FAQ_SIMILARITY_CACHE_ENABLED", False)
    
    mock_cache = MagicMock()
    orchestrator = QueryOrchestrator(
        response_cache=mock_cache,
    )
    # When SEMANTIC_CACHE_ENABLED=False, response_cache must be deactivated/ignored
    assert orchestrator.response_cache is None
    assert orchestrator.faq_cache is None

def test_prompt_lru_cache_disabled_when_llm_cache_disabled(monkeypatch):
    monkeypatch.setattr("app.core.settings.LLM_CACHE_ENABLED", False)
    monkeypatch.setattr("app.core.settings.LLM_CACHE_SIZE", 0)

    provider = FallbackLLMProvider(
        primary=MagicMock(),
        fallback=MagicMock(),
    )
    assert provider.cache.maxsize == 0
    # maxsize=0 must never store or return hits
    provider.cache.put([{"role": "user", "content": "hi"}], "hello")
    assert provider.cache.get([{"role": "user", "content": "hi"}]) is None
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cache_toggle.py -v`
Expected: FAIL

- [x] **Step 3: Update `app/core/settings.py` defaults to `false`**

Set:
```python
FAQ_SIMILARITY_CACHE_ENABLED = os.getenv("FAQ_SIMILARITY_CACHE_ENABLED", "false").lower() == "true"
SEMANTIC_CACHE_ENABLED = os.getenv("SEMANTIC_CACHE_ENABLED", "false").lower() == "true"
LLM_CACHE_ENABLED = os.getenv("LLM_CACHE_ENABLED", "false").lower() == "true"
LLM_CACHE_SIZE = int(os.getenv("LLM_CACHE_SIZE", "128")) if LLM_CACHE_ENABLED else 0
```

- [x] **Step 4: Update `app/api/routes/chat.py` and `app/use_cases/chat/query_orchestrator.py`**

In `chat.py:init_orchestrator()`:
```python
from app.core.settings import SEMANTIC_CACHE_ENABLED
response_cache = get_semantic_cache() if SEMANTIC_CACHE_ENABLED else None
_orchestrator = QueryOrchestrator(response_cache=response_cache)
```

In `QueryOrchestrator.__init__()`:
```python
self.response_cache = response_cache if SEMANTIC_CACHE_ENABLED else None
```

- [x] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_cache_toggle.py -v`
Expected: PASS

- [x] **Step 6: Commit Task 2**

```bash
git add app/core/settings.py app/api/routes/chat.py app/use_cases/chat/query_orchestrator.py tests/unit/test_cache_toggle.py
git commit -m "feat(cache): detach all cache layers by default via env flags"
```

---

### Task 3: Regression Suite & Dev Preparation

**Files:**
- Test: `tests/unit/test_cache_consistency.py`
- Test: `tests/unit/test_cache_factory.py`
- Test: `tests/unit/test_orchestrator_memory_tracing.py`
- Test: `tests/unit/test_pipeline_tracer_concurrency.py`

- [x] **Step 1: Run comprehensive regression test run**

Run: `pytest tests/unit/test_cache_consistency.py tests/unit/test_cache_toggle.py tests/unit/test_cache_factory.py tests/unit/test_orchestrator_memory_tracing.py tests/unit/test_pipeline_tracer_concurrency.py -v`
Expected: All tests PASS with zero tracer/concurrency failures.

- [x] **Step 2: Verify git status is clean and ready for push to dev**

Verify no unstaged artifacts or unintended file deletions.
