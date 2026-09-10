# Feature Specification: SQL Organization Access and User Management

**Feature Branch**: `002-sql-user-management`

**Created**: 2026-09-10

**Status**: Draft

**Input**: User description: "Integrate the corrected ERD with the existing project. A department has multiple employees and multiple projects. A user can belong to multiple projects and a project can contain multiple users. Admin and Manager are special key roles, while other organizational roles are dynamic and must not require a schema redesign."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Administrators manage organizational users (Priority: P1)

An administrator can create, view, update, deactivate, and delete user accounts with a free-form organizational role value. The system stores the user and department relationship so the account can participate in project access checks.

**Independent Test**: An admin creates a user with a new role value and department, then reads the persisted record back from SQL.

**Acceptance Scenarios**:

1. **Given** an authenticated admin, **When** they provide a valid UID, name, email, role, and department, **Then** the user persists in SQL.
2. **Given** an admin provides a duplicate UID or email, **When** they create the user, **Then** the system returns a conflict without a partial record.
3. **Given** an admin provides an invalid email or unknown department, **When** they create the user, **Then** the system returns a validation error.

### User Story 2 - Managers manage users in their scope (Priority: P1)

Managers can manage users within their authorized department scope. Administrators can manage users across the organization. Role values remain open text so a company can add roles such as Developer, Tester, or Solution Architect without a migration.

**Independent Test**: A manager successfully updates a user in the same department and is denied when targeting a user in another department.

**Acceptance Scenarios**:

1. **Given** an authenticated manager and a target user in the manager's department, **When** the manager updates permitted fields, **Then** the change is persisted atomically.
2. **Given** a manager targets a user outside their department, **When** they update or delete the user, **Then** the system denies the action.
3. **Given** an administrator changes a user's role, department, email, or status, **When** the change is saved, **Then** it is effective for subsequent authorization checks.

### User Story 3 - Administrators and managers manage project membership (Priority: P1)

Administrators can assign users to projects across the organization. Managers can assign users only within their department scope. A user may belong to many projects, and each project may contain many users.

**Independent Test**: An authorized actor adds and removes a project membership and the relationship is visible from both user and project queries.

**Acceptance Scenarios**:

1. **Given** an authorized manager or admin, **When** they add a user to a project in scope, **Then** the membership persists.
2. **Given** a user is already assigned to a project, **When** the same assignment is submitted, **Then** the operation is idempotent and creates no duplicate.
3. **Given** an unauthorized actor targets a project outside their scope, **When** they change membership, **Then** the system denies the operation.

### User Story 4 - Users can access only assigned project questions (Priority: P1)

The chat and question retrieval path evaluates the authenticated user's project memberships before retrieving evidence. Dynamic roles do not grant project access by themselves; access is derived from project membership and the actor's special admin or manager scope.

**Independent Test**: A user assigned to Project A receives only Project A evidence, while a request for Project B is denied before restricted retrieval.

**Acceptance Scenarios**:

1. **Given** a user is assigned to Project A, **When** they ask a question scoped to Project A, **Then** only Project A evidence is eligible.
2. **Given** a user is not assigned to Project B, **When** they request Project B directly or through chat, **Then** the system returns access denied and performs no restricted retrieval.
3. **Given** a user has multiple project assignments, **When** they ask a question spanning those projects, **Then** evidence from all assigned projects may be returned.

### User Story 5 - Admin has special troubleshooting access (Priority: P2)

Admin is a special system-level role value used by authorized developers for troubleshooting. Admin can access all departments, users, projects, memberships, and project questions.

**Independent Test**: An authenticated admin reads and modifies records across departments and accesses every project without explicit memberships.

**Acceptance Scenarios**:

1. **Given** a developer has authenticated admin credentials, **When** they log in, **Then** they have access to all projects and users without project restrictions.
2. **Given** the admin attempts to view or modify any user or project, **When** the operation is valid, **Then** it succeeds without scope errors.

