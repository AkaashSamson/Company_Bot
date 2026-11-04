# KnowLayer SQLite Database ERD

This is the complete entity-relationship view of the application SQLite database at `instance/knowlayer.db`.

- **12 application tables** are shown below.
- `sqlite_sequence` is an internal SQLite table created for `AUTOINCREMENT` and is intentionally omitted.
- Solid relationship lines represent declared SQLite foreign keys.
- Dashed lines represent application-level references that are stored as IDs but are not declared foreign keys.
- `PK` = primary key, `FK` = foreign key, `UK` = unique key, `NN` = not null.
- Conversation history is stored as JSON files under `conversation_logs/`; it is not part of this SQLite schema.

## Complete ER Diagram

```mermaid
erDiagram
    DEPARTMENTS {
        string department_id PK
        string department_name UK
        string status
        datetime created_at
        datetime updated_at
        string description
        string default_billable
    }

    USERS {
        string uid PK
        string username UK
        string name
        string email UK
        string role
        string department_id FK
        string status
        datetime created_at
        datetime updated_at
        string password_representation
        datetime password_changed_at
        boolean must_change_password
        string employee_id UK
        string first_name
        string last_name
    }

    PROJECTS {
        integer id PK
        string project_id UK
        string project_name
        string department_id FK
        string status
        datetime created_at
        datetime updated_at
        string description
        string manager_uid
        datetime start_date
        datetime end_date
        string created_by_uid
    }

    DOCUMENTS {
        integer id PK
        string document_id UK
        string document_name
        string project_id FK
        string status
        datetime created_at
        datetime updated_at
        string original_filename
        string file_type
        string description
        string version
        string storage_location
        string uploaded_by FK
        datetime uploaded_at
    }

    USER_PROJECTS {
        string uid PK, FK
        string project_id PK, FK
        string assigned_by_uid FK
        string status
        datetime assigned_at
        string membership_role
        datetime left_at
    }

    BUSINESS_ID_SEQUENCES {
        string sequence_key PK
        string prefix
        integer last_value
        datetime updated_at
    }

    ROLES {
        integer id PK
        string name UK
        string description
        string scope
        string department_id FK
        string status
        string created_by_uid FK
        datetime created_at
        datetime updated_at
    }

    PERMISSIONS {
        integer id PK
        string name UK
        string description
        datetime created_at
        datetime updated_at
    }

    ROLE_PERMISSIONS {
        integer role_id PK, FK
        integer permission_id PK, FK
        string granted_by_uid FK
        datetime granted_at
    }

    DEPARTMENT_MEMBERS {
        string user_id PK, FK
        string department_id PK, FK
        string membership_role
        string assigned_by_uid FK
        string status
        datetime assigned_at
        datetime created_at
        datetime updated_at
        string billable_status
        datetime left_at
    }

    DOCUMENT_PERMISSIONS {
        integer id PK
        string document_id FK
        string principal_type
        integer role_id FK
        string user_id FK
        string permission
        string granted_by_uid FK
        string status
        datetime created_at
        datetime updated_at
    }

    PROJECT_GRANTS {
        integer id PK
        string project_id FK
        string principal_type
        integer role_id FK
        string user_id FK
        string granted_by_uid FK
        string status
        datetime granted_at
    }

    DEPARTMENTS ||--o{ USERS : contains
    DEPARTMENTS ||--o{ PROJECTS : owns
    DEPARTMENTS ||--o{ ROLES : scopes
    DEPARTMENTS ||--o{ DEPARTMENT_MEMBERS : has
    USERS ||--o{ USER_PROJECTS : assigned_to
    PROJECTS ||--o{ USER_PROJECTS : includes
    PROJECTS ||--o{ DOCUMENTS : contains
    USERS ||--o{ DOCUMENTS : uploads
    ROLES ||--o{ ROLE_PERMISSIONS : receives
    PERMISSIONS ||--o{ ROLE_PERMISSIONS : grants
    USERS ||--o{ ROLE_PERMISSIONS : grants
    USERS ||--o{ DEPARTMENT_MEMBERS : belongs_to
    USERS ||--o{ DEPARTMENT_MEMBERS : assigns
    USERS ||--o{ USER_PROJECTS : assigns
    DOCUMENTS ||--o{ DOCUMENT_PERMISSIONS : protects
    ROLES ||--o{ DOCUMENT_PERMISSIONS : targets
    USERS ||--o{ DOCUMENT_PERMISSIONS : targets
    USERS ||--o{ DOCUMENT_PERMISSIONS : grants
    PROJECTS ||--o{ PROJECT_GRANTS : protects
    ROLES ||--o{ PROJECT_GRANTS : targets
    USERS ||--o{ PROJECT_GRANTS : targets
    USERS ||--o{ PROJECT_GRANTS : grants
    USERS ||--o{ ROLES : creates

    USERS ||..o{ PROJECTS : manages_logically
    USERS ||..o{ PROJECTS : creates_logically
```

