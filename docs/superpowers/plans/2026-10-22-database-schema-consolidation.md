# Database Schema Consolidation & Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate SQLite schema from 12 tables down to 8 clean, robust core tables in `models.py`, eliminating redundant tables (`department_members`, `document_permissions`, `project_grants`, `business_id_sequences`), deleting `foundation_models.py`, adding real foreign keys (`ondelete="SET NULL"` and `ondelete="CASCADE"`), and updating repositories and authorization engine to enforce a single security boundary.

**Architecture:** Single source of truth for ORM models in `app/infrastructure/persistence/sqlalchemy/models.py`. Department membership is strictly `users.department_id`; project and document access are strictly governed by `user_projects (uid, project_id, role_id)`. Business IDs are generated using configurable prefixes and monotonic in-memory sequence counters without SQLite table locks.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 (Mapped / mapped_column), SQLite (with `PRAGMA foreign_keys=ON`), pytest.

**Spec:** [Enterprise_Onboarding_RBAC_and_Bulk_Provisioning_Spec.md](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/Documentation/Architecture/Enterprise_Onboarding_RBAC_and_Bulk_Provisioning_Spec.md) and [database_refinement_ledger.md](file:///C:/Users/AkaashSamsonAnandGud/.gemini/antigravity/brain/92ff0570-bf59-4f8a-95f5-40d70353ac83/database_refinement_ledger.md).

## Global Constraints

- Never hardcode role names (e.g. `role == "Admin"`) in application logic; check capabilities strictly via `has_permission(actor, permission_name)`.
- Foreign key constraints must be strictly enabled on SQLite via `PRAGMA foreign_keys=ON`.
- Deleting a project cascades deletion to its `user_projects` memberships and `documents` (`ondelete="CASCADE"`).
- Deleting a user nullifies project manager or creator fields (`ondelete="SET NULL"`), never leaving dangling string IDs.
- Passwords must be stored in `users.password_hash` (no silent empty default).

## Review Focus

1. **Foreign key cascade on project deletion**: Deleting a project must cleanly remove associated `user_projects` and `documents` without foreign key constraint violation.
2. **User deletion nullifies manager/creator**: Deleting a user assigned as `manager_uid` or `created_by_uid` must set those columns to `NULL`.
3. **Empty password rejection**: Attempting to insert a user without a password hash must fail constraint validation rather than defaulting to empty string.
4. **Group grant expansion**: Adding a role to a project must populate `user_projects` for all active users holding that role without creating duplicate membership records.
5. **Single security boundary for documents**: A user not in `user_projects` for a project document must be denied access without checking obsolete grant tables.

---

### Task 1: Consolidate Models, Re-point Imports, & Delete `foundation_models.py`

**Files:**
- Modify: `app/infrastructure/persistence/sqlalchemy/models.py`
- Modify: `app/infrastructure/persistence/sqlalchemy/session.py` (remove foundation_models import)
- Modify: `app/infrastructure/persistence/sqlalchemy/repositories.py` (point Role/Permission imports to models.py)
- Modify: `tests/unit/test_database_foundation.py` (point imports to models.py)
- Delete: `app/infrastructure/persistence/sqlalchemy/foundation_models.py`

**Interfaces:**
- Consumes: `Base = DeclarativeBase()` in `models.py`.
- Produces: 8 ORM records (`UserRecord`, `DepartmentRecord`, `ProjectRecord`, `DocumentRecord`, `UserProjectRecord`, `RoleRecord`, `PermissionRecord`, `RolePermissionRecord`) exported from `models.py`.

- [ ] **Step 1: Update test expectations and imports in `test_database_foundation.py`**
Update imports to load all records from `models.py`.
Update `EXPECTED_TABLES` to exactly the 8 target tables:
```python
EXPECTED_TABLES = {
    "users",
    "departments",
    "projects",
    "documents",
    "user_projects",
    "roles",
    "permissions",
    "role_permissions",
}
```
Add tests verifying:
- `projects.manager_uid` and `projects.created_by_uid` have foreign keys to `users.uid`.
- `user_projects.project_id` and `documents.project_id` have `ondelete="CASCADE"`.
- `users.password_hash` exists, `password_representation` is gone, no empty string default.

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_database_foundation.py -v`
Expected: FAIL (missing `roles`/`permissions` in `models.py`, extra tables found, `password_hash` missing).

- [ ] **Step 3: Consolidate `models.py`, update callers, and delete `foundation_models.py`**
1. In `app/infrastructure/persistence/sqlalchemy/models.py`:
   - Move `RoleRecord`, `PermissionRecord`, `RolePermissionRecord` into `models.py`.
   - Update `UserRecord`:
     - Add `role_id: Mapped[Optional[int]] = mapped_column(ForeignKey("roles.id"), index=True, nullable=True)`
     - Add `job_title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)`
     - Rename `password_representation` $\rightarrow$ `password_hash: Mapped[str] = mapped_column(String(512), nullable=False)`
   - Update `ProjectRecord`:
     - `manager_uid: Mapped[Optional[str]] = mapped_column(ForeignKey("users.uid", ondelete="SET NULL"), nullable=True)`
     - `created_by_uid: Mapped[Optional[str]] = mapped_column(ForeignKey("users.uid", ondelete="SET NULL"), nullable=True)`
   - Update `DocumentRecord`:
     - `project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.project_id", ondelete="CASCADE"), index=True, nullable=True)`
   - Update `UserProjectRecord`:
     - `project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id", ondelete="CASCADE"), primary_key=True)`
     - `role_id: Mapped[Optional[int]] = mapped_column(ForeignKey("roles.id"), nullable=True)`
   - Remove `BusinessIdSequenceRecord`.
