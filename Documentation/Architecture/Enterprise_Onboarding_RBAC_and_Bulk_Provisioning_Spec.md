# Enterprise Onboarding, RBAC, and Bulk Provisioning Specification

**Document Version:** 1.0.0  
**Status:** Approved for Implementation  
**Target Subsystems:** FastAPI Backend (`app/`), Streamlit UI (`streamlit_app/`), Teams Channel Adapter (`app/infrastructure/channels/`)  
**Design Patterns:** Ports & Adapters (Hexagonal Architecture), Role-Based Access Control (RBAC), Strategy Pattern, Transactional Outbox / Batch Processing  

---

## 1. Executive Summary & Vision

This specification defines the functional and architectural behavior for **enterprise organization management, delegated access control, bulk provisioning, and document knowledge boundaries** in Company_Bot.

The core design principle is **Zero Hardcoded Capabilities**:
- An actor's ability to perform any action (upload documents, create projects, manage users, query knowledge) is governed strictly by **fine-grained permissions**, never hardcoded role strings like `if role == 'admin'`.
- Job titles and roles (e.g. `Developer`, `HR Specialist`, `Department Head`) are configurable database entities that bundle permissions.
- Access to documents is strictly governed by **Project Boundaries**, eliminating fragmented per-document permission micro-management.
- Enterprise onboarding supports **Bulk CSV Ingestion** with partial success reporting and automated credential receipt generation.

---

## 2. Actor Personas & Lifecycle

```
[Developer Handover]
        │
        ▼
[Dev Superadmin (admin)] ──(rotates password)──> [Initial Bootstrap]
        │
        ├──(creates)──> [Company Primary Admin]
        │                       │
        │                       ├──(bulk imports)──> [Departments & Users]
        │                       │
        │                       └──(delegates)─────> [Department Heads]
        │                                                    │
        │                                                    ├──(creates)──> [Projects]
        │                                                    └──(assigns)──> [Project Members]
        │                                                                            │
        ▼                                                                            ▼
[Microsoft Teams User (SSO)]                                              [Streamlit Web User]
(Passwordless: Email Matched)                                             (Username + Password)
```

### Primary Personas:

1. **Dev Superadmin (`admin`):**
   - Shipped by default with the platform for installation, initial setup, and break-glass maintenance.
   - Handed over to the customer; the default password must be rotated during handover.
   - Remains available if the company chooses to use it directly, but best practice delegates day-to-day operations to the Company Primary Admin.
2. **Company Primary Admin (e.g. `Director of HR`, `Company Manager`):**
   - Possesses global scope and administrative permissions.
   - Performs bulk enterprise onboarding (Departments, Users, Company-wide policies).
   - Delegates department administration to Department Heads.
3. **Department Head (e.g. `Engineering Lead`, `Finance Manager`):**
   - Granted department-scoped permissions (`PROJECT_CREATE`, `USER_VIEW`, `DOCUMENT_UPLOAD`).
   - Creates departmental projects, assigns members, and uploads or delegates document provisioning.
4. **Project Member / Contributor (e.g. `Senior Developer`, `Staff Analyst`):**
   - Belongs to a primary home department.
   - Assigned to specific projects across the company with project-specific capabilities (e.g. Uploader on Project A, Reader on Project B).
5. **Standard Employee / Reader:**
   - Possesses `DOCUMENT_QUERY` and `PROJECT_VIEW`.
   - Interacts with the chatbot in Streamlit or Microsoft Teams to query authorized company and project policies.
6. **Teams Chatbot User:**
   - Accesses knowledge via Microsoft Teams.
   - Authenticated passwordlessly via Microsoft 365 enterprise email matching.

---

## 3. System Invariants ("The Golden Rules")

1. **Permission-First Execution:**
   - Application code must never check `user.role == "Admin"` or `user.role == "Manager"`.
   - Capabilities are checked solely via:
     $$\text{has\_permission}(\text{actor}, \text{PERMISSION\_NAME}, \text{context})$$
2. **Strict Delegation Cap (Anti-Privilege Escalation):**
   - An actor can **only** grant, delegate, or assign permissions that the actor **actively possesses**.
   - A Department Head holding `DOCUMENT_UPLOAD` cannot create a role with `USER_DELETE`.
3. **Single Home Department:**
   - Every employee has exactly **one primary home department** (`users.department_id`).
   - Cross-department work occurs strictly through **Project Memberships** (`user_projects`), not by assigning an employee to multiple departments.
4. **Project as Primary Security Boundary:**
   - Documents belong to a Project (`documents.project_id`).
   - A user who is an active member of Project $P$ has read access to all documents within Project $P$.
   - Unassigned documents (`project_id = NULL`) are organization-wide policies readable by all active users.
