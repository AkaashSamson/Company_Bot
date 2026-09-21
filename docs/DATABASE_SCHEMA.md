# KnowLayer SQLite Database Schema

## 1. Overview

This document describes the SQLite database schema used by **KnowLayer** in its final, post-initialization state.

### Database Configuration

| Configuration      | Details                                                                                      |
| ------------------ | -------------------------------------------------------------------------------------------- |
| **Database URL**   | `sqlite:///./instance/knowlayer.db`                                                          |
| **ORM**            | SQLAlchemy 2.0                                                                               |
| **ORM Base**       | `app.infrastructure.persistence.sqlalchemy.models.Base`                                      |
| **Table Creation** | `Base.metadata.create_all()` on application startup                                          |
| **Foreign Keys**   | Enabled using `PRAGMA foreign_keys=ON`                                                       |
| **Seed Data**      | `permissions`, `roles`, and the default `Admin` user are inserted during application startup |

The application also performs an **in-place migration pass** during startup. This migration adds legacy columns, creates missing indexes, and rebuilds the `projects` and `documents` tables when required.

### SQLite Type Mapping

| SQLAlchemy Type           | SQLite Type  |
| ------------------------- | ------------ |
| `String(n)`               | `VARCHAR(n)` |
| `DateTime(timezone=True)` | `DATETIME`   |
| `Integer`                 | `INTEGER`    |
| `Boolean`                 | `BOOLEAN`    |

---

# 2. Tables Overview

The KnowLayer database contains **12 tables**.

|  # | Table                   | Purpose                                 | Model                      |
| -: | ----------------------- | --------------------------------------- | -------------------------- |
|  1 | `users`                 | Employee and user accounts              | `UserRecord`               |
|  2 | `departments`           | Company departments                     | `DepartmentRecord`         |
|  3 | `projects`              | Department projects                     | `ProjectRecord`            |
|  4 | `documents`             | HR, policy, and project documents       | `DocumentRecord`           |
|  5 | `user_projects`         | User-to-project assignment / membership | `UserProjectRecord`        |
|  6 | `business_id_sequences` | Business-ID sequence counters           | `BusinessIdSequenceRecord` |
|  7 | `roles`                 | RBAC roles                              | `RoleRecord`               |
|  8 | `permissions`           | Permission catalogue                    | `PermissionRecord`         |
|  9 | `role_permissions`      | Role-to-permission mapping              | `RolePermissionRecord`     |
| 10 | `department_members`    | User-to-department membership           | `DepartmentMemberRecord`   |
| 11 | `document_permissions`  | Document-level access grants            | `DocumentPermissionRecord` |
| 12 | `project_grants`        | Project-level access grants             | `ProjectGrantRecord`       |

---

# 3. Table Definitions

## 3.1 `users`

Stores employee and user account information.

| Column                    | SQLite Type    | Nullable | Key    | Default    | Description                                            |
| ------------------------- | -------------- | -------: | ------ | ---------- | ------------------------------------------------------ |
| `uid`                     | `VARCHAR(128)` |       No | PK     | —          | Unique internal user identifier                        |
| `username`                | `VARCHAR(128)` |       No | Unique | `''`       | User login name                                        |
| `name`                    | `VARCHAR(200)` |       No | —      | —          | User's full name                                       |
| `email`                   | `VARCHAR(320)` |       No | Unique | —          | User email address                                     |
| `role`                    | `VARCHAR(200)` |       No | —      | —          | Primary role name, e.g. `Admin`, `Manager`, `Employee` |
| `department_id`           | `VARCHAR(128)` |      Yes | FK     | —          | References `departments.department_id`                 |
| `status`                  | `VARCHAR(32)`  |       No | —      | `'active'` | Account status                                         |
| `created_at`              | `DATETIME`     |       No | —      | —          | Account creation timestamp                             |
| `updated_at`              | `DATETIME`     |       No | —      | —          | Last update timestamp                                  |
| `password_representation` | `VARCHAR(512)` |       No | —      | `''`       | Stored password representation                         |
| `password_changed_at`     | `DATETIME`     |      Yes | —      | —          | Last password-change timestamp                         |
| `must_change_password`    | `BOOLEAN`      |       No | —      | `0`        | Indicates whether password change is required          |
| `employee_id`             | `VARCHAR(64)`  |      Yes | Unique | —          | Employee identifier                                    |
| `first_name`              | `VARCHAR(200)` |      Yes | —      | —          | Employee first name                                    |
| `last_name`               | `VARCHAR(200)` |      Yes | —      | —          | Employee last name                                     |

