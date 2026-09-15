# KnowLayer Architecture

## Overview

KnowLayer is a modular monolith with clear boundaries between the API, use cases, domain services, infrastructure adapters, and Streamlit presentation layer. The current chat path is a document-grounded RAG flow with provider-independent LLM interfaces.

The core request path is:

```text
User
  -> Streamlit chat or FastAPI POST /api/chat
  -> Authentication token resolved to principal
  -> AuthorizationEngine resolves scoped projects and documents
  -> QueryOrchestrator
  -> ConversationQueryResolver when the question depends on history
  -> RetrievalService with authorized project/document filter
  -> ChromaVectorStore candidate retrieval
  -> distance-aware relevance and redundancy selection
  -> compact context assembly
  -> OpenRouter primary provider
  -> Groq fallback provider if the primary fails
  -> answer and citations from the same selected evidence
```

When no relevant evidence is selected, the orchestrator returns an information-not-found response and an empty citation list. It does not call an answer-generation provider for that path.

## Module Organization

```text
app/
├── main.py                             # FastAPI app, lifespan, router registration
├── api/
│   ├── routes/
│   │   ├── chat.py                     # POST /api/chat
│   │   ├── organization.py             # Users, departments, projects, memberships
│   │   ├── documents.py                # Document management and upload
│   │   ├── explorer.py                 # Organization Explorer data
│   │   ├── roles.py                    # RBAC role management
│   │   └── authentication.py           # Login, refresh, password change
│   ├── schemas/                        # Request/response models per domain
│   └── dependencies.py                 # FastAPI DI: UoW, auth, authorization
├── core/settings.py                    # Environment configuration
├── domain/
│   ├── entities/
│   │   ├── document_models.py
│   │   └── organization_models.py      # User, Department, Project, Role, Permission, etc.
│   ├── ports/
│   │   ├── authorization_service.py    # AuthenticatedPrincipal
│   │   ├── authentication_service.py
│   │   ├── organization_repositories.py
│   │   ├── document_repository.py
│   │   ├── retrieval.py
│   │   ├── sequence_repository.py      # Business ID sequence port
│   │   └── unit_of_work.py
│   └── services/
│       ├── authorization_engine.py     # Central RBAC authorization engine
│       ├── authorization_service.py    # Legacy shim
│       ├── authentication_service.py
│       ├── session_memory_service.py
│       ├── llm_provider.py
│       ├── organization_errors.py      # ForbiddenError, NotFoundError, ConflictError
│       ├── permission_catalog.py
│       └── business_id_generator.py    # Atomic ID generation (MSS/DEPT/PROJ/DOC)
├── infrastructure/
│   ├── vector/chroma_client.py         # Persistent Chroma adapter
│   ├── document/local_document_loader.py
│   ├── ingestion/provisioner.py
│   ├── llm/
│   │   ├── openrouter_client.py
│   │   ├── groq_client.py
│   │   └── fallback_llm_provider.py
│   ├── authentication/
│   │   ├── bootstrap.py               # Admin account provisioner
│   │   └── password_hasher.py          # PBKDF2-SHA256
│   ├── audit/authentication_events.py
│   └── persistence/
│       ├── factory.py                  # SQLAlchemy SessionFactory + lifespan init
│       ├── rbac_seed.py                # Seeds roles and permissions on startup
│       ├── sqlite/configuration.py
│       ├── postgres/configuration.py
│       └── sqlalchemy/
│           ├── models.py               # ORM mappings
│           ├── foundation_models.py    # Role, Permission, RBAC join tables
│           ├── repositories.py         # All repository implementations
│           ├── session.py
│           └── unit_of_work.py
└── use_cases/
    ├── chat/
    │   ├── query_orchestrator.py
    │   ├── conversation_query_resolver.py
    │   ├── retrieval_service.py
    │   ├── provenance_service.py
    │   └── session_memory.py
    ├── organization/
    │   ├── user_management.py
    │   ├── project_management.py
    │   ├── membership_management.py
    │   ├── department_membership.py
    │   ├── document_management.py
    │   ├── document_access.py
    │   ├── project_access.py
    │   ├── role_management.py
    │   ├── organization_explorer.py
    │   └── profile.py
    └── ingestion/document_processing.py
```

`streamlit_app/` is a separate presentation client with pages for chat, users, projects, departments, documents, organization explorer, profile, and roles. Pages are thin HTTP clients; they contain no `can_`, `has_permission`, or `AuthorizationEngine` logic.