2. In `app/infrastructure/persistence/sqlalchemy/session.py`:
   - Remove `import app.infrastructure.persistence.sqlalchemy.foundation_models as _foundation_models`.
3. In `app/infrastructure/persistence/sqlalchemy/repositories.py`:
   - Import `RoleRecord`, `PermissionRecord`, `RolePermissionRecord` from `models.py` instead of `foundation_models.py`.
4. Delete `app/infrastructure/persistence/sqlalchemy/foundation_models.py`.

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_database_foundation.py -v`
Expected: PASS.

- [ ] **Step 5: Commit changes**
```bash
git add app/infrastructure/persistence/sqlalchemy/models.py app/infrastructure/persistence/sqlalchemy/session.py app/infrastructure/persistence/sqlalchemy/repositories.py tests/unit/test_database_foundation.py
git rm app/infrastructure/persistence/sqlalchemy/foundation_models.py
git commit -m "feat(db): consolidate 8-table schema in models.py and delete foundation_models.py"
```

---

### Task 2: Encapsulated SQLite Schema Migration & Clean `session.py`

**Files:**
- Create: `app/infrastructure/persistence/sqlalchemy/migrations.py`
- Modify: `app/infrastructure/persistence/sqlalchemy/session.py`
- Modify: `tests/unit/test_database_foundation.py`

**Interfaces:**
- Consumes: Consolidated `models.py`.
- Produces: Clean `session.py` and dedicated `apply_legacy_schema_migration(engine)` in `migrations.py` that transparently updates teammates' local databases on startup.

- [ ] **Step 1: Write test for legacy table pruning and column migration**
In `tests/unit/test_database_foundation.py`, add a test that creates legacy tables (`department_members`, `document_permissions`, `project_grants`, `business_id_sequences`) and a `users` table with `password_representation`, runs `initialize_database(engine)`, and verifies:
- Obsolete tables are dropped.
- `users` column `password_representation` is migrated to `password_hash`.
- `users.role_id` and `users.job_title` columns are added if missing.

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_database_foundation.py -k test_legacy_cleanup -v`
Expected: FAIL.

- [ ] **Step 3: Create `migrations.py` and strip legacy bloat from `session.py`**
1. Create `app/infrastructure/persistence/sqlalchemy/migrations.py`:
   Define `apply_legacy_schema_migration(engine)` to:
   - Check SQLite inspector:
     - Drop obsolete tables: `DROP TABLE IF EXISTS department_members`, `DROP TABLE IF EXISTS document_permissions`, `DROP TABLE IF EXISTS project_grants`, `DROP TABLE IF EXISTS business_id_sequences`.
     - In `users`: add `role_id INTEGER NULL` and `job_title VARCHAR(200) NULL` if missing.
     - In `users`: if `password_representation` exists and `password_hash` does not, run:
       `ALTER TABLE users ADD COLUMN password_hash VARCHAR(512) NOT NULL DEFAULT ''`
       `UPDATE users SET password_hash = password_representation WHERE password_hash = ''`
     - Clean up indexes (`CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)`).