### Indexes

* `ix_users_username` — UNIQUE
* `ix_users_email` — UNIQUE
* `ix_users_employee_id` — UNIQUE
* `ix_users_department_id`

---

## 3.2 `departments`

Stores company department information.

| Column             | SQLite Type    | Nullable | Key    | Default      | Description                    |
| ------------------ | -------------- | -------: | ------ | ------------ | ------------------------------ |
| `department_id`    | `VARCHAR(128)` |       No | PK     | —            | Unique department identifier   |
| `department_name`  | `VARCHAR(200)` |       No | Unique | —            | Department name                |
| `status`           | `VARCHAR(32)`  |       No | —      | `'active'`   | Department status              |
| `created_at`       | `DATETIME`     |       No | —      | —            | Creation timestamp             |
| `updated_at`       | `DATETIME`     |       No | —      | —            | Last update timestamp          |
| `description`      | `VARCHAR(500)` |      Yes | —      | —            | Department description         |
| `default_billable` | `VARCHAR(32)`  |       No | —      | `'billable'` | Default billing classification |

> **Migration note:** `description` and `default_billable` were added through migration.

---

## 3.3 `projects`

Stores project information associated with departments.

| Column           | SQLite Type    | Nullable | Key                | Default    | Description                            |
| ---------------- | -------------- | -------: | ------------------ | ---------- | -------------------------------------- |
| `id`             | `INTEGER`      |       No | PK / AUTOINCREMENT | —          | Internal database identifier           |
| `project_id`     | `VARCHAR(128)` |       No | Unique             | —          | Business project identifier            |
| `project_name`   | `VARCHAR(200)` |       No | —                  | —          | Project name                           |
| `department_id`  | `VARCHAR(128)` |      Yes | FK                 | —          | References `departments.department_id` |
| `status`         | `VARCHAR(32)`  |       No | —                  | `'active'` | Project status                         |
| `created_at`     | `DATETIME`     |       No | —                  | —          | Creation timestamp                     |
| `updated_at`     | `DATETIME`     |       No | —                  | —          | Last update timestamp                  |
| `description`    | `VARCHAR(500)` |      Yes | —                  | —          | Project description                    |
| `manager_uid`    | `VARCHAR(128)` |      Yes | —                  | —          | Project manager                        |
| `start_date`     | `DATETIME`     |      Yes | —                  | —          | Project start date                     |
| `end_date`       | `DATETIME`     |      Yes | —                  | —          | Project end date                       |
| `created_by_uid` | `VARCHAR(128)` |      Yes | —                  | —          | User who created the project           |

### Indexes

* `ix_projects_project_id` — UNIQUE
* `ix_projects_department_id`

### Migration Behavior

If the legacy `projects` table does not contain the `id` column, it is rebuilt using:

```text
INTEGER PRIMARY KEY AUTOINCREMENT
```

The rebuild is handled by `_rebuild_legacy_table` in `session.py`.

---

## 3.4 `documents`

Stores metadata for documents uploaded into KnowLayer.

