# RB05: Cache Invalidation Poison Pill: Unicode Normalization Mismatch in Deletion

> **Category:** Semantic Caching & Vector Store Corruption  
> **Severity:** MEDIUM | **Probability:** MEDIUM  
> **Blast Radius:** Cache eviction fails silently; undeletable corrupted entries persist forever

---

## 1. Problem Description & Root Cause

An entry in `data/faqs.json` contains smart quotes, non-breaking spaces (U+00A0), or accented characters. When the UI or orchestrator attempts to evict the entry using standard ASCII strings (e.g. `"` vs `”`), `target == entry['question']` evaluates to False. The cache deletion silently reports 0 deletions, leaving the poison entry active.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Unicode Normalization Eviction Bypass             |
+-------------------------------------------------------------------------+
| Stored FAQ: 'What is company’s policy?' (Right curly quote U+2019)       |
| Evict Request: 'What is company's policy?' (Straight ASCII quote U+0027)|
|                                                                         |
| Code: if entry.get('question').strip().lower() == target:               |
|       'what is company’s policy?' == 'what is company's policy?'        |
|       -> False!                                                         |
|                                                                         |
| [!] Entry NOT deleted! Remains stuck in cache permanently.             |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Run NFKD or NFC unicode normalization via `unicodedata.normalize('NFKD', ...)` on all questions before caching and searching.
2. Strip non-alphanumeric punctuation when computing cache keys and comparison hashes.
3. Support deterministic canonical ID-based eviction rather than solely raw question string matching.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