### User Story 6 - Developers can audit access-management changes (Priority: P2)

Developers can review structured audit records for user, department, project, and membership changes without exposing secrets.

**Independent Test**: Perform a CRUD or membership operation and verify that actor, action, target, timestamp, and outcome are recorded.

**Acceptance Scenarios**:

1. **Given** a management operation completes, **When** its transaction commits, **Then** one audit record is stored with actor and target identifiers.
2. **Given** an authorization check denies an operation, **When** the request completes, **Then** the denial is auditable without passwords or tokens.

## Edge Cases

- Authorization for a new request uses the current persisted user role, department, status, and memberships after a mid-session change.
- A user assigned to no projects receives an empty authorized project set and no project evidence.
- Moving a project to another department revalidates affected manager operations before access changes.
- A database connection failure rolls back the current CRUD or membership transaction and returns an operational error.
- Deactivating or deleting a user removes or disables memberships transactionally while preserving project and document data.

## Goals

- Provide SQL-backed user, department, project, and project-membership management.
- Ensure users can only access questions from projects they are explicitly assigned to.
- Support flexible role values without a fixed Role or Permission table.
- Allow administrators organization-wide access and managers scoped organizational access.
- Maintain audit logs of access-management actions for compliance and debugging.

## Non-Goals

- Implementing a specific frontend UI framework or design language.
- Building a complete authentication system from scratch; existing authentication supplies an authenticated principal.
- Supporting social login or third-party identity providers in MVP.
- Creating a full-featured enterprise permission system or separate Role/Permission entities.
- Implementing advanced search or filtering beyond project-based access control.
- Adding multi-factor authentication or password complexity rules.

## Requirements *(mandatory)*

### Functional Requirements

1. **User and Department Management**: Admins can create, read, update, deactivate, and delete users and departments with referential integrity.
2. **Flexible Roles**: User role is a validated non-empty string; adding a new role requires no schema redesign or code deployment.
3. **Project Management**: Admins can create, read, update, and archive projects associated with a department.
4. **Project Membership**: Users and projects have a many-to-many relationship with unique assignments and transactional updates.
5. **Scoped Management**: Managers can manage users and memberships only within their authorized department scope.
6. **Project Question Access**: Authorization is evaluated before retrieval, and users receive evidence only for assigned projects.
7. **Admin Elevated Privileges**: The admin role value grants organization-wide access for approved troubleshooting.
8. **Audit Logging**: User, department, project, membership, and denied authorization operations are logged with timestamp, actor, target, and outcome.

### Non-Functional Requirements

1. **Performance**: User lookup and project authorization should complete in under 100ms for typical workloads.
2. **Security**: Authentication credentials remain outside this feature; no passwords or tokens are stored by these domain tables or logs.
3. **Scalability**: SQLite supports up to ~100 concurrent users; the design can scale to PostgreSQL later without schema changes.
4. **Reliability**: SQLite operations are atomic and maintain referential and uniqueness constraints via foreign keys and constraints.

### Assumptions

- Existing authentication provides user login and an authenticated user identifier.
- The SQL adapter targets SQLite dialect while keeping domain ports database-agnostic.
- `Admin` and `Manager` are special role values; all other role values are organization-defined strings.
- A department contains users and projects.
- Project assignments use an associative user-project relationship with a uniqueness constraint; Role and Permission are not entities/tables.
- Existing chat evidence can be associated with a project identifier for authorization filtering.

## Success Criteria

- [ ] Admin can manage users, departments, projects, and memberships.
- [ ] Managers are restricted to their authorized department scope.
- [ ] Dynamic role values can be added without schema changes.
- [ ] Regular users can only access questions from assigned projects.
- [ ] Admin has unrestricted access for troubleshooting.
- [ ] All access-management operations are logged.
- [ ] Authorization checks complete within performance targets.
- [ ] The specification contains no unresolved clarification items.