| Column              | SQLite Type     | Nullable | Key                | Default    | Description                          |
| ------------------- | --------------- | -------: | ------------------ | ---------- | ------------------------------------ |
| `id`                | `INTEGER`       |       No | PK / AUTOINCREMENT | —          | Internal database identifier         |
| `document_id`       | `VARCHAR(128)`  |       No | Unique             | —          | Business document identifier         |
| `document_name`     | `VARCHAR(255)`  |       No | —                  | —          | Document name                        |
| `project_id`        | `VARCHAR(128)`  |      Yes | FK                 | —          | References `projects.project_id`     |
| `status`            | `VARCHAR(32)`   |       No | —                  | `'active'` | Document status                      |
| `created_at`        | `DATETIME`      |       No | —                  | —          | Creation timestamp                   |
| `updated_at`        | `DATETIME`      |       No | —                  | —          | Last update timestamp                |
| `original_filename` | `VARCHAR(255)`  |      Yes | —                  | —          | Original uploaded filename           |
| `file_type`         | `VARCHAR(32)`   |      Yes | —                  | —          | Document file type                   |
| `description`       | `VARCHAR(500)`  |      Yes | —                  | —          | Document description                 |
| `version`           | `VARCHAR(32)`   |       No | —                  | `'1.0'`    | Document version                     |
| `storage_location`  | `VARCHAR(1024)` |      Yes | —                  | —          | Physical or logical storage location |
| `uploaded_by`       | `VARCHAR(128)`  |      Yes | FK                 | —          | References `users.uid`               |
| `uploaded_at`       | `DATETIME`      |      Yes | —                  | —          | Upload timestamp                     |

### Indexes

* `ix_documents_document_id` — UNIQUE
* `ix_documents_project_id`

### Migration Behavior

Legacy document tables are rebuilt when required, using the same migration approach as the `projects` table.

---

## 3.5 `user_projects`

Junction table representing the many-to-many relationship between users and projects.

| Column            | SQLite Type    | Nullable | Key               | Default    | Description                      |
| ----------------- | -------------- | -------: | ----------------- | ---------- | -------------------------------- |
| `uid`             | `VARCHAR(128)` |       No | Composite PK / FK | —          | References `users.uid`           |
| `project_id`      | `VARCHAR(128)` |       No | Composite PK / FK | —          | References `projects.project_id` |
| `assigned_by_uid` | `VARCHAR(128)` |      Yes | FK                | —          | User who assigned the project    |
| `status`          | `VARCHAR(32)`  |       No | —                 | `'active'` | Membership status                |
| `assigned_at`     | `DATETIME`     |       No | —                 | —          | Assignment timestamp             |
| `membership_role` | `VARCHAR(64)`  |       No | —                 | `'Member'` | User's project membership role   |
| `left_at`         | `DATETIME`     |      Yes | —                 | —          | Timestamp when user left project |

### Constraints

**Composite Primary Key:**

```text
(uid, project_id)
```

**Unique Constraint:**

```text
uq_user_project
```

### Indexes

* `ix_user_projects_uid`
* `ix_user_projects_project_id`

---

## 3.6 `business_id_sequences`

Stores sequence counters used to generate business identifiers.

| Column         | SQLite Type   | Nullable | Key | Default | Description                   |
| -------------- | ------------- | -------: | --- | ------- | ----------------------------- |
| `sequence_key` | `VARCHAR(32)` |       No | PK  | —       | Sequence identifier           |
| `prefix`       | `VARCHAR(64)` |       No | —   | `''`    | Business-ID prefix            |
| `last_value`   | `INTEGER`     |       No | —   | `0`     | Last generated sequence value |
| `updated_at`   | `DATETIME`    |       No | —   | —       | Last update timestamp         |

---

## 3.7 `roles`

Stores RBAC roles. Roles may be global or department-scoped.