2. Clean `app/infrastructure/persistence/sqlalchemy/session.py`:
   - Remove `_COLUMN_ADDITIONS`, `_INDEX_ADDITIONS`, `_LEGACY_PROJECTS_COLUMNS`, `_LEGACY_DOCUMENTS_COLUMNS`, and `_rebuild_legacy_table()`.
   - Update `initialize_database(engine)` to simply:
     ```python
     def initialize_database(engine) -> None:
         Path("instance").mkdir(exist_ok=True)
         Base.metadata.create_all(engine)
         # TODO(tech-debt): Remove once teammates have migrated their local SQLite DBs
         from app.infrastructure.persistence.sqlalchemy.migrations import apply_legacy_schema_migration
         apply_legacy_schema_migration(engine)
     ```

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_database_foundation.py -v`
Expected: PASS (all tests passing).

- [ ] **Step 5: Commit changes**
```bash
git add app/infrastructure/persistence/sqlalchemy/migrations.py app/infrastructure/persistence/sqlalchemy/session.py tests/unit/test_database_foundation.py
git commit -m "refactor(db): encapsulate legacy SQLite migration into migrations.py and clean session.py"
```

---

### Task 3: Replace Persistent `business_id_sequences` with In-Memory Sequence Generator & Human-Readable Document File Storage

**Files:**
- Modify: `app/domain/services/business_id_generator.py`
- Modify: `app/infrastructure/ingestion/provisioner.py`
- Modify: `tests/unit/test_business_id_generator.py`
- Modify: `tests/unit/test_document_provisioning.py`

**Interfaces:**
- Consumes: Entity list from unit of work (e.g. `[u.employee_id for u in uow.users.list()]`).
- Produces: `BusinessIdGenerator.next(uow, key) -> str` without querying or updating `business_id_sequences` table.
- Produces: Human-readable file saving in `provision_document` using `document_name` / `original_filename` instead of internal UUID/ID.

- [ ] **Step 1: Write test for database-independent sequence generation and human-readable document storage**
In `tests/unit/test_business_id_generator.py`, add a test verifying `generator.next(uow, "user")` generates `MSS-001`, `MSS-002`, etc. when `uow.sequences` is None or not present, relying directly on `highest_existing_suffix(existing_ids, prefix) + 1` with thread-safe atomic in-memory increment.
In `tests/unit/test_document_provisioning.py`, add a test asserting uploaded files in `DOCUMENTS_DIR` are saved using the sanitized `document_name` (e.g. `Leave_Policy.docx`) rather than internal ID (`DOC-001.docx` or UUID).

- [ ] **Step 2: Run tests to verify they fail**
Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_business_id_generator.py -k test_no_db_table -v`
Expected: FAIL.

- [ ] **Step 3: Update `business_id_generator.py` and `provisioner.py`**
1. In `app/domain/services/business_id_generator.py`:
   - Maintain thread-safe in-memory counters per sequence key initialized from `highest_existing_suffix(sequence.existing_ids(uow), sequence.prefix)`.
   - Generate next ID: `f"{sequence.prefix}-{counter:03d}"`.
   - Eliminate all calls to `uow.sequences.initialize` and `uow.sequences.allocate`.
2. In `app/infrastructure/ingestion/provisioner.py`:
   - Add `_safe_filename(name: str) -> str` to sanitize filenames without mangling user-facing document names.
   - When saving `content` to `DOCUMENTS_DIR`, use `f"{_safe_filename(base_name)}{ext}"` from `document.original_filename or document.document_name` instead of internal `document.document_id`.

- [ ] **Step 4: Run tests to verify they pass**
Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_business_id_generator.py tests/unit/test_document_provisioning.py -v`
Expected: PASS.

- [ ] **Step 5: Commit changes**
```bash
git add app/domain/services/business_id_generator.py app/infrastructure/ingestion/provisioner.py tests/unit/test_business_id_generator.py tests/unit/test_document_provisioning.py
git commit -m "refactor(ids): replace persistent sequence table with in-memory generator and human-readable doc filenames"
```

---

### Task 4: Update Domain Entities & Repositories for 8-Table Architecture

**Files:**
- Modify: `app/domain/entities/organization_models.py`
- Modify: `app/infrastructure/persistence/sqlalchemy/repositories.py`
- Modify: `app/infrastructure/persistence/sqlalchemy/unit_of_work.py`
- Modify: `app/domain/ports/unit_of_work.py`
- Test: `tests/unit/test_role_management.py`, `tests/unit/test_user_management.py`

**Interfaces:**
- Consumes: Consolidated models in `models.py`.
- Produces: Repositories for the 8 core tables with `password_hash`, `role_id`, and `job_title` mapped.

- [ ] **Step 1: Write failing test for entity fields and repository mapping**
In `tests/unit/test_user_management.py`, add test saving and retrieving a user with `role_id`, `job_title`, and `password_hash`. Verify `user.password_hash` stores the hash and `user.job_title` persists.

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_user_management.py -v`
Expected: FAIL.

