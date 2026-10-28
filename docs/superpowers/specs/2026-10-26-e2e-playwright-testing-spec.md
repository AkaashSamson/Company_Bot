# End-to-End Playwright Testing Specification: Nexora Storyline & Traceability Matrix

**Date:** 2026-10-26  
**Status:** DRAFT (Phase 1)  
**Target:** Playwright E2E UI Test Suite with Complete Storyline, RBAC Isolation, and Lifecycle Verification

---

## 1. Objective & Scope

Establish an automated, end-to-end (E2E) browser test suite using **Python Playwright** (`pytest-playwright`) that tests every feature and permission tier of KnowLayer through the Streamlit web interface.

The test suite will:
1. **Execute entirely through the browser UI**: Form fills, button clicks, file uploads, dropdown selections, tabs, and alerts.
2. **Follow a realistic company story** ("Nexora Technologies") across multiple departments, projects, and user personas.
3. **Run in 100% test isolation**: Spawns isolated test servers on dedicated ports (`:8001` backend, `:8502` frontend) with dedicated SQLite (`instance/test_e2e.db`) and ChromaDB (`.chroma_e2e`), guaranteeing zero pollution of development data.
4. **Support Live Visuals and Video**: Runnable with `--headed` for live browser playback and records `.webm` videos/traces for debugging.

---

## 2. Test Architecture & Environment Isolation

```
[Local Dev Environment]                 [Automated E2E Sandbox (conftest.py)]
FastAPI Backend: :8000                  FastAPI Backend: :8001
Streamlit UI:    :8501                  Streamlit UI:    :8502
Database:        instance/knowlayer.db  Database:        instance/test_e2e.db
ChromaDB:        .chroma/               ChromaDB:        .chroma_e2e/
Uploads:         input/                 Uploads:         tests/fixtures/synthetic_data/uploads/
```

### Environment Overrides for Test Session:
- `DATABASE_URL = "sqlite:///./instance/test_e2e.db"`
- `COLLECTION_NAME = "Nexora_E2E_Docs"`
- `CHROMA_PERSIST_DIRECTORY = ".chroma_e2e"`
- `DOCUMENTS_DIR = "tests/fixtures/synthetic_data/uploads"`
- `STREAMLIT_API_BASE_URL = "http://127.0.0.1:8001"`

---

## 3. Nexora Company Personas

| Persona | Username | Initial Password | Department | Roles / Capabilities |
|---|---|---|---|---|
| **System Admin** | `admin` | `admin` (seeded) | Global | Pre-existing superuser for initial bootstrap |
| **Sarah Chen** | `sarah.admin` | `Password123!` | Operations | Delegated Admin (`ADMIN` role, global access) |
| **Roy Miller** | `roy.hr` | `Password123!` | Human Resources | HR Lead (`USER_CREATE`, `DOCUMENT_UPLOAD`, `DOCUMENT_VIEW`) |
| **Marcus Vance**| `marcus.eng` | `Password123!` | Engineering | Engineering Lead & Project Manager (`PROJECT_CREATE`, `USER_CREATE`, `DOCUMENT_UPLOAD`, `DOCUMENT_MANAGE`) |
| **Elena Rostova**| `elena.dev` | `Password123!` | Engineering | Senior Developer (Project Member, later Apollo Manager) |
| **David Kim** | `david.hr` | `Password123!` | Human Resources | HR Specialist (Standard employee, non-admin) |

---

## 4. Synthetic Test Documents

Stored in `tests/fixtures/synthetic_data/`:

### 1. `timesheet_policy.md` (General Knowledge Base)
- **Scope**: General / Unassigned (All company employees).
- **Core Content**: Mandatory Friday 5 PM timesheet submission, client billing codes, overtime approval flow.
- **Purpose**: Distinctive company-wide policy with zero collision against leave/POSH files.

### 2. `titan_architecture.md` (Project Titan)
- **Scope**: Private to *Project Titan*.
- **Core Content**: Distributed microservices blueprint, gRPC protocol, Redis cache topology, Titan auth tokens.
- **Purpose**: Proprietary engineering specification used to verify strict RAG authorization boundaries and zero-leak guardrails.

### 3. `apollo_blueprint.md` (Project Apollo)
- **Scope**: Private to *Project Apollo*.
- **Core Content**: Apollo telemetry pipeline, Kafka partition schema, retention SLAs.
- **Purpose**: Document lifecycle testing (202 Accepted $\rightarrow$ Background Active $\rightarrow$ Chunk Inspection $\rightarrow$ Soft-Archive $\rightarrow$ Permanent Purge).