5. **Zero Data Leakage on Boundary Rejection:**
   - When a user asks a question whose answer resides in an unauthorized project, the chatbot must detect the boundary and return a safe contact prompt (e.g. *"This information is part of Project Phoenix. Contact project manager Alice to request access."*).
   - Document contents, citations, and metadata must never be exposed to unauthorized principals.
6. **Company Ownership of Knowledge Assets:**
   - Documents uploaded by an employee remain permanently attached to their project even if the uploader is deactivated or leaves the company.

---

## 4. Functional Specifications by Epic

### Epic 1: Developer Handover & Superadmin Bootstrap

- **Requirement 1.1:** The platform initializes with a break-glass `admin` account.
- **Requirement 1.2:** The setup wizard / API provides a dedicated handover workflow:
  1. Authenticate as default `admin`.
  2. Create the initial Company Primary Admin user (e.g. `hr_admin`) with full permissions.
  3. Rotate `admin` password to a client-specified secure password.
- **Requirement 1.3:** The system operates identically whether the company retains and uses `admin` or designates their own primary administrative role.

---

### Epic 2: Bulk Enterprise Onboarding Engine (CSV)

#### 2.1 Department Bulk Ingestion
- **Endpoint:** `POST /api/admin/bulk/departments`
- **CSV Format:**
  ```csv
  department_id,department_name,description,default_billable
  D-ENG,Engineering,Software and infrastructure teams,billable
  D-HR,Human Resources,People operations and talent acquisition,non-billable
  D-FIN,Finance,Financial planning and accounting,non-billable
  ```
- **Validation Rules:**
  - `department_id` and `department_name` are mandatory and unique.
  - `default_billable` must be one of `billable`, `non-billable`, or `both`.

#### 2.2 User Bulk Ingestion & Receipt Generation
- **Endpoint:** `POST /api/admin/bulk/users`
- **CSV Format:**
  ```csv
  username,name,email,department_id,role,employee_id,initial_password
  alice,Alice Smith,alice@company.com,D-ENG,Developer,EMP-1001,
  bob,Bob Jones,bob@company.com,D-ENG,Developer,EMP-1002,CustomPass123!
  carol,Carol White,carol@company.com,D-HR,HR_Specialist,,
  ```
- **Validation Rules:**
  - `username`, `email`, and `department_id` are **strictly mandatory**.
  - No magical fallback departments are created: if an employee is unassigned, the company admin must explicitly create a department (e.g. `General` or `Floating`) and provide its `department_id`.
  - If `department_id` is missing, empty, or does not exist in the database, that row fails validation with line-level error.
  - `email` must be valid format and unique.
  - `uid` is auto-generated as an internal stable UUID for database foreign keys.
  - `employee_id` is an optional company payroll/badge identifier (unique if provided, nullable if omitted).

- **Password Generation Strategy (Strategy Pattern):**
  - If `initial_password` is provided in CSV, validate minimum length (8 chars) and use it.
  - If `initial_password` is empty, invoke configured `PasswordGenerationStrategy`:
    - **Strategy 1 (Default):** `UsernameSuffixStrategy` $\rightarrow$ generates `<username>123`.
    - **Strategy 2 (Secure):** `RandomAlphanumericStrategy` $\rightarrow$ generates 10-character cryptographically secure token.
    - Strategy is switchable via environment variable `PASSWORD_GENERATION_STRATEGY`.
- **Partial Success Transaction Model (BS 1):**
  - Processing is line-by-line within an overall batch.
  - Valid rows are committed to the database.
  - Invalid rows (duplicate email, unknown department ID, invalid format) are captured with line numbers.
  - The API returns HTTP 200 with an execution receipt:
    ```json
    {
      "total_rows": 100,
      "successful_count": 98,
      "failed_count": 2,
      "receipt_csv": "data:text/csv;base64,..."
    }
    ```
- **Receipt CSV Schema:**
  ```csv
  line_number,username,email,status,generated_password,error_message
  2,alice,alice@company.com,SUCCESS,alice123,
  3,bob,bob@company.com,SUCCESS,CustomPass123!,
  4,charlie,bad_email,FAILED,,Invalid email format
  5,david,david@company.com,FAILED,,Department 'D-UNKNOWN' does not exist
  ```

---

### Epic 3: Organization & Scoped Permission Delegation

