# Feature Specification: Organization Access and User Management

**Feature Branch**: `002-sql-user-management`

**Created**: 2026-09-10

**Status**: Draft

**Input**: User description: "Integrate the corrected ERD with the existing project. A department has multiple employees and multiple projects. A user can belong to multiple projects and a project can contain multiple users. Admin and Manager are special key roles, while other organizational roles are dynamic and without restricting future organizational roles."

## Clarifications

### Session 2026-09-10

- Q: When a user does not select a project, should the system search across all projects the user is authorized to access, while allowing the UI to optionally restrict the search to one selected project? → A: Optional project selection; without one, search all projects the user is authorized to access.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Administrators manage organizational users (Priority: P1)

An administrator can create, view, update, deactivate, and delete user accounts with a free-form organizational role value. The system stores the user and department relationship so the account can participate in project access checks.

**Independent Test**: An admin creates a user with a new role value and department, then reads the account back from the system.

**Acceptance Scenarios**:

1. **Given** an authenticated admin, **When** they provide a valid UID, name, email, role, and department, **Then** the user account is created and available in the system.
2. **Given** an admin provides a duplicate UID or email, **When** they create the user, **Then** the system returns a conflict without a partial record.
3. **Given** an admin provides an invalid email or unknown department, **When** they create the user, **Then** the system returns a validation error.

### User Story 2 - Managers manage users in their scope (Priority: P1)

Managers can manage users within their authorized department scope. Administrators can manage users across the organization. The organization can add roles such as Developer, Tester, or Solution Architect without changing the role model.

**Independent Test**: A manager successfully updates a user in the same department and is denied when targeting a user in another department.

**Acceptance Scenarios**:

1. **Given** an authenticated manager and a target user in the manager's department, **When** the manager updates permitted fields, **Then** the change is saved completely or not applied.
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

Before answering a question, the system evaluates the authenticated user's project memberships. Project selection in the user interface is optional. Without a selected project, the system searches across all projects the user is authorized to access; with a selected project, it searches only that authorized project. Dynamic roles do not grant project access by themselves; access is derived from project membership and the actor's special admin or manager scope.

**Independent Test**: A user receives information only from authorized projects when no project is selected, and selecting one authorized project narrows the search while selecting an unauthorized project is denied before disclosing restricted information.

**Acceptance Scenarios**:

1. **Given** a user is assigned to Project A, **When** they ask a question scoped to Project A, **Then** only Project A evidence is eligible.
2. **Given** a user is not assigned to Project B, **When** they request Project B directly or through chat, **Then** the system returns access denied and does not disclose Project B information.
3. **Given** a user has multiple project assignments and does not select a project, **When** they ask a question, **Then** information from all assigned projects may be returned.
4. **Given** a user selects an authorized project, **When** they ask a question, **Then** only information from that project is eligible.

### User Story 5 - Admin has special troubleshooting access (Priority: P2)

Admin is a special system-level role value used by authorized developers for troubleshooting. Admin can access all departments, users, projects, memberships, and project questions.

**Independent Test**: An authenticated admin reads and modifies records across departments and accesses every project without being individually assigned to each project.

**Acceptance Scenarios**:

1. **Given** a developer has authenticated admin credentials, **When** they log in, **Then** they have access to all projects and users without project restrictions.
2. **Given** the admin attempts to view or modify any user or project, **When** the operation is valid, **Then** it succeeds without scope errors.

## Edge Cases

- Authorization for a new request uses the current persisted user role, department, status, and memberships after a mid-session change.
- A user assigned to no projects receives an empty authorized project set and no project evidence.
- Moving a project to another department revalidates affected manager operations before access changes.
- If a save operation fails, no partial user or membership change is applied and the user receives a clear error.
- Deactivating or deleting a user removes or disables their project assignments while preserving the projects.

## Goals

- Provide persistent management of users, departments, projects, and project assignments.
- Ensure users can only access questions from projects they are explicitly assigned to.
- Support flexible role values without requiring a predefined list of organizational roles.
- Allow administrators organization-wide access and managers scoped organizational access.

## Key Entities and Relationships

### User

Attributes: UID, name, email, role, department, and status.

A user belongs to one department and may belong to many projects.

### Department

Attributes: department ID and department name.

A department may have many users and many projects.

### Project

Attributes: project ID, project name, department, and status.

A project belongs to one department, may contain many users, and may contain many documents.

### Document

Attributes: document ID, document name, project, and status.

A document may be created before it is assigned to a project. Once assigned, it belongs to one project. A project may contain zero, one, or many documents.

### Participation Rules

- User-to-Department: a user must belong to a department; a department may exist without users.
- Department-to-Project: a project must belong to a department; a department may exist without projects.
- User-to-Project: participation is many-to-many; a user or project may exist without a current membership.
- Project-to-Document: participation is one-to-many and partial; a project may exist without documents, and a document may exist temporarily without a project assignment.
- A document without a project assignment must not be used to answer a project-scoped question.
## Non-Goals

- Implementing a specific frontend UI framework or design language.
- Building a complete authentication system from scratch; existing authentication supplies an authenticated principal.
- Supporting social login or third-party identity providers in MVP.
- Creating a full-featured enterprise permission system or separate Role/Permission entities.
- Implementing advanced search or filtering beyond project-based access control.
- Adding multi-factor authentication or password complexity rules.

## Requirements *(mandatory)*

### Functional Requirements

1. **User and Department Management**: Admins can create, read, update, deactivate, and delete users and departments while preserving valid relationships.
2. **Flexible Roles**: User role is required and can contain any organization-defined value; adding a new role must not require redesigning the role model.
3. **Project Management**: Admins can create, read, update, and archive projects associated with a department.
4. **Project Membership**: Users and projects have a many-to-many relationship with unique assignments and complete, reliable updates.
5. **Document Management**: Authorized administrators and managers can create, view, update, assign, and remove documents; a project can contain multiple documents, and unassigned documents cannot be used for project-scoped answers.
6. **Scoped Management**: Managers can manage users and memberships only within their authorized department scope.
7. **Project Question Access**: Authorization is evaluated before answering, and users receive information only for assigned projects.
8. **Admin Elevated Privileges**: The admin role value grants organization-wide access for approved troubleshooting.

### Non-Functional Requirements

1. **Performance**: User lookup and project authorization should complete in under 100ms for typical workloads.
2. **Security**: Authentication credentials remain outside this feature; passwords and access tokens are not exposed by this feature.
3. **Scalability**: The system supports the expected initial organization size and can grow without changing the organizational concepts.
4. **Reliability**: Changes preserve valid relationships and do not leave partial updates.

### Assumptions

- Existing authentication provides user login and an authenticated user identifier.
- The system can identify the authenticated user for each request.
- `Admin` and `Manager` are special role values; all other role values are organization-defined strings.
- A department contains users and projects.
- Project assignments are managed as a distinct relationship between users and projects; roles remain user attributes rather than a fixed catalog.
- Project questions can be associated with their project so access can be evaluated.
- Project selection is optional; an omitted selection means all currently authorized projects, while a selected project narrows the authorized scope.
- Documents may be managed independently before being assigned to a project.

## Success Criteria

- [ ] Admin can manage users, departments, projects, memberships, and documents.
- [ ] Managers are restricted to their authorized department scope.
- [ ] Dynamic role values can be added without redesigning the role model.
- [ ] Regular users can only access questions from assigned projects.
- [ ] Projects can contain multiple documents, with partial participation on the Project-Document relationship.
- [ ] Admin has unrestricted access for troubleshooting.

- [ ] Authorization checks complete within performance targets.
- [ ] The specification contains no unresolved clarification items.

