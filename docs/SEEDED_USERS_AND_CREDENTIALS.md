# KnowLayer — Seeded Users, Credentials & Structure

Generated on 18 Sep 2026 by `scripts/provision_demo.py`. The application database
(`instance/knowlayer.db`) was reset to a fresh state before provisioning.

> THIS FILE CONTAINS PLAIN-TEXT CREDENTIALS. Keep it out of public repositories
> and rotate passwords after first login. Every created user has
> `must_change_password = True` and will be forced to change their password on
> first login.

---

## Admin (bootstrap seed)

| Field | Value |
|-------|-------|
| UID | `admin` |
| Username | `admin` |
| Name | Administrator |
| Email | `admin@localhost` |
| Role | `Admin` |
| Department | `admin` (Administration) |
| Initial password | as set in `.env` → `ADMIN_INITIAL_PASSWORD` |
| Must change on login | Yes |

---

## Regular users (10)

All regular users share the initial password set by `DEFAULT_USER_PASSWORD`
(`ChangeMe123!` until the `.env` is changed). Every user must change it on
first login.

| UID | Username | Name | Email | Role | Employee ID | Department |
|-----|----------|------|-------|------|-------------|------------|
| `aarav.sharma` | `aarav` | Aarav Sharma | aarav.sharma@nexora.local | Manager | MSS-001 | DEPT-001 Human Resources |
| `priya.nair` | `priya` | Priya Nair | priya.nair@nexora.local | Tester | MSS-002 | DEPT-001 Human Resources |
| `rohan.yadav` | `rohan` | Rohan Yadav | rohan.yadav@nexora.local | Manager | MSS-003 | DEPT-002 Engineering |
| `vikram.singh` | `vikram` | Vikram Singh | vikram.singh@nexora.local | Developer | MSS-004 | DEPT-002 Engineering |
| `anita.gupta` | `anita` | Anita Gupta | anita.gupta@nexora.local | Developer | MSS-005 | DEPT-002 Engineering |
| `meera.iyer` | `meera` | Meera Iyer | meera.iyer@nexora.local | Solution Architect | MSS-006 | DEPT-002 Engineering |
| `karan.mehta` | `karan` | Karan Mehta | karan.mehta@nexora.local | Manager | MSS-007 | DEPT-003 Marketing |
| `sneha.patel` | `sneha` | Sneha Patel | sneha.patel@nexora.local | Tester | MSS-008 | DEPT-003 Marketing |
| `ritu.sharma` | `ritu` | Ritu Sharma | ritu.sharma@nexora.local | Manager | MSS-009 | DEPT-004 Finance |
| `deepak.kumar` | `deepak` | Deepak Kumar | deepak.kumar@nexora.local | Developer | MSS-010 | DEPT-004 Finance |

**Login:** use `username` (e.g. `aarav`) or email + initial password (`ChangeMe123!`).

---

## Departments

| Department ID | Name | Description | Default billable |
|---------------|------|-------------|------------------|
| `DEPT-001` | Human Resources | Recruitment, onboarding and employee relations. | billable |
| `DEPT-002` | Engineering | Product development and platform engineering. | billable |
| `DEPT-003` | Marketing | Brand, campaigns and market research. | both |
| `DEPT-004` | Finance | Accounting, payroll and budgeting. | non-billable |

## Projects

| Project ID | Name | Department | Manager |
|------------|------|------------|---------|
| `PROJ-001` | Employee Handbook Refresh | DEPT-001 | aarav.sharma |
| `PROJ-002` | Company Bot Platform | DEPT-002 | rohan.yadav |
| `PROJ-003` | Brand Website Rebuild | DEPT-003 | karan.mehta |
| `PROJ-004` | Payroll Upgrade | DEPT-004 | ritu.sharma |

## Roles

Standard seed roles from `permission_catalog.py`: `Admin`, `Manager`,
`Developer`, `Tester`, `Solution Architect` (all `global` scope).

Custom role created by the provisioning script: **`Project Coordinator`**
(department-scoped to DEPT-002) with permissions
`PROJECT_VIEW`, `DOCUMENT_VIEW`, `DOCUMENT_QUERY`, `USER_VIEW`, `DEPARTMENT_VIEW`.

## Memberships & grants

- Every user is an **active department member** of their own department
  (with their primary role as the membership role).
- Every user is an **active project member** of their department's project.
- Project grants (`project_grants`):
  - `PROJ-002` → role `Developer` (3), role `Project Coordinator` (6)
  - `PROJ-001` → role `Tester` (4)
  - `PROJ-003` → user `sneha.patel`

---

## Documents

The `input/` directory was cleared as part of the fresh start. No documents are
currently registered in SQLite or Chroma. Upload documents through the Streamlit
UI ("Documents" page → Upload document) to provision them for Q&A.