---

## 5. Story Acts & Detailed Test Specifications

### Act 1: Initial Bootstrap (`tests/e2e/test_01_bootstrap.py`)
1. **`POS-BOOT-01: System Admin Login`**:
   - `admin` navigates to `http://localhost:8502`.
   - Centered login card appears with Username and Password fields.
   - Enters `admin` / `admin` $\rightarrow$ redirects to Chat assistant.
2. **`POS-BOOT-02: Create Delegated Admin (Sarah)`**:
   - Admin navigates to `/users`.
   - Fills "Add User": Username `sarah.admin`, Name `Sarah Chen`, Email `sarah@nexora.com`, Role `Admin`, Initial Password `Password123!`.
   - Submits form $\rightarrow$ Success alert appears, Sarah listed in roster.
3. **`NEG-BOOT-01: Admin Role Immutability`**:
   - Admin navigates to `/roles`.
   - Selects role "Admin" under permission assignment $\rightarrow$ UI displays info message: `"The system Admin role cannot be modified"`, form disabled.
4. **`POS-BOOT-03: Admin Logout`**:
   - Clicks "Log out" button in sidebar $\rightarrow$ redirected back to login screen with empty session.

---

### Act 2: Organization Setup (`tests/e2e/test_02_org_setup.py`)
1. **`POS-ORG-01: Sarah First Login & Setup`**:
   - Sarah logs in with `sarah.admin` / `Password123!`.
   - Verified that sidebar shows "👤 Sarah Chen · Admin".
2. **`POS-ORG-02: Create Departments`**:
   - Sarah navigates to `/departments`.
   - Creates Department: `Engineering` (billable: `billable`).
   - Creates Department: `Human Resources` (billable: `non-billable`).
   - Both departments rendered in All Departments table.
3. **`POS-ORG-03: Onboard Department Leads`**:
   - Sarah navigates to `/users`.
   - Creates `roy.hr`: Name `Roy Miller`, Email `roy@nexora.com`, Dept `Human Resources`, Role `Manager`.
   - Creates `marcus.eng`: Name `Marcus Vance`, Email `marcus@nexora.com`, Dept `Engineering`, Role `Manager`.
4. **`NEG-ORG-01: Duplicate Department Name Rejected`**:
   - Sarah attempts to create another department named `Engineering` $\rightarrow$ error toast displays conflict message.
5. **`POS-ORG-04: Sarah Logout`**:
   - Sarah logs out cleanly.

---

### Act 3: HR Timesheet Policy & Onboarding (`tests/e2e/test_03_hr_timesheets.py`)
1. **`POS-HR-01: Roy Login`**:
   - Roy logs in with `roy.hr` / `Password123!`.
   - Verified that sidebar reflects HR department and Manager role.
2. **`POS-HR-02: Upload Timesheet Policy to General KB`**:
   - Roy navigates to `/documents`.
   - Opens "Upload & Ingest New Document".
   - Uses Playwright `set_input_files` to upload `timesheet_policy.md`.
   - Selects Project: `Unassigned (General Knowledge Base)`.
   - Clicks "Upload and Ingest" $\rightarrow$ Success message indicates HTTP 202 initiation.
   - Initial status badge displays `Processing`.
   - Fragment auto-refreshes within interval $\rightarrow$ badge transitions to `Active`.
3. **`NEG-HR-01: Reject Unsupported File Type`**:
   - Roy attempts to upload `malicious.exe` $\rightarrow$ UI displays error banner: `"Unsupported document type: .exe"`. No database record created.
4. **`NEG-HR-02: Reject Duplicate Upload in Same Scope`**:
   - Roy attempts to re-upload identical `timesheet_policy.md` to General KB $\rightarrow$ rejected with 409 Conflict: `"Exact file already exists in this project"`.
5. **`POS-HR-03: Roy Creates David`**:
   - Roy navigates to `/users`.
   - Adds employee `david.hr`: Name `David Kim`, Email `david@nexora.com`, Dept `Human Resources`, Role `Employee`.
6. **`POS-HR-04: Roy Logout`**:
   - Roy logs out.

---

### Act 4: Engineering Projects & Manager Handoff (`tests/e2e/test_04_projects.py`)
1. **`POS-ENG-01: Marcus Login & Onboard Elena`**:
   - Marcus logs in with `marcus.eng` / `Password123!`.
   - Navigates to `/users` $\rightarrow$ creates `elena.dev`: Name `Elena Rostova`, Email `elena@nexora.com`, Dept `Engineering`, Role `Developer`.