## Request Flow

1. `ChatRequest` validates the question, session ID, and optional conversation history.
2. The route resolves the authenticated principal from the bearer token.
3. `AuthorizationEngine.authorization_scope()` resolves scoped projects and document grants for the principal.
4. The chat route rejects requests selecting a project outside the principal's scope (403).
5. `ConversationQueryResolver` asks `SessionMemoryService` for only the most recent six messages by default.
6. A standalone question bypasses rewriting. A likely dependent question is sent to the configured LLM with a small rewrite prompt and bounded history. The rewrite is used only as a retrieval query.
7. `RetrievalService` applies the authorized project/document filter, retrieves candidates for the full query and explicit query parts, then filters and selects evidence.
8. `QueryOrchestrator` joins only the selected evidence text into the document context.
9. The original user question, rather than the rewritten retrieval query, is included in the final answer-generation prompt.
10. `FallbackLLMProvider` tries OpenRouter first and Groq second if OpenRouter raises `LLMProviderError`.
11. `ProvenanceService` builds citations from the selected results. The API serializes those citations, and Streamlit renders exactly what the API returns.

## Authorization Engine

`AuthorizationEngine` is the single source of truth for all access decisions. It resolves identity, active status, RBAC roles and permissions, and then answers questions about project, document, and retrieval scope access.

Key methods:
- `is_admin(principal)` — checks if the user holds the `admin` role.
- `has_permission(principal, permission)` — resolves RBAC permissions through roles.
- `can_manage_project(principal, project_id)` — manager scope is department-aware.
- `can_read_document(principal, document_id)` — membership, grant, or management.
- `authorization_scope(principal, selected_project_id)` — resolves the exact retrieval scope (project IDs, document grants, include_unassigned).

All authorization lives in the backend. Streamlit pages contain no permission logic. The chat route's 403 gate and the retrieval filter both derive from `authorization_scope`. Document grants grant document-level access; they do not grant broad project-wide access.

## RBAC and Roles

Roles and permissions are seeded on startup via `rbac_seed.py`. System roles (`Admin`, `Manager`, `Developer`, `Lead`, `Tester`) are global. Custom department-scoped roles are created through `role_management`. Permissions (e.g. `USER_CREATE`, `DOCUMENT_MANAGE_ACCESS`) are assigned to roles and evaluated by `AuthorizationEngine`.

Built-in role hierarchy:
- **Admin**: all permissions, all departments, all projects.
- **Manager**: user/project management within own department.
- **Lead**: project-level management for designated projects.
- **Developer**: document viewing and project access for assigned projects.
- **Tester**: read-only project access for assigned projects.

## Business ID Generation

Entity IDs use configurable prefixes and atomic counters stored in `business_id_sequences`:
- `MSS-NNN` for employees/users
- `DEPT-NNN` for departments
- `PROJ-NNN` for projects
- `DOC-NNN` for documents

The `DepartmentCreate.department_id` field is optional; when omitted, the system auto-generates the ID. The business ID is never reused after an entity is deleted.

## Retrieval and Evidence Selection

### Vector store

`ChromaVectorStore` uses `chromadb.PersistentClient` and stores its collection in `.chroma/`. It creates or opens the configured collection and uses the configured Sentence Transformers model to embed both documents and queries.

The default embedding setting is:

```text
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

The collection is configured for cosine distance. Raw Chroma distances are preserved in each result as `distance`; they are not mislabeled as similarity scores. Lower distance means a closer vector match.

### Candidate retrieval

`RAG_CANDIDATE_COUNT` controls the candidate count passed to each Chroma query and defaults to `5`. Retrieval is distinct from final evidence selection: candidate count is not the number of chunks that must be shown or sent to the LLM.

For explicit multi-part questions, `RetrievalService._query_parts()` keeps the full query and splits explicit comma-, semicolon-, and newline-delimited parts. It does not split every occurrence of `and` or `or`, so meaningful phrases such as `health and safety requirements` remain intact. Retrieved candidates retain their query-part association.

### Relevance decision

`RetrievalService.select_relevant()` applies these deterministic rules:

1. Discard empty text, duplicate text, invalid distances, and non-finite distances.
2. Sort remaining candidates by ascending cosine distance.
3. Accept candidates within `RAG_DISTANCE_THRESHOLD`.
4. For the top-ranked candidate only, allow a bounded relaxation up to `RAG_DISTANCE_THRESHOLD + RAG_DISTANCE_RELAXATION` when all of the following hold:
   - the candidate is clearly separated from the next candidate by at least `RAG_MIN_DISTANCE_GAP`; and
   - the candidate has generic lexical grounding with meaningful terms from the query.
5. Do not treat a relative gap by itself as proof of relevance. This prevents the least-bad result from an entirely unrelated candidate set from becoming evidence.
6. Prefer evidence covering distinct query parts, then fill remaining capacity by rank.
7. Remove highly redundant chunks and enforce the maximum evidence and context-size limits.

The current defaults are:

```text
RAG_DISTANCE_THRESHOLD=0.60
RAG_DISTANCE_RELAXATION=0.05
RAG_MIN_DISTANCE_GAP=0.10
RAG_MAX_EVIDENCE=3
RAG_MAX_CONTEXT_CHARS=12000
```

There is no BM25, hybrid search, cross-encoder, semantic reranker, or additional relevance-classification LLM call in the current implementation.

## Conversation Context

`SessionMemoryService` is a bounded window service. Its default `max_messages` value is `6`, and it returns only the last six messages supplied by the caller. It is not long-term memory and does not maintain a user profile.

`ConversationQueryResolver` identifies likely dependent questions using generic references such as pronouns and continuation phrasing. For a dependent question with history, it sends a compact conversation-plus-question prompt to the configured LLM and requests only a standalone search query. It does not include retrieved document context and does not ask the model to answer the question.

The rewritten query is used only for vector retrieval. The original user question remains the question in the final answer-generation prompt. If rewriting fails or returns an empty string, the original question is used for retrieval.

## LLM Provider Boundary

`LLMProvider` is the provider-independent interface with a `generate(messages)` method. `OpenRouterClient` and `GroqClient` implement that interface using OpenAI-compatible chat-completion APIs.

- OpenRouter is the primary provider.
- Groq is the fallback provider.
- `FallbackLLMProvider` tries the primary provider first and invokes the fallback only for `LLMProviderError` failures.
- If both providers fail, it raises an `LLMProviderError` describing that both providers failed.
- Provider model names come from `LLM_MODEL` and `GROQ_MODEL`.
- The currently confirmed Groq model is `openai/gpt-oss-20b`.
- API keys come from `.env`; they must never be committed. `.env.example` contains placeholders only.

Groq non-2xx responses include the HTTP status and a bounded sanitized response body in the provider error. API keys are not included in that diagnostic text.

## Grounding and Provenance

The final generation prompt instructs the LLM to use only the selected document context, avoid assumptions, answer supported parts of multi-part questions, and identify unsupported parts. If the selector returns no evidence, the orchestrator returns an information-not-found response with no citations.

`ProvenanceService` maps each selected result to a citation using its metadata:

```text
source  <- metadata["source"] or a default source label
section <- metadata["section"] or "Policy"
text    <- selected result text
```

The API returns these as `Citation` objects. The Streamlit client does not independently choose or hide chunks; it displays the citations returned by the backend. This keeps LLM context, citations, and UI evidence consistent.

## Ingestion Flow

Ingestion remains separate from application startup:

```text
scripts/ingest_documents.py
  -> LocalDocumentLoader enumerates input/
  -> document_processing extracts text and chunks documents
  -> ChromaVectorStore embeds and persists chunks with metadata
