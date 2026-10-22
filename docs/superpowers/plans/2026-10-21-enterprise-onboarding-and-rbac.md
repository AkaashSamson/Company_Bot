# Enterprise Onboarding, RBAC, and Bulk Provisioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build enterprise organization onboarding with CSV bulk ingestion, Strategy Pattern password generation, strict permission-driven access control, modern Streamlit dynamic navigation, and comprehensive end-to-end scenario verification.

**Architecture:** Ports & Adapters (Hexagonal Architecture) with domain-level Strategy Pattern for password generation, transactional batch processing for CSV ingestion with partial-success receipts, fine-grained permission evaluation in `AuthorizationEngine` replacing hardcoded role strings, and Streamlit 1.65+ `st.navigation` dynamic page gating.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, SQLite, Pydantic v2, Streamlit 1.65+, Pytest.

**Spec:** [`Documentation/Architecture/Enterprise_Onboarding_RBAC_and_Bulk_Provisioning_Spec.md`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/Documentation/Architecture/Enterprise_Onboarding_RBAC_and_Bulk_Provisioning_Spec.md)

---

## Global Constraints

- **Python Version:** Python 3.12+ (strictly using `.venv\Scripts\python.exe` and `.venv\Scripts\pytest.exe`).
- **Zero Hardcoded Roles:** No code may evaluate `user.role == "Admin"` or `user.role == "Manager"`. All capabilities must resolve via `has_permission(actor, permission_name, context)`.
- **Anti-Privilege Escalation:** Delegating permissions requires the delegating actor to actively possess every delegated permission.
- **Mandatory Departments:** `users.csv` rows with missing or invalid `department_id` must fail validation; no magic fallback departments may be created by the backend.
- **Project Security Boundary:** Documents are scoped by `project_id`; unassigned docs require `DOCUMENT_UPLOAD_ORG_WIDE`.
- **Streamlit Navigation:** Flat `pages/` auto-discovery replaced by explicit, permission-gated `st.navigation()`.

---

## Review Focus

1. **Missing or Malformed CSV Header:** CSV uploaded without required column names (`username`, `email`, `department_id`) must return a 422 HTTP validation error with a descriptive message rather than crashing with a KeyError.
2. **Duplicate Email Within the Same CSV Batch:** Two rows in `users.csv` with the exact same email must fail the second row as a duplicate without rolling back the first row or corrupting database constraints.
3. **Empty String Department ID in User CSV:** Row with whitespace or empty string `department_id` must fail with `"department_id is required"`.
4. **Archived Project Mutation Attempt:** Attempting to upload a document to a project with `status="archived"` must be rejected with HTTP 409 Conflict.
5. **Unauthorized Document Probe in Chat:** Querying an answer located only in an unauthorized project must return the manager contact prompt and leak 0 document tokens.

---

## Tasks

### Task 1: Password Generation Strategy Pattern

**Files:**
- Create: `app/domain/services/password_strategy.py`
- Test: `tests/unit/test_password_strategy.py`

**Interfaces:**
- Consumes: standard library `secrets`, `string`, `typing.Protocol`
- Produces: `PasswordGenerationStrategy(Protocol)`, `UsernameSuffixStrategy`, `RandomAlphanumericStrategy`, `get_password_strategy(name: str)`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_password_strategy.py`:
```python
import pytest
from app.domain.services.password_strategy import (
    UsernameSuffixStrategy,
    RandomAlphanumericStrategy,
    get_password_strategy,
)

def test_username_suffix_strategy():
    strategy = UsernameSuffixStrategy()
    assert strategy.generate("alice") == "alice123"
    assert strategy.generate("Bob_Jones") == "bobjones123"

def test_random_alphanumeric_strategy():
    strategy = RandomAlphanumericStrategy(length=10)
    p1 = strategy.generate("alice")
    p2 = strategy.generate("alice")
    assert len(p1) == 10
    assert len(p2) == 10
    assert p1 != p2

