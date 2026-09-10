# Data Model: SQL Organization Access

## Scope

This model implements the corrected ERD. `Role` and `Permission` are not entities or tables. Role is a flexible User attribute; authorization rules are domain behavior.

## Entities

### User
Represents an authenticated organization member.

Fields:
- `uid`: string, primary key, immutable external identity key
- `name`: string, required
- `email`: string, required, unique, normalized for comparison
- `role`: string, required, non-empty, case-normalized for special-role checks but preserved for display
- `department_id`: foreign key to Department, required
- `status`: enum `active` or `inactive`, default `active`
- `created_at`: timestamp
- `updated_at`: timestamp

Rules:
- `Admin` and `Manager` are special role values; any other non-empty organization-defined value is valid.
- Inactive users cannot manage records or retrieve project evidence.

### Department
Represents an organizational department.

Fields:
- `department_id`: string or UUID, primary key
- `department_name`: string, required, unique
- `status`: enum `active` or `inactive`
- `created_at`: timestamp
- `updated_at`: timestamp

Rules:
- A department may have many users and many projects.
- Deactivation must not orphan users or projects; reassignment or an explicit blocked operation is required.

### Project
Represents a project managed by one department and used to scope questions/evidence.

Fields:
- `project_id`: string or UUID, primary key
- `project_name`: string, required
- `department_id`: foreign key to Department, required
- `status`: enum `active` or `archived`
- `created_at`: timestamp
- `updated_at`: timestamp

Rules:
- A department may contain many projects.
- Archived projects are excluded from new access and retrieval.

### UserProject (associative relationship)
Represents explicit membership between a user and a project. It is a database relationship table, not a new business entity in the ERD.

Fields:
- `uid`: foreign key to User
- `project_id`: foreign key to Project
- `assigned_at`: timestamp
- `assigned_by_uid`: foreign key to User, nullable only for migration/bootstrap data
- `status`: enum `active` or `revoked`

Constraints:
- Composite primary key or unique constraint on (`uid`, `project_id`).
- Foreign keys use deliberate delete behavior; revoking/deactivating membership must not delete project data.

### AuditEvent
Represents a security and administration audit record.

Fields:
- `event_id`: UUID, primary key
- `actor_uid`: authenticated actor identifier
- `action`: controlled application action string
- `target_type`: `user`, `department`, `project`, `membership`, or `retrieval`
- `target_id`: string
- `outcome`: `success` or `denied`
- `occurred_at`: timestamp
- `metadata`: structured non-secret metadata

Rules:
- Never store passwords, access tokens, API keys, or unrestricted document text.
- Denied operations are recorded without revealing restricted record details to the caller.

## Relationships

- Department 1-to-many User.
- Department 1-to-many Project.
- User many-to-many Project through UserProject.
- User 1-to-many AuditEvent as actor.
- Project identity is propagated into document/vector metadata so retrieval can apply authorized project filters.

## Authorization rules

1. Load the current active User from the authenticated UID.
2. If role is `Admin`, all active projects are authorized.
3. If role is `Manager`, management targets are authorized only inside the Manager's department; question retrieval still uses explicit active memberships unless the product later approves broader manager read access.
4. Other role values receive only active projects in UserProject.
5. Missing, inactive, or unknown principals receive no project IDs and cannot retrieve restricted evidence.
6. Authorization executes before vector-store retrieval and before answer generation.
