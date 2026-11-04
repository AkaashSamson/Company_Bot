# Data Model: SQL Organization Access

## Scope

This model implements the corrected ERD. `Role` and `Permission` are not entities or tables. Role is a flexible User attribute; authorization rules are domain behavior.

## Entities

### User
Represents an authenticated organization member.

Fields:
- `uid`: string, primary key, immutable external identity key
- `username`: string, required, unique login identifier
- `name`: string, required
- `email`: string, required, unique, normalized for comparison
- `role`: string, required, non-empty, case-normalized for special-role checks but preserved for display
- `department_id`: foreign key to Department, required
- `status`: enum `active` or `inactive`, default `active`
- `password_representation`: secure password hash or equivalent representation; plaintext passwords are never persisted
- `password_changed_at`: timestamp for password-change tracking
- `created_at`: timestamp
- `updated_at`: timestamp

Rules:
- `Admin` and `Manager` are special role values; any other non-empty organization-defined value is valid.
- One Admin account is pre-seeded with an initial username and password supplied through secure configuration or deployment setup.
- Admin-created users receive an initial password and can change their own password; Admin can change a user's password.
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

### Document
Represents a document that may be assigned to a project and used as authorized source material.

Fields:
- `document_id`: string or UUID, primary key
- `document_name`: string, required
- `project_id`: foreign key to Project, nullable while unassigned
- `status`: enum `active`, `inactive`, or `archived`
- `created_at`: timestamp
- `updated_at`: timestamp

Rules:
- A project may contain zero, one, or many documents.
- A document may temporarily have no project assignment.
- An unassigned or inactive document is excluded from project-scoped retrieval.

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

## Relationships

- Department 1-to-many User.
- Department 1-to-many Project.
- Project 1-to-many Document with partial participation on both sides.
- User many-to-many Project through UserProject.
- Project identity is propagated into document/vector metadata so retrieval can apply authorized project filters.

## Authorization rules

1. Load the current active User from the authenticated UID.
2. If role is `Admin`, all active projects are authorized.
3. If role is `Manager`, management targets are authorized only inside the Manager's department; question retrieval still uses explicit active memberships unless the product later approves broader manager read access.
4. Other role values receive only active projects in UserProject.
5. Missing, inactive, or unknown principals receive no project IDs and cannot retrieve restricted evidence.
6. If no project is selected, authorize all active projects assigned to the user; if a project is selected, authorize only that project after intersecting it with the user's allowed project set.
7. Authorization executes before vector-store retrieval and before answer generation.

## Authentication rules

1. Login accepts a username and password and returns the authenticated principal through the configured session or token boundary.
2. The pre-seeded Admin must be able to log in during initial setup and should change the configured default password before normal administration.
3. Admin-created users, including Managers, can log in with their initial passwords after account creation.
4. Password changes replace the stored secure password representation and apply to subsequent login attempts.
