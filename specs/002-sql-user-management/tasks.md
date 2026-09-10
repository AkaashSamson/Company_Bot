# Tasks: Organization Access and User Management

**Input**: Design documents from `/specs/002-sql-user-management/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/user-management-api.md](./contracts/user-management-api.md), [quickstart.md](./quickstart.md)

**Organization**: Tasks are grouped by user story. All tasks use the existing modular monolith, one FastAPI application, and Streamlit as an HTTP client.

## Phase 1: Setup

**Purpose**: Establish dependencies, configuration, and directories for the database-agnostic organization feature.

- [X] T001 Add SQLAlchemy and migration dependencies to `requirements.txt` and document the initial SQLite database URL in `.env.example`
- [X] T002 [P] Create the planned persistence, organization use-case, API, Streamlit page, and test directories under `app/`, `streamlit_app/`, and `tests/`
- [X] T003 [P] Add organization and database settings to `app/core/settings.py`, including the configurable relational database URL and Streamlit API base URL
- [X] T004 [P] Add the organization feature configuration and local SQLite instance path to `README.md`

---

## Phase 2: Foundational

**Purpose**: Implement the boundaries that every user story depends on. No story work should begin until this phase is complete.

- [X] T005 Define framework-independent User, Department, Project, Document, and UserProject domain models in `app/domain/entities/organization_models.py`
- [X] T006 [P] Define `UserRepository`, `DepartmentRepository`, `ProjectRepository`, `DocumentRepository`, and `MembershipRepository` protocols in `app/domain/ports/`
- [X] T007 Define the Unit of Work protocol and transaction error types in `app/domain/ports/unit_of_work.py` and `app/domain/services/organization_errors.py`
- [X] T008 [P] Define authenticated principal and authorization service protocols in `app/domain/ports/authorization_service.py` and `app/domain/services/authorization_service.py`
- [X] T009 Implement database-agnostic SQLAlchemy mappings for User, Department, Project, Document, and UserProject in `app/infrastructure/persistence/sqlalchemy/models.py`
- [X] T010 Implement the SQLAlchemy session lifecycle, foreign-key setup, and transaction boundary in `app/infrastructure/persistence/sqlalchemy/session.py` and `app/infrastructure/persistence/sqlalchemy/unit_of_work.py`
- [X] T011 Implement the repository adapter and database configuration factory for SQLite now and PostgreSQL-compatible configuration later in `app/infrastructure/persistence/sqlalchemy/repositories.py`, `app/infrastructure/persistence/sqlite/configuration.py`, `app/infrastructure/persistence/postgres/configuration.py`, and `app/infrastructure/persistence/factory.py`
- [X] T012 Create the initial schema migration and indexes for department ownership, document project assignment, and UserProject membership in `app/infrastructure/persistence/migrations/`
- [X] T013 [P] Implement in-memory repository fakes for authorization and use-case unit tests in `tests/fixtures/organization_repositories.py`
- [X] T014 Implement trusted authenticated-principal dependency wiring for FastAPI in `app/api/dependencies.py`
- [X] T015 Register the organization and document routers with the existing FastAPI application in `app/main.py`
- [X] T016 [P] Add repository contract tests that can run against the configured adapter in `tests/contract/test_repository_contract.py`

**Checkpoint**: Persistence ports, adapter factory, Unit of Work, trusted-principal boundary, and FastAPI registration are ready for story implementation; username/password authentication is delivered in Phase 10.

---

## Phase 3: User Story 1 - Administrators Manage Organizational Users (Priority: P1) 🎯 MVP

**Goal**: Admins can create, read, update, deactivate, and delete users with flexible role values and department relationships.

**Independent Test**: An authenticated admin creates a user with a new role value, reads it back, updates it, and deactivates it; duplicate identifiers and invalid departments are rejected.

### Tests for User Story 1

- [X] T017 [P] [US1] Add API contract tests for user create, read, update, and delete behavior in `tests/contract/test_user_management_api.py`
- [X] T018 [P] [US1] Add user-management use-case tests for flexible roles, duplicate UID/email conflicts, invalid email, unknown department, and inactive status in `tests/unit/test_user_management.py`
- [X] T019 [P] [US1] Add FastAPI integration tests for admin user CRUD against the configured SQLite adapter in `tests/integration/test_user_management_e2e.py`

### Implementation for User Story 1

- [X] T020 [P] [US1] Add Pydantic request and response schemas for users and departments in `app/api/schemas/organization.py`
- [X] T021 [US1] Implement admin user and department management use cases using `UserRepository`, `DepartmentRepository`, and `UnitOfWork` in `app/use_cases/organization/user_management.py`
- [X] T022 [US1] Implement `POST /users`, `GET /users/{uid}`, `PATCH /users/{uid}`, `DELETE /users/{uid}`, and department endpoints in `app/api/routes/organization.py`
- [X] T023 [US1] Add the FastAPI dependency providers that construct user-management use cases from the repository factory in `app/api/dependencies.py`
- [X] T024 [US1] Add the Streamlit HTTP client methods for users and departments in `streamlit_app/services/organization_service.py`
- [X] T025 [US1] Build the simple Streamlit Users page for listing, creating, editing, and deactivating users in `streamlit_app/pages/users.py`
- [X] T026 [US1] Add user-page error, empty, loading, and success states without direct database access in `streamlit_app/pages/users.py`

**Checkpoint**: User Story 1 is independently usable by an admin through the FastAPI contract and Streamlit Users page.

---

## Phase 4: User Story 2 - Managers Manage Users in Their Scope (Priority: P1)

**Goal**: Managers can manage permitted users only within their own department, while Admin remains organization-wide.

**Independent Test**: A Manager can update an in-department user and is denied when targeting a user outside the department.

### Tests for User Story 2

- [X] T027 [P] [US2] Add authorization unit tests for Admin, Manager same-department, Manager cross-department, inactive actor, and dynamic-role behavior in `tests/unit/test_organization_authorization.py`
- [X] T028 [P] [US2] Add API contract tests for manager-scoped user updates and deletes in `tests/contract/test_user_scope_api.py`
- [X] T029 [US2] Add integration tests proving denied cross-department operations do not partially update SQLite state in `tests/integration/test_manager_scope_e2e.py`

### Implementation for User Story 2

- [X] T030 [US2] Implement current-user authorization and department-scope checks in `app/domain/services/authorization_service.py`
- [X] T031 [US2] Apply manager scope checks to user-management use cases in `app/use_cases/organization/user_management.py`
- [X] T032 [US2] Return consistent `401`, `403`, `404`, and `409` responses for scoped management failures in `app/api/routes/organization.py`
- [X] T033 [US2] Add manager-scoped controls and forbidden-operation messages to `streamlit_app/pages/users.py`

**Checkpoint**: User Stories 1 and 2 both work independently, with manager authorization enforced before mutation.

---

## Phase 5: User Story 3 - Manage Project Membership (Priority: P1)

**Goal**: Admins and in-scope Managers can manage the many-to-many UserProject relationship.

**Independent Test**: An authorized actor assigns a user to multiple projects, sees the relationship from both sides, and can revoke it without deleting project data.

### Tests for User Story 3

- [X] T034 [P] [US3] Add project and membership API contract tests for create, list, assign, revoke, idempotency, and scope errors in `tests/contract/test_project_membership_api.py`
- [X] T035 [P] [US3] Add membership unit tests for many-to-many relationships, duplicate assignments, revoked assignments, and department scope in `tests/unit/test_project_membership.py`
- [X] T036 [US3] Add SQLite integration tests for project membership transaction rollback and bidirectional reads in `tests/integration/test_project_membership_e2e.py`

### Implementation for User Story 3

- [X] T037 [P] [US3] Add project, membership, and department response schemas in `app/api/schemas/organization.py`
- [X] T038 [US3] Implement project creation, listing, and membership use cases with Unit of Work transactions in `app/use_cases/organization/project_management.py` and `app/use_cases/organization/membership_management.py`
- [X] T039 [US3] Implement `POST /projects`, `GET /projects`, `POST /projects/{project_id}/members/{uid}`, and `DELETE /projects/{project_id}/members/{uid}` in `app/api/routes/organization.py`
- [X] T040 [US3] Add project and membership methods to `streamlit_app/services/organization_service.py`
- [X] T041 [US3] Build the simple Streamlit Projects page for project listing, creation, membership assignment, and membership removal in `streamlit_app/pages/projects.py`
- [X] T042 [US3] Add project-page scope, duplicate-assignment, empty-state, and forbidden-operation handling in `streamlit_app/pages/projects.py`

**Checkpoint**: User Stories 1 through 3 provide usable organization and project-access administration.

---

## Phase 6: User Story 4 - Users Access Assigned Project Questions (Priority: P1)

**Goal**: Retrieve only information from projects authorized for the current user, with optional UI project selection.

**Independent Test**: Without a selected project, a user searches all authorized projects; with a selected authorized project, the search is narrowed; an unauthorized selection is denied before retrieval.

### Tests for User Story 4

- [X] T043 [P] [US4] Add chat contract tests for omitted project scope, authorized project scope, unauthorized project scope, and no authorized projects in `tests/contract/test_chat_authorization_api.py`
- [X] T044 [P] [US4] Add authorization unit tests for authorized-project-set resolution and optional project intersection in `tests/unit/test_project_authorization.py`
- [X] T045 [US4] Add security regression tests proving the retrieval adapter receives zero unauthorized project IDs and is not called for denied explicit scopes in `tests/integration/test_unauthorized_retrieval_e2e.py`

### Implementation for User Story 4

- [X] T046 [P] [US4] Add optional `project_id` and authenticated-context fields to `app/api/schemas/chat.py` without accepting caller-controlled identity
- [X] T047 [US4] Extend the retrieval port and Chroma adapter to accept authorized project filters and require project metadata in `app/domain/ports/retrieval.py` and `app/infrastructure/vector/chroma_client.py`
- [X] T048 [US4] Update `app/use_cases/chat/retrieval_service.py` and `app/use_cases/chat/query_orchestrator.py` to intersect optional project scope with authorized project IDs before retrieval
- [X] T049 [US4] Update `app/api/routes/chat.py` to resolve authorization before constructing or invoking the query orchestrator
- [X] T050 [US4] Update document ingestion metadata to associate each indexed chunk with its Document and Project in `scripts/ingest_documents.py` and `app/use_cases/ingestion/document_processing.py`
- [X] T051 [US4] Add optional project selection to the Streamlit chat UI and pass it through `streamlit_app/services/chat_service.py` without direct persistence access
- [X] T052 [US4] Add authorized-project loading, empty-project messaging, unauthorized-selection handling, and citation rendering to `streamlit_app/app.py`

**Checkpoint**: User Stories 1 through 4 enforce access control before retrieval and answer generation.

---

## Phase 7: User Story 5 - Admin Troubleshooting Access (Priority: P2)

**Goal**: Admin can access organization records and all active project information without individual project assignments.

**Independent Test**: An authenticated Admin can read and modify records across departments and retrieve information from every active project.

### Tests for User Story 5

- [X] T053 [P] [US5] Add admin-wide API access tests for users, projects, memberships, documents, and chat in `tests/contract/test_admin_access_api.py`
- [X] T054 [US5] Add end-to-end tests proving Admin bypasses project membership while inactive and unknown principals remain denied in `tests/integration/test_admin_access_e2e.py`

### Implementation for User Story 5

- [X] T055 [US5] Implement Admin organization-wide authorization for active projects and management records in `app/domain/services/authorization_service.py`
- [X] T056 [US5] Apply Admin access to organization and document routes without duplicating route logic in `app/api/routes/organization.py` and `app/api/routes/documents.py`
- [X] T057 [US5] Add Admin-only controls and all-project selection behavior to `streamlit_app/pages/users.py`, `streamlit_app/pages/projects.py`, and `streamlit_app/pages/documents.py`

**Checkpoint**: Admin troubleshooting access works across all active organization records and projects.

---

## Phase 8: Document Management and Cross-Cutting Polish

**Purpose**: Deliver the Document entity and keep the management UI simple, consistent, and validated.

- [X] T058 [P] Add Document domain model, repository port, and Unit of Work integration for optional Project assignment in `app/domain/entities/organization_models.py`, `app/domain/ports/document_repository.py`, and `app/infrastructure/persistence/sqlalchemy/repositories.py`
- [X] T059 [P] Add document API schemas and `GET /documents`, `POST /documents`, and `DELETE /documents/{document_id}` in `app/api/schemas/documents.py` and `app/api/routes/documents.py`
- [X] T060 Implement document registration, optional project assignment, status handling, and ingestion orchestration in `app/use_cases/organization/document_management.py`
- [X] T061 Add document client methods and the simple Streamlit Documents page in `streamlit_app/services/document_service.py` and `streamlit_app/pages/documents.py`
- [X] T062 Add document API and partial Project-Document participation tests in `tests/contract/test_document_management_api.py` and `tests/integration/test_document_management_e2e.py`
- [X] T063 [P] Add Streamlit navigation for chat, Users, Projects, and Documents in `streamlit_app/app.py`
- [X] T064 [P] Add UI smoke tests proving all management pages call the same FastAPI base URL in `tests/contract/test_streamlit_management_pages.py`
- [X] T065 [P] Update `README.md` and `ARCHITECTURE.md` with the adapter factory, FastAPI endpoint flow, project filtering, Document lifecycle, and Streamlit page responsibilities
- [X] T066 Run the complete validation scenarios from `specs/002-sql-user-management/quickstart.md` and record any implementation blockers

---

---

## Phase 9: Workflow Documentation, Change Log, and Final Verification

**Purpose**: Document the major implemented workflows, record code changes, and require executable test confirmation before the feature is considered complete.

- [X] T067 [P] Create the user-management workflow document, including Streamlit Users page, FastAPI endpoints, authorization, Unit of Work, and persistence adapter flow in `Documentation/Workflows/user-management.md`
- [X] T068 [P] Create the project-membership workflow document, including department scope, many-to-many assignment, manager restrictions, and rollback behavior in `Documentation/Workflows/project-membership.md`
- [X] T069 [P] Create the document-management workflow document, including optional project assignment, Project-Document partial participation, ingestion, and unassigned-document behavior in `Documentation/Workflows/document-management.md`
- [X] T070 [P] Create the question-answering workflow document, including optional project selection, authorized-project intersection, filtered retrieval, LLM generation, and citations in `Documentation/Workflows/question-answering.md`
- [X] T071 [P] Create the Streamlit-to-FastAPI workflow document, including Users, Projects, Documents, and Chat page HTTP calls in `Documentation/Workflows/streamlit-fastapi-integration.md`
- [X] T072 Create the workflow index with links to every major workflow and ownership notes in `Documentation/Workflows/README.md`
- [X] T073 Record every implementation code-file change for this feature in `Documentation/Team_logs/Roshan.md`, including date, file path, change summary, related task ID, and validation result
- [X] T074 Add or complete focused unit tests for domain entities, authorization, repository ports, Unit of Work behavior, membership rules, document assignment, and optional project selection in `tests/unit/`
- [X] T075 Run the complete unit-test suite with `pytest tests/unit` and fix all failures before marking the feature complete
- [X] T076 Run the full regression suite with `pytest`, then record the command, result, and any known environment limitations in `Documentation/Team_logs/Roshan.md`
- [X] T077 Validate every workflow document link, every required task checkbox, and the scenarios in `specs/002-sql-user-management/quickstart.md` before completion

---

## Phase 10: Basic Authentication and Organization Bootstrap

**Purpose**: Add the newly specified username/password authentication flow while preserving the completed organization, document, workflow, and validation history from Phases 1-9.

**Dependency**: Depends on the completed persistence, user-management, authorization, API, and Streamlit foundations from T001-T077. Existing task IDs and completion states must remain unchanged.

### Setup and contracts

- [X] T078 Add the selected password-hashing and session/token dependencies to `requirements.txt`, add secure Admin credential settings to `app/core/settings.py`, and document non-secret configuration names in `.env.example`
- [X] T079 [P] Add authentication domain port and error contracts for login, authenticated-principal resolution, password changes, and default-password rotation in `app/domain/ports/authentication_service.py` and `app/domain/services/organization_errors.py`

### Tests for authentication and bootstrap

- [X] T080 [P] Add unit tests for password hashing, invalid credentials, inactive users, password changes, default-password rotation, and authenticated-principal resolution in `tests/unit/test_authentication_service.py`
- [X] T081 [P] Add API contract tests for `POST /auth/login`, `POST /auth/change-password`, invalid credentials, Admin-only password changes, and protected requests in `tests/contract/test_authentication_api.py`
- [X] T082 Add SQLite integration tests for pre-seeded Admin bootstrap, first Admin login, default-password change, Admin-created Manager login, Manager-created employee login, and persistence across sessions in `tests/integration/test_authentication_bootstrap_e2e.py`
- [X] T083 [P] Add security regression tests proving plaintext passwords are absent from persistence, responses, and audit records, and that old passwords stop working after a change in `tests/integration/test_authentication_security_e2e.py`

### Authentication implementation

- [X] T084 Implement password hashing, credential verification, login, authenticated-principal issuance, and password-change rules behind the authentication port in `app/domain/services/authentication_service.py` and `app/infrastructure/authentication/password_hasher.py`
- [X] T085 Extend the User domain model and SQLAlchemy persistence with unique `username`, secure password representation, password-change metadata, and initial-password state in `app/domain/entities/organization_models.py`, `app/infrastructure/persistence/sqlalchemy/models.py`, and `app/infrastructure/persistence/sqlalchemy/repositories.py`
- [X] T086 Add the authentication schema migration and indexes for username lookup in `app/infrastructure/persistence/migrations/0002_authentication.sql`
- [X] T087 Implement secure pre-seeded Admin provisioning, configured default credentials, first-login/default-password rotation, and idempotent bootstrap behavior in `app/infrastructure/authentication/bootstrap.py` and `app/infrastructure/persistence/factory.py`
- [X] T088 Add login, logout/session or token, and password-change schemas and routes in `app/api/schemas/authentication.py` and `app/api/routes/authentication.py`
- [X] T089 Wire authentication dependencies and trusted principal resolution into protected organization, document, and chat routes in `app/api/dependencies.py`, `app/api/routes/organization.py`, `app/api/routes/documents.py`, and `app/api/routes/chat.py`
- [X] T090 Extend Admin and Manager user-creation flows to accept initial passwords, enforce unique usernames, and allow in-scope Managers to onboard employees in `app/api/schemas/organization.py` and `app/use_cases/organization/user_management.py`
- [X] T091 Add authenticated Streamlit login state, logout behavior, and password-change controls without direct persistence access in `streamlit_app/services/authentication_service.py`, `streamlit_app/app.py`, and `streamlit_app/pages/users.py`
- [X] T092 Add structured authentication audit events for login success/failure, logout, bootstrap, and password changes without recording passwords or tokens in `app/infrastructure/audit/authentication_events.py` and `app/api/routes/authentication.py`

### Documentation and verification

- [X] T093 [P] Document authentication bootstrap, default-password rotation, Manager onboarding, and protected-request flow in `Documentation/Workflows/authentication-and-bootstrap.md` and `Documentation/Workflows/README.md`
- [X] T094 [P] Update `README.md`, `ARCHITECTURE.md`, and `.env.example` with local authentication setup, secure Admin credential configuration, and password-handling boundaries
- [ ] T095 Run the authentication quickstart scenarios from `specs/002-sql-user-management/quickstart.md`, record any environment blockers, and verify the pre-seeded Admin to Manager to employee onboarding path in `Documentation/Team_logs/Akaash.md`
- [ ] T096 Run `pytest tests/unit tests/contract tests/integration`, fix authentication regressions, and record the result in `Documentation/Team_logs/Akaash.md`
- [ ] T097 Validate all Phase 10 task checkboxes, authentication workflow links, migration references, and the unchanged completion state of T001-T077 in `specs/002-sql-user-management/tasks.md`

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundational**: Depends on Setup and blocks all user stories.
- **Phase 3 User Story 1**: Depends on Foundational; recommended MVP.
- **Phase 4 User Story 2**: Depends on Foundational and shares user-management code with US1.
- **Phase 5 User Story 3**: Depends on Foundational; requires department and project authorization from US2.
- **Phase 6 User Story 4**: Depends on Foundational and project membership behavior from US3.
- **Phase 7 User Story 5**: Depends on the authorization and management paths from US1-US4.
- **Phase 8 Polish and Document completion**: Document tasks may begin after Foundational; final validation depends on the desired user stories.
- **Phase 9 Workflow and Verification**: Depends on all implementation tasks; T075 and T076 are the completion gates.
- **Phase 10 Basic Authentication and Organization Bootstrap**: Depends on Phases 1-9 and adds the username/password, pre-seeded Admin, password-change, and Manager-onboarding behavior from the updated specification.

### User Story Dependencies

- **US1**: Can start after Foundational; MVP for basic user administration.
- **US2**: Depends on US1's user-management use case and repository ports.
- **US3**: Depends on department/project foundations and US2's scope authorization.
- **US4**: Depends on US3's project membership and project identity in document metadata.
- **US5**: Depends on US1-US4 authorization boundaries.

### Parallel Opportunities

- Setup settings, directories, README configuration, and initial test scaffolding can run in parallel.
- Repository ports, domain authorization protocols, and in-memory fakes can run in parallel after entity definitions.
- US1 contract tests and use-case tests can run in parallel before implementation.
- US3 project schemas, repository methods, and contract tests can run in parallel after foundational ports exist.
- US4 authorization tests, chat schema work, and Streamlit chat selection work can run in parallel once the authorization contract is fixed.
- Document API, document page, and document integration tests can run in parallel after the Document repository port exists.
- README and architecture documentation can run in parallel with final UI smoke testing.
- Phase 10 authentication unit tests, API contract tests, and security tests can run in parallel after the authentication contracts are defined; implementation tasks affecting the same authentication files remain sequential.

## Parallel Example: User Story 1

```text
Task T017: User API contract tests in tests/contract/test_user_management_api.py
Task T018: User use-case tests in tests/unit/test_user_management.py
Task T020: Organization schemas in app/api/schemas/organization.py
```

## Parallel Example: User Story 4

```text
Task T043: Chat authorization contract tests in tests/contract/test_chat_authorization_api.py
Task T044: Project authorization unit tests in tests/unit/test_project_authorization.py
Task T051: Streamlit project selector in streamlit_app/services/chat_service.py and streamlit_app/app.py
```

## Implementation Strategy

### MVP First

1. Complete Setup and Foundational phases.
2. Complete User Story 1 for admin user and department management.
3. Validate with the user API contract, use-case tests, and Streamlit Users page.
4. Add User Story 2 scope enforcement before exposing broader management operations.

### Incremental Delivery

1. Add project membership management in User Story 3.
2. Add project-filtered question access in User Story 4.
3. Add Admin troubleshooting behavior in User Story 5.
4. Complete Document management and the three Streamlit management pages.
5. Create workflow documentation and update Roshan's team log for every code-file change.
6. Run `pytest tests/unit`, then run `pytest`; resolve failures before completion.
7. Run the quickstart scenarios and full regression suite.
8. Complete Phase 10 authentication bootstrap and password lifecycle work without rewriting or renumbering T001-T077.

## Format Validation

All implementation and completion tasks use the required checklist format: `- [ ] T###`, optional `[P]`, story labels only in story phases, and an explicit repository-relative file path in every task description. Completion requires workflow documents, a Roshan.md change record, passing unit tests, and a full regression run.