2. **`POS-ENG-02: Create Project Titan & Upload Blueprint`**:
   - Marcus navigates to `/projects` $\rightarrow$ "Create New Project": Name `Project Titan`, Dept `Engineering`, Manager `Marcus Vance`.
   - Navigates to `/documents` $\rightarrow$ uploads `titan_architecture.md` scoped to `Project Titan`.
   - Status switches from `Processing` to `Active`.
3. **`POS-ENG-03: Grant Roy Cross-Department Access via Project Titan Membership`**:
   - Marcus navigates to `/projects` $\rightarrow$ opens "Manage Project Membership".
   - Selects Project `Project Titan` and User `Roy Miller` (HR Manager).
   - Clicks "Assign Member" $\rightarrow$ `user_projects` membership row persisted.
4. **`POS-ENG-04: Verify Roy Access to Titan Documents`**:
   - Marcus logs out cleanly.
   - Roy Miller logs in with `roy.hr` / `Password123!`.
   - Navigates to `/documents` $\rightarrow$ verifies `titan_architecture.md` is visible under `Project Titan` (confirming cross-department project access boundary).
   - Roy logs out cleanly.
5. **`POS-ENG-05: Create Project Apollo & Add Elena`**:
   - Marcus logs back in with `marcus.eng` / `Password123!`.
   - Navigates to `/projects` $\rightarrow$ creates `Project Apollo` with himself as manager.
   - In "Manage Project Membership", adds `Elena Rostova` to `Project Apollo`.
6. **`NEG-ENG-01: Marcus Locked from Leaving Apollo as Manager`**:
   - Under "My Projects" table, `Project Apollo` has "Leave Project" button disabled with caption `"Manager (Transfer before leaving)"`.
7. **`POS-ENG-06: Transfer Apollo Manager Role to Elena & Leave`**:
   - In "Update Project", Marcus changes Apollo Manager from `Marcus Vance` to `Elena Rostova`.
   - Page refreshes $\rightarrow$ "Leave Project" button is now enabled for Marcus.
   - Marcus clicks "Leave Project" $\rightarrow$ project removed from his "My Projects" table.
8. **`POS-ENG-07: Marcus Logout`**:
   - Marcus logs out.

---

### Act 5: Apollo Document Lifecycle & Observability (`tests/e2e/test_05_lifecycle.py`)
1. **`POS-LIFE-01: Elena Login as Apollo Manager`**:
   - Elena logs in with `elena.dev` / `Password123!`.
   - Verified that `/projects` lists `Project Apollo` under "My Projects" and Elena has manager permissions for Apollo.
2. **`POS-LIFE-02: Elena Adds David to Apollo`**:
   - Elena assigns `David Kim` as member of `Project Apollo`.
3. **`POS-LIFE-03: Upload Apollo Blueprint`**:
   - Elena navigates to `/documents` $\rightarrow$ uploads `apollo_blueprint.md` to `Project Apollo`.
   - Ingestion completes $\rightarrow$ badge `Active`.
4. **`POS-LIFE-04: Chunk Inspector & Vector Search Sandbox`**:
   - Elena switches to Tab 2: "Chunk Inspector & Vector Search".
   - Selects `apollo_blueprint.md` $\rightarrow$ chunks rendered with tokens, chunk index, and metadata.
   - Runs test vector search: `"telemetry partition retention"` with threshold $0.5$ $\rightarrow$ relevant chunks returned with cosine similarity scores.
5. **`POS-LIFE-05: Soft-Archive Apollo Document`**:
   - Under Tab 1, Elena clicks "Archive" on `apollo_blueprint.md`.
   - Status badge switches to `Archived`.
   - File on disk verified moved to `archived/` subfolder.
   - Chroma chunks verified retained with metadata `status: "archived"`.
6. **`POS-LIFE-06: Permanent Purge Apollo Document`**:
   - Elena clicks "Permanent Purge" with confirmation dialog.
   - Document row removed from UI table.
   - Verified: database record deleted, storage file unlinked, ChromaDB chunks deleted.
7. **`POS-LIFE-07: Elena Logout`**:
   - Elena logs out.

---

### Act 6: Scoped Chat & RAG Authorization Verification (`tests/e2e/test_06_chat_rag.py`)
1. **`POS-CHAT-01: David Queries General Timesheet Policy`**:
   - David logs in (`david.hr` / `Password123!`).
   - Project scope set to `General Knowledge Base (All Accessible Documents)`.
   - Asks: `"What is the deadline for submitting weekly timesheets?"`.
   - Assistant answers with Friday 5 PM rule and citations citing `timesheet_policy.md`.
