# Specification: Frontend Page Architecture, RBAC Controls, and Document Lifecycle

- **Author**: Antigravity Pair Programmer
- **Date**: 2026-10-23
- **Branch**: `sidebar-improvements`
- **Status**: Draft for User Review
- **Related Issues / Work**: Database Migration (8 consolidated tables), Role-Based Sidebar Navigation

---

## 1. Executive Summary & Goals

This specification defines the complete end-to-end design for the KnowLayer user interface, role-based page interactions, document lifecycle (non-blocking ingestion, archival vs permanent deletion), chunk observability, and testing seed data.

### Key Architectural Principles
1. **Write Implies Read**: Any write, create, update, delete, or manage permission on a domain automatically grants view access to that domain's data tables and navigation. Specific action buttons remain strictly gated by the specific atomic permission.
2. **Non-Blocking Background Ingestion**: Uploading a document must never freeze the Streamlit UI or make the browser fade out. Document registration returns immediately with `status: "processing"`, while FastAPI executes chunking and embedding asynchronously in the background. The UI supports extendable progress tracking (status-first, ready for numeric progress when available).
3. **Archival vs. Permanent Deletion**: 
   - **Archive**: Preserves chunks in ChromaDB for future retrieval/restoration without re-parsing, moves disk file to `input/{project_id}/archived/`, sets SQL status to `"archived"`. Standard chat filters only active documents.
   - **Permanent Delete**: Completely purges chunks from ChromaDB, permanently erases disk file, and purges database row.
4. **Unified Document & Chunk Observability**: Chunk inspection and vector search testing are integrated directly into `pages/documents.py` (via dedicated tabs), preserving a clean sidebar while exposing complete RAG transparency.
5. **Resilient Concurrency & Storage**: Isolated project disk folders, SHA-256 duplicate rejection, SQLite WAL mode, process-level Chroma singleton, and server-restart recovery ensure robust operation under multi-threaded background workers.
6. **Minimal Teammate Impact**: No modifications to the underlying Docling parser pipeline or vector client architecture; backgrounding and chunk queries wrap existing interfaces cleanly.

---

## 2. Permission Model: "Write Implies Read"

The application enforces a strict role-based access control (RBAC) model. Permissions are loaded from `GET /api/users/me/profile`.

### 2.1 Domain View Rules
A user is granted read/view access to a domain table if they hold either the explicit view permission or **any mutation permission** for that domain, or if they have global admin access (`ADMIN` or `*` or role `Admin`):

| Domain | Table Visible If User Has ANY of: | Mutation Action Gates |
|---|---|---|
| **Users** (`pages/users.py`) | `USER_VIEW`, `USER_CREATE`, `USER_UPDATE`, `USER_DELETE`, `*`, `ADMIN` | • Add User: `USER_CREATE`<br>• Edit User: `USER_UPDATE`<br>• Deactivate/Delete: `USER_DELETE` |
| **Departments** (`pages/departments.py`) | `DEPARTMENT_VIEW`, `DEPARTMENT_CREATE`, `DEPARTMENT_UPDATE`, `DEPARTMENT_ASSIGN_USERS`, `*`, `ADMIN` | • Create Dept: `DEPARTMENT_CREATE`<br>• Edit Dept: `DEPARTMENT_UPDATE`<br>• Manage Members: `DEPARTMENT_ASSIGN_USERS` |
| **Projects** (`pages/projects.py`) | Any authenticated user sees "My Projects". Management section requires `PROJECT_VIEW`, `PROJECT_CREATE`, `PROJECT_UPDATE`, `PROJECT_DELETE`, `PROJECT_MANAGE`, `*`, `ADMIN` | • Create Project: `PROJECT_CREATE`<br>• Edit Project: `PROJECT_UPDATE`<br>• Assign Members: `PROJECT_MANAGE`<br>• Leave Project: Any non-manager member |
| **Documents** (`pages/documents.py`) | Any authenticated user sees accessible documents. Management requires `DOCUMENT_VIEW`, `DOCUMENT_CREATE`, `DOCUMENT_DELETE`, `DOCUMENT_MANAGE`, `*`, `ADMIN` | • Upload: Project member or `DOCUMENT_CREATE`<br>• Archive: Document uploader, project manager, or `DOCUMENT_DELETE`<br>• Hard Delete: Manager or Admin<br>• Grants: `DOCUMENT_MANAGE` |
| **Roles** (`pages/roles.py`) | `ROLE_VIEW`, `ROLE_CREATE`, `ROLE_UPDATE`, `ROLE_DELETE`, `*`, `ADMIN` | • Create Role: `ROLE_CREATE`<br>• Update Role / Permissions: `ROLE_UPDATE`<br>• Delete Role: `ROLE_DELETE` |

