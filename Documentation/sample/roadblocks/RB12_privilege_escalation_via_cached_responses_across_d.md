# RB12: Privilege Escalation via Cached Responses Across Differing User Role Scopes

> **Category:** Multi-Tenant RBAC / ABAC Security & Scoping  
> **Severity:** CRITICAL | **Probability:** HIGH  
> **Blast Radius:** Unprivileged users obtain confidential responses cached by admins

---

## 1. Problem Description & Root Cause

An Admin user asks: 'What is the executive bonus allocation formula?'. The LLM generates a comprehensive response based on executive documents, which is saved into `response_cache.json` under key 'executive bonus allocation formula'. An intern queries the exact same question. The orchestrator checks `response_cache` before evaluating document scopes, serving the admin-level cached answer to the intern.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Cache Key Role Agnosticism                        |
+-------------------------------------------------------------------------+
| Step 1: Admin User asks 'What is executive severance formula?'          |
|         LLM answers with confidential payout tiers                      |
|         Saved to response_cache with key='executive severance formula'   |
|                                                                         |
| Step 2: Regular Employee asks 'What is executive severance formula?'    |
|         Cache lookup matches key='executive severance formula'          |
|                                                                         |
| [!] Cache hit occurs BEFORE RBAC authorization check!                   |
|     Employee reads confidential executive severance figures.            |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Incorporate authorization scope hash into all cache keys (`cache_key = f'{scope_hash}:{normalized_query}'`).
2. Bypass response cache entirely whenever `authorization_scope` contains restricted project/document sets.
3. Enforce permission re-validation on cache hits before returning response payload to client.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
