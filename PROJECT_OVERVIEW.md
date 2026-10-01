# KnowLayer (`Company_Bot`) — Codebase Reference for LLM Agents

> **Purpose of this file.** This is a single, self-contained orientation document. Read it before
> touching the repository. It describes *what is actually implemented*, *how it is architected*,
> *what flows through it*, and — critically — **what exists as code but is NOT wired into the live
> runtime path**, so that you do not mistake built-but-unused capability for working behaviour.
>
> Every claim here was verified by reading the source at the referenced path. Where the repository's
> own docs (`README.md`, `ARCHITECTURE.md`, `Documentation/`) disagree with the code, **the code wins**
> and the divergence is called out.

---

## Table of Contents

1. [What This Project Is](#1-what-this-project-is)
2. [Repository Layout](#2-repository-layout)
3. [Technology Stack](#3-technology-stack)
4. [Architecture Style](#4-architecture-style)
5. [Layer-by-Layer Breakdown](#5-layer-by-layer-breakdown)
6. [The RAG / Chat Pipeline (most important flow)](#6-the-rag--chat-pipeline-most-important-flow)
7. [Authentication](#7-authentication)
8. [Authorization & RBAC Model](#8-authorization--rbac-model)
9. [Persistence & Data Model](#9-persistence--data-model)
10. [Caching Architecture](#10-caching-architecture)
11. [LLM Provider Layer](#11-llm-provider-layer)
12. [Observability & Tracing](#12-observability--tracing)
13. [Document Ingestion](#13-document-ingestion)
14. [API Surface (complete endpoint list)](#14-api-surface-complete-endpoint-list)
15. [Streamlit Admin UI](#15-streamlit-admin-ui)
16. [Configuration (every environment variable)](#16-configuration-every-environment-variable)
17. [Prompts](#17-prompts)
18. [Scripts & Operations](#18-scripts--operations)
19. [Test Suite](#19-test-suite)
20. [Implemented vs. Unwired — Critical Reading](#20-implemented-vs-unwired--critical-reading)
21. [Known Issues, Risks & Bugs](#21-known-issues-risks--bugs)
22. [Glossary](#22-glossary)

---

## 1. What This Project Is

**KnowLayer** is an internal **enterprise knowledge-assistant / RAG (Retrieval-Augmented Generation)
platform for HR policy documents**, wrapped in a full **organization-management and role-based
access-control (RBAC) system**.

Two things live in one repository:

1. **A RAG chatbot.** Users ask questions in natural language about HR policy documents (`.docx`,
   `.txt`, `.md`, `.rst`). The system retrieves semantically relevant chunks from a local ChromaDB
   vector store, filters them **by the asker's authorization scope**, builds a bounded prompt from
   the surviving evidence, and asks an LLM to answer *only* from that context. Answers carry
   citations back to the source document and section.

2. **An organization/RBAC admin platform.** Departments, projects, users, roles, permissions, and
   a two-axis access model (role permissions × project/document scope) that determines exactly which
   documents each person can retrieve through the chatbot.

The **governing design principle** is that the chatbot must never leak content the asker is not
authorized to see. Authorization is therefore resolved *before* retrieval, enforced again as a filter
inside the vector query, and — when content is found but withheld — the system returns a *templated,
non-LLM "ask your project manager" message that names no document content whatsoever*.

**It is not** a general-purpose document assistant, not multi-tenant, and not horizontally scaled
(all caches and the orchestrator are process-global singletons).

---

## 2. Repository Layout

```
Company_Bot/
├── app/                            # FastAPI backend — the entire domain lives here
│   ├── main.py                     # App entry, lifespan, router mounting, /health
│   ├── core/                       # settings.py (all env config), prompt_config.py, cache_quality.py
│   ├── api/                        # Delivery layer (NO __init__.py — namespace packages)
│   │   ├── dependencies.py         # Dependency-injection providers (the "container")
│   │   ├── routes/                 # chat, authentication, organization, roles, documents,
│   │   │                           #   explorer, tokens
│   │   └── schemas/                # Pydantic v2 request/response models
│   ├── domain/                     # PURE — zero framework dependencies
│   │   ├── entities/               # organization_models, document_models, conversation_log
│   │   ├── ports/                  # 9 Protocol/ABC contracts (hexagonal boundaries)
│   │   └── services/               # authorization_engine, authentication_service,
│   │                               #   permission_catalog, business_id_generator,
│   │                               #   session_memory_service, llm_provider,
│   │                               #   employee_id_provider, organization_errors
│   ├── use_cases/                  # Application logic / orchestration
│   │   ├── chat/                   # query_orchestrator (the core), retrieval_service,
│   │   │                           #   query_normalizer, query_intent_classifier,
│   │   │                           #   retrieval_quality, conversation_query_resolver,
│   │   │                           #   rag_context_builder, provenance_service
│   │   ├── organization/           # 10 services: user, project, department, membership,
│   │   │                           #   role, document, project_access, document_access,
│   │   │                           #   profile, organization_explorer
│   │   └── ingestion/document_processing.py
│   └── infrastructure/             # All adapters
│       ├── llm/                    # openrouter, groq, fallback, health, error tracker,
│       │                           #   llm_response, prompt_cache, json_semantic_cache
│       ├── cache/                  # quality_aware_cache, dual_cache
│       ├── faq/                    # faq_similarity_cache, json_faq_cache, mongo_faq_store
│       ├── observability/          # manager, langfuse, phoenix, null, pipeline_tracer,
│       │                           #   token_tracker, tracer, langsmith_integration
│       ├── persistence/            # factory, sqlalchemy/{models,foundation_models,
│       │   │                       #   repositories,session,unit_of_work}, rbac_seed,
│       │   │                       #   postgres/, sqlite/, migrations/*.sql
│       ├── authentication/         # password_hasher, bootstrap
│       ├── audit/                  # authentication_events
│       ├── document/               # local_document_loader
│       ├── ingestion/              # provisioner
│       ├── session/                # in_memory_store
│       ├── vector/                 # chroma_client
│       └── logging/                # conversation_logger, conversation_log_cleanup,
│                                   #   database_employee_id_provider
├── streamlit_app/                  # Admin UI (9 pages, 8 HTTP client modules)
├── scripts/                        # dump_db, ingest_documents, provision_demo, seed_faq_cache
├── config/prompts.yaml             # The ONLY externalized prompt
├── data/                           # faqs.json, seeded_users.json, runtime caches
├── input/                          # Source .docx files to ingest
├── .chroma/                        # Local ChromaDB persistent store (gitignored)
├── instance/                       # SQLite file knowlayer.db3 (gitignored)
├── conversation_logs/              # JSON audit logs (gitignored)
├── tests/                          # unit (53) / contract (18) / integration (19) + fixtures
├── docs/                           # DATABASE_SCHEMA.md, DATABASE_ERD.md, IMPLEMENTATION_NOTES.md
├── Documentation/                  # V2/V3 workflow guides, plans, team logs
├── specs/                          # Spec-Kit specs 001/002/003
├── .specify/                       # Spec-Kit tooling & constitution
├── .github/skills/                 # Spec-Kit agent skills (no CI workflows exist)
├── requirements.txt, setup.ps1, .env, .env.example, .gitignore
├── README.md                       # ⚠ 18 unresolved git merge-conflict markers
└── ARCHITECTURE.md                 # ⚠ 9 unresolved git merge-conflict markers
```

**Scale:** ~26,300 lines of Python across `app/`, `streamlit_app/`, `scripts/`, `tests/`.
Largest files: `query_orchestrator.py` (38 KB), `query_normalizer.py` (32 KB),
`quality_aware_cache.py` (26 KB), `repositories.py` (26 KB), `retrieval_quality.py` (23 KB),
`pipeline_tracer.py` (23 KB), `authorization_engine.py` (20 KB).

---

## 3. Technology Stack

| Concern | Choice | Notes |
|---|---|---|
| Web framework | **FastAPI** ≥0.110 | Sync handlers run in threadpool; one `async` handler (chat) |
| Validation | **Pydantic v2** ≥2.10 | `EmailStr` requires `email-validator` |
| ASGI server | **Uvicorn** ≥0.30 | Bound to `127.0.0.1:8000` |
| ORM | **SQLAlchemy 2.0** ≥2.0 | `DeclarativeBase`, `Mapped[...]` |
| Database | **SQLite** by default; PostgreSQL config present | `instance/knowlayer.db3` |
| Migrations | **No Alembic in the hot path.** `.sql` files are documentation; runtime uses `create_all()` + imperative ALTER/INDEX/table-rebuild | `alembic` is in requirements but unused |
| Auth | **PyJWT** ≥2.8 (HS256), PBKDF2-HMAC-SHA256 password hashing | Implemented in-house, no auth library |
| Vector store | **ChromaDB** ≥0.5, `PersistentClient`, cosine HNSW space | Local `.chroma/` dir |
| Embeddings | **sentence-transformers** `all-MiniLM-L6-v2` (384-dim) | Lazy-loaded |
| Primary LLM | **OpenRouter** (`https://openrouter.ai/api/v1/chat/completions`) | `LLM_MODEL` env |
| Fallback LLM | **Groq** (`https://api.groq.com/openai/v1/chat/completions`) | `GROQ_MODEL` env |
| HTTP for LLM | **httpx** ≥0.27 (persistent `httpx.Client`) | |
| Frontend | **Streamlit** ≥1.60 + `streamlit-cookies-controller` | Server-rendered, talks HTTP to FastAPI |
| Observability | LangSmith, Langfuse, Arize Phoenix, Null, in-house pipeline tracer | |
| Optional store | **MongoDB** (`pymongo`) for FAQ persistence | Disabled unless `MONGODB_URI` set |
| Semantic cache | **LangCache** (Redis-backed) + local JSON fallback | `langcache` is an *optional* import |
| Doc parsing | **python-docx** ≥1.1 | `.docx`, `.txt`, `.md`, `.rst` |
| Tests | **pytest** ≥8.2, `pytest-asyncio` ≥0.23 | |

---

## 4. Architecture Style

**Hexagonal / Ports-and-Adapters (Clean Architecture), enforced by convention, not by tooling.**

```
┌──────────────────────────────────────────────────────────────────┐
│  DELIVERY ADAPTERS                                                 │
│  streamlit_app/**  ──HTTP──►  app/api/routes/**  (FastAPI)         │
└────────────────────────────────┬─────────────────────────────────┘
                                 │  app/api/dependencies.py
                                 │  (FastAPI Depends = the DI container)
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│  APPLICATION / USE CASES            app/use_cases/**               │
│  query_orchestrator, retrieval_service, 10 org services           │
└────────────────────────────────┬─────────────────────────────────┘
                                 │  depends only on ports
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│  DOMAIN (PURE)                     app/domain/**                  │
│  entities/  ·  ports/ (9 Protocols)  ·  services/ (engine etc.)   │
│  NO FastAPI, NO SQLAlchemy, NO Chroma, NO httpx imports           │
└──────────────────────────────────────────────────────────────────┘
                                 ▲
┌──────────────────────────────────────────────────────────────────┐
│  ADAPTERS / INFRASTRUCTURE          app/infrastructure/**         │
│  SQLAlchemy · Chroma · OpenRouter · Groq · Mongo · PBKDF2 · JWT  │
└──────────────────────────────────────────────────────────────────┘
```

### The three kinds of "port"

| Kind | Files | Role |
|---|---|---|
| **Repository ports** | `organization_repositories.py` (10 protocols), `document_repository.py`, `sequence_repository.py` | Outbound persistence contracts |
| **Service/capability ports** | `authentication_service.py`, `authorization_service.py`, `retrieval.py`, `observability.py`, `session_store.py`, `llm_provider.py` (ABC), `employee_id_provider.py` (ABC) | Swappable outbound capabilities |
| **Unit of Work** | `unit_of_work.py` | Aggregate transactional boundary composing *all* repositories into one session |

`UnitOfWork` is the most important port in the codebase. Use cases **never** touch the database
except as `with uow_factory() as uow:`. This is what lets tests swap in `InMemoryUnitOfWork` with
zero production changes.

### Dependency-injection container

There is no DI framework. `app/api/dependencies.py` holds ~15 module-level provider functions used
as FastAPI `Depends`. Every provider **constructs fresh per-request objects** (a new
`SqlAlchemyUnitOfWork`, a new service instance). The only singletons in the whole system are the
chat-side components built inside `QueryOrchestrator.__init__`.

Because every provider is a plain function, `app.dependency_overrides[get_x] = lambda: ...` is the
universal test seam (heavily used in `tests/contract/`).

### Architectural principles actually honoured

- **Domain purity.** `app/domain/**` imports no framework. The only exception is a *lazy* import of
  `InMemorySessionStore` inside `SessionMemoryService.__init__` when no store is injected.
- **Authorization in one place.** Every authorization decision is routed through
  `app/domain/services/authorization_engine.py`. Use cases call `can(...)` / `authorization_scope(...)`.
- **Transaction discipline.** Repositories call `session.flush()`, never `session.commit()`. Only the
  use case commits, once, at the end of its `with` block.
- **Defensive mapping at the edge.** Domain exceptions (`NotFoundError`, `ConflictError`,
  `ForbiddenError`, `AuthenticationError`, `PersistenceError`) are mapped to HTTP codes in the route
  modules by a small `_error()` helper.
- **Graceful degradation over failure** is preferred throughout: LLM outage → citation-only answer;
  Mongo down → no-op; Langfuse down → self-disable; embedding model load is lazy.

---

## 5. Layer-by-Layer Breakdown

### 5.1 `app/main.py` — Entry point

```python
app = FastAPI(title="KnowLayer API", lifespan=lifespan)
app.include_router(chat_router)             # prefix /api,  tag chat
app.include_router(tokens_router)           # /api/tokens
app.include_router(organization_router)     # /api
app.include_router(explorer_router)         # /api
app.include_router(documents_router)        # /api
app.include_router(authentication_router)   # /api/auth
app.include_router(roles_router)            # /api

@app.get("/health")
async def health(): return {"status": "ok"}
```

**Lifespan startup sequence:**

1. Synchronous one-shot `ConversationLogCleanup().cleanup_expired_logs()` — deletes conversation-log
   JSON older than `CONVERSATION_LOG_RETENTION_DAYS` (default 30). Failures are logged and swallowed.
2. `initialize_persistence(get_session_factory)` — creates the engine, runs `Base.metadata.create_all()`,
   applies the imperative SQLite migration pass, seeds the bootstrap admin and the RBAC catalog.
   **Retries 3× with 0.5 s sleeps, then raises `RuntimeError` — this is fatal to startup.**
3. `init_orchestrator()` — builds the process-wide `QueryOrchestrator` singleton. This loads Chroma
   clients, the sentence-transformer model, OpenRouter + Groq clients, the Mongo FAQ store, and the
   FAQ similarity cache. **Not guarded — fatal on failure.**
4. Spawns `periodic_log_cleanup_task()` (async loop, default 24 h interval, uses `asyncio.to_thread`).

**Shutdown:** cancels the cleanup task, swallows `CancelledError`.

> ⚠ **There is no middleware stack.** No CORS, no rate limiting, no request-ID/correlation-ID, no
> access-log middleware, no custom exception handlers, no WebSockets. Verified by exhaustive search:
> `add_middleware` → 0 matches, `CORSMiddleware` → 0, `slowapi`/`Limiter` → 0. The API is therefore
> only callable same-origin/server-side — which is fine for the Streamlit client but blocks a
> browser SPA.

### 5.2 `app/api/dependencies.py` — The DI container

Key providers and what they build:

| Provider | Builds |
|---|---|
| `get_current_principal(request, auth_service)` | **`AuthenticatedPrincipal`** or 401. Reads `request.state.principal` first (a vestigial hook nothing populates), then falls back to `Authorization: Bearer <token>` → `auth_service.resolve_token()`. **Explicitly rejects `token_type == "refresh"`.** |
| `get_chat_principal(...)` | Optional auth: swallows the 401, returns `None` |
| `get_authentication_service()` | `AuthenticationServiceImpl(create_unit_of_work, PasswordHasher(), AUTH_SECRET_KEY)` |
| `get_authorization_service()` | `OrganizationAuthorizationService(create_unit_of_work())` — a thin facade over `AuthorizationEngine` |
| `get_business_id_generator()` | `BusinessIdGenerator` with 4 registered sequences: `user`(`MSS`), `department`(`DEPT`), `project`(`PROJ`), `document`(`DOC`) |
| `get_user_management_service()` | `UserManagementService(uow, PasswordHasher(), business_id_generator)` |
| `get_document_management_service()` | `DocumentManagementService(uow, provision_document, remove_document, business_id_generator)` — the **only** service with side-effect handlers |
| `get_document_access_service()` / `get_project_access_service()` | `...Service(uow, AuthorizationEngine(create_unit_of_work))` |
| `get_role_management_service()` | `RoleManagementService(uow, get_authorization_service())` |
| `get_profile_service()`, `get_organization_explorer_service()`, `get_membership_management_service()`, `get_department_membership_service()`, `get_project_management_service()` | direct |

> ⚠ **Note:** `AuthorizationEngine` opens its **own** UoW per decision (it takes a *factory*). So
> `ProfileService`/`OrganizationExplorerService` issue one extra transaction per per-item check.

### 5.3 `app/api/routes/*` — the delivery layer

Uniform handler idiom used across `organization.py`, `roles.py`, `documents.py`:

```python
def _error(error):
    if isinstance(error, ConflictError):  return HTTPException(409, detail=str(error))
    if isinstance(error, NotFoundError):   return HTTPException(404, detail=str(error))
    if isinstance(error, ForbiddenError):  return HTTPException(403, detail=str(error))
    return HTTPException(400, detail=str(error))

@router.get("/thing")
def get_thing(principal = Depends(get_current_principal),
              service   = Depends(get_x_service)):
    try:
        return service.do_thing(principal.uid)
    except Exception as error:
        raise _error(error) from error
```

Handlers are **sync `def`**, so FastAPI runs them in the threadpool and blocking SQLAlchemy is fine.
The chat handler is the one `async def`, using `asyncio.to_thread` for the orchestrator.

**Two coexisting principal conventions:** most endpoints pass `principal.uid` (the use case
re-looks-up the actor inside its own UoW), while document/project-access/profile/explorer/chat pass
the whole `AuthenticatedPrincipal` object so the use case can drive `AuthorizationEngine` directly.

### 5.4 `app/api/schemas/*` — Pydantic v2 models

All response models that serialize domain dataclasses set `model_config = ConfigDict(from_attributes=True)`.

Notable validation rules:
- `UserCreate.email: EmailStr`, `UserCreate.initial_password` min-length 8.
- `ChangePasswordRequest.new_password` min-length 8; `uid: str | None` is the **admin-impersonation switch**.
- Regex-constrained enums-as-strings: `^(billable|non-billable|both)$` (department default billable),
  `^(active|inactive)$` (user/department status), `^(active|inactive|completed|archived)$` (project status),
  `^(role|user)$` (grant principal_type).
- `ChatRequest.session_id` defaults to the non-random literal `"default-session"` — **all clients that
  omit it share one session bucket.**

### 5.5 `app/domain/entities/organization_models.py` — the aggregate model

All `@dataclass(slots=True)` with a shared `utc_now()` (`datetime.now(timezone.utc)`) factory.

| Entity | Notable fields |
|---|---|
| `User` | `uid`, `username`, `name`, `email`, `role`, `department_id`, `status`, `password_representation`, `password_changed_at`, `must_change_password`, `employee_id`, `first_name`, `last_name`. `__post_init__` defaults `username = uid`. |
| `Department` | `department_id`, `department_name`, `status`, `description`, `default_billable` |
| `Project` | `project_id`, `project_name`, `department_id`, `status`, `description`, **`manager_uid`** (the project lead — key to the "WHERE" authorization axis), `start_date`, `end_date`, `created_by_uid`, `internal_id` |
| `Document` | `document_id`, `document_name`, **`project_id: Optional[str] = None`** (nullable = org-wide/unassigned), `status`, `original_filename`, `file_type`, `version`, `storage_location`, `uploaded_by`, `uploaded_at` |
| `UserProject` | `uid`, `project_id`, `assigned_by_uid`, `status`, `assigned_at`, `membership_role`, `left_at` |
| `DepartmentMember` | `user_id`, `department_id`, `membership_role`, `billable_status`, `assigned_by_uid`, `status`, `assigned_at`, `left_at` |
| `Permission` / `Role` | `Role.scope: "global" | "department"` and `Role.department_id` — the tenant-isolation dimension |
| `ProjectGrant` | `project_id`, `principal_type: "role"|"user"`, `role_id?`, `user_id?`, `granted_by_uid`, `status` |
| `DocumentGrant` | `document_id`, `principal_type`, `permission="read"`, `role_id?`, `user_id?`, `granted_by_uid`, `status` |

Both grant types use a **polymorphic principal** — one table shape serves "grant to a role" and
"grant to a user".

`document_models.py` (`DocumentSource`, `DocumentChunk`, `VectorRecord`, `Message`, `QuerySession`,
`RetrievedEvidence`, `AnswerResponse`) is an **older, currently-unused** retrieval-pipeline model set.
The live pipeline passes plain dicts `{text, metadata, distance}`.

`conversation_log.py` uses Pydantic (`ConversationMessage`, `ConversationLog`) because it is a
serialization boundary for the JSON audit file. It is deliberately keyed by **`employee_id`**, not `uid`.

### 5.6 `app/domain/services/*` — domain services

| File | Contents |
|---|---|
| `organization_errors.py` | `OrganizationError` → `NotFoundError`(404), `ConflictError`(409), `ForbiddenError`(403), `AuthenticationError`(401), `PersistenceError`(500) |
| `permission_catalog.py` | Seed definitions **only**. 25 permissions in 5 groups (User×4, Department×4, Project×6, Document×6, Role/Permission×5) and 5 initial roles (Admin=`*`, Manager, Developer, Tester, Solution Architect). Its docstring states explicitly: *"Nothing here is consulted when authorizing a request"* — the DB is the source of truth. |
| `authorization_engine.py` | **The security core.** See §8. |
| `authorization_service.py` | `OrganizationAuthorizationService` — a pure pass-through facade over `AuthorizationEngine`, kept only to preserve the DI signature. |
| `authentication_service.py` | `AuthenticationServiceImpl` — see §7. |
| `business_id_generator.py` | Monotonic, never-reused human IDs (`MSS-001`, `DEPT-001`, `PROJ-001`, `DOC-001`). Sequence keys: `user`, `department`, `project`, `document`. Lazy one-shot seeding from the highest existing suffix; thereafter the `business_id_sequences` table is authoritative and **independent of the data rows**, so numbers are never recycled after deletion. `threading.Lock` guards only the registry, not the counter. |
| `session_memory_service.py` | Sliding-window conversation memory: **6 turns (= 12 messages)** by default, 12 h inactivity TTL, cross-user ownership isolation. Depends on `SessionStorePort`. |
| `llm_provider.py` | `LLMProviderError` + `LLMProvider` **ABC** (the only nominal, not structural, port — deliberate, it's the vendor-swap boundary) |
| `employee_id_provider.py` | `EmployeeIdProvider` **ABC** — documented as a *temporary* boundary pending a trusted IdP |

### 5.7 `app/use_cases/organization/*` — 10 use-case services

All take `unit_of_work_factory: Callable` as the first constructor argument and open their own
transactions. Scope-check pattern is consistent: `_scope(uow, actor_uid, ...)` / `_actor(uow, principal)`
/ `_require_active(uow, actor_uid)` at the top of every method.

| Service | Methods |
|---|---|
| `UserManagementService` | `create_department`, `list_departments`, `get_department`, `update_department`, `create_user`, `get_user`, `list_users`, `update_user`, `deactivate_user` |
| `ProjectManagementService` | `create_project`, `get_project`, `update_project`, `list_projects` |
| `MembershipManagementService` | `assign`, `revoke`, `leave`, `list_members` (project membership) |
| `DepartmentMembershipService` | `assign`, `list_for_department`, `list_for_user`, `update`, `leave` |
| `RoleManagementService` | `list_permissions`, `create_permission`, `list_roles`, `get_role`, `list_role_permissions`, `create_role`, `update_role`, `set_role_permissions`, `delete_role`, `effective_permissions`, `roles_for_user` |
| `DocumentManagementService` | `list_documents`, `list_project_documents`, `register_document`, `register_project_document` *(not route-exposed)*, `delete_document` (soft archive) |
| `DocumentAccessService` | `grant`, `list`, `revoke` |
| `ProjectAccessService` | `grant`, `list`, `revoke` |
| `ProfileService` | `get_profile` — assembles the read-only self-service view (personal info, projects, documents, permissions, access-source labels) |
| `OrganizationExplorerService` | `get_organization` — the authorization-scoped org-chart + accessible-documents tree for the UI |

### 5.8 `app/infrastructure/*` — adapters

See §9–§13. Key point: **every outward-facing technology lives here and nowhere else**, so swapping
the vector store or the LLM vendor touches exactly one package.

---

## 6. The RAG / Chat Pipeline (most important flow)

### 6.1 Entry point: `POST /api/chat`

`app/api/routes/chat.py`:

```python
@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest,
               principal     = Depends(get_chat_principal),      # optional auth
               authorization = Depends(get_authorization_service)):
    # 1. Build the authorization scope (three distinct behaviours)
    if principal is not None:
        scope = authorization.authorization_scope(principal, request.project_id)
        if request.project_id is not None and scope.project_ids == [] and not scope.document_ids:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        scope = AuthorizationScope(is_admin=False, project_ids=[], document_ids=None,
                                   include_unassigned=True)

    # 2. Three-tier orchestrator resolution (test-injected instance → test-patched class → global)
    # 3. Signature-introspecting dispatch: only pass kwargs the target accepts
    result = await asyncio.to_thread(active_orchestrator.answer, request.question, **kwargs)
```

Behaviour matrix:

| Caller | `project_id` supplied | Result |
|---|---|---|
| Authenticated | no | Engine-computed scope (may legitimately be empty → grounded "no access" answer, not 403) |
| Authenticated | yes, has access | Scope narrowed to that project |
| Authenticated | yes, **no** access | **HTTP 403 `"Access denied"`** before any retrieval |
| Anonymous | no | Org-wide unassigned docs only |

On `LLMProviderError` the route returns **HTTP 200 with a friendly degraded message** rather than 5xx.
All other exceptions propagate to 500.

Response mapping: `result["tokens"]` → `TokenUsageInfo`; evidence → `Citation(source, section, text)`
with `"Policy"` fallbacks.

### 6.2 `QueryOrchestrator.answer()` — the 871-line core

File: `app/use_cases/chat/query_orchestrator.py`. Decorated `@traceable(name="QueryOrchestrator.answer", run_type="chain")`.

Signature:
```python
def answer(self, question, conversation_history=None, session_id="default",
           authorized_project_ids=None, authorization_scope=None,
           defer_citations=False, user_context=None, question_timestamp=None) -> dict
```

Collaborators constructed in `__init__` (all injectable, all defaulting to real adapters):
`RetrievalService`, `ProvenanceService`, `MongoFAQStore`, `FAQSimilarityCache`, `RAGContextBuilder`,
`QueryNormalizer`, `PipelineTracer`, `ConversationLogger` (+ `DatabaseEmployeeIdProvider`),
`FallbackLLMProvider(primary=OpenRouterClient(), fallback=GroqClient())`,
`ConversationQueryResolver(llm, memory=SessionMemoryService())`.

**Stage-by-stage:**

| Stage | What happens |
|---|---|
| **0a. Not-relevant feedback** | If the previous assistant turn asked "Was this response relevant to your question?" and the user says no → **clear `response_cache` and the LLM prompt cache**, then (once per question) re-retrieve more broadly and generate one *alternative* answer. |
| **0b. Relevant feedback** | If the user says yes/relevant → return the **stashed** `_pending_citations[session_id]` with `show_citations: True`. |
| **0c. Legacy references flow** | If the previous turn offered "references" and the user says yes → return stashed citations; no → acknowledge and drop. |
| **1. Normalization** | `self.query_normalizer.normalize(question)` → `NormalizationResult(normalized_query, cache_key)`. Both are used downstream. |
| **2. Response cache read** | `response_cache.get(cache_key)`, falling back to `get(question)`. **Quality gate on read:** if `is_negative_response(answer)` the entry is *evicted and treated as a miss*. On hit, returns `cache_hit: True` with all-zero tokens and stashes citations. |
| **3. FAQ cache** | Only consulted when **no** `response_cache` **and** no authorization scoping is in play. Cosine ≥ `FAQ_SIMILARITY_THRESHOLD` (0.92) against `data/faqs.json`. Negative matches are discarded. |
| **4. Query resolution** | `self.query_resolver.resolve(processed_query, conversation_history)` — rewrites pronoun/ellipsis-dependent questions using history. |
| **5. Scope → filter translation** | Builds `retrieval_kwargs` = `{top_k, authorized_project_ids, authorized_document_ids, include_unassigned}`. Admins are left completely unfiltered. |
| **6. Retrieval** | `self._retrieve(...)` → `RetrievalService.retrieve` → `ChromaVectorStore.query`. |
| **6b. Unauthorized-relevance probe** | If retrieval returned *nothing*, `RetrievalService.detect_unauthorized_relevance` runs an **unrestricted** Chroma query and keeps only candidates that (a) pass the distance threshold, (b) have lexical grounding, and (c) are outside the scope. If found → return a **templated, non-LLM "contact the project manager" message** that includes only `project_id`/`document_id`/`source`/`distance` — never text. See §6.3. |
| **7. No evidence** | `"I could not find that information in the available documents."` + relevance prompt. |
| **8. Prompt build** | `self.context_builder.build_messages(question, context_chunks, include_system_prompt=True)` → `[system, user]` using `config/prompts.yaml`. |
| **9. Citations** | `self.provenance.build_citations(selected_evidence)` — derived from the **same** evidence that went into the prompt. |
| **10. Generation** | `self._generate(messages, session_id)` — temporarily sets `llm.session_id`, restores in `finally`. |
| **10b. LLM outage fallback** | On **any** exception: concatenate the first 3 citations into one paragraph and return it as the answer with `citations: []`. Never 500. |
| **11. Write-through** | Non-negative answers are saved to `faq_store` (Mongo) and `response_cache` (under both `cache_key` and the raw question). **Negative answers are never written.** |
| **12. Token accounting** | `llm.get_last_tokens()` (or `llm.primary.get_last_tokens()`), then best-effort `add_tokens_to_current_run(...)` for LangSmith. |
| **13. State stash** | Rewrites `"Would you like to see the references for this?"` → the relevance prompt, then stores `_pending_citations`, `_last_interaction`, and resets `_alternative_answer_given` for this `session_id`. |
| **14. Return** | Honours `defer_citations` (Streamlit sends `True` so the UI can render citations as a blockquote and the follow-up flow can trigger). |

Every return path is wrapped in `_finish(res)`, which (a) writes the conversation JSON log and
(b) attaches `cache_hit`/`has_citations` metadata to the LangSmith run.

**Module-level mutable state (per-process, keyed by `session_id`):** `_pending_citations`,
`_last_interaction`, `_alternative_answer_given`. These are **not** TTL'd and not bounded — a
long-running process accumulates them. They are also the reason the follow-up flow is
single-instance-only (won't work across multiple workers).

**Other method:** `generate_faqs()` — duck-typed over `faq_cache.load/get/read`, retrieves
`"frequently asked questions HR policies"`, asks the LLM for 5 FAQs, caches the result.

Private helpers `_faq_search`, `_retrieve`, `_generate` are each `@traceable`-decorated
(`run_type="retriever"`, `"retriever"`, `"llm"`).

### 6.3 The unauthorized-relevance probe (a distinctive feature)

`RetrievalService.detect_unauthorized_relevance` (`retrieval_service.py:87`):

> *"Probe the full corpus for content relevant to the query that lies outside the principal's
> authorized scope… Returns **redacted** hits only — no document text and no full metadata — enough
> to build an access-request response without ever exposing document content to the caller or the LLM."*

```python
# early-out: authorized_project_ids=None means admin/unrestricted -> nothing can be out of scope
if authorized_project_ids is None:
    return []
candidates = self.store.query(query_text, top_k=top_k)   # UNRESTRICTED query
# keep only: distance <= RAG_DISTANCE_THRESHOLD  AND  lexical grounding  AND  out-of-scope
hits.append({"project_id": ..., "document_id": ..., "source": ..., "distance": ...})
```

`QueryOrchestrator._access_denied_response` then renders, with no LLM call:

> *"Relevant information exists in a project document that you do not currently have access to.
> Please contact {manager_name}, the manager of {project_name}, to request access."*

The manager name comes from `AuthorizationEngine.project_access_contact(project_id)`, which returns
`{project_id, project_name, manager_name}` — **contact metadata only, never content.**

### 6.4 `RetrievalService` — evidence selection

`app/use_cases/chat/retrieval_service.py`.

**Filter construction** (`retrieve`, lines 40–65):
```python
project_ids_for_filter = None
if authorized_project_ids is not None:
    scoped = sorted(set(authorized_project_ids) | ({"unassigned"} if include_unassigned else set()))
    project_ids_for_filter = scoped
if authorized_document_ids:
    document_filter = {"document_id": {"$in": list(authorized_document_ids)}}
    where_filter = {"$or": [{"project_id": {"$in": project_ids_for_filter}}, document_filter]} \
                   if project_ids_for_filter else document_filter
```

**`select_relevant` — the ranking algorithm** (static, lines 156–244):
1. Dedupe by exact chunk text.
2. Keep only candidates with a finite numeric `distance`; sort ascending (Chroma cosine distance: lower = closer).
3. Accept if `distance <= RAG_DISTANCE_THRESHOLD` (0.60) **OR** the candidate is a *separated top
   candidate* — index 0, within `+RAG_DISTANCE_RELAXATION` (0.05) of the threshold, separated from
   the runner-up by at least `RAG_MIN_DISTANCE_GAP` (0.10), and lexically grounded.
4. Coverage pass: prefer one chunk per `_query_part_index` (multi-part queries).
5. Fill pass up to `RAG_MAX_EVIDENCE` (4).
6. Redundancy filter: `_is_redundant` — token-set overlap / min(size) ≥ 0.90 ⇒ drop.
7. Context budget: truncate once cumulative `len(text) + 2` would exceed `RAG_MAX_CONTEXT_CHARS` (12000).

`_has_lexical_grounding` lowercases, strips a 30-word stopword set, singularizes trailing `s` on
tokens longer than 3 chars, and requires a non-empty query∩chunk term intersection.

### 6.5 `QueryNormalizer` — 31 KB, the most feature-rich support module

`app/use_cases/chat/query_normalizer.py`. Singleton via `get_query_normalizer()`.

Produces a `NormalizationResult` with the normalized query **and a canonical `cache_key`**, so
"what did the user mean" and "what do we cache under" are decided together.

Pipeline stages, each returning `(text, applied_rules)`:
`_clean_text` → `_normalize_unicode` → `_handle_punctuation` → `_fix_word_boundaries` →
`_fix_keyboard_layout` (QWERTY-adjacent substitution) → `_correct_typos` (Levenshtein ≤ 2 against a
domain vocabulary) → `_spellcheck` → `_identify_entities` (preserved from lemmatization) →
`_apply_vocabulary` → `_lemmatize` → `_generate_cache_key`.

Public surface: `add_vocabulary(words)`, `learn_document(text)` (builds vocabulary from corpus),
`normalize(query)`, `is_semantically_equivalent(q1, q2)`.

Toggles: `ENABLE_QUERY_NORMALIZATION`, `QUERY_NORMALIZER_TYPO_CORRECTION`,
`QUERY_NORMALIZER_VOCABULARY`, `QUERY_NORMALIZER_EXPANSION` (default **false**).

### 6.6 `RAGContextBuilder` — prompt assembly

`app/use_cases/chat/rag_context_builder.py`:
- `load_prompts()` (module-level, once) reads `config/prompts.yaml` via `yaml.safe_load`; returns `{}` on failure.
- `build_system_prompt()` → `prompts["prompts"]["rag_answer_generation"]["system_prompt"]`, hardcoded fallback on any failure.
- `build_user_prompt(question, context_chunks, include_references=True)` — uses `question_template`
  (`<user_question>{question}</user_question>` — the XML-tag prompt-injection defense), wraps it in
  `"\nQuestion: …"`, appends `user_instructions`, and prefixes the joined context chunks.
- `build_messages(...)` → `[{"role":"system",…},{"role":"user",…}]`
- `format_evidence_for_citations(chunks)` (static) — maps chunk metadata to citation dicts with
  `"Unknown Section"` / `"HR Policy Handbook"` / `"Document Reference"` fallbacks.

`ProvenanceService` is a 1-method class: `build_citations(results)` → `[{source, section, text}]`.

`ConversationQueryResolver` — `resolve(question, history)` rewrites dependent questions (pronouns,
ellipsis) using history via the LLM; `_is_dependent()` gates when rewriting happens at all.

---

## 7. Authentication

Implemented in-house. No auth library.

### 7.1 `AuthenticationServiceImpl` (`app/domain/services/authentication_service.py`)

```python
AuthenticationServiceImpl(unit_of_work_factory, password_hasher, secret_key,
                          access_token_expires_minutes=480, refresh_token_expires_minutes=10080)
```

| Method | Behaviour |
|---|---|
| `authenticate(identifier, password)` | Looks up by **username, then email**. Three failure modes — unknown user / non-active user / bad password — all raise the *identical* `AuthenticationError("Invalid credentials")` (**no user-enumeration oracle**), but log three distinct `warning` lines server-side. On success issues a fresh access **and** refresh token. |
| `resolve_token(token)` | HS256 decode. **Rejects `token_type == "refresh"`** so a refresh token can never authenticate a request. Requires `sub`. |
| `refresh_access_token(refresh_token)` | Requires `token_type == "refresh"`, **re-checks the user still exists and is `active`**, returns a **rotated pair** `(uid, new_access, new_refresh)`. No denylist — old refresh tokens stay valid until expiry. |
| `change_password(principal, current, new)` | Requires `len(new) >= 8`, re-verifies current, sets `password_changed_at`, clears `must_change_password`. |
| `admin_change_password(actor, target_uid, new)` | Requires `actor.role.casefold() == "admin"` else `ForbiddenError`. Sets `must_change_password = True` on the target. |

**JWT claim shape:** `{sub: uid, token_type: "access"|"refresh", iat, exp, jti: uuid4().hex}`, HS256.

### 7.2 Password hashing (`app/infrastructure/authentication/password_hasher.py`)

PBKDF2-HMAC-SHA256 with a per-password salt, stored in a `pbkdf2_sha256$iterations$salt$hash` string.
`DEFAULT_USER_PASSWORD = "ChangeMe123!"` is the fallback password when a created user supplies none.

### 7.3 Bootstrap (`app/infrastructure/authentication/bootstrap.py` + `persistence/rbac_seed.py`)

On first startup, `get_session_factory()` (an `lru_cache(maxsize=1)`) creates the schema, then:
1. `bootstrap_admin(uow_factory, PasswordHasher())` — creates the `admin` user from
   `ADMIN_USERNAME` / `ADMIN_INITIAL_PASSWORD` if absent.
2. `seed_rbac(uow_factory)` — writes the 25 permissions and 5 initial roles from
   `permission_catalog.py` if absent.

### 7.4 Endpoints (`app/api/routes/authentication.py`, prefix `/api/auth`)

| Method | Path | Auth | Success | Notes |
|---|---|---|---|---|
| POST | `/login` | — | 200 | `LoginRequest` → `LoginResponse`; returns `access_token`, `refresh_token`, `uid`, `must_change_password`. All failures → generic 401. |
| POST | `/refresh` | — | 200 | `RefreshRequest` → `RefreshResponse`; rotates the pair; re-validates user active. |
| POST | `/change-password` | principal | 204 | Dual mode: omit `uid` → self-service (needs `current_password`); set `uid` != caller → admin path (403 if not admin). |
| POST | `/logout` | principal | 204 | **Audit event only — no server-side token invalidation.** |

> ⚠ `change_password` returns `detail=str(error)`, leaking internal messages ("Invalid credentials",
> "Admin access required", "User not found") to the client.
> ⚠ `must_change_password` is **advisory** — nothing on the server blocks other endpoints while it is set.

---

## 8. Authorization & RBAC Model

### 8.1 The two-axis thesis (verbatim from `authorization_engine.py`)

> *"Every authorization decision in the platform is resolved here and only here. System-level roles
> ('Admin', 'Manager', …) are **department-aware**: a manager only acts on projects/documents that
> belong to the manager's own department. Custom RBAC roles … grant **what** a user may do
> (permissions); the engine decides **where** they may do it via project membership, being the
> designated project lead, or an explicit ProjectGrant / DocumentGrant assigned to a role or a
> specific user."*

**AXIS 1 — WHAT:** 25 permissions in the `permissions` table, assigned to roles via `role_permissions`.
**AXIS 2 — WHERE:** project membership ∪ project-lead/manager authority ∪ explicit grants.

### 8.2 `ACTION_PERMISSIONS` — action string → permission name

A 24-entry translation table so use cases write `can(principal, "manage_document_access")` instead of
the magic string `"DOCUMENT_MANAGE_ACCESS"`. **Unknown actions return `False` (fail-closed).**

```python
"view_users"→USER_VIEW          "view_projects"→PROJECT_VIEW
"create_user"→USER_CREATE       "create_project"→PROJECT_CREATE
"update_user"→USER_UPDATE       "update_project"→PROJECT_UPDATE
"deactivate_user"→USER_DELETE   "delete_project"→PROJECT_DELETE
"view_departments"→DEPARTMENT_VIEW            "create_department"→DEPARTMENT_CREATE
"update_department"→DEPARTMENT_UPDATE         "assign_department_users"→DEPARTMENT_ASSIGN_USERS
"manage_project_members"→PROJECT_MANAGE_MEMBERS    "leave_project"→PROJECT_LEAVE
"view_documents"→DOCUMENT_VIEW  "upload_document"→DOCUMENT_UPLOAD
"update_document"→DOCUMENT_UPDATE  "delete_document"→DOCUMENT_DELETE
"query_documents"→DOCUMENT_QUERY     "manage_document_access"→DOCUMENT_MANAGE_ACCESS
"create_role"→ROLE_CREATE   "update_role"→ROLE_UPDATE   "delete_role"→ROLE_DELETE
"view_roles"→ROLE_VIEW      "manage_permissions"→PERMISSION_MANAGE
```

### 8.3 `AuthenticatedPrincipal` and `AuthorizationScope`

```python
@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    uid: str; token: str | None = None; must_change_password: bool = False
    refresh_token: str | None = None

@dataclass(frozen=True, slots=True)
class AuthorizationScope:
    """- project_ids=None  means UNRESTRICTED (admins only)
       - project_ids=[]    means DENY-ALL
       - document_ids      are per-document grants that go BEYOND project membership
       - include_unassigned authorizes organization-wide documents"""
    is_admin: bool = False
    project_ids: Optional[list[str]] = None
    document_ids: Optional[list[str]] = None
    include_unassigned: bool = False
```

**The `None` vs `[]` distinction is load-bearing.** `RetrievalService` only applies a Chroma filter when
`authorized_project_ids is not None`; `chroma_client.query` short-circuits on `project_ids == []` and
returns `[]`. Confusing the two would either leak the whole corpus or deny admins.

### 8.4 Role resolution — two sources, scoped

```python
def _roles_for_user(uow, uid):
    user = uow.users.get_by_uid(uid)
    if user is None or user.status != "active": return []
    candidates = []
    if user.role:                                   # (a) primary system role by NAME
        named = uow.roles.get_by_name(user.role)
        if named: candidates.append((named, user.department_id))
    for member in uow.department_members.list_for_user(uid):   # (b) dept membership roles
        if member.status != "active" or not member.membership_role: continue
        role = uow.roles.get_by_name(member.membership_role)
        if role: candidates.append((role, member.department_id))
    # dedupe by role_id; enforce department-scope guard:
    if role.scope == "department" and role.department_id not in (membership_dept, user.department_id):
        continue                                     # ← cannot self-grant via department membership
    return roles
```

`_permission_names`: admin reads the **actual `permissions` table** (not a wildcard), so even admin is
bound to the configured catalog.

### 8.5 Project-management: a strict three-tier rule

```python
def _can_manage_project(uow, user, project) -> bool:
    if user.role.casefold() == "admin":     return True
    if user.role.casefold() == "manager" and user.department_id == project.department_id: return True
    return project.manager_uid == user.uid
```
**Admin (global) → same-department manager → designated project lead.**

### 8.6 Retrieval scope: deliberately strict

```python
def _project_access_scope(uow, user) -> set[str]:
    """Strict retrieval scope: memberships, leads, grants.
    Deliberately does not grant every project in the user's department;
    a Developer may only see projects they were actually assigned to or explicitly granted."""
    project_ids = {m.project_id for m in uow.memberships.list_for_user(user.uid) if m.status == "active"}
    for project in uow.projects.list_active():
        if self._can_manage_project(uow, user, project): project_ids.add(project.project_id)
    project_ids.update(uow.project_grants.project_ids_for_principal(user.uid, self._role_ids(uow, user)))
    return project_ids
```

> Note the contrast with the looser, "backwards-compatible" `authorized_project_ids()` which uses a
> broader membership-derived set. **`_project_access_scope` is the security-correct one** and is what
> backs `AuthorizationScope`.

### 8.7 `authorization_scope()` — including the selected-project escalation fix

```python
def authorization_scope(self, principal, selected_project_id=None) -> AuthorizationScope:
    empty = AuthorizationScope(False, [], None, False)
    if principal is None: return empty
    user = self._active_user(uow, principal.uid)
    if user is None: return empty                                  # inactive ⇒ deny-all
    if user.role.casefold() == "admin":
        return AuthorizationScope(True, None, None, True)          # unrestricted
    scoped_projects = self._project_access_scope(uow, user)
    document_ids = [d for d in uow.document_grants.document_ids_for_principal(uid, role_ids)
                    if _document_active(uow, d)]
    if selected_project_id is not None:
        if selected_project_id in scoped_projects:
            return AuthorizationScope(False, [selected_project_id], document_ids or None, True)
        selected_doc_grants = [d for d in document_ids if _document_project(uow, d) == selected_project_id]
        if selected_doc_grants:
            return AuthorizationScope(False, [], selected_doc_grants, True)   # ← only granted docs
        return empty                                                    # hard deny
    return AuthorizationScope(False, sorted(scoped_projects), document_ids or None, True)
```

**The security fix:** when the user selects an unauthorized project but holds individual *document*
grants inside it, the scope becomes `project_ids=[]` **plus** only the granted document IDs. It
deliberately does **not** return `project_ids=[selected_project_id]`, so one document grant cannot
unlock the whole project corpus. This is documented in
`Documentation/Workflows/V2/security-authorization-review.md` as HIGH-severity finding #4, now fixed.

### 8.8 The full `AuthorizationEngine` public surface

| Method | Semantics |
|---|---|
| `is_admin(principal)` | active user whose `role == "admin"` |
| `roles_for_user(uid)` | resolved, scoped, active roles |
| `permissions_for_user(uid)` | union of role permissions; **empty set if user is inactive** |
| `has_permission(principal, perm)` | admin ⇒ `True`; else set membership |
| `can(principal, action)` | `ACTION_PERMISSIONS[action]` → `has_permission`; **unknown action ⇒ `False`** |
| `can_manage_department(principal, dept_id)` | admin, or own department |
| `can_manage_role(principal, role)` | admin, or `role.scope == "department" and role.department_id == user.department_id` |
| `can_manage_project(principal, project_id)` | three-tier rule (§8.5) |
| `can_manage_project_members(...)` | alias of the above |
| `can_access_project(principal, project_id)` | **wide**: manage ∥ same-department ∥ active member ∥ grant |
| `can_view_project_documents(principal, project_id)` | **strict**: manage ∥ active member ∥ grant (**no** department rule) |
| `accessible_project_ids(principal)` | admin ⇒ all active; else sorted `_project_access_scope` |
| `authorized_project_ids(principal, selected=None)` | membership-only, "backwards-compatible" |
| `can_upload_document(principal, project_id \| None)` | admin ⇒ True; `None` ⇒ manager only; else project-manage |
| `can_read_document(principal, document_id)` | six ordered checks (§below) |
| `can_manage_document(principal, document_id)` | admin, or (no project ⇒ manager) / project-manage |
| `project_access_contact(project_id)` | `{project_id, project_name, manager_name}` — **contact only** |
| `authorization_scope(principal, selected=None)` | §8.7 |

`can_read_document` — six ordered, fail-closed checks:
1. user inactive **or** document missing **or** document `status != "active"` → `False`
2. admin → `True`
3. explicit `DocumentGrant` → `True`
4. `document.project_id is None` → `True` (org-wide unassigned)
5. project missing (**orphan document**) → `False` ← *fail-closed*
6. `_can_manage_project` → `True`; active membership → `True`; `ProjectGrant` → `True`; else `False`

### 8.9 Inactive users

Every public method funnels through `_active_user(uow, uid)`, which returns `None` for
`status != "active"`. **Inactive users are treated as non-existent by the engine.** However, the API
layer's `get_current_principal` only validates the JWT — so a deactivated user's token still
*authenticates* (200-class) and the 403 surfaces later, from the use case's `_require_active`.

### 8.10 Permission catalog (seed data, 25 permissions / 5 roles)

| Role | Scope | Permissions |
|---|---|---|
| **Admin** | global | `"*"` → all 25 |
| **Manager** | global | `USER_VIEW/CREATE/UPDATE`, `DEPARTMENT_VIEW/ASSIGN_USERS`, `PROJECT_VIEW/CREATE/UPDATE/MANAGE_MEMBERS/LEAVE`, `DOCUMENT_VIEW/UPLOAD/UPDATE/QUERY/MANAGE_ACCESS`, `ROLE_VIEW/CREATE/UPDATE` |
| **Developer** | global | `USER_VIEW`, `DEPARTMENT_VIEW`, `PROJECT_VIEW/LEAVE`, `DOCUMENT_VIEW/UPLOAD/UPDATE/QUERY` |
| **Tester** | global | `USER_VIEW`, `DEPARTMENT_VIEW`, `PROJECT_VIEW`, `DOCUMENT_VIEW/QUERY` |
| **Solution Architect** | global | `USER_VIEW`, `DEPARTMENT_VIEW`, `PROJECT_VIEW/CREATE/UPDATE`, `DOCUMENT_VIEW/UPLOAD/UPDATE/QUERY/MANAGE_ACCESS`, `ROLE_VIEW` |

`resolve_role_permissions(names)` expands `"*"`.

> Note: `ARCHITECTURE.md` describes a built-in `Lead` role. **`permission_catalog.py` does not seed
> one** — lead authority is derived from `Project.manager_uid == user.uid`, not from a role. The doc is stale.

---

## 9. Persistence & Data Model

### 9.1 Bootstrap chain

```
app.main.lifespan
  └─ initialize_persistence(get_session_factory)        # 3 attempts, 0.5s sleep, then RuntimeError
       └─ get_session_factory()                         # @lru_cache(maxsize=1)
            ├─ create_engine_and_session_factory(DATABASE_URL)   # session.py
            │    ├─ create_engine(connect_args={"check_same_thread": False} for sqlite)
            │    ├─ @event.listens_for(engine,"connect") → PRAGMA foreign_keys=ON   (SQLite only)
            │    └─ sessionmaker(expire_on_commit=False)
            ├─ initialize_database(engine)              # create_all + imperative migrations
            ├─ bootstrap_admin(lambda: SqlAlchemyUnitOfWork(sf), PasswordHasher())
            └─ seed_rbac(lambda: SqlAlchemyUnitOfWork(sf))
create_unit_of_work() → SqlAlchemyUnitOfWork(get_session_factory())
```

`DATABASE_URL` default `sqlite:///./instance/knowlayer.db`; if it equals that exact literal it is
rewritten to an absolute path. `.env` overrides to `.../knowlayer.db3`.

### 9.2 Migrations — two mechanisms, only one runs

1. **`app/infrastructure/persistence/migrations/0001…0005_*.sql`** — the *documented* DDL
   (`0001_initial`, `0002_authentication`, `0003_organization_rbac`, `0004_employee_and_departments`,
   `0005_roles_and_permissions`). **These files are never executed.**
2. **`app/infrastructure/persistence/sqlalchemy/session.py:initialize_database()`** — the runnable path:
   `Base.metadata.create_all(engine)` then an imperative, SQLite-only, additive/idempotent pass:
   - `ALTER TABLE … ADD COLUMN` for every entry in `_COLUMN_ADDITIONS`
   - `UPDATE users SET username = uid WHERE username = ''` (backfill)
   - `CREATE [UNIQUE] INDEX …` from `_INDEX_ADDITIONS`
   - `_rebuild_legacy_table()` for `projects` and `documents` — the SQLite 12-step "create `_new`,
     insert-select, `PRAGMA foreign_keys=OFF`, drop, rename, `PRAGMA foreign_keys=ON`" dance to add
     `INTEGER PRIMARY KEY AUTOINCREMENT`.

`alembic` appears in `requirements.txt` but is not wired. `postgres/configuration.py` and
`sqlite/configuration.py` exist alongside the generic factory but are not the active path.

### 9.3 The 12 tables

| Table | Purpose | Key columns |
|---|---|---|
| `users` | Identity + credentials | `uid` (PK), `username` (UNIQUE idx), `name`, `email`, `role`, `department_id`, `status`, `password_representation`, `password_changed_at`, `must_change_password`, `employee_id`, `first_name`, `last_name`, `created_at`, `updated_at` |
| `departments` | Org units | `department_id` (PK), `department_name`, `status`, `description`, `default_billable` |
| `projects` | Work units | `internal_id` (INTEGER PK AUTOINCREMENT), `project_id` (business ID), `project_name`, `department_id`, `status`, `description`, `manager_uid`, `start_date`, `end_date`, `created_by_uid`, `created_at`, `updated_at` |
| `documents` | Registered documents | `internal_id` (INTEGER PK AUTOINCREMENT), `document_id`, `document_name`, **`project_id` NULLABLE**, `status`, `original_filename`, `file_type`, `description`, `version`, `storage_location`, `uploaded_by`, `uploaded_at` |
| `user_projects` | Project membership junction | `uid`, `project_id`, `assigned_by_uid`, `status`, `assigned_at`, `membership_role`, `left_at` |
| `business_id_sequences` | Monotonic counters | `sequence_key` (PK), `prefix`, `last_value` |
| `roles` | RBAC roles | `role_id` (PK), `name`, `description`, `scope` (`global`/`department`), `department_id`, `status`, `created_by_uid`, timestamps |
| `permissions` | RBAC catalog | `permission_id` (PK), `name`, `description`, timestamps |
| `role_permissions` | Role↔Permission | `role_id` + `permission_id` composite, `granted_by_uid`, `granted_at` |
| `department_members` | Dept membership | `user_id`, `department_id`, `membership_role`, `billable_status`, `assigned_by_uid`, `status`, `assigned_at`, `left_at`, timestamps |
| `document_permissions` | Per-document grants | `internal_id` (PK), `document_id`, `principal_type` (`role`/`user`), `permission` (`read`), `role_id?`, `user_id?`, `granted_by_uid`, `status`, `granted_at` |
| `project_grants` | Per-project grants | `internal_id` (PK), `project_id`, `principal_type`, `role_id?`, `user_id?`, `granted_by_uid`, `status`, `granted_at` |

Full column-level detail lives in `docs/DATABASE_SCHEMA.md`; the Mermaid ERD is in `docs/DATABASE_ERD.md`.

> **Not in SQL:** conversation logs (JSON files in `conversation_logs/`) and vectors (Chroma `.chroma/`).
> Only `token_tracker` history is in-memory. There is no Redis anywhere except optional LangCache.

### 9.4 `SqlAlchemyUnitOfWork`

`app/infrastructure/persistence/sqlalchemy/unit_of_work.py` implements the `UnitOfWork` protocol with
11 repository attributes + `sequences`, plus `__enter__`/`__exit__`/`commit`/`rollback`.
`__exit__` rolls back on exception. All 11 repositories share **one** `Session`.

### 9.5 The 11 repositories (`repositories.py`, 645 lines)

`SqlAlchemyUserRepository` (`get_by_uid`, `get_by_username`, `get_by_email`, `get_by_employee_id`,
`list`, `save`, `delete`), `…DepartmentRepository`, `…ProjectRepository` (`+get_by_internal_id`,
`list_active`), `…DocumentRepository`, `…MembershipRepository` (`+revoke` sets `status="revoked"`),
`…DepartmentMemberRepository`, `…PermissionRepository`, `…RoleRepository`
(`+permissions_for_role`, `set_permissions` = **replace**, not merge), `…ProjectGrantRepository`
(**`project_ids_for_principal(user_id, role_ids)`**), `…DocumentGrantRepository`
(**`document_ids_for_principal(user_id, role_ids)`**), `…SequenceRepository`.

Two decisive methods: `project_ids_for_principal` / `document_ids_for_principal` resolve the
**polymorphic grant union** (user grants ∪ role grants) **in one query**, keeping SQL out of the
authorization engine.

All `save()` methods call `session.flush()`, never `commit()`. Records are mapped to domain dataclasses
by module-level `_to_*()` functions.

**Atomic sequence allocation** (`SqlAlchemySequenceRepository.allocate`) — dialect-aware:
```python
@staticmethod
def _insert_ignore(dialect_name, values):
    if dialect_name.startswith("postgresql"):
        return postgres_insert(BusinessIdSequenceRecord).values(**values) \
            .on_conflict_do_nothing(index_elements=[BusinessIdSequenceRecord.sequence_key])
    return sqlite_insert(BusinessIdSequenceRecord).values(**values) \
        .on_conflict_do_nothing(index_elements=[BusinessIdSequenceRecord.sequence_key])
# allocate(): UPDATE ... SET last_value = last_value + :by WHERE sequence_key = :key RETURNING last_value
# raises RuntimeError if the RETURNING yields None
```

---

## 10. Caching Architecture

There are **five** distinct cache mechanisms. Knowing which is which prevents a lot of confusion.

| # | Layer | Class | Wired into live path? |
|---|---|---|---|
| 1 | Response cache (orchestrator-level) | *whatever is passed as `response_cache`* | **Default `None`.** Read at orchestrator step 2, written at step 11. `api/dependencies.py` and `init_orchestrator()` do **not** pass one. |
| 2 | FAQ similarity cache | `FAQSimilarityCache` | **YES** — constructed in `QueryOrchestrator.__init__` |
| 3 | LLM prompt/response cache | `PromptLRUCache` inside `FallbackLLMProvider` | **YES** |
| 4 | Quality-aware cache | `InMemoryQualityAwareCache` / `get_quality_cache()` | **NO** — fully built, unit-tested, never instantiated by the app |
| 5 | Dual cache (LangCache + JSON) | `DualCache` / `get_dual_cache()` | **NO** — never instantiated by the app |

### 10.1 `InMemoryQualityAwareCache` (layer 4, unwired — 702 lines)

Quality-gated LRU+TTL cache. `max_entries=1000` (`SEMANTIC_CACHE_MAX_ENTRIES`),
`ttl_seconds=3600` (`SEMANTIC_CACHE_TTL_SECONDS`).

`CacheQualityValidator` — seven ordered checks, thresholds defaulting from settings:

| # | Check | Default | On failure |
|---|---|---|---|
| 1 | non-empty response | — | FAIL |
| 2 | `confidence >= 0.60` | `SEMANTIC_CACHE_MIN_CONFIDENCE` | FAIL |
| 3 | best evidence distance < 0.85 | — | FAIL |
| 4 | RAG source needs ≥ 1 evidence chunk | — | FAIL |
| 5 | `lexical_grounding >= 0.20` | — | FAIL (or REVIEW if `allow_review`) |
| 6 | `separation_gap >= 0.10` | — | **soft warning only** — decision stays PASS |
| 7 | `is_negative_response(response)` | — | **always FAIL** |

`classify_distance(distance)`: `< 0.60` STRONG · `0.60–0.70` BORDERLINE · `0.70–0.85` WEAK · `>= 0.85` INVALID.

Eviction: `_access_order[0]` popped when `len >= max_entries` and the key is new.
TTL: lazy on `get()` (counts as a miss) plus eager `cleanup_expired()`.
Stats: `hits, misses, hit_rate, evictions, expirations, writes, rejected_low_confidence,
rejected_quality_gate, current_entries, max_entries, utilization`.
Key = arbitrary caller-supplied `cache_key` string, **exact match only** (not semantic).

### 10.2 `DualCache` (layer 5, unwired — 466 lines)

LangCache (Redis-backed semantic) as primary, whole-file-rewrite JSON at
`data/semantic_cache.json` as always-available fallback, plus a daemon sync thread
(`sync_interval=60.0`) whose `_sync_json_to_langcache` is currently a **debug-log stub**.

- `LANGCACHE_AVAILABLE` via a guarded `try: from langcache import LangCache` import.
- Read: LangCache first (only when `original_query` non-empty), else JSON by exact key.
  **Negative responses are evicted on read.**
- Write: negatives refused; otherwise LangCache (best-effort) **and always** JSON.
- `is_healthy()` always returns `True` (JSON tier is always available).
- **No TTL, no max size.** `invalidate()`/`clear()` only touch the JSON tier.

### 10.3 `PromptLRUCache` (layer 3, wired)

`maxsize=LLM_CACHE_SIZE` (128). Thread-safe `OrderedDict` + `threading.RLock`, LRU via `popitem(last=False)`.

Key = canonical JSON of the entire message list (`json.dumps(sort_keys=True, separators=(",",":"))`).
On a key miss it embeds and does a **linear cosine scan** against every entry, accepting a hit at
`>= LLM_CACHE_SIMILARITY_THRESHOLD` (0.92).

**Key subtlety:** the embedded text is only the `system`+`user` messages, and if it contains
`"Question:"` **everything before the marker is dropped** — otherwise the shared document context
would dominate the vector and collapse distinct questions together. `maxsize == 0` disables the cache
entirely. `embedder` is injectable so tests never load the transformer.

### 10.4 `FAQSimilarityCache` (layer 2, wired)

`threshold = FAQ_SIMILARITY_THRESHOLD` (0.92). Loads `data/faqs.json` **once** at construction,
embeds every question, stores a **normalized** `(N, 384)` float32 matrix so cosine == dot product
(`scores = self._matrix @ query_vec`). Argmax; return only if `>= threshold`.

Graceful degradation: disabled / missing file / unparseable / empty ⇒ `self.enabled = False` and
`search()` returns `None`. Guarded by `threading.RLock`. **No TTL, no write path, no invalidation,
no `clear()` method** (the `/cache/clear` route guards with `hasattr`).

FAQ JSON schema: `[{"id": str, "question": str, "answer": str}]`.

### 10.5 The negative-response invariant

`app/core/cache_quality.py` exports `is_negative_response(text)` and `_NO_INFO_PATTERN`. Enforced at
**four** points, which is why negative answers can never poison a cache:

1. `FallbackLLMProvider.generate` — refuses to `put` a negative response; evicts a cached one.
2. `QueryOrchestrator` step 2 — evicts a cached negative on read and treats it as a miss.
3. `QueryOrchestrator` step 3 — discards a negative FAQ match.
4. `DualCache.get/put` — evicts on read, refuses on write.
5. `CacheQualityValidator` check #7 — always FAILs admission.

### 10.6 `JsonSemanticResponseCache` (unwired)

File-backed semantic cache that survives restarts. Key is the **user question only** (not the full
prompt). Re-reads and re-writes the whole JSON file on **every** `get`/`put`. Atomic via `.tmp` +
`Path.replace()`. De-dupes by exact input, trims with `entries[-maxsize:]` (**FIFO, not LRU**).

### 10.7 `JsonFAQCache` (unwired)

Handles both the legacy shape (`{"faqs": "<markdown>"}`) and the modern shape
(`{"entries": [{"input","output","input_vector"}]}`). `migrate_to_entries()` regex-splits legacy
markdown on numbered headings and re-embeds. All failures logged, never raised.

---

## 11. LLM Provider Layer

### 11.1 Contract

```python
class LLMProviderError(Exception): ...

class LLMProvider(ABC):
    @abstractmethod
    def generate(self, messages: List[Dict[str, str]]) -> str: ...
```

Every concrete client implements **two** call styles:
- `generate(messages) -> str` — raises `LLMProviderError` on failure. **This is what the orchestrator calls.**
- `generate_with_response(messages) -> LLMResponse` — never raises; returns a structured error object. **Not called by the orchestrator.**

Adapters additionally expose a duck-typed `get_last_tokens()` and an assignable `session_id`.

### 11.2 Composition

```
QueryOrchestrator.llm = FallbackLLMProvider(primary=OpenRouterClient(), fallback=GroqClient())
                            │
                            ├─ PromptLRUCache(maxsize=128)          ← checked first
                            │
                            └─ OpenRouterClient ──► get_token_tracker() ──► TokenTracker
                                             └─► langsmith_integration.add_tokens_to_current_run()
```

### 11.3 `FallbackLLMProvider`

```
cache.get(messages)
  ├─ hit & not negative → return, tokens = {0,0,0,cache_hit: True}
  ├─ hit & negative     → log llm_cache_evict, fall through
  └─ miss               ↓
try primary.generate()
  except LLMProviderError → try fallback.generate()
                              except LLMProviderError → raise LLMProviderError(
                                  "Both primary and fallback LLM providers failed.")
if not is_negative_response(response): cache.put(messages, response)
```

### 11.4 `OpenRouterClient` (primary, 369 lines)

- Persistent `httpx.Client(timeout=60)` with `Authorization: Bearer …`. Default `max_tokens=400`.
- Health-monitor hooks on **every** path: `record_request_start` → `record_request_success(latency_ms)`
  / `record_request_failure`.
- **HTTP-200-with-error detection:** `if "error" in data and "choices" not in data: raise`.
- **Empty-content self-heal retry** (exactly once): re-POST with only the last user message — guards
  against over-long system prompts. A second empty result raises.
- `429 → LLMResponseStatus.RATE_LIMITED` on the structured path.
- **Reasoning-model sanitisation** (`_strip_reasoning`): strips `<think>…</think>`, then finds the
  *last* line matching a thinking-header regex (`analyze|thinking process|reasoning process|formulate|
  determine if…|let me|I'll…|here's my thinking…`) or an instruction echo, and returns everything
  after it; falls back to the last paragraph. Needed because reasoning models leak planning text.
- `_track_tokens` → `TokenTracker.track(model, prompt_tokens, completion_tokens, session_id, cache_hit, provider="openrouter")`.
- `_add_tokens_to_langsmith` — best-effort mutation of `langsmith.get_run_tree()._metadata`.

**Only OpenRouter feeds the `TokenTracker`.** Groq does not.

### 11.5 `GroqClient` (fallback, 207 lines)

`llama-3.1-8b-instant` by default; `.env` sets `openai/gpt-oss-20b`. Same two call styles.
**No** empty-content retry, **no** reasoning stripping, **no** token tracking.

Contains an explicit secret-sanitiser that runs before any error text is logged or raised:
```python
def _sanitize_response_body(body: str, max_length: int = 1000) -> str:
    sanitized = body[:max_length]
    sanitized = re.sub(r"(?i)bearer\s+[a-z0-9._-]+", "Bearer [REDACTED]", sanitized)
    sanitized = re.sub(r"(?i)(?:gsk_|sk-)[a-z0-9_-]+", "[REDACTED_KEY]", sanitized)
    return sanitized
```

### 11.6 `ProviderHealthMonitor` / `CircuitBreaker`

`app/infrastructure/llm/provider_health.py` (377 lines), thread-safe singleton
`get_provider_health_monitor()`.

| State | Trigger | Next |
|---|---|---|
| HEALTHY | `_failure_count >= 5` | DEGRADED |
| DEGRADED | `_failure_count >= 10` (2× threshold) | UNHEALTHY |
| DEGRADED | `_success_count >= 2` | HEALTHY |
| OPEN / UNHEALTHY | elapsed ≥ 30 s | RECOVERING (`_success_count = 0`) |
| RECOVERING | 2 × `record_success()` | HEALTHY |
| RECOVERING | `record_failure()` | OPEN |

Latency is smoothed with an EMA (`alpha = 0.1`). `is_provider_available` **fails open** (unknown
provider ⇒ `True`).

Settings exist (`CIRCUIT_BREAKER_*`) but the monitor **hardcodes the same defaults** — the env values
are not read. `ENABLE_PROVIDER_HEALTH` is likewise unread.

Exposed at `GET /api/providers/health` and reset at `POST /api/providers/reset` (both unauthenticated).
Metrics returned: `status, available, total_requests, successful_requests, failed_requests,
consecutive_failures, consecutive_successes, average_latency_ms, success_rate, last_success_time,
last_failure_time`.

### 11.7 `ProviderErrorTracker` / `RetryPolicy` (built, **not wired**)

`app/infrastructure/llm/provider_error_tracker.py` (490 lines). Fully implemented, fully unit-tested,
**but no client references it — there is no retry loop anywhere.**

- 10 `ErrorCategory` values: `TIMEOUT, RATE_LIMIT, AUTHENTICATION, QUOTA_EXCEEDED, SERVER_ERROR,
  NETWORK_ERROR, INVALID_REQUEST, MODEL_UNAVAILABLE, CONTEXT_LENGTH, UNKNOWN`.
- `classify_error` maps status codes first (429→RATE_LIMIT, 401/403→AUTHENTICATION, 404→MODEL_UNAVAILABLE,
  400→INVALID_REQUEST, 5xx→SERVER_ERROR), then falls back to keyword matching on the lower-cased message.
- `is_retryable_status`: **429 and 5xx ⇒ True**; 400/401/403/404/422 ⇒ False.
- `RetryPolicy(max_retries=3, initial_delay=1.0, backoff_factor=2.0, max_delay=10.0)` →
  backoff `1 s, 2 s, 4 s`.
- `error_ttl_seconds` is stored but **never enforced**. `is_provider_critical` = >10 errors AND known
  category AND >5 errors/min.

### 11.8 `llm_response.py` (built, mostly unwired — 568 lines)

`LLMProviderName`, `LLMResponseStatus` (`SUCCESS, PARTIAL, CACHED, FAILED, TIMEOUT, RATE_LIMITED`),
`CacheEntrySource` (`RAG_GENERATED, FAQ_MATCHED, LLM_CACHED, SEMANTIC_CACHE`), `LLMTokenUsage`,
`LLMResponse` (with `from_provider_response` / `from_cache` / `error_response`), the fluent
`LLMResponseBuilder`, and the `ResponseAggregator` singleton (`__new__` pattern) computing
per-provider/global success rate, cache-hit rate, token totals, average latency.
`is_successful()` treats `SUCCESS` and `CACHED` as success; `CACHED` increments `cache_hits` but
deliberately **not** `total_success`. Only reachable through `generate_with_response`, which the
orchestrator never calls.

---

## 12. Observability & Tracing

**Four separate systems coexist.** Only two are live.

### 12.1 The vendor-neutral port (live but unused)

`app/domain/ports/observability.py`:
```python
@dataclass(frozen=True) class TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    # __post_init__ derives total_tokens; uses object.__setattr__ to bypass frozen
@runtime_checkable class TraceSpanPort(Protocol):  end(outputs=None, error=None); __enter__; __exit__
@runtime_checkable class BaseObservabilityProvider(Protocol):
    create_trace(name, session_id=None, user_id=None, metadata=None) -> TraceSpanPort
    record_llm_call(model, token_usage, latency_ms=0.0, metadata=None) -> None
    flush() -> None
ObservabilityPort = BaseObservabilityProvider
```

### 12.2 `ObservabilityManager` (built, **not in the request path**)

Proxy/facade with a `threading.Lock`-guarded active-provider pointer, selected from
`OBSERVABILITY_PROVIDER` (`null` | `langfuse` | `phoenix`, unknown → Null). Supports runtime
`switch_provider()`. Process-wide singleton `get_observability_manager()`, plus
`reset_observability_manager()` for tests.

- `NullObservabilityProvider` — no-ops, guarantees zero network calls in dev/test.
- `LangfuseProvider` — Langfuse **v4** SDK (`start_observation(as_type=...)`, `auth_check()` at init,
  5 s timeout). Maps names to observation types (`retrieval`→`retriever`, `llm`→`generation`,
  `guardrail`, `tool`, `agent`, else `span`). `record_llm_call` emits a `generation` observation with
  `usage_details`. **Fails safe:** any SDK error logs a warning and sets `self.enabled = False`.
- `PhoenixProvider` — emits **OpenInference** attributes (`llm.model_name`, `llm.token_count.*`,
  `llm.latency_ms`). **No OTLP exporter is wired** — spans are buffered in memory and exposed via
  `get_stats()`. `flush()` moves buffers to `last_flushed_*` and clears.

**Nothing in the live path calls `get_observability_manager()`.** The intended bridge is
`PipelineTracer.set_observability_callback(...)`, which is itself never called.

### 12.3 LangSmith (the **live** tracing system)

`app/infrastructure/observability/tracer.py` sets `LANGCHAIN_TRACING_V2` / `LANGCHAIN_API_KEY` /
`LANGCHAIN_ENDPOINT` / `LANGCHAIN_PROJECT` into `os.environ` at import time.

```python
@contextmanager
def trace_step(name, inputs=None, run_type="chain"): ...   # yields a NoOpSpan on any failure
def traceable(name=None, run_type="chain"): ...            # identity decorator when disabled
```

Applied at: `QueryOrchestrator.answer` (`chain`), `QueryOrchestrator._faq_search` (`retriever`),
`_retrieve` (`RAGRetrieval`, `retriever`), `_generate` (`LLMGenerate`, `llm`). `answer()` also stamps
run-tree metadata (`session_id`, `conversation_id`, `user_id`) and tags `["company_bot","v3","rag"]`.

`langsmith_integration.py` provides `add_tokens_to_current_run(prompt, completion, model)`,
`add_token_metadata`, `add_tokens_via_extra`, `format_tokens_for_display` (`"123P + 45C = 168T"`) —
all wrapped in `try/except` so tracking never breaks a response.

### 12.4 `TokenTracker` (live, in-memory)

`app/infrastructure/observability/token_tracker.py`. Process-global singleton, `max_history=10000`,
ring buffer via `self._history = self._history[-self.max_history:]`.

`TokenUsage(timestamp, model, prompt_tokens, completion_tokens, total_tokens, session_id, cache_hit, provider)`
and `AggregatedTokens` (with `update()` recomputing averages).
API: `track`, `get_total`, `get_by_model`, `get_by_session`, `get_by_provider`, `get_all_models`,
`get_all_sessions`, `get_recent(limit)`, `get_cache_stats`, `clear_history`, `export_as_list`.

Fed **only** by `OpenRouterClient._track_tokens`. Exposed (unauthenticated) via `/api/tokens/*`.

### 12.5 `PipelineTracer` (built, **not used**)

`app/infrastructure/observability/pipeline_tracer.py` (633 lines). 8 canonical stages:
`CONTEXT_REWRITE, NORMALIZATION, CACHE_LOOKUP, VECTOR_RETRIEVAL, RERANKING, QUALITY_GATE,
LLM_GENERATION, POST_GUARDRAILS` (plus compat aliases `CACHE_CHECK, FAQ_CHECK, QUERY_EXPANSION,
RETRIEVAL, QUALITY_ASSESSMENT, CACHE_WRITE`).

`StageSpan` (timing, in/out metadata, tokens, error) → `TraceContext` (context manager,
auto-registers) → `PipelineTrace` (spans, `cache_hit`, `early_exit`, `exit_stage`, `exit_reason`,
`total_tokens`) → `PipelineTracer` (singleton, `max_traces=1000`, `RLock`, overflow eviction).

`QueryOrchestrator.__init__` does `self.pipeline_tracer = pipeline_tracer or get_pipeline_tracer()`
— **and then never uses it.** A repo-wide search for `trace_stage` / `PipelineStage` in `app/**` finds
matches only inside `pipeline_tracer.py` itself. Settings `ENABLE_PIPELINE_TRACING` /
`PIPELINE_TRACER_MAX_TRACES` are not read by the constructor either.

### 12.6 Conversation logging (live, JSON files)

`app/infrastructure/logging/conversation_logger.py` + `conversation_log_cleanup.py` +
`database_employee_id_provider.py`.

- `ConversationLog(employee_id, session_id, messages[], recording_status="completed")` serialized to
  `conversation_logs/<…>.json`. **Keyed by `employee_id`, resolved from the `users` table** via
  `DatabaseEmployeeIdProvider(unit_of_work_factory)`.
- Atomic persistence; redaction; failure isolation (`_safe_log_conversation` swallows all errors and
  logs them) — logging can never break a chat response.
- Retention: `CONVERSATION_LOG_RETENTION_DAYS` (30) enforced at **startup** (sync) and every
  `LOG_CLEANUP_INTERVAL_SECONDS` (86400 s = 24 h) by an asyncio task using `asyncio.to_thread`.
- `parse_retention_days()` validates with a `logger.warning` **and** a `warnings.warn` fallback.

### 12.7 Authentication audit (minimal)

`app/infrastructure/audit/authentication_events.py`:
```python
def record_authentication_event(event, uid=None, success=None):
    logger.info("authentication_event", extra={"event": event, "uid": uid, "success": success})
```
Structured-extra logging only. **No durable audit sink, no separate logger, no DB table.**

---

## 13. Document Ingestion

### 13.1 `app/use_cases/ingestion/document_processing.py`

The new ingestion architecture follows this pipeline:
`Document` → `Document Processing Port` → `Docling Adapter` → `HybridChunker` → `Canonical Chunk Metadata` → `ChromaVectorStore`

Key architectural rules:
- **Docling is infrastructure.** It is strictly isolated behind the adapter pattern in `app/infrastructure/document/docling_processor.py`.
- **Application code depends on the port.** The use-case layer operates exclusively on neutral `ProcessedDocument` and `ProcessedChunk` interfaces from `app/domain/ports/document_processing.py`.
- **Domain code does not depend on Docling.** The domain layer is pure and knows nothing about the underlying document parser.
- **RBAC metadata comes from KnowLayer, not Docling.** While Docling enriches structural metadata (`section_heading`, `hierarchy_path`), authorization properties such as `project_id` and document identity are injected by the application layer. The parser is never trusted to compute security scopes.

The `app/use_cases/ingestion/document_processing.py` file maps the parser's structural results to store-ready records:
- `build_chunk_records_from_processed(processed, document_id, project_id, source, file_type, version)` — produces:
  ```python
  {"id": f"{document_id}-{index}", "text": chunk.text,
   "metadata": {"document_id":…, "project_id": project_id or "unassigned", "source":…,
                "chunk_index": index, "file_type":…, "version": version or "1.0",
                "section_heading":…, "hierarchy_path":…}}
  ```
  **`project_id` defaults to the literal string `"unassigned"`** — that literal is what the
  `include_unassigned` filter matches on.

*(Note: The old `python-docx → 500-character chunks` fixed-width logic is retained purely as a fallback adapter in `PlainTextDocumentProcessor` for formats Docling cannot parse, like `.rst`.)*

### 13.2 `app/infrastructure/ingestion/provisioner.py`

Injected into `DocumentManagementService` as `ingestion_handler` / `deletion_handler`, so the use case
stays pure and side effects are testable.

- `provision_document(source_path, document, content=None, store=None) -> int`
  - `content` is base64 (upload path) or `source_path` points at a file under `DOCUMENTS_DIR`.
  - `_detect_extension(raw, name)` — **sniffs the bytes**, not the name: `raw[:2] == b"PK"` and
    `b"[Content_Types].xml" in raw[:4096]` ⇒ `.docx`; else try UTF-8 decode ⇒ `.txt`; else fall back
    to the filename suffix.
  - Unsupported ⇒ `ValueError` listing the supported set.
  - Writes the raw bytes to `DOCUMENTS_DIR/<safe_document_id><ext>` and back-fills
    `document.original_filename`, `file_type`, `storage_location`.
  - `build_chunk_records` → `ChromaVectorStore.add_documents`. Returns the chunk count.
  - **Neither `content` nor `source_path`** (metadata-only registration) ⇒ returns `0` without touching Chroma.
- `remove_document(document_id)` — `store.collection.delete(where={"document_id": document_id})`.
- `_UNSAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9 _.\-]+")` guards the filename; a fully-stripped ID raises `ValueError`.

### 13.3 `ChromaVectorStore`

`app/infrastructure/vector/chroma_client.py`. `chromadb.PersistentClient(path=.chroma)`,
`get_or_create_collection(name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"})`.

- **Lazy** `SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")` via an
  `@property` with a setter (so tests can inject a fake).
- ⚠ **The model string is hardcoded** — the `EMBEDDING_MODEL` env var is *not* read here.
- `add_documents(docs)` — encodes with `convert_to_numpy=True`, then `collection.add(ids, documents,
  metadatas, embeddings)`.
- `query(query_text, top_k=3, project_ids=None, where=None) -> [{text, metadata, distance}]`
  - Empty text ⇒ `[]`. `project_ids == []` ⇒ **`[]` short-circuit** (the deny-all path).
  - Composes filters: `project_ids` ⇒ `{"project_id": {"$in": [...]}}`; `where` ⇒ the caller's filter.
    One filter ⇒ `where=<f>`; two ⇒ `where={"$and": [f1, f2]}`.
  - `include=["documents","metadatas","distances"]`.
  - Verbose `logger.info` of distances at every step (`knowlayer.retrieval`).

### 13.4 `LocalDocumentLoader`

`app/infrastructure/document/local_document_loader.py` — lists files under `DOCUMENTS_DIR`;
used by `scripts/ingest_documents.py`.

---

## 14. API Surface (complete endpoint list)

**66 unique endpoints** (69 route decorators — 3 of them are alias decorators) across 7 routers + `/health`:
authentication 4 · chat 5 · documents 9 · explorer 1 · organization 27 · roles 11 · tokens 8 · health 1.

### 14.1 `chat.py` — prefix `/api`, tag `chat` (5)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/chat` | **optional** (`get_chat_principal`) | The RAG endpoint. See §6.1. |
| GET | `/api/faqs` | **none** | `generate_faqs()`; **runs synchronously on the event loop.** |
| POST | `/api/chat/cache/clear` **and** `/api/cache/clear` | **none** | Clears `response_cache`, `llm.cache`, `faq_cache`, `_pending_citations`, `_last_interaction`, `_alternative_answer_given`. Each step individually `try/except`→`warning`. Returns `{"status":"ok","cleared":[…]}`. **Two aliases via stacked decorators.** |
| GET | `/api/providers/health` **and** `/api/chat/providers/health` | **none** | Per-provider circuit-breaker metrics. |
| POST | `/api/providers/reset` **and** `/api/chat/providers/reset` | **none** | `monitor.reset_all()`. |

> ⚠ **Four of five chat endpoints are unauthenticated, including two destructive ones.**

### 14.2 `tokens.py` — prefix `/api/tokens`, tag `tokens` (8 — **all unauthenticated**)

| Method | Path | Returns |
|---|---|---|
| GET | `/stats` | totals, `call_count`, averages, `cache_hits/misses/hit_rate_percent` |
| GET | `/by-model` | `{model: AggregatedTokens}` |
| GET | `/by-session` | `{session_id: AggregatedTokens}` — **exposes every session ID** |
| GET | `/by-provider` | hardcoded to `openrouter`/`groq` |
| GET | `/recent?limit=50` | `List[usage.to_dict()]`, `limit` capped at 1000 |
| GET | `/session/{session_id}` | per-session usage |
| GET | `/model/{model_name}` | per-model usage |
| POST | `/clear` | `{"status": "Token history cleared"}` — **destructive, unauthenticated** |

The `clear` docstring literally says *"requires authentication in production"* — **not implemented.**

### 14.3 `organization.py` — prefix `/api`, tag `organization` (27, all require principal)

Departments: `GET /organization/status` (unauth), `POST /departments` (201), `GET /departments`,
`GET /departments/{id}`, `PATCH /departments/{id}`.
Users: `POST /users` (201), `GET /users`, `GET /users/{uid}`, `GET /users/{uid}/memberships`,
`GET /users/me/profile`, `PATCH /users/{uid}`, `DELETE /users/{uid}` (204, **soft deactivate**).
Department membership: `POST /departments/{id}/members` (201), `GET /departments/{id}/members`,
`PATCH /departments/{id}/members/{user_id}`, `DELETE /departments/{id}/members/{user_id}` (204).
Projects: `POST /projects` (201), `GET /projects`, `GET /projects/{key}`, `PATCH /projects/{id}`,
`GET /projects/{id}/members`, `POST /projects/{id}/members/{uid}` (204), `DELETE` same (204),
`POST /projects/{id}/members/me/leave` (204).
Project access: `GET /projects/{id}/access`, `POST /projects/{id}/access` (201),
`DELETE /project-access/{grant_id}` (204).

> `GET /api/departments` and `GET /api/users` receive the principal but **do not use it** — any
> authenticated user can list all departments and all users. No pagination on any list endpoint.

### 14.4 `roles.py` — prefix `/api`, tag `roles` (11, all require principal)

`GET /permissions`, `POST /permissions` (201), `GET /roles`, `POST /roles` (201), `GET /roles/{id}`,
`PATCH /roles/{id}`, `DELETE /roles/{id}` (204), `GET /roles/{id}/permissions`,
`PUT /roles/{id}/permissions` (**full replace**), `GET /users/{uid}/permissions`, `GET /users/{uid}/roles`.

> The `/api/users/{uid}/…` paths live in a *different router* than `organization.py`'s `/api/users/{uid}`.
> Same URL namespace split across two modules.

### 14.5 `documents.py` — prefix `/api`, tag `documents` (9)

`GET /documents/status` (**unauth**), `GET /documents`, `POST /documents` (201),
`GET /projects/{id}/documents`, `POST /projects/{id}/documents` (201, **path param wins over body**),
`DELETE /documents/{id}` (204, soft archive + Chroma cleanup), `GET /documents/{id}/access`,
`POST /documents/{id}/access` (201), `DELETE /document-access/{grant_id}` (204).

### 14.6 `authentication.py` — prefix `/api/auth` (4) — see §7.4.

### 14.7 `explorer.py` — prefix `/api` (1)

`GET /explorer/organization` → `OrganizationExplorerResponse`. The simplest route file: `ForbiddenError`
→ 403, everything else → 400 (no 404/409 mapping).

### 14.8 App-level

`GET /health` → `{"status":"ok"}` (no auth).

---

## 15. Streamlit Admin UI

**9 pages, 8 HTTP client modules. No `__init__.py` anywhere** (PEP 420 namespace packages).

### 15.1 Hard architectural rule

`AdminAPI` and the contract test `tests/contract/test_streamlit_management_pages.py` enforce that
**no page or client may** import `sqlite`, import `AuthorizationEngine`, or contain `can_` /
`has_permission` logic. **All business authorization lives on the backend**; the client only surfaces
the `detail` string of a 403.

### 15.2 Pages

| File | Title | Clients | Functionality |
|---|---|---|---|
| `app.py` | KnowLayer HR Chatbot 📘 | `ChatService`, `AuthenticationService`, `OrganizationService` | Login form; sidebar nav (9 links); **Clear Chat**; **Clear Cache**; project-scope `selectbox`; `_format_citations` (builds the `--- **References:**` block, suppressing duplicates via a 40-char containment heuristic); `_format_token_info`; token-metrics expander; provider-health expander with 🟢🟡🔄🔴 and a ⚡ Reset button; history replay; 👍/👎 feedback buttons (only shown when the last answer contains "relevant to your question"); `st.chat_input`. Calls `importlib.reload(chat_service_module)` at import — a hot-reload hack. |
| `pages/profile.py` | My Profile | `ProfileAPI` | Read-only: personal info, billable status, current projects (with **Leave project** button when membership is active), additional project access, document access grouped by project, effective permissions, per-document grant detail. |
| `pages/users.py` | Users | `OrganizationService`, `AdminAPI` | Add department; add user (client-side min-8 password check); manage user (edit/deactivate/reactivate); **View user access** (`/roles`, `/permissions`, `/memberships`); assign billable status. |
| `pages/departments.py` | 🏢 Departments | `AdminAPI` | Create/update department; assign employee (with "Unset (department default)"); list members with inline update + remove. |
| `pages/projects.py` | Projects | `OrganizationService`, `AdminAPI` | Add project; assign/revoke member; project details with 240 px Members **and** Documents dataframes; update project. **Project *access grants* are supported by the client but not surfaced on this page.** |
| `pages/documents.py` | Documents | `DocumentService`, `OrganizationService`, `AdminAPI` | Upload (`st.file_uploader` → base64 → `POST /api/documents`, 90 s timeout); 6 `st.metric` tiles; access-grant table with revoke + grant (principal type `role`/`user`, permission fixed to `read`); per-document **Archive**. |
| `pages/explorer.py` | Organization Explorer | `ExplorerAPI` | Read-only, authorization-scoped tree. People dataframe; per-department expander → per-project card → members expander (**hidden** with an explanatory caption when not visible) and documents expander. Additional-documents section split into "Unassigned" / "accessible by direct grant". `access_labels` maps `document_grant`/`project_access`/`org_wide` to human text. "Expand all sections" checkbox. |
| `pages/roles.py` | 🔑 Roles & Permissions | `AdminAPI` | `permission_checkboxes()` renders a 2-column checkbox grid with stable `{prefix}-perm-{id}` keys. Create/update/delete role; **assign permissions — with a hard `if role == "Admin"` special case** that shows an `st.info` and skips the grid entirely (Admin is authorized by role *identity*). |
| `pages/organization.py` | 📊 Organization Overview | `AdminAPI` | Summary metrics; users-by-department; projects table (manager uid→name resolved client-side); documents table; roles table; "Your access" resolved from `st.session_state.auth`. |

### 15.3 Client modules

All share: `base_url = (base_url or os.getenv("STREAMLIT_API_BASE_URL", "http://127.0.0.1:8000")).rstrip("/")`
and a `_headers()` that prefers `self.token`, else `st.session_state.auth["access_token"]`.

| Module | Lines | Covers |
|---|---|---|
| `admin_api.py` / `AdminAPI` | 237 | Everything: users, departments + members, roles + permissions, projects + members + access grants, documents + grants. Timeouts: GET 20 s, POST 60 s, PATCH/PUT/DELETE 20 s. |
| `chat_service.py` / `ChatService` | 66 | `ask()` (t=90, always `defer_citations=True`), `clear_cache()` (t=10), `get_provider_health()` (t=5, swallows→`{}`), `reset_providers()` (t=5, swallows→`{}`) |
| `authentication_service.py` / `AuthenticationService` | 38 | `login` (t=15), `refresh` (t=15), `change_password` (t=15). **The only client without session-token plumbing** — takes an explicit token. |
| `document_service.py` / `DocumentService` | 42 | `/api/documents` only |
| `explorer_api.py` / `ExplorerAPI` | 44 | `organization()` (t=30) |
| `organization_service.py` / `OrganizationService` | 83 | **Legacy duplicate of `AdminAPI`** (users, departments, projects, members). `pages/users.py` and `pages/projects.py` still use it. |
| `profile_api.py` / `ProfileAPI` | 52 | `profile()` (t=20), `leave_project()` (t=30) |
| `ui_helpers.py` (module) | 31 | `format_error(error)` — pulls `response.json()["detail"]`, handling both string and list-of-dicts shapes; `unavailable(service_name)` — canned "backend not running at 127.0.0.1:8000" message. |

### 15.4 `session_auth.py` — cookie session persistence

`session_auth.py` (53 lines), documented in `docs/IMPLEMENTATION_NOTES.md`. Exists because
**Streamlit re-runs the whole script from zero on every interaction**, which would otherwise log the
user out on any widget change.

- `AUTH_COOKIE = "knowlayer_auth"`, controller key `"knowlayer_cookies"`.
- `bootstrap_cookies()` — creates the `CookieController`; on first run sets a session flag and
  `st.stop()`s to wait for the browser postback.
- `restore_auth(cookies)` — reads the cookie, accepts raw JSON **or** a parsed dict, removes the
  cookie on parse failure or missing `access_token`, and on success sets `session_state.auth` +
  `st.rerun()`.
- `persist_auth(cookies)` — **writes only if the cookie does not already exist**, specifically to
  avoid a re-render loop from the component-postback rerun.
- `require_auth()` — bootstrap → restore → if still anonymous, warn + `st.page_link("app.py")` + `st.stop()`.

**Documented limitations:** the cookie is **JS-readable (not HttpOnly)**, expires ~1 day, and is
therefore unsuitable for production/multi-tenant use. **There is no client-side token refresh** — the
cookie holds whatever login returned, and **no page ever calls `AuthenticationService.refresh()`**.
There is also **no change-password UI**, despite the endpoint existing.

Uses `streamlit-cookies-controller` (not `-manager`) because the latter relies on `st.cache`, which
Streamlit 1.60 no longer provides.

---

## 16. Configuration (every environment variable)

All read in `app/core/settings.py` (202 lines) via `python-dotenv` `load_dotenv()`. Only the first 16
are present in `.env` / `.env.example`; the rest rely on code defaults.

### 16.1 Documents / vector store
| Var | Default | Meaning |
|---|---|---|
| `DOCUMENTS_DIR` | `<BASE_DIR>/input` | Source-document directory |
| `COLLECTION_NAME` | `hr_policy_docs` | Chroma collection |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | ⚠ **hardcoded in `chroma_client.py`; env is ignored there** |
| `DEFAULT_PROJECT_ID` | *(unset)* | Stamped onto ingested chunks. **Only consumer is `scripts/ingest_documents.py`** |

### 16.2 RAG retrieval tuning
| Var | Default | Meaning |
|---|---|---|
| `RAG_DISTANCE_THRESHOLD` | `0.60` (`.env` = **0.80**) | Max distance for a chunk to be kept as evidence |
| `RAG_DISTANCE_RELAXATION` | `0.05` | Slack granted to the single separated best result |
| `RAG_MIN_DISTANCE_GAP` | `0.10` | Required separation from the runner-up |
| `RAG_CANDIDATE_COUNT` | `8` | Chroma `n_results` pool |
| `RAG_MAX_EVIDENCE` | `4` | Chunks surviving into the prompt |
| `RAG_MAX_CONTEXT_CHARS` | `12000` | Hard context budget |

### 16.3 Caching
| Var | Default |
|---|---|
| `LLM_CACHE_SIZE` | `128` |
| `FAQ_SIMILARITY_CACHE_ENABLED` | `true` |
| `FAQ_SIMILARITY_THRESHOLD` | `0.92` |
| `FAQ_JSON_PATH` | `<BASE_DIR>/data/faqs.json` |
| `LLM_CACHE_SIMILARITY_THRESHOLD` | `0.92` |
| `RESPONSE_CACHE_FILE` | `<BASE_DIR>/data/response_cache.json` |
| `FAQ_CACHE_FILE` | `<BASE_DIR>/data/faqs_cache.json` |
| `SEMANTIC_CACHE_ENABLED` | `true` |
| `SEMANTIC_CACHE_MAX_ENTRIES` | `1000` |
| `SEMANTIC_CACHE_TTL_SECONDS` | `3600` |
| `SEMANTIC_CACHE_MIN_CONFIDENCE` | `0.6` |
| `LANGCACHE_ENABLED` | `true` |
| `LANGCACHE_SERVER_URL` | `https://aws-us-east-1.langcache.redis.io` |
| `LANGCACHE_CACHE_ID` / `LANGCACHE_API_KEY` | `""` |
| `DUAL_CACHE_JSON_FALLBACK_ENABLED` | `true` |
| `DUAL_CACHE_JSON_FILE_PATH` | `<BASE_DIR>/data/semantic_cache.json` |
| `DUAL_CACHE_SYNC_INTERVAL_SECONDS` | `60.0` |
| `DUAL_CACHE_SYNC_ON_WRITE` | `true` |

### 16.4 MongoDB FAQ store
`MONGODB_URI` (`""` = disabled) · `FAQ_DATABASE_NAME` (`knowlayer`) · `FAQ_COLLECTION_NAME` (`faqs`) ·
`MONGODB_SERVER_SELECTION_TIMEOUT_MS` (`2000`)

### 16.5 LLM providers
`OPENROUTER_API_KEY` (`""`) · `GROQ_API_KEY` (`""`) ·
`LLM_MODEL` (`openrouter/anthropic/claude-3.5-sonnet`; `.env` → `nvidia/nemotron-3-ultra-550b-a55b:free`) ·
`GROQ_MODEL` (`llama-3.1-8b-instant`; `.env` → `openai/gpt-oss-20b`)

### 16.6 Persistence / identity / auth
`DATABASE_URL` (`sqlite:///./instance/knowlayer.db`; `.env` → `…knowlayer.db3`) ·
`STREAMLIT_API_BASE_URL` (`http://127.0.0.1:8000`) · `ADMIN_USERNAME` (`admin`) ·
`ADMIN_INITIAL_PASSWORD` (`""`) · `DEFAULT_USER_PASSWORD` (`ChangeMe123!`) ·
`AUTH_SECRET_KEY` (`change-this-development-secret`) · `AUTH_TOKEN_EXPIRE_MINUTES` (`480`) ·
`AUTH_REFRESH_TOKEN_EXPIRE_MINUTES` (`10080`)

### 16.7 Business-ID prefixes
`EMPLOYEE_ID_PREFIX`=`MSS` · `DEPARTMENT_ID_PREFIX`=`DEPT` · `PROJECT_ID_PREFIX`=`PROJ` · `DOCUMENT_ID_PREFIX`=`DOC`

### 16.8 Session memory
`SESSION_INACTIVITY_TIMEOUT_HOURS`=`12.0` · `SESSION_MAX_HISTORY_TURNS`=`6` (6 turns = 12 messages)

### 16.9 Observability
`OBSERVABILITY_PROVIDER`=`null` | `langfuse` | `phoenix` ·
`LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST`(`http://localhost:3000`) ·
`PHOENIX_COLLECTOR_ENDPOINT`(`http://localhost:6006/v1/traces`) · `PHOENIX_PROJECT_NAME`(`company-bot`) ·
`LANGCHAIN_TRACING_V2`=`false` · `LANGCHAIN_API_KEY` · `LANGCHAIN_PROJECT`=`company-bot` ·
`LANGCHAIN_ENDPOINT`(`https://api.smith.langchain.com`)

### 16.10 Conversation logging
`CONVERSATION_LOG_DIR`=`conversation_logs` (relative resolved against `BASE_DIR`) ·
`CONVERSATION_LOG_RETENTION_DAYS`=`30` (validated; `logger.warning` + `warnings.warn` fallback) ·
`LOG_CLEANUP_INTERVAL_SECONDS`=`86400`

### 16.11 Query normalization & quality gate
`ENABLE_QUERY_NORMALIZATION`=`true` · `QUERY_NORMALIZER_TYPO_CORRECTION`=`true` ·
`QUERY_NORMALIZER_VOCABULARY`=`true` · `QUERY_NORMALIZER_EXPANSION`=`**false**` ·
`ENABLE_QUALITY_GATE`=`true` · `QUALITY_GATE_MIN_SCORE`=`0.4` · `QUALITY_GATE_MIN_EVIDENCE`=`1` ·
`QUALITY_GATE_DISTANCE_THRESHOLD`=`0.60` · `QUALITY_GATE_GROUNDING_THRESHOLD`=`0.2`

### 16.12 Provider health · pipeline tracing
`ENABLE_PROVIDER_HEALTH`=`true` · `CIRCUIT_BREAKER_FAILURE_THRESHOLD`=`5` ·
`CIRCUIT_BREAKER_SUCCESS_THRESHOLD`=`2` · `CIRCUIT_BREAKER_TIMEOUT_SECONDS`=`30.0` ·
`ENABLE_PIPELINE_TRACING`=`true` · `PIPELINE_TRACER_MAX_TRACES`=`1000`

> ⚠ The circuit-breaker, quality-gate, and pipeline-tracer settings are **defined but never read** by
> their respective classes (they hardcode the same values). `ENABLE_QUALITY_GATE` in particular
> controls a module that is never invoked.

### 16.13 `.env` reality check

`.env` is correctly listed in `.gitignore`. However the working copy contains:
- **two real-format provider keys** (`sk-or-v1-…`, `gsk_…`) — **rotate these**;
- `AUTH_SECRET_KEY` and `ADMIN_INITIAL_PASSWORD` **still at their placeholder values** — a critical
  pre-deployment blocker;
- `LLM_MODEL` and `RAG_DISTANCE_THRESHOLD` diverging from the code defaults, and
  `DATABASE_URL` pointing at `.db3` while docs say `.db`.

---

## 17. Prompts

`config/prompts.yaml` is the **only** externalized prompt file, and it holds **one** prompt set
(3 keys). Full content:

```yaml
prompts:
  rag_answer_generation:
    system_prompt: |
      You are a helpful company knowledge assistant. Your role is to provide accurate answers based exclusively on the HR policy documents provided to you.

      Guidelines:
      - Answer ONLY using the provided document context
      - Be concise (2-4 sentences)
      - If information is not in the context, say 'I could not find that information in the available documents'
      - Cite relevant sections when applicable
      - Do not add external knowledge or assumptions
      - End with: 'Would you like to see the references for this?'
    user_instructions: |
      Instructions: Answer using ONLY the document context above. Write 2-4 sentences. No analysis or reasoning — just the answer. End with: 'Would you like to see the references for this?'
    question_template: |
      <user_question>{question}</user_question>
```

`<user_question>{question}</user_question>` is the **XML prompt-injection defense** — the user question
is wrapped in tags so injected instructions in the query are structurally separable from the
instruction block (git commit `96cbf4b`).

**Hardcoded prompts that do NOT come from the YAML** (all inside `query_orchestrator.py`):
- `RELEVANCE_PROMPT = "Was this response relevant to your question?"`
- the alternative-answer system prompt (the "user said it wasn't relevant" regeneration path)
- the FAQ-generation prompt
- the fallback system/user messages used when the context builder has no `build_messages`

> ⚠ **Bug:** `app/core/prompt_config.py` defines `load_prompt(name)` which reads
> `prompts["prompts"][name]["system"]` — a key that **does not exist** in the YAML (it's `system_prompt`).
> It is **never imported anywhere**, so it is dead code that would `KeyError` if called. The live path
> is `rag_context_builder.load_prompts()`.

---

## 18. Scripts & Operations

### 18.1 `setup.ps1` — one-command dev launcher

Parameters `[int]$ApiPort = 8000`, `[int]$StreamlitPort = 8501`. Resolves the project root from the
script location and `Set-Location`s there. **Asserts `.venv\Scripts\python.exe` exists — it does NOT
create the venv.** Launches two visible PowerShell windows:
```
Set-Location '<root>'; $env:PYTHONPATH='<root>'; & '<venv>' -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Set-Location '<root>'; & '<venv>' -m streamlit run streamlit_app/app.py --server.port 8501
```
No `--reload`, no log capture, no error propagation.

### 18.2 `scripts/dump_db.py`

Read-only SQLite inspector: `python scripts/dump_db.py [table_name] [--db instance/knowlayer.db3]`.
Enumerates `sqlite_master`, prints each table with a row count, column header, and pipe-delimited
rows (values truncated to 117 chars). Returns 1 with a stderr message when the DB or table is missing.

### 18.3 `scripts/ingest_documents.py`

`LocalDocumentLoader(DOCUMENTS_DIR).list_documents()` → for each file
`extract_text_from_document(path)` → `build_chunk_records(text, document_id=<stem>, project_id=DEFAULT_PROJECT_ID, source=<filename>)`
→ `ChromaVectorStore.add_documents(records)`. Prints per-file chunk counts and the collection name.
**This is the only consumer of `DEFAULT_PROJECT_ID`.**

### 18.4 `scripts/provision_demo.py` (151 lines)

Builds a full demo dataset **through the application's own services** (so hashing, business-ID
allocation, and authorization all match production). `ADMIN_UID = "admin"`, `DEFAULT_PASSWORD = "ChangeMe123!"`.

- **4 departments:** Human Resources (billable), Engineering (billable), Marketing (both), Finance (non-billable)
- **10 users** at `@nexora.local` with short usernames (`aarav`, `priya`, `rohan`, `vikram`, `anita`,
  `meera`, `karan`, `sneha`, `ritu`, `deepak`) and roles Manager/Tester/Manager/Developer/Developer/
  Solution Architect/Manager/Tester/Manager/Developer; all `must_change_password=True`
- **1 custom department-scoped role:** "Project Coordinator" (Engineering) with
  `PROJECT_VIEW, DOCUMENT_VIEW, DOCUMENT_QUERY, USER_VIEW, DEPARTMENT_VIEW`
- **4 projects:** Employee Handbook Refresh (HR), Company Bot Platform (Engineering),
  Brand Website Rebuild (Marketing), Payroll Upgrade (Finance)
- 1 department membership + 1 project membership per user; 4 project grants
- Writes `data/seeded_users.json` including **plaintext passwords**

### 18.5 `scripts/seed_faq_cache.py` (170 lines)

Pre-warms `data/response_cache.json` with **34 standard HR FAQ answers** by calling the live API at
`http://127.0.0.1:8000/api/chat` with `session_id="faq-seeder"`. Skips any question whose cosine
similarity to an existing entry is `>= LLM_CACHE_SIMILARITY_THRESHOLD`; `time.sleep(0.4)` between
calls. Stores `{input, vector, output: json.dumps(result)}`. Prints seeded/skipped/errors.

### 18.6 Runtime directories

| Path | Contents | Git |
|---|---|---|
| `.chroma/` | ChromaDB SQLite + HNSW index | ignored |
| `instance/` | `knowlayer.db3` (+ backup) | ignored |
| `conversation_logs/` | JSON audit logs | ignored |
| `data/` | `faqs.json`, `seeded_users.json` (committed) + `response_cache.json`, `faqs_cache.json`, `semantic_cache.json` (ignored) | mixed |
| `input/` | Source `.docx` files | committed |

---

## 19. Test Suite

**90 test files**: 53 unit, 18 contract, 19 integration, plus 2 fixture modules.

### 19.1 Structure

```
tests/
├── fixtures/
│   ├── organization_repositories.py   # InMemoryUnitOfWork + in-memory repo implementations
│   └── rbac.py                        # RBAC seeding helpers
├── unit/        53 files
├── contract/    18 files
└── integration/ 19 files
```

`tests/fixtures/organization_repositories.py` is the reason the `UnitOfWork` protocol pays off: the
entire organization domain is tested against in-memory repositories with no database.

### 19.2 What the suites cover

**Unit (53)** — grouped by area:
- *Authorization*: `test_authorization_engine.py`, `test_organization_authorization.py`,
  `test_permission_authorization.py`, `test_project_authorization.py`, `test_authz_bypass_regression.py`
  (29 tests / 15 scenarios, added after the security review), `test_orchestrator_access_gate.py`,
  `test_document_access_service.py`, `test_project_access_service.py`, `test_rag_access_probe.py`
- *Auth*: `test_authentication_service.py`
- *Chat pipeline*: `test_query_normalizer.py`, `test_query_intent_classifier.py`,
  `test_query_orchestrator_logging.py`, `test_conversation_query_resolver.py`, `test_retrieval_quality.py`,
  `test_retrieval_selection.py`, `test_negative_response_cache_prevention.py`
- *Cache*: `test_dual_cache.py`, `test_quality_aware_cache.py`, `test_prompt_cache.py`, `test_json_faq_cache.py`
- *LLM*: `test_llm_provider.py`, `test_llm_response.py`, `test_provider_health.py`
- *Observability*: `test_observability.py`, `test_observability_manager.py`, `test_pipeline_tracing.py`
- *Persistence/logging*: `test_database_foundation.py`, `test_employee_id_provider.py`,
  `test_database_employee_id_provider.py`, `test_conversation_logger.py`, `test_conversation_log_cleanup.py`
- *Domain services*: `test_business_id_generator.py`, `test_session_memory_service.py`, `test_settings.py`
- *Organization use cases*: `test_user_management.py`, `test_project_management.py`,
  `test_department_membership.py`, `test_project_membership.py`, `test_project_membership_leave.py`,
  `test_role_management.py`, `test_profile_service.py`, `test_organization_explorer_service.py`,
  `test_employees_and_departments.py`
- *Documents*: `test_document_ingestion.py`, `test_document_management.py`, `test_document_provisioning.py`,
  `test_document_metadata.py`, `test_document_chunk_metadata.py`, `test_document_upload_authorization.py`
- *Lifespan*: `test_app_lifespan.py`

**Contract (18)** — one per route module, all using `app.dependency_overrides`:
`test_authentication_api.py`, `test_chat_api_contract.py`, `test_chat_access_denied_routes.py`,
`test_chat_authorization_api.py`, `test_access_management_api.py`, `test_admin_access_api.py`,
`test_department_membership_api.py`, `test_document_management_api.py`, `test_documents_project_api.py`,
`test_explorer_api.py`, `test_profile_api.py`, `test_project_membership_api.py`, `test_projects_api.py`,
`test_roles_api.py`, `test_repository_contract.py`, `test_user_management_api.py`, `test_user_scope_api.py`,
`test_streamlit_management_pages.py` (the no-SQL/no-authz-in-UI guard).

**Integration (19)** — end-to-end with a real database:
`test_authentication_bootstrap_e2e.py`, `test_authentication_security_e2e.py`, `test_rbac_e2e.py`,
`test_chat_e2e.py`, `test_rag_authorization_e2e.py`, `test_unauthorized_retrieval_e2e.py`,
`test_retrieval_authorized_scope_e2e.py`, `test_admin_access_e2e.py`, `test_manager_scope_e2e.py`,
`test_user_management_e2e.py`, `test_project_management_e2e.py`, `test_project_membership_e2e.py`,
`test_department_membership_e2e.py`, `test_document_management_e2e.py`, `test_document_upload_e2e.py`,
`test_document_upload_validation.py`, `test_document_metadata_persistence.py`,
`test_document_chroma_metadata_e2e.py`, `test_business_id_concurrency.py`.

`Documentation/Workflows/V2/security-authorization-review.md` records the last full run:
**394 unit+contract, 41 integration, 435 total.**

---

## 20. Implemented vs. Unwired — Critical Reading

This is the single most important section for anyone (human or LLM) about to change this codebase.
A large amount of well-tested, well-documented capability **exists but is not reachable from the
running application.** Do not assume a feature works because the class exists and has tests.

### 20.1 Built, unit-tested, NOT in the request path

| Component | File | Evidence |
|---|---|---|
| `RetrievalQualityGate` / `get_retrieval_quality_gate()` | `use_cases/chat/retrieval_quality.py` (23 KB) | Repo-wide search: only self-references. Never imported by the orchestrator. All four `QUALITY_GATE_*` env vars are dead. |
| `QueryIntentClassifier` / `get_query_intent_classifier()` | `use_cases/chat/query_intent_classifier.py` (15 KB) | Same — only self-references. |
| `PipelineTracer` (8-stage tracing) | `observability/pipeline_tracer.py` (23 KB) | `QueryOrchestrator.__init__` assigns `self.pipeline_tracer` then **never calls it**. No `trace_stage`/`PipelineStage` use outside the module. `ENABLE_PIPELINE_TRACING` unread. |
| `ObservabilityManager`, `LangfuseProvider`, `PhoenixProvider`, `NullObservabilityProvider` | `observability/` | Nothing in the live path calls `get_observability_manager()`. Intended bridge (`set_observability_callback`) is never wired. Phoenix has no OTLP exporter. |
| `InMemoryQualityAwareCache` / `get_quality_cache()` | `cache/quality_aware_cache.py` (26 KB) | Never instantiated by the app. |
| `DualCache` / `get_dual_cache()` (LangCache + JSON) | `cache/dual_cache.py` (16 KB) | Never instantiated. `_sync_json_to_langcache` is a log stub. |
| `JsonSemanticResponseCache` | `llm/json_semantic_cache.py` | Never instantiated. |
| `JsonFAQCache` | `faq/json_faq_cache.py` | Never instantiated (the wired FAQ cache is `FAQSimilarityCache`). |
| `ProviderErrorTracker`, `RetryPolicy` | `llm/provider_error_tracker.py` (18 KB) | No client references it. **There is no retry loop anywhere in the codebase.** |
| `LLMResponse`, `LLMResponseBuilder`, `ResponseAggregator` | `llm/llm_response.py` (19 KB) | Only reachable via `generate_with_response`, which the orchestrator never calls (it uses `generate`). |
| `ResponseAggregator` stats | — | Nothing feeds it. |
| `DocumentManagementService.register_project_document()` | `use_cases/organization/document_management.py:126` | Not exposed by any route. |
| `domain/ports/retrieval.py` `RetrievalPort` | `domain/ports/retrieval.py` | Vestigial — `RetrievalService.retrieve()` has a richer signature and does not implement it. |
| `domain/entities/document_models.py` (7 dataclasses) | — | Superseded by plain dicts in the live pipeline. |
| `app/core/prompt_config.py` `load_prompt()` | — | Dead code; reads a nonexistent YAML key. |
| `EmployeeIdProvider` docstring promise | — | "Temporary mock boundary pending a trusted IdP" — the DB-backed implementation is now in place. |
| `AdminAPI.list_project_access_grants` / `grant_project_access` / `revoke_project_access` | `streamlit_app/services/admin_api.py` | Implemented client-side, **no Streamlit page surfaces them**. |
| `AuthenticationService.refresh()` / `change_password()` | `streamlit_app/services/authentication_service.py` | Implemented, **never called from any page**. There is no refresh or change-password UI. |
| `OrganizationService` (83 lines) | `streamlit_app/services/` | Legacy duplicate of `AdminAPI`; still used by 2 pages. |
| `postgres/configuration.py`, `sqlite/configuration.py` | `persistence/` | Present but not the active path (generic `factory.py` is). |
| `migrations/*.sql` (5 files) | `persistence/migrations/` | Documented DDL; **never executed**. |
| `alembic` | `requirements.txt` | Dependency present, no configuration, no usage. |
| `scripts/smoke_test.py` | — | **Referenced in README validation commands but does not exist.** |
| CI workflows | `.github/` | `.github/skills/` only (Spec-Kit skills). **No CI.** |

### 20.2 Enabled but with no effect

`ENABLE_PROVIDER_HEALTH`, `CIRCUIT_BREAKER_*` (monitor hardcodes the same values),
`ENABLE_QUALITY_GATE`, `QUALITY_GATE_*`, `ENABLE_PIPELINE_TRACING`, `PIPELINE_TRACER_MAX_TRACES`,
`LANGCACHE_*`, `DUAL_CACHE_*`, `SEMANTIC_CACHE_*`, `RESPONSE_CACHE_FILE`, `FAQ_CACHE_FILE`,
`QUERY_NORMALIZER_EXPANSION`, `CHROMA_HOST`, `CHROMA_PORT`, `EMBEDDING_MODEL` (in `chroma_client.py`).

### 20.3 Effectively disabled in the running deployment

- `response_cache` is `None` by default ⇒ **the orchestrator's response-cache stage (steps 2 and 11) is a no-op in the standard deployment.** Steps 0a/0b feedback still work (they only read `_last_interaction`).
- `RAG_DISTANCE_THRESHOLD = 0.80` in `.env` vs `0.60` in code ⇒ retrieval is materially **more permissive** in the running app than the code default suggests.
- `MONGODB_URI` is unset ⇒ `MongoFAQStore` is a **no-op**; FAQ writes are discarded.
- `LANGCACHE_*` are empty ⇒ if `DualCache` were wired it would fall back to JSON only.
- `OBSERVABILITY_PROVIDER = null` ⇒ no vendor tracing even if the manager were wired.
- `LANGCHAIN_TRACING_V2 = false` ⇒ **the only live tracing system is also off by default.**

### 20.4 Where the docs contradict the code

| Doc claim | Reality |
|---|---|
| `ARCHITECTURE.md:300` describes a built-in `Lead` role | `permission_catalog.py` does not seed one. Lead authority = `Project.manager_uid == user.uid`. |
| `ARCHITECTURE.md:277` "most recent six messages" | `SESSION_MAX_HISTORY_TURNS = 6` is 6 **turns** = 12 **messages**. |
| Docs reference `instance/knowlayer.db` | `.env` points at `knowlayer.db3`; the file on disk is `.db3`. |
| `core/prompt_config.py` reads key `"system"` | The YAML key is `system_prompt`. Dead code. |
| README validation uses `scripts/smoke_test.py` | File does not exist. |
| `README.md` / `ARCHITECTURE.md` | **Contain 18 and 9 unresolved git merge-conflict markers respectively.** Do not trust them. |

---

## 21. Known Issues, Risks & Bugs

### 21.1 Security-relevant

| # | Issue | Location | Impact |
|---|---|---|---|
| 1 | **4 of 5 chat endpoints unauthenticated**, including destructive `cache/clear` and `providers/reset` | `api/routes/chat.py` | Anyone who can reach the API can wipe caches and trip provider breakers. |
| 2 | **All 8 `/api/tokens/*` endpoints unauthenticated** | `api/routes/tokens.py` | `by-session` leaks every session ID; `recent` leaks per-call usage; `POST /clear` destroys all telemetry. Docstring says "requires authentication in production" — not done. |
| 3 | `AUTH_SECRET_KEY` and `ADMIN_INITIAL_PASSWORD` still at **placeholder values** in `.env` | `.env` | Anyone who has read this repo can forge an Admin JWT. **Rotate both before any shared deployment.** |
| 4 | Real-format OpenRouter/Groq keys present in the working copy | `.env` | **Rotate both.** (`.env` is gitignored, so the git history is clean.) |
| 5 | `change_password` returns `detail=str(error)` | `api/routes/authentication.py` | Leaks "Invalid credentials" / "Admin access required" / "User not found". |
| 6 | `POST /auth/logout` performs **no** token invalidation | `api/routes/authentication.py` | Access token remains valid for up to 8 h; refresh tokens have no denylist. |
| 7 | `must_change_password` is advisory only | — | Nothing blocks any endpoint while the flag is set. |
| 8 | `GET /api/departments` and `GET /api/users` receive the principal but **don't use it** | `api/routes/organization.py` | Any authenticated user enumerates all users and departments. No pagination. |
| 9 | The Streamlit auth cookie is **JS-readable, not HttpOnly**, ~1 day TTL | `streamlit_app/session_auth.py` | Documented as unsuitable for production. |
| 10 | Deactivated users' tokens still *authenticate* (401 vs 403) | `dependencies.py` + engine `_active_user` | Engine still denies everything, so not a bypass — but the status code is misleading. |
| 11 | Hard-coded minimum password length 8 lives in the service, not settings | `authentication_service.py` | Not configurable; duplicated client-side in the UI. |

### 21.2 Correctness / robustness

| # | Issue | Location |
|---|---|---|
| 12 | **`QueryOrchestrator` mutates process-global state per request:** `active_orchestrator.project_contact_lookup = authorization.project_access_contact` on the shared singleton | `api/routes/chat.py` tier-3 branch | Thread-safety race under concurrency, and permanently pins a **per-request** `OrganizationAuthorizationService` (and thus a per-request SQLAlchemy `Session`) onto the global orchestrator. |
| 13 | `GET /api/faqs` calls the orchestrator **synchronously on the event loop** | `api/routes/chat.py` | Blocks the loop for the duration of an LLM call. |
| 14 | Startup conversation-log cleanup runs **synchronously on the event loop** (the periodic one correctly uses `asyncio.to_thread`) | `app/main.py:57` | Startup latency. |
| 15 | `_pending_citations` / `_last_interaction` / `_alternative_answer_given` are **unbounded and un-TTL'd** | `query_orchestrator.py:64-68` | Unbounded memory growth in a long-running process. |
| 16 | The follow-up citation/relevance flow is **per-process only** | same | Breaks entirely with multiple Uvicorn workers. |
| 17 | `ChromaVectorStore` **hardcodes** the embedding model string | `chroma_client.py:33` | Changing `EMBEDDING_MODEL` in `.env` silently does nothing; a model change would also require re-embedding the whole collection. |
| 18 | `DualCache` re-reads and rewrites the whole JSON file on **every** get/put | `dual_cache.py` | O(N) disk I/O per request if ever wired. |
| 19 | `JsonSemanticResponseCache` uses **FIFO, not LRU** | `json_semantic_cache.py` | Contradicts its class contract. |
| 20 | `AuthorizationEngine` opens its **own UoW per decision** | `authorization_engine.py` | `ProfileService` / `OrganizationExplorerService` issue one extra transaction per per-item check (N+1). |
| 21 | `session_memory_service.py` lazily imports its own infrastructure default | `SessionMemoryService.__init__` | Pragmatic layering violation (documented as such in-file). |
| 22 | `llm_provider.py` and `employee_id_provider.py` are **ABCs** while every other port is a `Protocol` | `domain/services/` | Inconsistent; structural typing is lost for those two. |
| 23 | `document_repository.py` duplicates the `DocumentRepository` protocol also declared in `organization_repositories.py` | `domain/ports/` | The `unit_of_work.py` import resolves to the standalone file; the declaration in `organization_repositories.py` is the one actually used. |
| 24 | Two `AuthorizationEngine` instances built over two separate UoWs inside `get_document_access_service` / `get_project_access_service` | `api/dependencies.py` | Inconsistent with `get_authorization_service`, which shares one UoW. |
| 25 | `GET /api/users/{uid}` is registered before `GET /api/users/me/profile` | `api/routes/organization.py` | Currently safe (different segment counts) but fragile. |
| 26 | `POST /api/projects/{id}/members/{uid}` returns **204** on a create, while department-member assignment returns 201 | `api/routes/organization.py` | Inconsistent. |
| 27 | `import logging` duplicated; `logger` assigned twice in `retrieval_service.py` | `retrieval_service.py:1-21` | Cosmetic. |
| 28 | `README.md` (18 markers) and `ARCHITECTURE.md` (9 markers) contain **unresolved merge conflicts** | repo root | Both are unreliable sources. This document is the substitute. |

### 21.3 Operational

- **No CORS** ⇒ any browser SPA on another origin is blocked.
- **No rate limiting** anywhere.
- **No request-ID / correlation-ID**, so multi-hop traces can't be stitched from logs.
- **No health/readiness probe that checks dependencies** — `/health` returns `{"status":"ok"}` unconditionally; `/api/documents/status` and `/api/organization/status` are hardcoded literals.
- **No CI** (`.github/` contains only Spec-Kit skills).
- **No containerization** despite it appearing in `Documentation/Plan/v3/Akaash.md`.
- **Everything is process-global**: the orchestrator, all caches, `TokenTracker`, `PipelineTracer`, `ObservabilityManager`, the `AuthorizationEngine` UoW, `_pending_citations`. **Cannot run multi-worker without losing the conversation-follow-up feature.**

---

## 22. Glossary

| Term | Meaning in this codebase |
|---|---|
| **KnowLayer** | The product name. `Company_Bot` is the repo name. |
| **Business ID** | Human-readable, never-reused identifier: `MSS-001`, `DEPT-001`, `PROJ-001`, `DOC-001`. Allocated from `business_id_sequences` via atomic `UPDATE … RETURNING`. |
| **`uid`** | Internal user primary key (uuid4 hex). Distinct from `username` (login) and `employee_id` (business ID). |
| **`internal_id`** | Surrogate autoincrement PK for `projects` / `documents`; the business ID is a separate unique column. |
| **Principal** | `AuthenticatedPrincipal` — the frozen trust token passed across every security boundary. Carries only `uid`, `token`, `must_change_password`, `refresh_token`. |
| **AuthorizationScope** | The exact retrieval boundary: `is_admin`, `project_ids` (`None`=unrestricted / `[]`=deny-all / list=allow-list), `document_ids`, `include_unassigned`. |
| **Two-axis RBAC** | **WHAT** = permission from the role. **WHERE** = project membership ∪ lead/manager authority ∪ explicit grant. |
| **Polymorphic principal** | `principal_type ∈ {role, user}` plus `role_id?` / `user_id?` — one table serves both grant kinds. |
| **Department-scoped role** | `Role.scope == "department"`; only honored when `role.department_id` matches the membership's department **or** the user's home department. |
| **Unassigned document** | `documents.project_id IS NULL` ⇒ rendered as the literal string `"unassigned"` in Chroma metadata; authorized org-wide via `include_unassigned`. |
| **Negative response** | An answer matching `_NO_INFO_PATTERN` ("I could not find that information…"). **Never written to or served from any cache** — enforced at 5 call sites. |
| **Evidence** | A retrieved Chroma chunk that passed the distance threshold, redundancy, and context-budget filters. |
| **Distance** | Chroma **cosine distance**; lower = closer. Threshold 0.60 (code) / 0.80 (`.env`). |
| **Lexical grounding** | Non-empty intersection of query and chunk terms after stopword removal and crude singularization. |
| **Provenance / citation** | `{source, section, text}` built from the **same** evidence that entered the prompt. |
| **defer_citations** | Streamlit sends `True` so the UI renders citations as a blockquote and the relevance follow-up can trigger. |
| **Relevance prompt** | `"Was this response relevant to your question?"` — the hardcoded string that gates the 👍/👎 feedback flow. |
| **Access-denied probe** | Unrestricted Chroma query used to detect that relevant content exists but is out of scope; returns redacted metadata only. |
| **Unit of Work** | `UnitOfWork` protocol — 11 repositories sharing one transactional session. The only DB access path. |
| **Port / adapter** | `Protocol`/`ABC` in `app/domain/ports|services` (the contract) vs. the concrete implementation in `app/infrastructure` (the adapter). |
| **Use case** | `app/use_cases/**` — application orchestration over ports. Not to be confused with "business logic", which mostly lives in `domain/services`. |
| **`defer_citations` / `_finish`** | `_finish(res)` wraps every orchestrator return: writes the conversation JSON log and stamps LangSmith metadata. |
| **Spec-Kit** | GitHub's spec-driven development scaffolding, vendored in `.specify/` and `.github/skills/`. Produced the three `specs/00{1,2,3}-*` feature specs. |

---

## Appendix A — Quick "Where do I change X?" Index

| I want to change… | Go to |
|---|---|
| The LLM prompt | `config/prompts.yaml` → `prompts.rag_answer_generation` (plus the hardcoded prompts in `query_orchestrator.py`) |
| A retrieval threshold | `app/core/settings.py` §"RAG retrieval tuning" |
| Which documents a user can see | `app/domain/services/authorization_engine.py` (`_project_access_scope`, `can_read_document`, `authorization_scope`) |
| The Chroma metadata schema | `app/use_cases/ingestion/document_processing.py::build_chunk_records` + `.env`'s `COLLECTION_NAME` |
| A new API endpoint | `app/api/routes/<resource>.py` + `app/api/schemas/<resource>.py` + a provider in `app/api/dependencies.py` + a service method in `app/use_cases/organization/` |
| A new RBAC permission | `app/domain/services/permission_catalog.py` `PERMISSION_DEFINITIONS` **and** `ACTION_PERMISSIONS` in `authorization_engine.py` |
| A new role | `permission_catalog.py::INITIAL_ROLE_DEFINITIONS` (seed only applies on a fresh DB) |
| A DB table/column | `sqlalchemy/models.py` or `foundation_models.py` **+** the `_COLUMN_ADDITIONS`/`_INDEX_ADDITIONS` lists in `sqlalchemy/session.py` + `repositories.py` mapper |
| An HTTP error code | The `_error()` helper in the relevant `routes/*.py` |
| A new Streamlit page | `streamlit_app/pages/<name>.py` + register it in `app.py`'s `st.page_link` sidebar + add the client method to a `services/*.py` |
| Token/cost reporting | `token_tracker.py` + `api/routes/tokens.py` + the Streamlit token-metrics expander |
| The LLM vendor or fallback order | `QueryOrchestrator.__init__` (the `FallbackLLMProvider(...)` construction) + `api/routes/chat.py::get_providers_health` |

## Appendix B — How to Run

```powershell
# One-time
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env       # then fill in real keys + a real AUTH_SECRET_KEY

# Seed reference data (optional but recommended)
.\.venv\Scripts\python.exe scripts\provision_demo.py
.\.venv\Scripts\python.exe scripts\ingest_documents.py        # requires docs in input/

# Run (launches two windows)
.\setup.ps1

# Or separately
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m streamlit run streamlit_app/app.py --server.port 8501

# Tests
.\.venv\Scripts\python.exe -m pytest tests/unit
.\.venv\Scripts\python.exe -m pytest tests/contract
.\.venv\Scripts\python.exe -m pytest tests/integration

# DB inspection
.\.venv\Scripts\python.exe scripts\dump_db.py users --db instance/knowlayer.db3
```

**Bootstrap admin:** `admin` / `ADMIN_INITIAL_PASSWORD` (from `.env`). The first login is expected to
be followed by a password change (`must_change_password`).

---

*End of document. If you find a claim here that contradicts the code, the code is correct and this
file needs updating. Sections 20 and 21 are the highest-value sections for anyone about to change
this system.*
