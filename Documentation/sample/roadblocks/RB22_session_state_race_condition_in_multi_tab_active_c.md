# RB22: Session State Race Condition in Multi-Tab Active Conversations

> **Category:** Concurrency, Session State & Database Deadlocks  
> **Severity:** HIGH | **Probability:** HIGH  
> **Blast Radius:** User receives answers to questions asked in another browser tab; citations cross-pollinated

---

## 1. Problem Description & Root Cause

Streamlit users frequently open multiple browser tabs. If the frontend passes a default or fixed `session_id` (or tab switching occurs rapidly), global orchestrator state `_last_interaction[session_id]` is overwritten by Tab 2 while Tab 1 is awaiting citations, returning references for the wrong question.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Multi-Tab State Cross-Pollination                 |
+-------------------------------------------------------------------------+
| Browser Tab 1: 'What is maternity leave?' (Session: 'user_101')         |
| Browser Tab 2: 'How to claim travel expense?' (Session: 'user_101')     |
|                                                                         |
| Tab 2 overwrites _last_interaction['user_101'] with 'travel expense'   |
| User in Tab 1 clicks '👍 Yes, show references'                          |
|                                                                         |
| [!] Orchestrator returns Travel Expense references for Maternity Leave! |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Generate unique UUIDs per browser tab (`session_id = f'{user_id}_{tab_uuid}'`) stored in Streamlit session_state.
2. Decouple interaction state from memory dictionaries by persisting interaction IDs in the message payload itself.
3. Enforce stateless reference requests where the client transmits the target interaction ID.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
