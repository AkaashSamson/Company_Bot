# RB28: PII and Sensitive Salary Information Leakage into Pipeline Tracer Log Spans

> **Category:** Observability, Traceability & Production Deployment  
> **Severity:** CRITICAL | **Probability:** HIGH  
> **Blast Radius:** GDPR / HIPAA compliance violation; unauthorized exposure of employee compensation

---

## 1. Problem Description & Root Cause

Employees ask questions about their specific salary, medical leave reasons, or performance improvement plans. `PipelineTracer` logs input queries, retrieved evidence, and generated answers into plaintext log files and cloud spans. Internal developers with logging access can view private employee medical and payroll records.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: PII Leakage into Plaintext Traces                 |
+-------------------------------------------------------------------------+
| Employee Query: 'My salary is $120,000, why was my medical deduction...'|
|                                                                         |
| PipelineTracer records span:                                            |
| {                                                                       |
|   'stage': 'RETRIEVAL',                                                 |
|   'input': 'My salary is $120,000...',                                  |
|   'output': 'Deductions for employee John Doe...'                       |
| }                                                                       |
| [!] Exported to third-party LangSmith / saved in world-readable logs    |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Implement a Regex PII masking scrubber in `PipelineTracer` (redact SSN, salary figures, phone numbers, emails).
2. Enable telemetry encryption at rest and strict role-based access to telemetry projects.
3. Store only anonymized session hashes rather than employee names in trace spans.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