| Column           | SQLite Type    | Nullable | Key                | Default    | Description                                       |
| ---------------- | -------------- | -------: | ------------------ | ---------- | ------------------------------------------------- |
| `id`             | `INTEGER`      |       No | PK / AUTOINCREMENT | —          | Internal role identifier                          |
| `name`           | `VARCHAR(100)` |       No | Unique             | —          | Role name                                         |
| `description`    | `VARCHAR(255)` |      Yes | —                  | NULL       | Role description                                  |
| `scope`          | `VARCHAR(32)`  |       No | —                  | `'global'` | `global` or `department`                          |
| `department_id`  | `VARCHAR(128)` |      Yes | FK                 | —          | Associated department for department-scoped roles |
| `status`         | `VARCHAR(32)`  |       No | —                  | `'active'` | Role status                                       |
| `created_by_uid` | `VARCHAR(128)` |      Yes | FK                 | —          | User who created the role                         |
| `created_at`     | `DATETIME`     |       No | —                  | —          | Creation timestamp                                |
| `updated_at`     | `DATETIME`     |       No | —                  | —          | Last update timestamp                             |

### Indexes

* `ix_roles_name` — UNIQUE
* `ix_roles_department_id`

---

## 3.8 `permissions`

Stores the permission catalogue used by the RBAC system.

| Column        | SQLite Type    | Nullable | Key                | Default | Description            |
| ------------- | -------------- | -------: | ------------------ | ------- | ---------------------- |
| `id`          | `INTEGER`      |       No | PK / AUTOINCREMENT | —       | Permission identifier  |
| `name`        | `VARCHAR(150)` |       No | Unique             | —       | Permission name        |
| `description` | `VARCHAR(255)` |      Yes | —                  | NULL    | Permission description |
| `created_at`  | `DATETIME`     |       No | —                  | —       | Creation timestamp     |
| `updated_at`  | `DATETIME`     |       No | —                  | —       | Last update timestamp  |

### Indexes

* `ix_permissions_name` — UNIQUE

---

## 3.9 `role_permissions`

Junction table connecting roles to permissions.

| Column           | SQLite Type    | Nullable | Key               | Default | Description                     |
| ---------------- | -------------- | -------: | ----------------- | ------- | ------------------------------- |
| `role_id`        | `INTEGER`      |       No | Composite PK / FK | —       | References `roles.id`           |
| `permission_id`  | `INTEGER`      |       No | Composite PK / FK | —       | References `permissions.id`     |
| `granted_by_uid` | `VARCHAR(128)` |      Yes | FK                | —       | User who granted the permission |
| `granted_at`     | `DATETIME`     |       No | —                 | —       | Permission grant timestamp      |

### Constraints

**Composite Primary Key:**

```text
(role_id, permission_id)
```

Both foreign keys use:

```text
ON DELETE CASCADE
```

### Indexes

* `ix_role_permissions_permission_id`

---

## 3.10 `department_members`

Junction table representing user-to-department membership.

| Column            | SQLite Type    | Nullable | Key               | Default    | Description                            |
| ----------------- | -------------- | -------: | ----------------- | ---------- | -------------------------------------- |
| `user_id`         | `VARCHAR(128)` |       No | Composite PK / FK | —          | References `users.uid`                 |
| `department_id`   | `VARCHAR(128)` |       No | Composite PK / FK | —          | References `departments.department_id` |
| `membership_role` | `VARCHAR(200)` |       No | —                 | `'Member'` | Membership role                        |
| `assigned_by_uid` | `VARCHAR(128)` |      Yes | FK                | —          | User who assigned membership           |
| `status`          | `VARCHAR(32)`  |       No | —                 | `'active'` | Membership status                      |
| `assigned_at`     | `DATETIME`     |       No | —                 | —          | Assignment timestamp                   |
| `created_at`      | `DATETIME`     |       No | —                 | —          | Creation timestamp                     |
| `updated_at`      | `DATETIME`     |       No | —                 | —          | Last update timestamp                  |
| `billable_status` | `VARCHAR(32)`  |      Yes | —                 | —          | Billing classification                 |
| `left_at`         | `DATETIME`     |      Yes | —                 | —          | Timestamp when membership ended        |