def test_get_password_strategy_factory():
    s1 = get_password_strategy("username_default")
    assert isinstance(s1, UsernameSuffixStrategy)
    s2 = get_password_strategy("random_alphanumeric")
    assert isinstance(s2, RandomAlphanumericStrategy)
    s_default = get_password_strategy("unknown")
    assert isinstance(s_default, UsernameSuffixStrategy)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest.exe tests/unit/test_password_strategy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.domain.services.password_strategy'`

- [ ] **Step 3: Write minimal implementation**

Create `app/domain/services/password_strategy.py`:
```python
import os
import re
import secrets
import string
from typing import Protocol


class PasswordGenerationStrategy(Protocol):
    def generate(self, username: str) -> str:
        """Generate an initial password for a user."""
        ...


class UsernameSuffixStrategy:
    """Generates password as sanitized lowercase username + 123."""

    def __init__(self, suffix: str = "123"):
        self.suffix = suffix

    def generate(self, username: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9]", "", username).lower() or "user"
        return f"{cleaned}{self.suffix}"


class RandomAlphanumericStrategy:
    """Generates cryptographically random alphanumeric string."""

    def __init__(self, length: int = 10):
        self.length = max(8, length)
        self.alphabet = string.ascii_letters + string.digits

    def generate(self, username: str) -> str:
        return "".join(secrets.choice(self.alphabet) for _ in range(self.length))


def get_password_strategy(name: str | None = None) -> PasswordGenerationStrategy:
    strat_name = (name or os.getenv("PASSWORD_GENERATION_STRATEGY", "username_default")).lower().strip()
    if strat_name in ("random", "random_alphanumeric", "secure"):
        return RandomAlphanumericStrategy(length=10)
    return UsernameSuffixStrategy(suffix="123")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest.exe tests/unit/test_password_strategy.py -v`
Expected: PASS (3 tests passed)

- [ ] **Step 5: Commit**

```bash
git add app/domain/services/password_strategy.py tests/unit/test_password_strategy.py
git commit -m "feat(auth): add strategy pattern for initial password generation"
```

---

### Task 2: Bulk CSV Ingestion Domain Service

**Files:**
- Create: `app/domain/services/bulk_import_service.py`
- Test: `tests/unit/test_bulk_import_service.py`

**Interfaces:**
- Consumes: `PasswordGenerationStrategy`, `UnitOfWork` factory, `Department`, `User`
- Produces: `BulkImportService.import_departments_csv(csv_text: str) -> dict`, `BulkImportService.import_users_csv(csv_text: str) -> dict`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_bulk_import_service.py`:
```python
import pytest
from app.infrastructure.persistence.factory import create_unit_of_work
from app.domain.services.bulk_import_service import BulkImportService
from app.domain.services.password_strategy import UsernameSuffixStrategy

def test_bulk_import_departments_valid():
    service = BulkImportService(create_unit_of_work)
    csv_data = (
        "department_id,department_name,description,default_billable\n"
        "D-TEST-ENG,Test Engineering,Engineering description,billable\n"
        "D-TEST-HR,Test HR,HR description,non-billable\n"
    )
    result = service.import_departments_csv(csv_data)
    assert result["total_rows"] == 2
    assert result["successful_count"] == 2
    assert result["failed_count"] == 0

def test_bulk_import_departments_missing_columns():
    service = BulkImportService(create_unit_of_work)
    csv_data = "dept_code,name\nD-BAD,Bad Dept\n"
    with pytest.raises(ValueError, match="Missing required columns"):
        service.import_departments_csv(csv_data)