#### 3.1 Permission Scope Hierarchy
- Permissions are flat capability strings:
  - `DOCUMENT_QUERY`, `DOCUMENT_VIEW`, `DOCUMENT_UPLOAD`, `DOCUMENT_UPLOAD_ORG_WIDE`, `DOCUMENT_DELETE`
  - `PROJECT_VIEW`, `PROJECT_CREATE`, `PROJECT_UPDATE`, `PROJECT_DELETE`, `PROJECT_MANAGE_MEMBERS`
  - `USER_VIEW`, `USER_CREATE`, `USER_UPDATE`, `USER_DELETE`
  - `DEPARTMENT_VIEW`, `DEPARTMENT_CREATE`, `DEPARTMENT_UPDATE`
  - `ROLE_VIEW`, `ROLE_CREATE`, `ROLE_UPDATE`, `PERMISSION_MANAGE`
- Scoping rules:
  - **Global Scope (`scope="global"`):** Applies company-wide across all departments and projects.
  - **Department Scope (`scope="department"`, `department_id="D-ENG"`):** Applies strictly within the specified department.

#### 3.2 Project-Level Contextual Roles
- Users have a global job title (`users.role`), which grants base platform capabilities (e.g. `Developer` has `DOCUMENT_QUERY`, `PROJECT_VIEW`).
- Inside each project (`user_projects`), users are assigned a **Project Role** (`membership_role`).
- *Note:* Role names below are illustrative examples; companies can define custom role names and assign any permission set dynamically:
  - `Lead`: Grants `DOCUMENT_UPLOAD` and `PROJECT_MANAGE_MEMBERS` on that specific project.
  - `Contributor`: Grants `DOCUMENT_UPLOAD` on that specific project.
  - `Member` / `Viewer`: Grants `DOCUMENT_QUERY` and read access only.
- Alice and Bob can both be global `Developer`s; Alice is `Lead` on Project Alpha, while Bob is `Viewer` on Project Alpha and `Lead` on Project Beta.

#### 3.3 Employee Department Transfers vs Offboarding (BS 3)
- **Department Transfer:**
  - Changing `users.department_id` updates home department.
  - All existing `user_projects` memberships and uploaded documents **remain unaffected**.
- **Employee Offboarding (Deactivation):**
  - Setting `users.status = "inactive"`:
    1. Immediately invalidates web authentication tokens and prevents login.
    2. Deactivates all `user_projects` memberships (`status = "inactive"`).
    3. Blocks chatbot access from Teams.
    4. Documents previously uploaded by the employee stay active in their projects.

---

### Epic 4: Document Governance & RAG Knowledge Boundaries

#### 4.1 Document Ingestion Rules (BS 5)
- Standard document uploads (`DOCUMENT_UPLOAD`) **require a valid `project_id`**.
- Creating an Organization-Wide (Unassigned) Document requires the explicit permission:
  $$\text{DOCUMENT\_UPLOAD\_ORG\_WIDE}$$
  *(Prevents accidental global publication of confidential departmental files).*

#### 4.2 Archived Projects (BS 4)
- A project with `status = "archived"` enters **Read-Only Maintenance**:
  - Chatbot queries against project documents continue to function for authorized project members.
  - Uploading new documents or modifying existing documents is blocked with HTTP 409 Conflict.
  - Adding or modifying project members is blocked.

#### 4.3 Database Schema Simplification
- **Deprecate `document_permissions`:** Project membership is the single source of truth for document access.
- **Deprecate `department_members`:** `users.department_id` is the single source of truth for employee department.

---

### Epic 5: Channel Authentication Parity (Teams vs Web)

- **Microsoft Teams Channel:**
  - Authenticates natively via Azure Bot Framework activity payload.
  - The bot extracts `activity.from.email` or `activity.from.user_principal_name`.
  - Queries `users` table for an active user matching that email.
  - **Zero password required in Teams.**
  - If email is not found or user is inactive $\rightarrow$ returns *"Your Microsoft Teams account (email) is not registered in KnowLayer. Contact HR."*
- **Streamlit Web Channel:**
  - Authenticates via `username` and `password`.
  - Password change compulsion is controlled via configurable setting `ENFORCE_PASSWORD_CHANGE_ON_FIRST_LOGIN` (Default: `False`).

---

## 5. End-to-End User Scenarios & Acceptance Criteria

### Scenario 1: Initial Handover & Superadmin Bootstrap
- **Given** a fresh system deployment with default credentials (`admin` / default pass).
- **When** the developer executes the bootstrap handover script with `hr_director` payload and new admin password `SecureRoot2026!`.
- **Then** the `hr_director` user is created with full company admin permissions.
- **And** the default `admin` password is updated to `SecureRoot2026!`.
- **And** the old default credentials are permanently rejected.

