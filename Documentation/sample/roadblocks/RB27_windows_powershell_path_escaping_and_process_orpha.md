# RB27: Windows PowerShell Path Escaping and Process Orphanage in Local Server Management

> **Category:** Observability, Traceability & Production Deployment  
> **Severity:** HIGH | **Probability:** CRITICAL  
> **Blast Radius:** Port 8000 / 8501 collisions; server scripts fail to start silently

---

## 1. Problem Description & Root Cause

On Windows environments with OneDrive paths containing spaces (`OneDrive - McLaren Strategic Solutions...`), PowerShell scripts without strict escaping fail on virtualenv binary invocation. Terminated Streamlit or Uvicorn processes leave zombie Python PIDs holding open listening ports, causing `setup.ps1` to stall.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Windows Process Orphanage & Port Lock             |
+-------------------------------------------------------------------------+
| User stops script via Ctrl+C                                            |
| Shell terminates, but Python child process (PID 14280) remains running  |
| Port 8000 remains bound to PID 14280 in TIME_WAIT                       |
|                                                                         |
| User runs setup.ps1:                                                    |
| [!] Uvicorn Error: [WinError 10048] Only one usage of each socket address|
|     is normally permitted                                               |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Enforce proactive port cleanup via `Get-NetTCPConnection` and `Stop-Process -Force` in `setup.ps1` (already implemented).
2. Use properly quoted Call operators `& "$venvPython"` for paths with spaces.
3. Register Windows Job Objects to guarantee child process tree termination on shell exit.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
