# Security, Authorization & Regression Review — KnowLayer

Date: 2026-09-15
Scope: complete authorization review of the KnowLayer (Company_Bot) system against 15 authorization-bypass scenarios, full test-suite runs, fixes for genuine defects, and hardening recommendations. No new features were added.

---

## 1. Test results

| Suite | Result |
| --- | --- |
| `compileall -q app streamlit_app tests` | passed |
| `pytest tests/unit tests/contract` | **394 passed** |
| `pytest tests/integration` | **41 passed** |

Total: **435 passed, 0 failed.** (Baseline was 365 unit/contract + 40 integration with one failing e2e test; the +29 unit tests are the new scenario-regression suite added by this review.)

New test file: `tests/unit/test_authz_bypass_regression.py` (29 tests) pins the fixed behavior for all 15 scenarios.

---

## 2. Genuine defects found and fixed

### 2.1 Privilege escalation via `update_user` role change (HIGH)
Any non-admin actor (including a plain Developer) could change the `role` field of any in-scope user through `update_user` — including their **own** role to `Admin`, and managers could promote other department users.
**Fix:** `app/use_cases/organization/user_management.py:166` — only administrators may change user roles (`ForbiddenError`).

### 2.2 Manager can create Admin users (HIGH)
`create_user` allowed a department manager to create new users with `role="Admin"` in their own department, escalating to global admin without any admin involvement.
**Fix:** `app/use_cases/organization/user_management.py:105` — only administrators may create admin users (`ForbiddenError`).

### 2.3 User enumeration via `update_user` 404/403 split (MEDIUM)
`update_user` raised `NotFoundError` (→ 404) for a missing target BEFORE the scope check, while an existing-but-out-of-scope target raised 403. A non-admin could distinguish existing user IDs (404) from non-existing ones (403) by probing `PUT /api/users/{id}`.
**Fix:** `app/use_cases/organization/user_management.py:147-150` — non-admin actors receive the scope-shaped `ForbiddenError` (403) for a missing target; only an admin gets the truthful 404.

### 2.4 Document grant escalates into whole-project retrieval (HIGH)
In selected-project chat, `authorization_scope` returned `project_ids=[selected_project_id]` when the user held **only** a document grant inside that project. The retrieval filter (`$or: [project_id IN ... , document_id IN ...]`) then exposed **every active document in the project**, not just the granted one. A single-document grant therefore opened the entire project corpus to the LLM via `POST /api/chat` with that `project_id`.
**Fix:**
- `app/domain/services/authorization_engine.py` — the doc-grant-only branch now returns `project_ids=[]` + `document_ids=[grants belonging to the selected project]`; the project is never added wholesale.
- `app/api/routes/chat.py:19` — the 403 gate now also requires `not scope.document_ids`, so a legitimate document-grant selection is served document-scoped instead of denied or leaked.
- Pinned test updated: `tests/unit/test_authorization_engine.py::test_selected_project_with_document_grant` now asserts `project_ids == []`.

### 2.5 Incorrect e2e authorization assertion (LOW, test-only)
`tests/integration/test_user_management_e2e.py` asserted an admin deleting a missing user returns 403 (it correctly returns 404/204-flow) and used a skipif that always skipped.
**Fix:** rewrote the test to seed `e2e-deactivate`, expect `204`, and verify `status == "inactive"`; skipif now checks `_admin_exists(...)`. Also made it idempotent against the persistent SQLite DB (leftover user cleanup before seeding).

---

## 3. Scenario-by-scenario findings

| # | Scenario | Verdict | Notes |
| --- | --- | --- | --- |
| 1 | Unauthorized project docs | Safe | `can_read_document` / `can_view_project_documents` gate membership/lead/manage/grant only |
| 2 | Unauthorized doc metadata | Safe | Profile & explorer already leak-free; contract tests assert `doc-secret` never appears |
| 3 | Cross-dept manager scope | Safe | Manager scope is department-aware end to end |
| 4 | Doc-level restrictions vs project membership | **FIXED (2.4)** | Doc grants previously broadened into whole-project retrieval |
| 5 | Inactive users | Safe | Rejected at authn, engine, profile, explorer layers |
| 6 | Unauthorized Chroma chunks | Safe | Empty `project_ids` early-returns `[]`; doc-id filter isolates grants |
| 7 | Unauthorized citations | Safe | Protected end-to-end via orchestrator + access probe (integration tests) |
| 8 | Direct API call bypass | Safe | Backend chat gate returns 403; access-request response for empty scope reveals no content |
| 9 | Streamlit not sole control | Safe | Pages are thin HTTP clients; no `can_`/`AuthorizationEngine`/sqlite in page code (contract-level source scans) |
| 10 | Self-privilege escalation | **FIXED (2.1)** | Previously non-admin could change own role to Admin |
| 11 | Manager → admin escalation | **FIXED (2.2)** | Previously manager could create Admin users |
| 12 | Dept-scoped manager vs other departments | Safe | Project + user + role management all scope-checked |
| 13 | Self-add to projects | Safe | Assignment goes through `can_manage_project`; self-add of an out-of-scope project is denied |
| 14 | Unauthorized doc-access modification | Safe | Grant/revoke requires `DOCUMENT_MANAGE_ACCESS` + document manage scope |
| 15 | Leave project removes scope | Safe | `leave` flips membership to `left`; scope derived from active memberships only (now regression-pinned) |

---

## 4. Remaining risks / observations (no changes required)

1. **Enumeration surface (low):** other endpoints may still differ subtly between 403/404 (e.g. `get_user` only for admins). Consistent 403-for-out-of-scope is applied to `update_user`; a broader pass over every route could unify this.
2. **`can_manage_department` intentionality:** any same-department user may manage department memberships (pinned test at `tests/unit/test_authorization_engine.py:134`). Documented as intentional, but worth confirming it matches product intent (a Developer managing department membership is unusual).
3. **Document grants are global by design:** a doc grant in a project the user cannot otherwise access is retrievable in unselected chat (that is the documented purpose), and is enforced only via `document_id` filtering. If new retrieval paths are added, they must reuse `authorization_scope`.
4. **Empty-scope chat returns a safe access-request response (200) by design**, not an error; consider whether this should be 4xx in stricter environments.
5. **Password hygiene:** seed admin still uses `ADMIN_INITIAL_PASSWORD=change-me-before-first-login` with `must_change_password=True`; keep this enforced (no fallback bypass).

---

## 5. Hardening recommendations

- Add an E2E Chroma-level test that chats with a selected project where the only grant is a document grant, asserting the sibling documents are absent from citations (extends `tests/integration/test_retrieval_authorized_scope_e2e.py`).
- Add contract tests for the two new escalation guards (non-admin role change → 403; manager creating Admin → 403) so the HTTP envelope is pinned, not just the service layer.
- Standardize 403 vs 404 semantics across all `use_cases/organization/*` endpoints in one pass.
- Re-run the full suite (`pytest tests/unit tests/contract -q -p no:cacheprovider` then `pytest tests/integration -q -p no:cacheprovider`) in CI on every PR; consider a scheduled run against the seeded `instance/knowlayer.db` to catch idempotency regressions.