2. **`NEG-CHAT-01: David Blocked from Project Titan Knowledge`**:
   - Project scope dropdown does NOT show `Project Titan` (David was never added and has no grant).
   - In General KB scope, David asks: `"What is the microservices topology in Project Titan?"`.
   - Assistant returns negative response or zero Titan citations. Zero data leak.
3. **`POS-CHAT-02: David Clears Chat`**:
   - Clicks "Clear" in top actions bar $\rightarrow$ chat history wiped, session ID refreshed.
   - David logs out.
4. **`POS-CHAT-03: Roy Queries Titan via Cross-Department Grant`**:
   - Roy logs in (`roy.hr` / `Password123!`).
   - Project scope dropdown shows `Project Titan` (or readable via document grant).
   - Roy asks: `"Describe the Titan architecture microservices topology"`.
   - Assistant returns technical answer citing `titan_architecture.md`.
   - Roy logs out.
5. **`POS-CHAT-04: Elena Queries Titan as Project Member`**:
   - Elena logs in (`elena.dev` / `Password123!`).
   - Selects `Project Titan` in Project scope.
   - Asks: `"What cache topology does Project Titan use?"`.
   - Assistant returns Redis cache details citing `titan_architecture.md`.
   - Elena logs out.

---

## 6. Traceability Matrix

| Test ID | Story Act | Target Page | Persona | Primary Verification |
|---|---|---|---|---|
| `POS-BOOT-01` | Act 1 | `app.py` | `admin` | Login modal authentication |
| `POS-BOOT-02` | Act 1 | `pages/users.py` | `admin` | User creation with Admin role |
| `NEG-BOOT-01` | Act 1 | `pages/roles.py` | `admin` | Admin role immutability enforcement |
| `POS-ORG-01` | Act 2 | `app.py` | `sarah.admin` | Delegated admin authentication |
| `POS-ORG-02` | Act 2 | `pages/departments.py` | `sarah.admin` | Department creation with billable policies |
| `POS-ORG-03` | Act 2 | `pages/users.py` | `sarah.admin` | Multi-user onboarding under departments |
| `NEG-ORG-01` | Act 2 | `pages/departments.py` | `sarah.admin` | Duplicate department name 409 rejection |
| `POS-HR-01` | Act 3 | `pages/documents.py` | `roy.hr` | Async upload (202 $\rightarrow$ polling $\rightarrow$ Active) |
| `NEG-HR-01` | Act 3 | `pages/documents.py` | `roy.hr` | Unsupported file extension rejection (`.exe`) |
| `NEG-HR-02` | Act 3 | `pages/documents.py` | `roy.hr` | SHA-256 duplicate upload 409 Conflict |
| `POS-ENG-01` | Act 4 | `pages/projects.py` | `marcus.eng` | Project Titan creation |
| `POS-ENG-02` | Act 4 | `pages/documents.py` | `marcus.eng` | Project-scoped upload & access grant |
| `NEG-ENG-01` | Act 4 | `pages/projects.py` | `marcus.eng` | Manager leave-lock verification |
| `POS-ENG-03` | Act 4 | `pages/projects.py` | `marcus.eng` | Manager transfer and successful exit |
| `POS-LIFE-01` | Act 5 | `pages/documents.py` | `elena.dev` | In-page Chunk Inspector & Vector Search |
| `POS-LIFE-02` | Act 5 | `pages/documents.py` | `elena.dev` | Soft-archive file movement and chunk status |
| `POS-LIFE-03` | Act 5 | `pages/documents.py` | `elena.dev` | Permanent purge (DB + disk + Chroma) |
| `POS-CHAT-01` | Act 6 | `app.py` | `david.hr` | General KB citation retrieval |
| `NEG-CHAT-01` | Act 6 | `app.py` | `david.hr` | Scope restriction & zero cross-project leak |
| `POS-CHAT-02` | Act 6 | `app.py` | `roy.hr` | Cross-department access grant retrieval |
| `POS-CHAT-03` | Act 6 | `app.py` | `elena.dev` | Project member retrieval |

---

## 7. Approval Gate

Review the above specification and test matrix. Upon user approval:
1. Proceed to **Phase 2**: Generate synthetic test documents in `tests/fixtures/synthetic_data/`.
2. Proceed to **Phase 3**: Install Playwright and create `tests/e2e/conftest.py`.
