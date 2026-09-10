# 2026-09-10

## Feature: SQL Organization Access - Phase 1 Setup

- requirements.txt: added SQLAlchemy and Alembic dependencies for the database-agnostic persistence adapter.
- .env.example: added configurable DATABASE_URL and STREAMLIT_API_BASE_URL.
- app/core/settings.py: added environment-backed database and Streamlit API settings.
- .gitignore: excluded SQLite runtime files under instance/.
- README.md: documented the initial SQLite configuration and organization feature setup.
- Directories created for persistence adapters, organization use cases, Streamlit pages, fixtures, and workflow documentation.
- Validation: Phase 1 setup checks and focused test command pending after implementation.

## Feature: SQL Organization Access - Phase 2 Foundation

Code files added or changed:
- app/domain/entities/organization_models.py
- app/domain/ports/organization_repositories.py
- app/domain/ports/unit_of_work.py
- app/domain/ports/authorization_service.py
- app/domain/services/organization_errors.py
- app/domain/services/authorization_service.py
- app/infrastructure/persistence/sqlalchemy/models.py
- app/infrastructure/persistence/sqlalchemy/session.py
- app/infrastructure/persistence/sqlalchemy/repositories.py
- app/infrastructure/persistence/sqlalchemy/unit_of_work.py
- app/infrastructure/persistence/sqlite/configuration.py
- app/infrastructure/persistence/postgres/configuration.py
- app/infrastructure/persistence/factory.py
- app/infrastructure/persistence/migrations/0001_initial.sql
- app/infrastructure/persistence/__init__.py
- app/api/dependencies.py
- app/api/routes/organization.py
- app/api/routes/documents.py
- app/main.py
- tests/fixtures/organization_repositories.py
- tests/contract/test_repository_contract.py

Summary: Added database-agnostic domain ports, SQLite/PostgreSQL adapter seams, Unit of Work, SQLAlchemy mappings, FastAPI dependency boundaries, router registration, and repository contract coverage.
Validation: Phase 2 syntax validation, SQLite metadata creation, authorization resolution, and repository contract test passed (1 passed).

## Feature: SQL Organization Access - Phase 3 US1

Code files added or changed:
- requirements.txt
- app/api/schemas/organization.py
- app/api/dependencies.py
- app/api/routes/organization.py
- app/domain/ports/organization_repositories.py
- app/infrastructure/persistence/sqlalchemy/repositories.py
- app/use_cases/organization/user_management.py
- streamlit_app/services/organization_service.py
- streamlit_app/pages/users.py
- tests/unit/test_user_management.py
- tests/contract/test_user_management_api.py
- tests/integration/test_user_management_e2e.py
- tests/fixtures/organization_repositories.py

Summary: Implemented admin user and department CRUD with flexible roles, validation, authentication boundaries, and the Streamlit Users page.
Validation: Focused US1 suite passed: 7 tests.

## Feature: SQL Organization Access - Phases 4 and 5

Code files added or changed:
- app/use_cases/organization/user_management.py
- app/use_cases/organization/project_management.py
- app/use_cases/organization/membership_management.py
- app/api/schemas/organization.py
- app/api/dependencies.py
- app/api/routes/organization.py
- streamlit_app/services/organization_service.py
- streamlit_app/pages/projects.py
- tests/unit/test_organization_authorization.py
- tests/unit/test_project_membership.py
- tests/contract/test_user_scope_api.py
- tests/contract/test_project_membership_api.py
- tests/integration/test_manager_scope_e2e.py
- tests/integration/test_project_membership_e2e.py
- tests/unit/test_user_management.py
- tests/contract/test_user_management_api.py
- tests/integration/test_user_management_e2e.py

Summary: Added Manager department scoping, project CRUD, many-to-many membership assignment/revocation, idempotent membership behavior, Projects Streamlit page, and SQLite integration coverage.
Validation: Combined US1-US3 focused suite passed: 16 tests.

## Feature: SQL Organization Access - Phases 6 and 7

Code files added or changed:
- app/domain/ports/retrieval.py
- app/api/schemas/chat.py
- app/api/dependencies.py
- app/api/routes/chat.py
- app/use_cases/chat/retrieval_service.py
- app/use_cases/chat/query_orchestrator.py
- app/infrastructure/vector/chroma_client.py
- app/use_cases/ingestion/document_processing.py
- scripts/ingest_documents.py
- streamlit_app/services/chat_service.py
- streamlit_app/app.py
- tests/unit/test_project_authorization.py
- tests/integration/test_unauthorized_retrieval_e2e.py
- tests/contract/test_chat_authorization_api.py
- tests/contract/test_admin_access_api.py
- tests/integration/test_admin_access_e2e.py

Summary: Added optional project selection, authorized-project intersection before retrieval, Chroma project filtering, Document/Project chunk metadata, Streamlit project scope selection, and Admin-wide project access tests.
Validation: US4/US5 and retrieval compatibility suite passed: 24 tests. Existing chat contract remains environment-sensitive because the current local Chroma data returned zero citations.