### Scenario 2: Bulk CSV Ingestion with Partial Failure & Credential Receipt
- **Given** authenticated Company Admin `hr_director`.
- **When** the admin uploads a `users.csv` containing 10 rows:
  - 8 rows have valid departments and formatting.
  - 1 row has duplicate email.
  - 1 row has nonexistent department `D-GHOST`.
- **Then** exactly 8 users are created in the database with status `active`.
- **And** the API returns HTTP 200 with `successful_count: 8` and `failed_count: 2`.
- **And** the downloaded receipt CSV shows passwords for the 8 created users and clear error messages for the 2 failed rows.

### Scenario 3: Department Head Scoped Delegation
- **Given** user `eng_head` assigned role `Department_Head` with `scope="department"` and `department_id="D-ENG"`.
- **When** `eng_head` creates a project with `department_id="D-ENG"`, the request succeeds.
- **When** `eng_head` attempts to create a project with `department_id="D-HR"`, the request is rejected with HTTP 403 Forbidden.
- **When** `eng_head` attempts to create a role granting `USER_DELETE` (which `eng_head` does not possess), the request is rejected with HTTP 403 (Anti-Privilege Escalation).

### Scenario 4: Cross-Department Project Collaboration
- **Given** users `alice` (home: `D-ENG`) and `bob` (home: `D-ENG`), both with primary role `Developer`.
- **And** project `PRJ-INFRA` (Engineering) and project `PRJ-PORTAL` (Marketing).
- **When** `alice` is assigned to `PRJ-INFRA` as `membership_role: "Lead"` and to `PRJ-PORTAL` as `membership_role: "Viewer"`.
- **And** `bob` is assigned to `PRJ-INFRA` as `membership_role: "Viewer"`.
- **Then** `alice` can upload documents to `PRJ-INFRA`.
- **And** `bob` cannot upload documents to `PRJ-INFRA` (query only).
- **And** `alice` cannot upload documents to `PRJ-PORTAL` (query only).

### Scenario 5: Accidental Leak Prevention (`DOCUMENT_UPLOAD_ORG_WIDE`)
- **Given** user `alice` possessing `DOCUMENT_UPLOAD` but lacking `DOCUMENT_UPLOAD_ORG_WIDE`.
- **When** `alice` attempts to upload a document with `project_id = None`.
- **Then** the request is rejected with HTTP 403: *"Organization-wide document provisioning requires DOCUMENT_UPLOAD_ORG_WIDE permission."*

### Scenario 6: Employee Offboarding & Department Transfer
- **Given** employee `alice` assigned to project `PRJ-INFRA` with 3 uploaded documents.
- **When** `alice` is transferred from `D-ENG` to `D-PRODUCT`.
- **Then** `alice` retains query and membership access to `PRJ-INFRA`.
- **When** `alice` is deactivated (`status = "inactive"`).
- **Then** `alice` login tokens are rejected immediately.
- **And** all 3 documents remain active and queryable by other members of `PRJ-INFRA`.

### Scenario 7: Teams Chatbot Email-Matched Boundary Query
- **Given** Microsoft Teams activity payload from verified email `alice@company.com`.
- **When** `alice` asks a question answerable only by project `PRJ-FINANCE` (to which Alice has no access).
- **Then** the bot returns a contact prompt for the finance project manager.
- **And** zero citations or financial policy sentences are rendered.

---

## 6. Mock Datasets Specification

### `test_data/departments.csv`
```csv
department_id,department_name,description,default_billable
D-ENG,Engineering,Core platform engineering and cloud infrastructure,billable
D-HR,Human Resources,People operations compensation and policy,non-billable
D-FIN,Finance,Corporate accounting payroll and financial planning,non-billable
D-PROD,Product,Product management design and user research,billable
```

### `test_data/users.csv`
```csv
username,name,email,department_id,role,initial_password
john_eng,John Doe,john.doe@company.com,D-ENG,Developer,
neha_eng,Neha Sharma,neha.sharma@company.com,D-ENG,Developer,
carol_hr,Carol Danvers,carol.danvers@company.com,D-HR,HR_Specialist,WelcomeHR2026!
frank_fin,Frank Castle,frank.castle@company.com,D-FIN,Financial_Analyst,
lead_eng,Sarah Connor,sarah.connor@company.com,D-ENG,Department_Head,
```

### `test_data/projects.csv`
```csv
project_id,project_name,department_id,manager_username,description
PRJ-CLOUD,Cloud Migration 2026,D-ENG,lead_eng,Next-gen infrastructure migration
PRJ-BENEFITS,Annual Benefits Overhaul,D-HR,carol_hr,Healthcare and wellness policy rollouts
PRJ-AUDIT,Q4 Financial Compliance,D-FIN,frank_fin,External audit documentation
```