## Relationship Inventory

| Parent          | Child                    | FK column                               | Cardinality  | Delete behavior | Notes                                      |
| --------------- | ------------------------ | --------------------------------------- | ------------ | --------------- | ------------------------------------------ |
| `departments` | `users`                | `users.department_id`                 | 1 to 0..N    | default         | Primary department on a user.              |
| `departments` | `projects`             | `projects.department_id`              | 1 to 0..N    | default         | Project department.                        |
| `departments` | `roles`                | `roles.department_id`                 | 1 to 0..N    | default         | Used for department-scoped roles.          |
| `departments` | `department_members`   | `department_members.department_id`    | 1 to 0..N    | `CASCADE`     | Department membership junction.            |
| `users`       | `department_members`   | `department_members.user_id`          | 1 to 0..N    | `CASCADE`     | User membership junction.                  |
| `users`       | `user_projects`        | `user_projects.uid`                   | 1 to 0..N    | default         | Project membership junction.               |
| `projects`    | `user_projects`        | `user_projects.project_id`            | 1 to 0..N    | default         | Project membership junction.               |
| `projects`    | `documents`            | `documents.project_id`                | 1 to 0..N    | default         | Nullable: documents may be unassigned.     |
| `users`       | `documents`            | `documents.uploaded_by`               | 1 to 0..N    | default         | Nullable uploader audit reference.         |
| `roles`       | `role_permissions`     | `role_permissions.role_id`            | 1 to 0..N    | `CASCADE`     | RBAC junction.                             |
| `permissions` | `role_permissions`     | `role_permissions.permission_id`      | 1 to 0..N    | `CASCADE`     | RBAC junction.                             |
| `users`       | `role_permissions`     | `role_permissions.granted_by_uid`     | 1 to 0..N    | default         | Nullable audit reference.                  |
| `documents`   | `document_permissions` | `document_permissions.document_id`    | 1 to 0..N    | `CASCADE`     | Document access grants.                    |
| `roles`       | `document_permissions` | `document_permissions.role_id`        | 1 to 0..N    | `CASCADE`     | Used only when`principal_type = 'role'`. |
| `users`       | `document_permissions` | `document_permissions.user_id`        | 1 to 0..N    | `CASCADE`     | Used only when`principal_type = 'user'`. |
| `users`       | `document_permissions` | `document_permissions.granted_by_uid` | 1 to 0..N    | default         | Nullable audit reference.                  |
| `projects`    | `project_grants`       | `project_grants.project_id`           | 1 to 0..N    | `CASCADE`     | Project access grants.                     |
| `roles`       | `project_grants`       | `project_grants.role_id`              | 1 to 0..N    | `CASCADE`     | Used only when`principal_type = 'role'`. |
| `users`       | `project_grants`       | `project_grants.user_id`              | 1 to 0..N    | `CASCADE`     | Used only when`principal_type = 'user'`. |
| `users`       | `project_grants`       | `project_grants.granted_by_uid`       | 1 to 0..N    | default         | Nullable audit reference.                  |
| `users`       | `roles`                | `roles.created_by_uid`                | 1 to 0..N    | default         | Nullable audit reference.                  |
| `users`       | `projects`             | `projects.manager_uid`                | logical only | n/a             | Stored ID; no declared FK in current ORM.  |
| `users`       | `projects`             | `projects.created_by_uid`             | logical only | n/a             | Stored ID; no declared FK in current ORM.  |

## Table Constraints

- `user_projects` has composite primary key `(uid, project_id)` and `uq_user_project`.
- `department_members` has composite primary key `(user_id, department_id)`.
- `role_permissions` has composite primary key `(role_id, permission_id)`.
- `document_permissions` has `uq_document_permission` over `(document_id, principal_type, role_id, user_id, permission)`.
- `project_grants` has `uq_project_grant` over `(project_id, principal_type, role_id, user_id)`.
- `document_permissions` and `project_grants` require `principal_type` to be `role` or `user`, with exactly one of `role_id` and `user_id` populated.
- The application enables `PRAGMA foreign_keys=ON` on SQLAlchemy SQLite connections. A standalone SQLite connection defaults to reporting `PRAGMA foreign_keys=0` unless it enables the pragma itself.

## Non-SQLite Persistence

Conversation records are written separately as employee-scoped JSON files in `conversation_logs/`. They have no database foreign keys and are intentionally outside this ERD. Chroma stores vector retrieval data separately from SQLite as well.
