# KnowLayer Workflows

Workflow guides for the SQL organization-access feature:

- [User management](user-management.md): Users page, user CRUD, authorization, Unit of Work, and persistence adapters.
- [Project membership](project-membership.md): department scope, many-to-many assignment, idempotency, and rollback.
- [Document management](document-management.md): optional project assignment, lifecycle, ingestion metadata, and unassigned documents.
- [Question answering](question-answering.md): project selection, authorized intersection, filtered retrieval, LLM generation, and citations.
- [Streamlit to FastAPI integration](streamlit-fastapi-integration.md): shared API base URL and page responsibilities.

## Ownership

- API, domain, use cases, and persistence: backend feature owners.
- Streamlit pages and HTTP clients: UI feature owners.
- Workflow accuracy and validation records: the feature implementation owner.
