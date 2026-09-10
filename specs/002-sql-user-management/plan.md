# Implementation Plan: SQL Organization Access and User Management

**Branch**: `feature/sql-user-management` | **Date**: 2026-09-10 | **Spec**: [spec.md](./spec.md)

## Summary

Integrate the corrected Department–User–Project ERD into KnowLayer through a PostgreSQL-compatible persistence adapter, management API contracts, and an authorization service that resolves project access before Chroma retrieval. User role remains a flexible string; `Admin` and `Manager` are special values, and no Role or Permission table is introduced. The User–Project many-to-many relationship is represented by the required associative database table with uniqueness and foreign-key constraints.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: FastAPI, Pydantic 2, pytest, existing Chroma/LLM adapters; SQLAlchemy 2 and Alembic are the planned relational persistence dependencies.

**Storage**: SQLite database file at `./instance/sqlite.db` for organization/access data; Chroma remains the vector store and must carry project identity in retrieval metadata.

**Testing**: pytest unit tests, FastAPI contract tests, integration tests against a temporary SQLite database, and authorization regression tests proving zero restricted retrieval.

**Target Platform**: Existing local/internal web application with FastAPI backend and Streamlit client.

**Project Type**: Modular monolith web application with API and Streamlit presentation layers.

**Performance Goals**: Typical user lookup and project authorization under 100ms; preserve the existing low-seconds interactive chat target.

**Constraints**: Authorization must occur before vector retrieval; no secrets in audit data; dynamic roles must not require migrations; domain logic cannot depend on SQLAlchemy, Chroma, FastAPI, or Streamlit; existing chat behavior must remain usable when no project scope is supplied only through an explicit compatibility policy.

**Scale/Scope**: SQLite supports up to ~100 concurrent users; the design can scale to PostgreSQL later without schema changes; initial model includes User, Department, Project, UserProject, and AuditEvent.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- PASS: Persistence and authorization are isolated behind domain ports and infrastructure adapters.
- PASS: SQL becomes the authoritative source for organization and access facts; the LLM remains synthesis-only.
- PASS: Authorization is resolved before retrieval, and project IDs are injected into the retrieval context.
- PASS: Audit events cover management operations and denied access without raw secrets or unrestricted content.
- PASS: Unit, contract, integration, and security regression tests are planned.
- PASS: The design avoids Role/Permission entities, microservices, and premature enterprise complexity.

## Phase 0: Research Summary

See [research.md](./research.md). Decisions resolve the technology and integration questions: relational constraints, associative membership, pre-retrieval authorization, department-scoped Manager operations, structured audits, and migrations.

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
│   │   └── organization_models.py          # User, Department, Project, membership values
│   ├── ports/
│   │   ├── organization_repository.py      # persistence abstraction
│   │   └── authorization_service.py        # access abstraction
│   └── services/
│       └── authorization_service.py        # pre-retrieval rules
├── infrastructure/
│   └── sql/
│       ├── database.py                      # engine/session lifecycle
│       ├── models.py                        # SQLAlchemy mappings
│       ├── repositories.py                  # repository adapter
│       └── migrations/                      # Alembic revisions
└── use_cases/
    ├── organization/
    │   ├── user_management.py
    │   ├── project_management.py
    │   └── membership_management.py
    └── chat/
        └── query_orchestrator.py            # consume authorized project IDs

streamlit_app/
└── services/
    └── organization_service.py              # thin API client as needed

tests/
├── contract/
│   └── test_user_management_api.py
├── integration/
│   └── test_sql_authorization_e2e.py
└── unit/
    ├── test_user_authorization.py
    └── test_project_membership.py
```

**Structure Decision**: Extend the existing modular monolith. Domain entities, ports, and authorization rules remain framework-independent. SQLAlchemy/Alembic belongs under infrastructure; routes remain thin; use cases own transaction orchestration. The existing Chroma adapter is changed only to accept authorized project filters and project metadata.

## Implementation Sequence

1. Add SQL configuration, engine/session lifecycle, migration baseline, and relational mappings.
2. Add domain entities and repository/authorization ports with fake implementations for unit tests.
3. Implement user, department, project, and membership use cases with transaction and audit behavior.
4. Add organization API schemas/routes and trusted authentication-context dependency boundary.
5. Add pre-retrieval project authorization to FastAPI and Streamlit chat paths; update Chroma metadata/filter contracts.
6. Add unit, API contract, SQL integration, and unauthorized-retrieval regression tests.
7. Run the quickstart scenarios and document migration/configuration operations.

## Risks and Mitigations

- Existing Chroma documents may lack project IDs: fail closed for restricted requests and provide a migration/re-ingestion step.
- No authentication provider is currently present: keep a narrow principal port and use a development-only explicit test principal; do not trust caller-supplied UID in production.
- Manager scope interpretation could drift: enforce same-department user and project ownership in one authorization service and contract-test it.
- Audit writes could affect business transactions: define whether audit is in-transaction for management writes and use an observable failure path for denied/read events.

## Post-Design Constitution Check

- PASS: The plan keeps SQL, Chroma, and authentication behind replaceable adapters.
- PASS: The data model treats SQL organization records as authoritative and prevents LLM-side access decisions.
- PASS: The retrieval path is fail-closed for missing identity, inactive users, and missing project metadata.
- PASS: The design includes security regression tests and contract tests before implementation completion.
- PASS: No unresolved clarification items remain in the plan or corrected specification.

## Complexity Tracking

No constitution violations require justification. The associative membership table is required by the many-to-many relationship, not an additional domain entity, and the SQL adapter is required for referential integrity and transactional access control.