- [ ] **Step 3: Update domain models, repositories, and unit of work**
1. In `app/domain/entities/organization_models.py`:
   - Update `User`: add `role_id: Optional[int] = None`, `job_title: Optional[str] = None`, rename `password_representation` $\to$ `password_hash: str = ""`. Preserve `role: str = ""` for backward compatibility with existing views.
   - Update `UserProject`: add `role_id: Optional[int] = None`.
2. In `app/infrastructure/persistence/sqlalchemy/repositories.py`:
   - Import `RoleRecord`, `PermissionRecord`, `RolePermissionRecord` from `models.py`.
   - In `SqlAlchemyUserRepository`: map `password_hash`, `role_id`, `job_title`.
   - In `SqlAlchemyMembershipRepository`: map `role_id`.
   - Remove/stub obsolete repositories (`SqlAlchemyDepartmentMemberRepository`, `SqlAlchemyProjectGrantRepository`, `SqlAlchemyDocumentGrantRepository`, `SqlAlchemySequenceRepository`).
3. In `unit_of_work.py`:
   - Clean up unit of work bindings to the 8 core repositories.

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_user_management.py tests/unit/test_role_management.py -v`
Expected: PASS.

- [ ] **Step 5: Commit changes**
```bash
git add app/domain/entities/organization_models.py app/infrastructure/persistence/sqlalchemy/repositories.py app/infrastructure/persistence/sqlalchemy/unit_of_work.py app/domain/ports/unit_of_work.py tests/unit/test_user_management.py
git commit -m "feat(repo): map role_id, job_title, and password_hash to consolidated repositories"
```

---

### Task 5: Consolidate Project Access & Document Security into `user_projects`

**Files:**
- Modify: `app/domain/services/authorization_engine.py`
- Modify: `app/use_cases/organization/project_access.py`
- Modify: `tests/unit/test_authorization_engine.py`

**Interfaces:**
- Consumes: `uow.memberships` (`user_projects`) and `uow.documents`.
- Produces: Clean authorization checks without querying dropped grant tables.

- [ ] **Step 1: Write test for unified project membership and document authorization**
In `tests/unit/test_authorization_engine.py`, add tests asserting:
- Project access is granted when a record exists in `user_projects` with a valid `role_id`.
- Document access for a project document requires membership in `user_projects` for that project.
- "Add Group to Project" expands role members into `user_projects` rows.

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_authorization_engine.py -k "test_unified" -v`
Expected: FAIL.

- [ ] **Step 3: Update `authorization_engine.py` and `project_access.py`**
1. In `app/domain/services/authorization_engine.py`:
   - Replace `_has_project_grant` and `_has_document_grant` with checks against `uow.memberships.get_membership(project_id, user.uid)`.
   - Remove calls to `uow.project_grants`, `uow.document_grants`, and `uow.department_members`.
   - Verify department check uses `user.department_id`.
2. In `app/use_cases/organization/project_access.py`:
   - When assigning a role/group to a project, query all active users with that role:
     `users = [u for u in uow.users.list() if u.role_id == role_id or u.role == role_name]`
     and create `UserProject` records for each user with `project_id` and `role_id`.

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_authorization_engine.py -v`
Expected: PASS.

- [ ] **Step 5: Commit changes**
```bash
git add app/domain/services/authorization_engine.py app/use_cases/organization/project_access.py tests/unit/test_authorization_engine.py
git commit -m "feat(authz): unify project and document access under user_projects single security boundary"
```

---

### Task 6: Full Verification Gate & Regression Test Suite

**Files:**
- Run all test suites across the repository.

- [ ] **Step 1: Run core unit test suites**
Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_database_foundation.py -v
.venv\Scripts\python.exe -m pytest tests/unit/test_business_id_generator.py -v
.venv\Scripts\python.exe -m pytest tests/unit/test_role_management.py -v
.venv\Scripts\python.exe -m pytest tests/unit/test_user_management.py -v
.venv\Scripts\python.exe -m pytest tests/unit/test_authorization_engine.py -v
```
Expected: All 100+ tests PASS.

- [ ] **Step 2: Run chat and contract test suites**
Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_prompt_config.py tests/unit/test_provenance_service.py tests/contract/test_chat_api_contract.py -v
```
Expected: All tests PASS.

- [ ] **Step 3: Verify clean git status on `database-migration` branch**
Run: `git status`
Expected: Working tree clean, ready for review.
