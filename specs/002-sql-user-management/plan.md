# Implementation Plan: SQL Organization Access and User Management

**Branch**: `feature/sql-user-management` | **Date**: 2026-09-10 | **Spec**: [spec.md](./spec.md)

## Summary

Integrate the corrected Department–User–Project ERD into KnowLayer through database-agnostic persistence ports, basic username/password authentication, a configurable relational adapter, management API contracts, and an authorization service that resolves project access before retrieval. User role remains a flexible string; `Admin` and `Manager` are special values, and no Role or Permission table is introduced. The User–Project many-to-many relationship is represented by the required associative database table with uniqueness and foreign-key constraints.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: FastAPI, Pydantic 2, pytest, password hashing/session or token support, existing Chroma/LLM adapters; SQLAlchemy 2 and Alembic are the planned relational persistence dependencies.

**Storage**: A relational persistence port with SQLite as the initial configuration and PostgreSQL as a compatible future configuration; Chroma remains the vector store and carries project identity in retrieval metadata.

**Testing**: pytest unit tests, FastAPI contract tests, integration tests against a temporary SQLite database, and authorization regression tests proving zero restricted retrieval.

**Target Platform**: Existing local/internal web application with FastAPI backend and Streamlit client.

**Project Type**: Modular monolith web application with API and Streamlit presentation layers.

**Performance Goals**: Typical user lookup and project authorization under 100ms; preserve the existing low-seconds interactive chat target.

**Constraints**: Authentication and authorization must occur before protected operations and vector retrieval; passwords must be stored only as secure representations; dynamic roles must not require migrations; domain logic cannot depend on SQLAlchemy, Chroma, FastAPI, or Streamlit; existing chat behavior must remain usable when no project scope is supplied only through an explicit compatibility policy.

**Scale/Scope**: Initial lightweight deployment uses SQLite; the same repository contracts must support PostgreSQL later without changing domain or use-case code. The model includes User, Department, Project, Document, and UserProject.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- PASS: Persistence and authorization are isolated behind domain ports and infrastructure adapters.
- PASS: SQL becomes the authoritative source for organization and access facts; the LLM remains synthesis-only.
- PASS: Authorization is resolved before retrieval, and project IDs are injected into the retrieval context.
- PASS: Unit, contract, integration, and security regression tests are planned.
- PASS: The design avoids Role/Permission entities, microservices, and premature enterprise complexity.

## Phase 0: Research Summary

See [research.md](./research.md). Decisions resolve the technology and integration questions: relational constraints, associative membership, pre-retrieval authorization, department-scoped Manager operations, and migrations.

## Phase 1: Design Summary

See [data-model.md](./data-model.md) for fields, relationships, constraints, and authorization rules. See [contracts/user-management-api.md](./contracts/user-management-api.md) for endpoint behavior. See [quickstart.md](./quickstart.md) for runnable validation scenarios.

## Project Structure

```text
app/
├── api/
│   ├── routes/
│   │   ├── chat.py                         # inject auth context and project scope
│   │   └── organization.py                 # user/department/project/membership endpoints
│   └── schemas/
│       └── organization.py                 # request/response validation
├── core/
│   └── settings.py                         # SQL URL and feature settings
├── domain/
│   ├── entities/
│   │   └── organization_models.py          # User, Department, Project, Document, membership values
│   ├── ports/
│   │   ├── user_repository.py             # user persistence port
│   │   ├── department_repository.py       # department persistence port
│   │   ├── project_repository.py          # project persistence port
│   │   ├── membership_repository.py       # user-project persistence port
│   │   ├── authentication_service.py       # username/password authentication boundary
│   │   ├── unit_of_work.py                # transaction boundary
│   │   └── authorization_service.py       # access abstraction
│   └── services/
│       ├── authentication_service.py       # login and password-change rules
│       └── authorization_service.py        # pre-retrieval rules
├── infrastructure/
│   └── persistence/
│       ├── sqlalchemy/                       # shared relational adapter
│       │   ├── models.py
│       │   ├── repositories.py
│       │   ├── unit_of_work.py
│       │   └── session.py
│       ├── sqlite/                           # SQLite configuration
│       ├── postgres/                         # PostgreSQL configuration
│       └── factory.py                        # selects configured adapter
└── use_cases/
    ├── organization/
    │   ├── user_management.py
    │   ├── project_management.py
    │   └── membership_management.py
    └── chat/
        └── query_orchestrator.py            # consume authorized project IDs

streamlit_app/
├── app.py                                  # navigation and chat page
├── pages/
│   ├── users.py                             # user and department management
│   ├── projects.py                          # project and membership management
│   └── documents.py                         # document listing and ingestion controls
└── services/
    ├── chat_service.py                      # chat API client
    ├── organization_service.py              # users/projects API client
    └── document_service.py                  # documents API client

tests/
├── contract/
│   ├── test_user_management_api.py
│   ├── test_document_management_api.py
│   └── test_streamlit_management_pages.py
├── integration/
│   └── test_sql_authorization_e2e.py
└── unit/
    ├── test_user_authorization.py
    └── test_project_membership.py
```

**Structure Decision**: Extend the existing modular monolith. Domain entities, repository ports, authorization rules, and use cases remain database-agnostic. A shared SQLAlchemy-based relational adapter is configured for SQLite initially and can be configured for PostgreSQL later. FastAPI routes receive use cases through dependency injection; Streamlit pages call the same FastAPI application over HTTP. Document management remains a thin operational page over document endpoints and the existing ingestion use case.

## Implementation Sequence

1. Add basic username/password authentication with a pre-seeded Admin, password-change behavior, and a trusted authenticated-principal boundary.
2. Add database-agnostic repository ports for users, departments, projects, documents, memberships, and Unit of Work; configure SQLite first.
3. Add domain entities and authorization services with in-memory fake repositories for unit tests.
4. Implement user, department, project, and membership use cases using the Unit of Work boundary, including Admin-created initial passwords.
5. Add organization and document API schemas/routes plus authentication-context dependencies; make chat project scope optional.
6. Add pre-retrieval project authorization to FastAPI and Streamlit chat paths; intersect an optional selected project with the user's authorized project set before retrieval.
7. Add Streamlit Users, Projects, and Documents pages backed by small HTTP client services.
8. Add repository contract, SQLite integration, authentication/API contract, UI smoke, and unauthorized-retrieval regression tests.
9. Run the quickstart scenarios and document adapter configuration, authentication bootstrap, and migration operations.

## Risks and Mitigations

- Existing documents may lack project IDs: fail closed for restricted requests and provide a migration/re-ingestion step.
- No external authentication provider is required for the basic flow: keep a narrow authentication/principal port, pre-seed the Admin through secure configuration, and do not trust caller-supplied UID in production.
- Manager scope interpretation could drift: enforce same-department user and project ownership in one authorization service and contract-test it.

## Post-Design Constitution Check

- PASS: The plan keeps SQL, Chroma, and authentication behind replaceable adapters.
- PASS: The data model treats SQL organization records as authoritative and prevents LLM-side access decisions.
- PASS: The retrieval path is fail-closed for missing identity, inactive users, and missing project metadata.
- PASS: The design includes security regression tests and contract tests before implementation completion.
- PASS: No unresolved clarification items remain in the plan or corrected specification.

## Complexity Tracking

No constitution violations require justification. The associative membership table is required by the many-to-many relationship, not an additional domain entity, and the SQL adapter is required for referential integrity and transactional access control.