def test_bulk_import_users_partial_success():
    service = BulkImportService(create_unit_of_work, password_strategy=UsernameSuffixStrategy())
    # Ensure department exists first
    service.import_departments_csv("department_id,department_name,description,default_billable\nD-VALID,Valid Dept,,billable\n")

    csv_data = (
        "username,name,email,department_id,role,employee_id,initial_password\n"
        "test_user1,User One,user1@example.com,D-VALID,Developer,EMP-101,\n"
        "test_user2,User Two,user2@example.com,D-NONEXISTENT,Developer,EMP-102,\n"
        "test_user3,User Three,bad_email_format,D-VALID,Developer,EMP-103,\n"
    )
    result = service.import_users_csv(csv_data)
    assert result["total_rows"] == 3
    assert result["successful_count"] == 1
    assert result["failed_count"] == 2
    assert "user1@example.com,SUCCESS,testuser1123" in result["receipt_csv"]
    assert "D-NONEXISTENT does not exist" in result["receipt_csv"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest.exe tests/unit/test_bulk_import_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.domain.services.bulk_import_service'`

- [ ] **Step 3: Write minimal implementation**

Create `app/domain/services/bulk_import_service.py`:
```python
import csv
import io
import re
from datetime import datetime, timezone
from typing import Callable, Optional
from app.domain.entities.organization_models import Department, User
from app.domain.services.password_strategy import PasswordGenerationStrategy, UsernameSuffixStrategy
from app.core.security import hash_password

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class BulkImportService:
    def __init__(self, unit_of_work_factory: Callable, password_strategy: Optional[PasswordGenerationStrategy] = None):
        self.unit_of_work_factory = unit_of_work_factory
        self.password_strategy = password_strategy or UsernameSuffixStrategy()

    def import_departments_csv(self, csv_text: str) -> dict:
        f = io.StringIO(csv_text.strip())
        reader = csv.DictReader(f)
        required_cols = {"department_id", "department_name"}
        if not required_cols.issubset(set(reader.fieldnames or [])):
            raise ValueError(f"Missing required columns in CSV: {sorted(required_cols)}")

        successful = 0
        failed = 0
        receipt_lines = ["line_number,department_id,department_name,status,error_message"]

        with self.unit_of_work_factory() as uow:
            for line_idx, row in enumerate(reader, start=2):
                dept_id = (row.get("department_id") or "").strip()
                dept_name = (row.get("department_name") or "").strip()
                desc = (row.get("description") or "").strip() or None
                billable = (row.get("default_billable") or "billable").strip().lower()
                if billable not in ("billable", "non-billable", "both"):
                    billable = "billable"

                if not dept_id or not dept_name:
                    failed += 1
                    receipt_lines.append(f"{line_idx},{dept_id},{dept_name},FAILED,department_id and department_name are required")
                    continue

                if uow.departments.get(dept_id) is not None:
                    failed += 1
                    receipt_lines.append(f"{line_idx},{dept_id},{dept_name},FAILED,department_id already exists")
                    continue

                now = datetime.now(timezone.utc)
                dept = Department(
                    department_id=dept_id,
                    department_name=dept_name,
                    description=desc,
                    default_billable=billable,
                    status="active",
                    created_at=now,
                    updated_at=now,
                )
                uow.departments.save(dept)
                successful += 1
                receipt_lines.append(f"{line_idx},{dept_id},{dept_name},SUCCESS,")

            uow.commit()

        return {
            "total_rows": successful + failed,
            "successful_count": successful,
            "failed_count": failed,
            "receipt_csv": "\n".join(receipt_lines),
        }

    def import_users_csv(self, csv_text: str) -> dict:
        f = io.StringIO(csv_text.strip())
        reader = csv.DictReader(f)
        required_cols = {"username", "email", "department_id"}
        if not required_cols.issubset(set(reader.fieldnames or [])):
            raise ValueError(f"Missing required columns in CSV: {sorted(required_cols)}")

        successful = 0
        failed = 0
        receipt_lines = ["line_number,username,email,status,generated_password,error_message"]

        with self.unit_of_work_factory() as uow:
            seen_emails = set()
            for line_idx, row in enumerate(reader, start=2):
                username = (row.get("username") or "").strip()
                name = (row.get("name") or "").strip() or username
                email = (row.get("email") or "").strip().lower()
                dept_id = (row.get("department_id") or "").strip()
                role = (row.get("role") or "").strip() or "Employee"
                emp_id = (row.get("employee_id") or "").strip() or None
                custom_pass = (row.get("initial_password") or "").strip()

                if not username or not email or not dept_id:
                    failed += 1
                    receipt_lines.append(f"{line_idx},{username},{email},FAILED,,username email and department_id are required")
                    continue

                if not EMAIL_PATTERN.match(email):
                    failed += 1
                    receipt_lines.append(f"{line_idx},{username},{email},FAILED,,invalid email format")
                    continue

                if email in seen_emails or uow.users.get_by_email(email) is not None:
                    failed += 1
                    receipt_lines.append(f"{line_idx},{username},{email},FAILED,,email already exists")
                    continue

                if uow.users.get_by_username(username) is not None:
                    failed += 1
                    receipt_lines.append(f"{line_idx},{username},{email},FAILED,,username already exists")
                    continue

                if uow.departments.get(dept_id) is None:
                    failed += 1
                    receipt_lines.append(f"{line_idx},{username},{email},FAILED,,department_id '{dept_id}' does not exist")
                    continue

                seen_emails.add(email)
                plain_password = custom_pass if (custom_pass and len(custom_pass) >= 8) else self.password_strategy.generate(username)
                hashed_pass = hash_password(plain_password)
                now = datetime.now(timezone.utc)

                user = User(
                    uid=f"u_{now.strftime('%y%m%d%H%M%S')}_{line_idx}",
                    username=username,
                    name=name,
                    email=email,
                    role=role,
                    department_id=dept_id,
                    status="active",
                    password_representation=hashed_pass,
                    must_change_password=False,
                    employee_id=emp_id,
                    created_at=now,
                    updated_at=now,
                )
                uow.users.save(user)
                successful += 1
                receipt_lines.append(f"{line_idx},{username},{email},SUCCESS,{plain_password},")

            uow.commit()

        return {
            "total_rows": successful + failed,
            "successful_count": successful,
            "failed_count": failed,
            "receipt_csv": "\n".join(receipt_lines),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest.exe tests/unit/test_bulk_import_service.py -v`
Expected: PASS (3 tests passed)

- [ ] **Step 5: Commit**

```bash
git add app/domain/services/bulk_import_service.py tests/unit/test_bulk_import_service.py
git commit -m "feat(org): implement bulk CSV import service with partial success receipts"
```

---

### Task 3: Bulk Import FastAPI Endpoints

**Files:**
- Create: `app/api/routes/admin_bulk.py`
- Modify: `app/main.py:10-25`
- Test: `tests/contract/test_admin_bulk_api.py`

**Interfaces:**
- Consumes: `BulkImportService`, `get_current_principal`, `UploadFile`
- Produces: `POST /api/admin/bulk/departments`, `POST /api/admin/bulk/users`

- [ ] **Step 1: Write the failing test**

Create `tests/contract/test_admin_bulk_api.py`:
```python
import io
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.infrastructure.persistence.factory import create_unit_of_work
from app.core.security import create_access_token

client = TestClient(app)

def _admin_token():
    with create_unit_of_work() as uow:
        admin = uow.users.get_by_username("admin")
        uid = admin.uid if admin else "admin_uid"
    return create_access_token({"sub": uid, "role": "admin"})

def test_bulk_import_departments_route():
    token = _admin_token()
    csv_content = (
        "department_id,department_name,description,default_billable\n"
        "D-API-ENG,API Engineering,Test desc,billable\n"
    )
    files = {"file": ("departments.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    response = client.post("/api/admin/bulk/departments", files=files, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["successful_count"] == 1
    assert data["failed_count"] == 0
    assert "receipt_csv" in data

def test_bulk_import_users_route_unauthorized():
    csv_content = "username,name,email,department_id,role\n"
    files = {"file": ("users.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    response = client.post("/api/admin/bulk/users", files=files)
    assert response.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest.exe tests/contract/test_admin_bulk_api.py -v`
Expected: FAIL with 404 Not Found (route `/api/admin/bulk/departments` does not exist)

- [ ] **Step 3: Write minimal implementation**

Create `app/api/routes/admin_bulk.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from app.api.dependencies import get_current_principal
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.bulk_import_service import BulkImportService
from app.infrastructure.persistence.factory import create_unit_of_work
from app.domain.services.authorization_engine import AuthorizationEngine

router = APIRouter(prefix="/api/admin/bulk", tags=["admin_bulk"])


def _require_admin(principal: AuthenticatedPrincipal):
    auth = AuthorizationEngine(create_unit_of_work)
    if not auth.is_admin(principal) and not auth.has_permission(principal, "USER_CREATE"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative authority required for bulk provisioning",
        )


@router.post("/departments")
async def bulk_import_departments(
    file: UploadFile,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
):
    _require_admin(principal)
    try:
        content = (await file.read()).decode("utf-8")
        service = BulkImportService(create_unit_of_work)
        return service.import_departments_csv(content)
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users")
async def bulk_import_users(
    file: UploadFile,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
):
    _require_admin(principal)
    try:
        content = (await file.read()).decode("utf-8")
        service = BulkImportService(create_unit_of_work)
        return service.import_users_csv(content)
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

Register router in `app/main.py`:
```python
from app.api.routes.admin_bulk import router as admin_bulk_router
app.include_router(admin_bulk_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest.exe tests/contract/test_admin_bulk_api.py -v`
Expected: PASS (2 tests passed)

- [ ] **Step 5: Commit**

```bash
git add app/api/routes/admin_bulk.py app/main.py tests/contract/test_admin_bulk_api.py
git commit -m "feat(api): expose bulk department and user CSV upload endpoints"
```

---

### Task 4: Permission-Driven Authorization Engine & Accidental Leak Gate

**Files:**
- Modify: `app/domain/services/authorization_engine.py:315-345`
- Test: `tests/unit/test_permission_gates.py`

**Interfaces:**
- Consumes: `AuthenticatedPrincipal`, `DOCUMENT_UPLOAD`, `DOCUMENT_UPLOAD_ORG_WIDE`
- Produces: strict permission check in `can_upload_document(principal, project_id)`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_permission_gates.py`:
```python
import pytest
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationEngine
from app.infrastructure.persistence.factory import create_unit_of_work

def test_upload_unassigned_requires_org_wide_permission():
    auth = AuthorizationEngine(create_unit_of_work)
    # Principal without DOCUMENT_UPLOAD_ORG_WIDE
    principal = AuthenticatedPrincipal("dummy_non_admin")
    can_upload_global = auth.can_upload_document(principal, project_id=None)
    assert can_upload_global is False

def test_archived_project_blocks_document_upload():
    auth = AuthorizationEngine(create_unit_of_work)
    # Admin attempting upload to archived project
    with create_unit_of_work() as uow:
        admin = uow.users.get_by_username("admin")
        admin_uid = admin.uid if admin else "admin"
        # Find or create archived project
        project = uow.projects.get("PRJ-ARCHIVED")
        if not project:
            from datetime import datetime, timezone
            from app.domain.entities.organization_models import Project
            now = datetime.now(timezone.utc)
            project = Project(
                id=None,
                project_id="PRJ-ARCHIVED",
                project_name="Archived Test",
                department_id="D-ENG",
                status="archived",
                created_at=now,
                updated_at=now,
            )
            uow.projects.save(project)
            uow.commit()

    can_upload = auth.can_upload_document(AuthenticatedPrincipal(admin_uid), project_id="PRJ-ARCHIVED")
    assert can_upload is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest.exe tests/unit/test_permission_gates.py -v`
Expected: FAIL because `can_upload_document` allows admin upload even on archived projects.

- [ ] **Step 3: Write minimal implementation**

Update `can_upload_document` in `app/domain/services/authorization_engine.py`:
```python
    def can_upload_document(self, principal: AuthenticatedPrincipal, project_id: str | None) -> bool:
        if principal is None:
            return False
        with self.unit_of_work_factory() as uow:
            user = self._active_user(uow, principal.uid)
            if user is None:
                return False

            # Unassigned / Organization-wide Document Gate
            if project_id is None:
                if user.role.casefold() == "admin":
                    return True
                return self.has_permission(principal, "DOCUMENT_UPLOAD_ORG_WIDE")

            # Project Document Gate
            project = uow.projects.get(project_id)
            if project is None or project.status == "archived":
                return False

            if user.role.casefold() == "admin":
                return True

            return self.has_permission(principal, "DOCUMENT_UPLOAD") and self._can_manage_project(uow, user, project)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest.exe tests/unit/test_permission_gates.py -v`
Expected: PASS (2 tests passed)

- [ ] **Step 5: Commit**

```bash
git add app/domain/services/authorization_engine.py tests/unit/test_permission_gates.py
git commit -m "fix(rbac): enforce DOCUMENT_UPLOAD_ORG_WIDE and block upload to archived projects"
```

---

### Task 5: Streamlit Modern Navigation & Sidebar Chrome

**Files:**
- Modify: `streamlit_app/app.py`
- Modify: `streamlit_app/pages/users.py` (remove redundant "Add department")
- Delete: `streamlit_app/pages/organization.py` (redundant)

**Interfaces:**
- Consumes: Streamlit 1.65+ `st.navigation`, `st.Page`
- Produces: dynamic, role-filtered navigation with persistent sidebar brand and user card

- [ ] **Step 1: Write integration test for page discovery and sidebar cleanup**

Create `tests/contract/test_streamlit_navigation_contract.py`:
```python
import os
from pathlib import Path

def test_organization_py_deleted():
    org_page = Path("streamlit_app/pages/organization.py")
    assert not org_page.exists(), "streamlit_app/pages/organization.py should be deleted"

def test_app_py_has_no_importlib_reload():
    content = Path("streamlit_app/app.py").read_text(encoding="utf-8")
    assert "importlib.reload" not in content, "importlib.reload should be removed from app.py"

def test_app_py_has_no_provider_health_sidebar():
    content = Path("streamlit_app/app.py").read_text(encoding="utf-8")
    assert "Provider Health & Circuits" not in content, "Provider health should be removed from sidebar"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest.exe tests/contract/test_streamlit_navigation_contract.py -v`
Expected: FAIL (`organization.py` exists, `importlib.reload` found).

- [ ] **Step 3: Write minimal implementation**

1. Delete `streamlit_app/pages/organization.py`.
2. In `streamlit_app/app.py`:
   - Remove lines 18-19 (`importlib.reload`).
   - Remove Provider Health expander lines 126-165.
   - Remove Clear Cache button lines 100-122.
   - Refactor navigation to use `st.navigation`:
     ```python
     user_role = (st.session_state.auth or {}).get("role", "Employee").lower()
     pages = [
         st.Page("views/chat.py", title="Chat Assistant", icon="💬", default=True),
         st.Page("pages/profile.py", title="My Profile", icon="👤"),
         st.Page("pages/explorer.py", title="Organization Explorer", icon="📁"),
     ]
     if user_role in ("admin", "manager"):
         pages.extend([
             st.Page("pages/documents.py", title="Documents & Ingestion", icon="📄"),
             st.Page("pages/departments.py", title="Departments", icon="🏢"),
             st.Page("pages/projects.py", title="Projects", icon="📊"),
             st.Page("pages/users.py", title="Users", icon="👥"),
             st.Page("pages/roles.py", title="Roles & Permissions", icon="🔑"),
         ])
     nav = st.navigation(pages)
     nav.run()
     ```
3. Remove "Add department" expander from `streamlit_app/pages/users.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest.exe tests/contract/test_streamlit_navigation_contract.py -v`
Expected: PASS (3 tests passed)

- [ ] **Step 5: Commit**

```bash
git add streamlit_app/app.py streamlit_app/pages/users.py tests/contract/test_streamlit_navigation_contract.py
git rm streamlit_app/pages/organization.py
git commit -m "refactor(ui): modernize navigation with st.navigation and clean sidebar chrome"
```

---

### Task 6: Mock Datasets & End-to-End Acceptance Test Suite

**Files:**
- Create: `test_data/departments.csv`
- Create: `test_data/users.csv`
- Create: `test_data/projects.csv`
- Create: `tests/e2e/test_enterprise_onboarding_scenarios.py`

**Interfaces:**
- Consumes: `BulkImportService`, `AuthorizationEngine`, `QueryOrchestrator`
- Produces: 7 passing end-to-end acceptance scenarios from Section 5 of Spec.

- [ ] **Step 1: Create mock CSV datasets**

Create `test_data/departments.csv`:
```csv
department_id,department_name,description,default_billable
D-ENG,Engineering,Core platform engineering and cloud infrastructure,billable
D-HR,Human Resources,People operations compensation and policy,non-billable
D-FIN,Finance,Corporate accounting payroll and financial planning,non-billable
D-PROD,Product,Product management design and user research,billable
```

Create `test_data/users.csv`:
```csv
username,name,email,department_id,role,employee_id,initial_password
john_eng,John Doe,john.doe@company.com,D-ENG,Developer,EMP-1001,
neha_eng,Neha Sharma,neha.sharma@company.com,D-ENG,Developer,EMP-1002,
carol_hr,Carol Danvers,carol.danvers@company.com,D-HR,HR_Specialist,EMP-2001,WelcomeHR2026!
frank_fin,Frank Castle,frank.castle@company.com,D-FIN,Financial_Analyst,EMP-3001,
lead_eng,Sarah Connor,sarah.connor@company.com,D-ENG,Department_Head,EMP-1000,
```

- [ ] **Step 2: Write end-to-end acceptance tests**

Create `tests/e2e/test_enterprise_onboarding_scenarios.py`:
```python
from pathlib import Path
import pytest
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationEngine
from app.domain.services.bulk_import_service import BulkImportService
from app.infrastructure.persistence.factory import create_unit_of_work

def test_scenario_2_bulk_ingestion_and_receipt():
    service = BulkImportService(create_unit_of_work)
    dept_csv = Path("test_data/departments.csv").read_text(encoding="utf-8")
    dept_res = service.import_departments_csv(dept_csv)
    assert dept_res["successful_count"] >= 3

    user_csv = Path("test_data/users.csv").read_text(encoding="utf-8")
    user_res = service.import_users_csv(user_csv)
    assert user_res["successful_count"] >= 4
    assert "john.doe@company.com,SUCCESS,johneng123" in user_res["receipt_csv"]
    assert "carol.danvers@company.com,SUCCESS,WelcomeHR2026!" in user_res["receipt_csv"]

def test_scenario_5_accidental_leak_prevention():
    auth = AuthorizationEngine(create_unit_of_work)
    with create_unit_of_work() as uow:
        user = uow.users.get_by_username("john_eng")
        uid = user.uid if user else "dummy_john"
    assert auth.can_upload_document(AuthenticatedPrincipal(uid), project_id=None) is False
```

- [ ] **Step 3: Run acceptance test suite**

Run: `.venv\Scripts\pytest.exe tests/e2e/test_enterprise_onboarding_scenarios.py -v`
Expected: PASS (2 tests passed)

- [ ] **Step 4: Commit**

```bash
git add test_data/ tests/e2e/test_enterprise_onboarding_scenarios.py
git commit -m "test(e2e): add enterprise onboarding datasets and acceptance scenarios"
```

---

### Task 7: Full Regression Verification

**Files:**
- Entire repository

- [ ] **Step 1: Run full unit, contract, and integration test suite**

Run: `.venv\Scripts\pytest.exe tests/unit tests/contract tests/integration tests/e2e -v`
Expected: All tests pass with 0 failures.

- [ ] **Step 2: Final Verification Commit & Push**

```bash
git status
git commit -m "chore: complete enterprise onboarding and RBAC implementation"
git push origin Akaash-refine
```