---

## 3. Page-by-Page Specifications

### 3.1 `app.py` (Chat & Workspace)
- **Header**: Clean title and brief subtitle.
- **Project Context Filter**: Selectbox allowing the user to scope chat answers to:
  - "General Knowledge Base (All Accessible Documents)"
  - Specific Project (filtered strictly to projects the user is assigned to or has global access to).
- **Chat History & Interaction**:
  - Chat message container rendering user prompts, assistant answers, and citation expandable pills.
  - Chat input box at the bottom.
- **Top Actions Bar (Inline, not in sidebar)**:
  - Small popover/buttons for "Clear Chat" and "Session Info" to keep the sidebar minimalist.
- **In-flight Ingestion Notification**:
  - If any document is currently in `status: "processing"`, a subtle, non-intrusive status pill is shown above chat: `⏳ Ingesting "{doc_name}" in background...`.

### 3.2 `pages/profile.py` (My Profile)
- **Personal Information Card**:
  - Displays Full Name, Username, Employee ID, Email, Department, Job Title, Account Status.
- **Assigned Roles & Permissions**:
  - Visual badge pills displaying user roles.
  - Expandable chip list of active permissions granted to the user.
- **Security & Password Management**:
  - "Change Password" form: `Current Password`, `New Password`, `Confirm New Password`.
  - Client validates passwords match; invokes `AuthenticationService.change_password()`.
- *(Note: Project leave action is located in `pages/projects.py`, keeping Profile strictly personal).*

### 3.3 `pages/projects.py` (Projects Management)
- **Section 1: 📁 My Projects (All Users)**:
  - Shows table of projects where current user is assigned (`user_projects`) or manages.
  - Columns: `Project ID`, `Project Name`, `Department`, `Manager`, `Status`, `Action`.
  - **"Leave Project" Protection**:
    - An assigned member (who is not the designated manager) can click "Leave Project". Prompts confirmation dialog, then calls `POST /api/projects/{project_id}/members/me/leave`.
    - **Orphan Lock**: If current user is the project's manager, "Leave Project" is disabled with tooltip: `"Project manager cannot leave without reassigning the manager role first."`
- **Section 2: ⚙️ Project Administration (Gated)**:
  - Rendered only if user has project mutation/management permissions or is Admin.
  - **Create Project Form**: `Project ID` (optional), `Project Name`, `Department ID` (dropdown), `Manager UID` (dropdown), `Description`, `Start Date`, `End Date`.
  - **Project Members Sub-Panel**: Select a project -> view table of current members -> assign new member with role, or revoke member.
  - **Project Access Grants Sub-Panel**: Assign explicit role or user grant to project.

### 3.4 `pages/documents.py` (Documents & Observability)
The document page is split into two primary tabs:

#### Tab 1: 📚 Document Library
- **Auto-Refresh via Fragment**:
  - The documents table is wrapped in a Streamlit fragment `@st.fragment(run_every=int(os.getenv("DOC_INGESTION_REFRESH_INTERVAL", 5)))`.
  - Polling only activates when at least one document has `status == "processing"`. Once all documents reach `active` or `failed`, auto-refresh unregisters to save network/CPU.