### Constraints

Composite Primary Key:

```text
(user_id, department_id)
```

Foreign keys use:

```text
ON DELETE CASCADE
```

### Indexes

* `ix_department_members_department_id`
* `ix_department_members_user_id`

---

## 3.11 `document_permissions`

Stores document-level access grants for individual users or roles.

| Column           | SQLite Type    | Nullable | Key                | Default    | Description                                    |
| ---------------- | -------------- | -------: | ------------------ | ---------- | ---------------------------------------------- |
| `id`             | `INTEGER`      |       No | PK / AUTOINCREMENT | —          | Permission record identifier                   |
| `document_id`    | `VARCHAR(128)` |       No | FK                 | —          | References `documents.document_id`             |
| `principal_type` | `VARCHAR(12)`  |       No | —                  | —          | `role` or `user`                               |
| `role_id`        | `INTEGER`      |      Yes | FK                 | —          | References `roles.id`                          |
| `user_id`        | `VARCHAR(128)` |      Yes | FK                 | —          | References `users.uid`                         |
| `permission`     | `VARCHAR(32)`  |       No | —                  | —          | Permission such as `view`, `edit`, or `manage` |
| `granted_by_uid` | `VARCHAR(128)` |      Yes | FK                 | —          | User who granted access                        |
| `status`         | `VARCHAR(32)`  |       No | —                  | `'active'` | Permission status                              |
| `created_at`     | `DATETIME`     |       No | —                  | —          | Creation timestamp                             |
| `updated_at`     | `DATETIME`     |       No | —                  | —          | Last update timestamp                          |

### Constraints

**Unique Constraint:**

```text
UNIQUE (
    document_id,
    principal_type,
    role_id,
    user_id,
    permission
)
```

Constraint name:

```text
uq_document_permission
```

**Principal Constraint:**

```text
principal_type IN ('role', 'user')
```

Exactly one of `role_id` or `user_id` must be populated.

### Indexes

* `ix_document_permissions_document_id`
* `ix_document_permissions_role_id`
* `ix_document_permissions_user_id`

Foreign keys use:

```text
ON DELETE CASCADE
```

---

## 3.12 `project_grants`

Stores project-level access grants for individual users or roles.

| Column           | SQLite Type    | Nullable | Key                | Default    | Description                      |
| ---------------- | -------------- | -------: | ------------------ | ---------- | -------------------------------- |
| `id`             | `INTEGER`      |       No | PK / AUTOINCREMENT | —          | Grant identifier                 |
| `project_id`     | `VARCHAR(128)` |       No | FK                 | —          | References `projects.project_id` |
| `principal_type` | `VARCHAR(12)`  |       No | —                  | —          | `role` or `user`                 |
| `role_id`        | `INTEGER`      |      Yes | FK                 | —          | References `roles.id`            |
| `user_id`        | `VARCHAR(128)` |      Yes | FK                 | —          | References `users.uid`           |
| `granted_by_uid` | `VARCHAR(128)` |      Yes | FK                 | —          | User who granted access          |
| `status`         | `VARCHAR(32)`  |       No | —                  | `'active'` | Grant status                     |
| `granted_at`     | `DATETIME`     |       No | —                  | —          | Grant timestamp                  |

### Constraints

**Unique Constraint:**

```text
UNIQUE (
    project_id,
    principal_type,
    role_id,
    user_id
)
```

Constraint name:

```text
uq_project_grant
```

**Principal Constraint:**

```text
principal_type IN ('role', 'user')
```

Exactly one of `role_id` or `user_id` must be populated.

### Indexes

* `ix_project_grants_project_id`
* `ix_project_grants_role_id`
* `ix_project_grants_user_id`

Foreign keys use:

```text
ON DELETE CASCADE
```

---

# 4. Database Relationships

