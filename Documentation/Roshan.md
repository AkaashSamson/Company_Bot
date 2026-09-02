# Roshan — Backend

## Role Overview
Owns the API and domain layer: request/response contracts, authentication and authorization, persistence, and the enterprise-system adapters that will eventually make KnowLayer permission-aware rather than a single-document demo.

## Core Responsibilities
- **API contracts** — `app/api/routes/chat.py`, `app/api/schemas/chat.py`: request validation, response serialization (`ChatRequest`, `ChatResponse`, `Citation`).
- **Domain modeling** — `app/domain/entities/document_models.py` and related entities (`DocumentChunk`, `QuerySession`, `Message`), keeping business logic framework-independent.
- **Authorization** — building the pre-retrieval permission model described in the platform README: role-based access control, document-level and employee-level authorization, so no data is retrieved before a permission check.
- **Persistence** — introducing PostgreSQL + SQLAlchemy + Alembic migrations for application state, permissions, and audit logs (currently absent from the MVP).
- **Enterprise connectors** — the adapter layer for HR systems, Jira, Zoho, Slack/Teams (Phase 2 roadmap), each implementing a common interface so the core doesn't depend on any one vendor.
- **Audit logging** — every query, retrieval, and authorization decision logged with user context, without ever logging sensitive data in cleartext.

## Current System Touchpoints
- `app/api/routes/chat.py`, `app/api/schemas/chat.py`
- `app/domain/entities/document_models.py`
- `app/infrastructure/document/local_document_loader.py` (first adapter to generalize beyond local filesystem)
- `tests/contract/` (API schema validation)

## Research Topics to Improve Efficiency

1. **Authorization model design** — RBAC vs attribute-based access control (ABAC) for the two-tier permission problem here (document-level *and* employee-level), and how to enforce it *before* vector retrieval rather than filtering after.
2. **Auth architecture** — SSO/JWT integration patterns for FastAPI, session handling, and how identity flows from Streamlit → FastAPI → authorization checks.
3. **Schema design for permissions + audit** — a PostgreSQL schema that supports fast permission checks per query without becoming a bottleneck, plus an append-only audit log design.
4. **Adapter pattern for enterprise connectors** — a common interface (`fetch_employee_data`, `list_authorized_documents`, etc.) so HR/Jira/Zoho connectors are pluggable, mirroring the existing `LocalDocumentLoader` → `SharePointDocumentLoader` swap pattern in the architecture doc.
5. **Caching hot lookups** — Redis (or similar) for frequently-requested authoritative data (leave balances, role lookups) to avoid hammering upstream HR systems on every hybrid query.
6. **Async performance in FastAPI** — profiling the request path (auth check → retrieval → LLM call → response) to find where async/await actually saves latency versus where it adds complexity.
7. **API rate limiting & abuse prevention** — protecting `/api/chat` and future `/api/query` endpoints once this is internet-facing rather than localhost-only.
8. **Contract-test coverage** — expanding `tests/contract/` as new endpoints (`/api/search`, `/session/:id/history`) are added, so schema changes don't silently break the Streamlit client.

## Coordination Notes
- Authorization must be enforced *before* [Abhinav](Abhinav.md)'s retrieval/synthesis logic runs — coordinate on where that check lives in `QueryOrchestrator`.
- Database and secrets provisioning depend on [Akaash](Akaash.md)'s deployment environment decisions.
- Any change to `DocumentChunk`/metadata shape affects [Neha](Neha.md)'s embedding pipeline — keep the domain model as the shared contract.