- **Non-Blocking Upload Card**:
  - File uploader supporting `.pdf`, `.docx`, `.txt`, `.md`, `.rst`.
  - Project selector dropdown (pre-filtered by user's upload permissions).
  - Optional Document Name & Description.
  - **Collision & Duplicate Handling**:
    - **Identical Hash in Same Project**: If uploaded file's SHA-256 hash matches an active document in the same project, reject upload with warning: `"This exact file already exists in this project as '{name}'."`
    - **Different Hash, Same Name in Same Project**: Prompt user:
      1. *Replace existing*: Archives old doc, moves old file to `input/{project_id}/archived/`, saves new file, ingests new vectors.
      2. *Keep both*: Auto-increments name to next available number (e.g. `report_1.pdf`).
    - **Different Project, Same Name**: Permitted without renaming.
  - Button: `Upload and Process`.
  - **Behavior**: Form submits file to backend. Backend returns `HTTP 202 Accepted` with `status: "processing"`.
  - Streamlit immediately displays: `✅ Document registered. Processing in background...` without freezing or fading the page.
- **Documents Overview Table**:
  - Columns: `Document ID`, `Name`, `Project`, `Type`, `Version`, `Status`, `Uploader`, `Uploaded At`, `Actions`.
  - Status display:
    - `🟢 active`: Fully processed and searchable.
    - `⏳ processing`: Shows spinner/badge (with background polling or rerun refresh).
    - `🔴 failed`: Shows failure alert with error tooltip.
    - `⚪ archived`: Soft-deleted.
  - Action buttons:
    - `Archive`: Soft-delete document (moves to archived folder, keeps chunks in Chroma, omitted from active chat).
    - `Delete Permanently`: Hard purge (purges Chroma vectors and erases file; visible for managers/admin).
- **Document Details & Access Configuration**:
  - Metadata inspect viewer.
  - Access Grants table and Grant Access form (gated by `DOCUMENT_MANAGE`).

#### Tab 2: 🔍 Chunk Inspector & Vector Search (Observability)
- **Chunk Explorer**:
  - Dropdown: Select any active or archived document.
  - Metrics: Total chunks, average chunk size, chunk status.
  - Chunks Table/List:
    - Chunk Index (`#1`, `#2`, ...), Character Length, Token Estimate.
    - Metadata display (`document_id`, `project_id`, `version`, `source`, `status`).
    - Expandable chunk text preview.
- **Live Vector Search Sandbox**:
  - Search query text input: e.g. "What is our company travel policy?".
  - Top-K slider (1 to 10).
  - Optional Project filter dropdown.
  - Checkbox: "Include archived documents in search" (for testing/inspection).
  - Button: `Test Vector Retrieval`.
  - Result cards displaying:
    - Retrieved chunk content.
    - Source document and chunk index.
    - Vector similarity/distance score.
    - Match status (`active` or `archived`).

### 3.5 `pages/users.py` (Users Administration)
- **Gated By**: `has_user_perm` (`USER_VIEW` or any user mutation / Admin).
- **Users Table**:
  - Columns: `UID`, `Employee ID`, `Username`, `Email`, `Name`, `Department`, `Job Title`, `Status`, `Role`, `Created At`.
  - Filter by Department or Status (`active` / `inactive`).
- **Add User Form** (Gated by `USER_CREATE`):
  - `Username`, `Password`, `Email`, `Name`, `Department ID`, `Job Title`, `Role ID`.
- **User Actions** (Gated by `USER_UPDATE` / `USER_DELETE`):
  - Edit user fields (Name, Department, Job Title).
  - Toggle Status (`active` / `inactive` / Deactivate).

### 3.6 `pages/departments.py` (Departments Administration)
- **Gated By**: `has_dept_perm` (`DEPARTMENT_VIEW` or any dept mutation / Admin).
- **Departments Table**:
  - Columns: `Department ID`, `Department Name`, `Description`, `Default Billable`, `Status`, `Member Count`.
- **Create Department Form** (Gated by `DEPARTMENT_CREATE`):
  - `Department ID`, `Department Name`, `Description`, `Default Billable`.
- **Department Members Management** (Gated by `DEPARTMENT_ASSIGN_USERS`):
  - Select department -> View member roster -> Assign user with membership role (`Head`, `Member`, `Lead`) -> Remove member.

### 3.7 `pages/roles.py` (Roles & Permissions Administration)
- **Gated By**: `has_role_perm` (`ROLE_VIEW` or any role mutation / Admin).
- **Roles Table**:
  - Columns: `Role ID`, `Role Name`, `Scope` (`global` / `department`), `Description`, `Status`.
- **Role Permissions Matrix Editor** (Gated by `ROLE_UPDATE` / Admin):
  - Select a role from dropdown.
  - Multi-select or category checkboxes of all available system permissions (`USER_*`, `PROJECT_*`, `DEPARTMENT_*`, `DOCUMENT_*`, `ROLE_*`, `CHAT_*`).
  - Button: `Save Permissions`.
- **Create Role Form** (Gated by `ROLE_CREATE`):
  - `Role Name`, `Scope`, `Description`, Initial Permissions.

---

## 4. Backend Architecture: Async Document Ingestion & Synchronized Deletion

### 4.1 Non-Blocking Background Ingestion Workflow

```
[Streamlit UI]                     [FastAPI /api/documents]               [Background Worker]             [ChromaDB & Storage]
      |                                        |                                  |                                |
      |--- POST /api/documents (file data) --->|                                  |                                |
      |                                        |-- 1. Check SHA-256 hash in project                                |
      |                                        |-- 2. Create SQL row (status="processing")                         |
      |                                        |-- 3. Save raw file to input/{project_id}/                         |
      |                                        |-- 4. Enqueue BackgroundTasks --->|                                |
      |<-- 202 Accepted (doc, status="proc") --|                                  |                                |
      |                                                                           |-- 5. Docling/Parser process -->|
      |                                                                           |-- 6. Chunk records ------------|
      |                                                                           |-- 7. chroma.add_documents() ->|
      |                                                                           |-- 8. Update SQL row (status="active")
      |                                                                           |                                |
      |--- GET /api/documents/{id}/status ---->|                                  |                                |
      |<-- { "status": "active" } -------------|                                  |                                |
```

#### API Contracts:
1. `POST /api/documents`:
   - Computes SHA-256 checksum of uploaded bytes.
   - If identical checksum exists for active document in same project: returns HTTP 409 Conflict.
   - Saves record with `status: "processing"` and `file_hash`.
   - Saves file to disk under project directory: `input/{project_id or "unassigned"}/{document_id}_{safe_filename}`.
   - Returns HTTP 202 Accepted with `DocumentResponse` (`status="processing"`).
   - Starts ingestion via `BackgroundTasks`.
2. `GET /api/documents/{document_id}/status`:
   - Returns:
     ```json
     {
       "document_id": "DOC-0001",
       "status": "processing" | "active" | "failed",
       "progress": null,
       "message": "Processing chunks and vector embeddings"
     }
     ```
   - When numeric progress is not supplied by Docling, `progress` is `None` and UI renders the status string. Extendable for percentage when available.

### 4.1.1 Concurrency & Storage Resilience
- **SQLite Concurrency**: Enable WAL mode (`PRAGMA journal_mode=WAL;`) and connection `busy_timeout=30000` (`timeout=30`) in SQLite session setup. Readers never block writers; concurrent background ingestion commits and user mutations queue cleanly without throwing `database is locked`.
- **ChromaDB Thread Safety**: Manage `chromadb.PersistentClient` as a shared process singleton across background workers and chat retrieval. On Windows, this prevents OS file lock collisions (`WinError 32`) between write operations and concurrent search queries.
- **RAG Retrieval Status Isolation**: Chunks stored in ChromaDB include `status: "active"` in metadata, and retrieval queries filter strictly for active documents (`status == "active"` or authorized active document IDs). Incomplete or processing uploads never leak into chat responses.
- **Server Restart Zombie Recovery**: FastAPI lifespan startup hook scans the `documents` table for any row with `status == "processing"`. All found rows are transitioned to `status = "failed"` with description `"Server restarted during ingestion"` to prevent permanent zombie locks.
- **Project Directory Isolation**: Uploaded files reside in `input/{project_id or "unassigned"}/{document_id}_{filename}`. Projects never overwrite each other's disk files.

### 4.2 Document Archival vs. Permanent Deletion Workflow

#### A. Archival (Default / Soft Delete)
When `DELETE /api/documents/{document_id}` (or `POST /api/documents/{document_id}/archive`) is called:
1. **Authorization Check**: Verify actor is uploader, project manager, or has `DOCUMENT_DELETE` / `ADMIN`.
2. **Database Update**: Update document row `status = "archived"`, `updated_at = now`.
3. **ChromaDB Vectors Preserved**: Chunks in ChromaDB are **kept** (not deleted). Normal RAG retrieval queries filter for `status == "active"`, automatically omitting archived chunks from chat.
4. **Disk File Relocation to Archived Folder**: Move file from `input/{project_id}/` to `input/{project_id}/archived/{document_id}_{safe_filename}` (or `input/unassigned/archived/`). Update `document.storage_location` to point to the archived file path.
5. **RAG Cache Invalidation**: Clear semantic query cache entries to prevent stale citations.

#### B. Permanent Deletion (Hard Purge)
When `DELETE /api/documents/{document_id}?permanent=true` is called:
1. **Authorization Check**: Requires project manager or `ADMIN`.
2. **ChromaDB Vector Purge**: Call `store.collection.delete(where={"document_id": document_id})`. Chunks are permanently deleted.
3. **Disk File Permanent Erasure**: Unlink/delete file from disk.
4. **Database Purge**: Delete SQL row from `documents` table.

### 4.3 Chunk Observability Endpoints

1. `GET /api/documents/{document_id}/chunks`:
   - Queries ChromaDB: `store.collection.get(where={"document_id": document_id}, include=["documents", "metadatas"])`.
   - Returns list of chunks: `[{ "id": str, "content": str, "metadata": dict }]`.
2. `POST /api/documents/chunks/search`:
   - Payload: `{ "query": str, "project_id": str | None, "top_k": int = 4, "include_archived": bool = False }`.
   - Queries ChromaDB with embedding function and returns ranked matching chunk records with distance scores.

---

## 5. Post-Implementation Phase: Test Seed & Reset Script Specification

To ensure thorough manual and automated verification across roles and scenarios, a seed script will be constructed after the frontend and API contracts are finalized:

- **Script Locations**:
  - `scripts/seed_mock_data.py`: Idempotently populates diverse test data.
  - `scripts/reset_mock_data.py`: Cleans mock data, resets ChromaDB test documents, and clears cache.
- **Mock Data Topology**:
  - **1 System Admin**: `admin` / `adminpass`
  - **1 Department Head (Engineering)**: `eng_lead` (Role: Department Manager, permissions to create projects and assign users)
  - **1 Department Head (HR)**: `hr_lead` (Role: Department Manager)
  - **3 Department Members**: `dev_alice`, `dev_bob`, `hr_carol` (Contributors and Viewers)
  - **2 Departments**: `DEP-ENG` ("Engineering"), `DEP-HR` ("Human Resources")
  - **2 Projects**: `PRJ-INFRA` (Managed by `eng_lead`), `PRJ-ONBOARD` (Managed by `hr_lead`)
  - **3 Sample Documents**: 1 in `PRJ-INFRA`, 1 in `PRJ-ONBOARD`, 1 Global/Unassigned.
- **Idempotency**: All insertions check existing IDs first, preventing duplicate key violations on repeated execution.

---

## 6. Implementation Stages & Verification Strategy

1. **Phase 1: Backend Async Ingestion & Concurrency Guardrails**
   - Configure SQLite WAL mode and busy timeout in session setup.
   - Wire `ChromaVectorStore` client as process-level singleton with status-based retrieval filtering.
   - Add server startup recovery hook for orphaned `processing` documents.
   - Add SHA-256 hash calculation, per-project collision detection, and `input/{project_id}/` storage pathing.
   - Add background task ingestion handler and `GET /api/documents/{document_id}/status`.
   - Add chunk inspection and search endpoints.
   - Enhance document deletion: soft-archive moves file to `input/{project_id}/archived/` while preserving Chroma chunks; permanent purge deletes vectors and disk file.
2. **Phase 2: Streamlit Document Page Enhancement**
   - Implement non-blocking upload and status badge in `pages/documents.py`.
   - Add configurable `@st.fragment` auto-refresh (`DOC_INGESTION_REFRESH_INTERVAL`).
   - Add Tab 2 for Chunk Explorer and Vector Search Sandbox.
3. **Phase 3: Pages Standardization & RBAC Controls**
   - Update `pages/projects.py`: "My Projects" table with "Leave Project" action (manager orphan lock), plus gated project management.
   - Update `pages/profile.py`: Profile badge, permissions list, change password form.
   - Update `pages/users.py`, `pages/departments.py`, `pages/roles.py`: Apply "Write implies Read" rule and gated action buttons.
   - Clean `app.py`: Inline clear chat controls, in-flight document processing toast.
4. **Phase 4: Seed & Reset Scripts and End-to-End Testing**
   - Implement `scripts/seed_mock_data.py` and `scripts/reset_mock_data.py`.
   - Run verification across all user personas (Admin, Dept Lead, Regular User).

---

## 7. Approval Gate

Before any implementation code is written:
- Review page layouts and permission rules.
- Confirm non-blocking background ingestion design.
- Confirm placement of Chunk Observability inside `pages/documents.py` (Tab 2).
- Confirm Archive (preserves Chroma chunks, relocates disk file) vs. Permanent Delete (purges Chroma vectors and deletes disk file).