The major relationships between the tables are shown below.

```text
departments
    │
    ├─────────────── 1:N ─────────────── users
    │                                      │
    │                                      │
    ├─────────────── 1:N ─────────────── projects
    │                                      │
    │                                      ├──────── 1:N ─────── documents
    │                                      │
    │                                      ├──────── 1:N ─────── project_grants
    │                                      │
    │                                      └──────── N:M ─────── users
    │                                                   │
    │                                                   │
    ├─────────────── 1:N ─────────────── roles          │
    │                                      │             │
    │                                      │             │
    │                                      └──── N:M ─── permissions
    │
    └─────────────── N:M ─────────────── users
```

### Relationship Details

| Parent        | Child                  | Relationship | Purpose                                        |
| ------------- | ---------------------- | ------------ | ---------------------------------------------- |
| `departments` | `users`                | 1:N          | A department can contain multiple users        |
| `departments` | `projects`             | 1:N          | A department can contain multiple projects     |
| `departments` | `roles`                | 1:N          | Department-scoped roles belong to a department |
| `projects`    | `documents`            | 1:N          | A project can contain multiple documents       |
| `projects`    | `user_projects`        | 1:N          | Associates projects with users                 |
| `users`       | `user_projects`        | 1:N          | Associates users with projects                 |
| `projects`    | `project_grants`       | 1:N          | Defines project-level access                   |
| `documents`   | `document_permissions` | 1:N          | Defines document-level access                  |
| `users`       | `department_members`   | 1:N          | Associates users with departments              |
| `departments` | `department_members`   | 1:N          | Associates departments with users              |
| `roles`       | `role_permissions`     | 1:N          | Associates roles with permissions              |
| `permissions` | `role_permissions`     | 1:N          | Associates permissions with roles              |

---

# 5. Access-Control Structure

KnowLayer implements access control at multiple levels:

### Role-Based Access

```text
Role
  │
  └── Role Permissions
          │
          └── Permission
```

Roles can be global or department-scoped.

### Project-Level Access

```text
Project
   │
   └── Project Grant
          │
          ├── User
          └── Role
```

A project can therefore be granted to either a specific user or a role.

### Document-Level Access

```text
Document
    │
    └── Document Permission
            │
            ├── User
            └── Role
```

Document permissions additionally specify the permission level, such as:

```text
view
edit
manage
```

---

# 6. Startup and Migration Behavior

When KnowLayer starts, the database initialization process performs the following operations.

### Step 1 — Create Tables

`Base.metadata.create_all()` idempotently creates the required 12 tables.

### Step 2 — Add Missing Legacy Columns

The migration process checks for missing columns and adds them using:

```sql
ALTER TABLE ... ADD COLUMN
```

### Step 3 — Backfill Legacy Data

Existing users with an empty username are updated using:

```sql
UPDATE users
SET username = uid
WHERE username = '';
```

### Step 4 — Create or Repair Indexes

Required indexes are created when they are missing.

### Step 5 — Rebuild Legacy Tables

If the legacy `projects` or `documents` table does not contain the required `id` column, the table is rebuilt.

The rebuilt structure uses:

```text
INTEGER PRIMARY KEY AUTOINCREMENT
```

This allows older database structures to transition to the current ORM model.

---

# 7. Seed Data

The following foundational data is inserted during application startup:

* Permissions
* Roles
* Default `Admin` user

This seed data is managed by the application's permission catalogue rather than by static SQL DDL scripts.

---

# 8. Summary

The KnowLayer SQLite schema consists of **12 tables** supporting:

* User and employee management
* Department management
* Project management
* Document management
* Project membership
* Department membership
* Role-based access control
* Permission management
* Project-level authorization
* Document-level authorization
* Business-ID generation
* Database migration and backward compatibility

The access-control model supports both **role-based and user-specific permissions**, allowing access to be controlled at the project and document levels.
