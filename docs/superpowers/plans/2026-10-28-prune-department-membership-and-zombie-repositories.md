# Prune Zombie Repositories & Unify Single Security Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cleanly prune all 4 zombie subsystems (`department_members`, `project_grants`, `document_grants`, and `business_id_sequences`), eliminating hollow repository stubs and dead services; establish `users.department_id` as the single source of truth for departments and `user_projects` as the single security boundary for projects and documents; update API endpoints and Streamlit UI to query live tables; fix the failing integration test `test_department_membership_lifecycle_end_to_end`.

**Architecture:** 
1. **Department Membership:** Strict 1:1 mapping in `users.department_id`. Department members are queried directly from `users` (`WHERE department_id = :id`). User `billable_status` resolves from `departments.default_billable`.
2. **Project & Document Security:** `user_projects` is the single security boundary. A user has access to a project and its documents if and only if they hold an active membership in `user_projects` (or manage the project, or are admin). Explicit grant tables (`project_grants`, `document_grants`) are eliminated.
3. **Database Foundation:** 8 core tables in `models.py` (`users`, `departments`, `projects`, `documents`, `user_projects`, `roles`, `permissions`, `role_permissions`). Zero dummy repository stubs.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Streamlit, Pytest.

**Spec:** [database_refinement_ledger.md](file:///C:/Users/AkaashSamsonAnandGud/.gemini/antigravity/brain/92ff0570-bf59-4f8a-95f5-40d70353ac83/database_refinement_ledger.md) and [Enterprise_Onboarding_RBAC_and_Bulk_Provisioning_Spec.md](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/Documentation/Architecture/Enterprise_Onboarding_RBAC_and_Bulk_Provisioning_Spec.md).

## Global Constraints

- Never query or reference dropped tables (`department_members`, `project_grants`, `document_permissions`, `business_id_sequences`).
- Department membership is strictly defined by `users.department_id`.
- Project and project document access is strictly defined by `user_projects` (`uow.memberships`).
- Never grant departmental management authority simply because `user.department_id == department_id`; verify admin privileges or explicit permissions (`DEPARTMENT_UPDATE` / `DEPARTMENT_MANAGE`).
- Streamlit UI must read and mutate live entities via `users` and `user_projects`.
- All changes must pass existing E2E Acts 1 through 4 without regression.

## Review Focus

1. **Department Member Operations**: Querying members of a department returns active users from `users` whose `department_id` matches. Assigning an employee updates `users.department_id`.
2. **Single Security Boundary for Documents**: A user assigned to a project in `user_projects` can view and read all documents in that project. A non-member cannot read project documents.
3. **Profile Assembly**: `ProfileService.get_profile()` resolves `billable_status` from `departments.default_billable` and project/document lists without querying grant tables.
4. **Authorization Security**: `can_manage_department` and `can_manage_role` cannot be bypassed by non-admin users lacking explicit permissions.
5. **Zero Zombie Code in UnitOfWork**: Calling any repository on `SqlAlchemyUnitOfWork` targets an active table with real SQL statements.

---

### Task 1: Prune Zombie Repositories & Stub Classes from Persistence Layer

**Files:**
- Modify: `app/infrastructure/persistence/sqlalchemy/repositories.py`
- Modify: `app/infrastructure/persistence/sqlalchemy/unit_of_work.py`
- Modify: `app/domain/ports/unit_of_work.py`
- Modify: `app/domain/ports/organization_repositories.py`
- Modify: `tests/fixtures/organization_repositories.py`
- Test: `tests/unit/test_database_foundation.py`

**Interfaces:**
- Consumes: `UnitOfWork` protocols and `SqlAlchemyUnitOfWork`.
- Produces: Clean `UnitOfWork` containing only active repositories (`users`, `departments`, `projects`, `documents`, `memberships`, `roles`, `permissions`).

- [x] **Step 1: Write test in `tests/unit/test_database_foundation.py` verifying no zombie stubs**

Add assertion in `test_database_foundation.py`:
```python
def test_unit_of_work_has_no_zombie_stubs():
    from app.infrastructure.persistence.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork
    from app.infrastructure.persistence.sqlalchemy.session import create_engine_and_session_factory
    engine, session_factory = create_engine_and_session_factory("sqlite:///:memory:")
    uow = SqlAlchemyUnitOfWork(session_factory)
    assert not hasattr(uow, "department_members")
    assert not hasattr(uow, "project_grants")
    assert not hasattr(uow, "document_grants")
    assert not hasattr(uow, "sequences")
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_database_foundation.py -k "test_unit_of_work_has_no_zombie_stubs" -v`
Expected: FAIL (`AssertionError: assert not hasattr(uow, 'department_members')`).

- [x] **Step 3: Remove zombie repository classes and UoW bindings**

1. In `app/infrastructure/persistence/sqlalchemy/repositories.py`:
   - Delete `DepartmentMemberRecord = None` and `ProjectGrantRecord = None` (lines 28, 30).
   - Delete `_department_member`, `_project_grant`, `_document_grant` mappers (lines 89-126).
   - Delete `SqlAlchemyDepartmentMemberRepository` (lines 328-343).
   - Delete `SqlAlchemyProjectGrantRepository` (lines 431-455).
   - Delete `SqlAlchemyDocumentGrantRepository` (lines 457-478).
   - Delete `SqlAlchemySequenceRepository` (lines 480-496).
2. In `app/infrastructure/persistence/sqlalchemy/unit_of_work.py`:
   - Remove imports of `SqlAlchemyDepartmentMemberRepository`, `SqlAlchemyProjectGrantRepository`, `SqlAlchemyDocumentGrantRepository`, `SqlAlchemySequenceRepository`.
   - Remove `self.department_members`, `self.project_grants`, `self.document_grants`, `self.sequences` from `__init__`.
3. In `app/domain/ports/unit_of_work.py`:
   - Remove `department_members`, `project_grants`, `document_grants`, `sequences` attributes from `UnitOfWork` protocol.
4. In `app/domain/ports/organization_repositories.py`:
   - Remove protocols `DepartmentMemberRepository`, `ProjectGrantRepository`, `DocumentGrantRepository`, `SequenceRepository`.
5. In `tests/fixtures/organization_repositories.py`:
   - Remove `self.department_members`, `self.project_grants`, `self.document_grants`, `self.sequences` from `InMemoryUnitOfWork` (or preserve lightweight no-op properties if needed by legacy unit fixtures).

- [x] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_database_foundation.py -k "test_unit_of_work_has_no_zombie_stubs" -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add app/infrastructure/persistence/sqlalchemy/repositories.py app/infrastructure/persistence/sqlalchemy/unit_of_work.py app/domain/ports/unit_of_work.py app/domain/ports/organization_repositories.py tests/fixtures/organization_repositories.py tests/unit/test_database_foundation.py
git commit -m "refactor(persistence): remove zombie repository stubs and unbind from UnitOfWork"
```

---

### Task 2: Purge Grants and Department Members from `AuthorizationEngine` & `ProfileService`

**Files:**
- Modify: `app/domain/services/authorization_engine.py`
- Modify: `app/use_cases/organization/profile.py`
- Test: `tests/unit/test_authorization_engine.py`
- Test: `tests/unit/test_profile_service.py`

**Interfaces:**
- Consumes: `uow.users`, `uow.departments`, `uow.projects`, `uow.documents`, `uow.memberships` (`user_projects`).
- Produces:
  - Clean `AuthorizationEngine` evaluating project and document access solely via `uow.memberships`.
  - Secure `can_manage_department` requiring admin or `DEPARTMENT_UPDATE`/`DEPARTMENT_MANAGE`.
  - Clean `ProfileService` resolving `billable_status` from `department.default_billable` and project access from `user_projects`.

- [x] **Step 1: Write failing test in `tests/unit/test_profile_service.py`**

```python
def test_profile_resolves_without_grants_or_department_members():
    # Verify profile succeeds when UoW has neither department_members nor grant repositories
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_profile_service.py -k "test_profile_resolves_without_grants_or_department_members" -v`
Expected: FAIL.

- [x] **Step 3: Update `authorization_engine.py` and `profile.py`**

1. In `app/domain/services/authorization_engine.py`:
   - Remove `_has_project_grant` and `_has_document_grant` helper methods (lines 131-136).
   - In `_roles_for_user`: delete the `if hasattr(uow, "department_members"):` loop (lines 98-107).
   - In `_project_access_scope`: remove line `project_ids.update(uow.project_grants.project_ids_for_principal(...))`.
   - In `can_access_project`: remove fallback `return self._has_project_grant(uow, user, project_id)`. Access is granted if manager, same department, or in `uow.memberships`.
   - In `can_view_project_documents`: remove fallback `return self._has_project_grant(...)`. Access is granted if manager or in `uow.memberships`.
   - In `can_read_document`: remove `_has_document_grant` and `_has_project_grant`. If `document.project_id` is set, user must be manager or have active membership in `uow.memberships`.
   - In `authorization_scope`: remove `uow.document_grants` and `uow.project_grants`. Return `AuthorizationScope(is_admin=False, project_ids=effective_projects, document_ids=None, include_unassigned=True)`.
   - In `can_manage_department`:
     ```python
     def can_manage_department(self, principal: AuthenticatedPrincipal, department_id: str) -> bool:
         if principal is None:
             return False
         with self.unit_of_work_factory() as uow:
             user = self._active_user(uow, principal.uid)
             if user is None:
                 return False
             if self._is_admin_user(uow, user):
                 return True
             if user.department_id == department_id:
                 perms = self._permission_names(uow, user)
                 return bool({"DEPARTMENT_UPDATE", "DEPARTMENT_MANAGE", "ADMIN"} & perms)
             return False
     ```
2. In `app/use_cases/organization/profile.py`:
   - Replace lines 38-48:
     ```python
     department = uow.departments.get(actor.department_id) if actor.department_id else None
     billable_status = department.default_billable if department is not None else None
     ```
   - In `_project`: access source is `"lead_or_manager"`, `"department"`, or `"member"` (remove `grant_project_ids`).
   - In `_document`: access source is `"org_wide"` (if `project_id is None`) or `"project_access"` (remove `grant_document_ids`).

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_profile_service.py tests/unit/test_authorization_engine.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add app/domain/services/authorization_engine.py app/use_cases/organization/profile.py tests/unit/test_profile_service.py tests/unit/test_authorization_engine.py
git commit -m "fix(authz): eliminate grant stubs from authorization engine and profile service"
```

---

### Task 3: Implement `list_department_users` in `UserManagementService` & Fix Integration Test

**Files:**
- Modify: `app/use_cases/organization/user_management.py`
- Modify: `app/use_cases/organization/department_membership.py` (deprecate / simplify)
- Modify: `tests/integration/test_department_membership_e2e.py`
- Test: `tests/integration/test_department_membership_e2e.py`

**Interfaces:**
- Consumes: `uow.users` and `uow.departments`.
- Produces: `UserManagementService.list_department_users(actor_uid, department_id) -> list[User]`.

- [x] **Step 1: Update `tests/integration/test_department_membership_e2e.py` to test true department user lifecycle**

Update test to verify:
1. Users created with `department_id="d1"` are listed via `users.list_department_users("admin", "d1")`.
2. Department default billable status is returned via `department.default_billable`.
3. Updating a user's department moves them cleanly from department A to department B.

- [x] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_department_membership_e2e.py -v`
Expected: FAIL (`AttributeError: 'UserManagementService' object has no attribute 'list_department_users'`).

- [x] **Step 3: Implement `list_department_users` in `UserManagementService`**

In `app/use_cases/organization/user_management.py`:
```python
    def list_department_users(self, actor_uid: str, department_id: str) -> list[User]:
        with self.unit_of_work_factory() as uow:
            actor = uow.users.get_by_uid(actor_uid)
            if actor is None or actor.status != "active":
                raise ForbiddenError("Active authenticated user required")
            department = uow.departments.get(department_id)
            if department is None:
                raise NotFoundError("Department not found")
            return [
                user for user in uow.users.list()
                if user.department_id == department_id and user.status == "active"
            ]
```
In `app/use_cases/organization/department_membership.py`:
Turn `DepartmentMembershipService` into a thin backward-compatible adapter delegating to `UserManagementService` or query `uow.users`.

- [x] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_department_membership_e2e.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add app/use_cases/organization/user_management.py app/use_cases/organization/department_membership.py tests/integration/test_department_membership_e2e.py
git commit -m "feat(users): add list_department_users and fix department lifecycle integration test"
```

---

### Task 4: Re-route FastAPI Endpoints & Deprecate Dead Grant Routes

**Files:**
- Modify: `app/api/dependencies.py`
- Modify: `app/api/routes/organization.py`
- Modify: `app/api/routes/documents.py`
- Test: `tests/contract/test_explorer_api.py`
- Test: `tests/contract/test_profile_api.py`

**Interfaces:**
- Consumes: `get_user_management_service` and `get_membership_management_service`.
- Produces:
  - `GET /api/departments/{department_id}/members` returning `list[UserResponse]`.
  - `POST /api/departments/{department_id}/members` assigning user to department via `user_management.update_user`.
  - `DELETE /api/departments/{department_id}/members/{user_id}` unassigning user from department.
  - Safe deprecation of `/projects/{id}/access` and `/documents/{id}/access` endpoints.

- [x] **Step 1: Write test verifying `GET /api/departments/{id}/members` returns user list**

Test in contract suite:
`GET /api/departments/{department_id}/members` returns HTTP 200 with list of `UserResponse`.

- [x] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/contract/test_explorer_api.py -v`
Expected: FAIL or verify current response schema.

- [x] **Step 3: Update endpoints in `organization.py` and `documents.py`**

1. In `app/api/routes/organization.py`:
   - `GET /api/departments/{department_id}/members`:
     ```python
     @router.get("/departments/{department_id}/members", response_model=list[UserResponse])
     def list_department_members(
         department_id: str,
         principal=Depends(get_current_principal),
         service=Depends(get_user_management_service),
     ):
         try:
             return service.list_department_users(principal.uid, department_id)
         except Exception as error:
             raise _error(error) from error
     ```
   - `POST /api/departments/{department_id}/members`: Calls `user_management.update_user(principal.uid, payload.user_id, {"department_id": department_id})`.
   - `DELETE /api/departments/{department_id}/members/{user_id}`: Calls `user_management.update_user(principal.uid, user_id, {"department_id": None})`.
   - Deprecate `/projects/{id}/access` endpoints: Return HTTP 200 with empty list or forward to project members.
2. In `app/api/routes/documents.py`:
   - Deprecate `/documents/{id}/access` endpoints: Return HTTP 200 with empty list.
3. In `app/api/dependencies.py`:
   - Clean up unused service dependencies.

- [x] **Step 4: Run contract tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/contract/test_explorer_api.py tests/contract/test_profile_api.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add app/api/dependencies.py app/api/routes/organization.py app/api/routes/documents.py tests/contract/test_explorer_api.py tests/contract/test_profile_api.py
git commit -m "refactor(api): route department member endpoints through UserManagementService and prune grant routes"
```

---

### Task 5: Streamlit Frontend Alignment & AdminAPI Cleanup

**Files:**
- Modify: `streamlit_app/pages/departments.py`
- Modify: `streamlit_app/services/admin_api.py`
- Test: `tests/contract/test_streamlit_management_pages.py`

**Interfaces:**
- Consumes: `admin.list_users()`, `admin.update_user()`.
- Produces: Live, reactive Department Members table in Streamlit powered directly by active user accounts.

- [x] **Step 1: Check `test_streamlit_management_pages.py`**

Run: `.venv\Scripts\python.exe -m pytest tests/contract/test_streamlit_management_pages.py -v`
Ensure test expectations match the API interface.

- [x] **Step 2: Update `streamlit_app/pages/departments.py`**

1. In "Assign Employee to Department" section:
   Call `service.update_user(user_options[user_label], {"department_id": department_options[dept_label]})`.
2. In "Department Members" section:
   Filter users directly:
   ```python
   members = [u for u in users if u.get("department_id") == member_dept_id]
   ```
   Display data table containing: Employee ID, Name, Username, Role, Status.
3. In "Remove Member" section:
   Call `service.update_user(selected_uid, {"department_id": None})`.

- [x] **Step 3: Update `AdminAPI` in `streamlit_app/services/admin_api.py`**

Keep required method signatures for backward compatibility (e.g. `list_department_members`, `grant_document_access`) but point them to safe operations or empty lists without network errors.

- [x] **Step 4: Run contract tests to verify compliance**

Run: `.venv\Scripts\python.exe -m pytest tests/contract/test_streamlit_management_pages.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add streamlit_app/pages/departments.py streamlit_app/services/admin_api.py tests/contract/test_streamlit_management_pages.py
git commit -m "fix(streamlit): render department members directly from active user directory"
```

---

### Task 6: Full Regression Verification (Unit, Integration, E2E Acts 1-4)

**Files:**
- None (verification only)

- [x] **Step 1: Run complete unit, integration, and contract test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/unit tests/integration tests/contract -v`
Expected: All tests PASS with 0 errors.

- [x] **Step 2: Run End-to-End Acts 1 through 4**

Run:
```bash
.venv\Scripts\python.exe -m pytest tests/e2e/test_01_bootstrap.py tests/e2e/test_02_org_setup.py tests/e2e/test_03_hr_timesheets.py tests/e2e/test_04_projects.py -v
```
Expected: All 4 E2E acts pass cleanly.

- [x] **Step 3: Update Documentation Ledger**

Update [`Documentation/Team_logs/Akaash/Discovered_Issues_and_Fix_Proposals.md`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/Documentation/Team_logs/Akaash/Discovered_Issues_and_Fix_Proposals.md) logging Issue 009 (Zombie Repositories and Security Boundary Unification) as Resolved.

- [x] **Step 4: Commit**

```bash
git add Documentation/Team_logs/Akaash/Discovered_Issues_and_Fix_Proposals.md
git commit -m "docs(ledger): record resolution of zombie repository pruning and security boundary unification"
```