```

The current chunking and document-processing implementation is unchanged by the chat retrieval and provider work.

## Configuration

`app/core/settings.py` loads `.env` with `python-dotenv`. The code defaults are:

```text
DOCUMENTS_DIR=<project>/input
COLLECTION_NAME=hr_policy_docs
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
RAG_DISTANCE_THRESHOLD=0.60
RAG_DISTANCE_RELAXATION=0.05
RAG_MIN_DISTANCE_GAP=0.10
RAG_CANDIDATE_COUNT=5
RAG_MAX_EVIDENCE=3
RAG_MAX_CONTEXT_CHARS=12000
OPENROUTER_API_KEY=""
GROQ_API_KEY=""
LLM_MODEL=openrouter/anthropic/claude-3.5-sonnet
GROQ_MODEL=llama-3.1-8b-instant
DATABASE_URL=sqlite:///./instance/knowlayer.db
STREAMLIT_API_BASE_URL=http://127.0.0.1:8000
ADMIN_USERNAME=admin
ADMIN_INITIAL_PASSWORD=""
DEFAULT_USER_PASSWORD=ChangeMe123!
AUTH_SECRET_KEY=change-this-development-secret
AUTH_TOKEN_EXPIRE_MINUTES=480
EMPLOYEE_ID_PREFIX=MSS
DEPARTMENT_ID_PREFIX=DEPT
PROJECT_ID_PREFIX=PROJ
DOCUMENT_ID_PREFIX=DOC
```

In the checked-in `.env.example`, `GROQ_MODEL` is overridden to `openai/gpt-oss-20b`, the confirmed available fallback model. Environment variables override the Python defaults.

## Testing

The test suite comprises **435 tests** across three layers:

- `tests/unit/` (46 files): domain logic, authorization engine, RBAC, business ID generation, retrieval selection, conversation resolution, profile, explorer, document access, project membership, role management, and 29 authorization-bypass regression tests.
- `tests/contract/` (15 files): FastAPI API contract tests, Streamlit page source audits, and chat authorization tests.
- `tests/integration/` (20 files): SQLite persistence, Chroma retrieval scoping, RAG authorization end-to-end, RBAC, authentication, business ID concurrency, and user management e2e.

Key test files for the authorization layer:
- `tests/unit/test_authorization_engine.py`: comprehensive coverage of `AuthorizationEngine` decisions.
- `tests/unit/test_authz_bypass_regression.py`: 29 targeted tests pinning the 15 authorization-bypass scenarios.
- `tests/contract/test_streamlit_management_pages.py`: source-level audits confirming no permission logic in Streamlit.

Tests use `InMemoryUnitOfWork` for unit and contract tests. Integration tests exercise the SQLAlchemy persistence layer against a real SQLite database and Chroma vector store. Run with:

```powershell
.\.venv\Scripts\python.exe -m compileall -q app streamlit_app tests
.\.venv\Scripts\python.exe -m pytest tests\unit tests\contract -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest tests\integration -q -p no:cacheprovider
```

## Extension Boundaries

The current architecture leaves these replaceable boundaries:

- Replace `ChromaVectorStore` without moving vector-store details into the use cases.
- Add document loaders without changing chat orchestration.
- Replace OpenRouter or Groq adapters while preserving `LLMProvider`.
- Replace Streamlit while preserving the FastAPI chat contract.
- Replace SQLite with PostgreSQL by changing `DATABASE_URL` and selecting the postgres configuration.

Authentication and authorization are part of the current MVP. The `AuthorizationEngine` is centralized and used by all routes and use cases; adding new permission types requires updating only `permission_catalog` and `rbac_seed`.

## SQL Organization Flow

The persistence factory selects the configured relational adapter and supplies a SQLAlchemy Unit of Work. Repository ports expose User, Department, Project, Document, UserProject, Role, and Permission operations without leaking SQLAlchemy into domain services. FastAPI dependencies construct use cases, routes translate domain failures into HTTP responses, and Streamlit pages use HTTP clients only.

Document registration stores a nullable project assignment. The document use case validates optional project scope, persists the active record, and can invoke the existing ingestion handler. Archiving changes lifecycle status rather than removing project history. During chat, authorization resolves the active project set before the retrieval adapter receives project filters; the LLM sees only selected evidence and citations are built from that same evidence.

Detailed sequence guides are maintained in [Documentation/Workflows/README.md](Documentation/Workflows/README.md).

Authentication is a replaceable domain boundary. A configured bootstrap operation creates one Admin account, the authentication service verifies PBKDF2 password representations and issues signed bearer tokens, and FastAPI resolves those tokens into trusted principals before protected operations. Streamlit stores only the returned session state and calls the authentication endpoints over HTTP.

## Security Review

A comprehensive authorization review was performed on 2026-09-15. Four genuine defects were identified and fixed:

1. **Privilege escalation via role change**: non-admin could change own or others' roles to `admin` via `update_user`. Fixed by adding an admin-only guard.
2. **Manager can create admin users**: `create_user` allowed managers to set `role="admin"`. Fixed by adding an admin-only guard.
3. **User enumeration via 404/403 split**: `update_user` returned 404 for missing targets before scope check for non-admin actors. Fixed by returning 403 for out-of-scope missing targets.
4. **Document grant escalates into whole-project retrieval**: a single document grant in a project was sufficient to retrieve the entire project corpus via selected-project chat. Fixed by scoping the retrieval to granted documents only.

Full report: [Documentation/Workflows/security-authorization-review.md](Documentation/Workflows/security-authorization-review.md).
