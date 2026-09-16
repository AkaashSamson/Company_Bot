# Company Bot Platform

An enterprise organizational intelligence platform that gives authenticated employees secure, permission-aware access to internal policy and document knowledge, authoritative employee data, and hybrid synthesis across trusted sources.

## Overview

**Company Bot** is a secure, policy-aware organizational knowledge assistant that draws on internal documents and enterprise systems. It delivers grounded answers with provenance, citations, and clear source attribution while maintaining strict authorization boundaries and preventing unauthorized data access.

### Platform Highlights
- Local document storage in `input/` with DOCX, TXT, Markdown, and RST ingestion
- Text extraction and chunking with `python-docx`
- Local persistent Chroma database in `.chroma/` with Sentence-Transformer embeddings
- FastAPI backend with chat, token observability, and SQL RBAC routes
- Organization management foundation with a configurable SQLite database
- Streamlit multi-page UI with RBAC management and interactive chat
- Two-step citation flow (initial concise response with on-demand citations)
- Distance-aware evidence selection and unauthorized relevance probing
- OpenRouter primary LLM with Groq fallback and LangSmith tracing

### Vision

Build a system that transforms fragmented organizational knowledge into decision-ready answers by combining:
- Internal policy and handbook knowledge retrieval
- Employee-specific authoritative data lookups
- Permission-aware synthesis across multiple sources
- Complete audit trails and citation provenance

---

## Key Features

### 📋 Core Capabilities

1. **Document-Based Knowledge Retrieval (P1)**
   - Ask questions about policies, handbooks, procedures, and technical documentation
   - Retrieve relevant approved documents with authorization checks
   - Receive answers grounded in source material with citations

2. **Employee-Specific Data Lookup (P1)**
   - Query leave balances, role-based benefits, appraisal information from authoritative HR systems
   - Ensure data comes from trusted sources, not stale documents
   - Maintain access controls and traceability

3. **Hybrid Question Answering (P1)**
   - Combine policy and personal context in a single answer
   - Example: "How many annual leave days can I take and how many do I have left?"
   - Clear provenance from both sources

4. **Cross-Functional Knowledge Search (P2)**
   - Search internal technical, project, and policy documentation
   - Find prior solutions and architecture patterns
   - Authorization-aware results filtered by role and permissions

### 🔒 Security & Authorization

- **Pre-retrieval authorization enforcement** - No data is retrieved without permission
- **Role-based access control** - Different access levels for different roles and teams
- **Document-level and employee-level authorization** - Granular permission boundaries
- **Comprehensive audit logging** - Track all queries, retrievals, and system interactions
- **Sensitive data protection** - Prevent unauthorized exposure of personal or confidential records

---

## Architecture Overview

KnowLayer follows a **modular monolith** design with clear separation of concerns:

```
┌─────────────────────────────────────────────────────┐
│         Streamlit UI / Future Integrations          │
│         (Teams, Slack, Custom APIs)                 │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│              FastAPI Backend Layer                  │
│   ├── API Routes & Request Handling                 │
│   ├── Authentication & Authorization               │
│   └── Audit & Observability                         │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│          Core Domain Intelligence Layer             │
│   ├── Query Routing & Intent Understanding         │
│   ├── Authorization Evaluation                      │
│   ├── Evidence Retrieval & Synthesis               │
│   ├── Provenance & Citation Management             │
│   └── Source-of-Truth Enforcement                  │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│     Adapter & Infrastructure Layer                  │
│   ├── LLM Provider Abstraction                      │
│   ├── Vector Search & Document Retrieval           │
│   ├── Enterprise System Connectors                 │
│   │   ├── HR System Adapter                        │
│   │   ├── Document Storage Adapter                 │
│   │   └── Authorization Provider                   │
│   └── Storage & Cache Layer                        │
└─────────────────────────────────────────────────────┘
```

### Design Principles

- **Independence**: Core intelligence remains decoupled from UI, LLM provider, storage, and enterprise connectors
- **Authorization First**: Permission checks occur before any data retrieval
- **Provenance Mandatory**: Every answer includes explicit source citations
- **Adapter Pattern**: Enterprise systems plugged in via clean interfaces
- **Testability**: Unit, integration, security regression, and contract tests throughout

---

## Project Structure

```
Company_Bot/
<<<<<<< HEAD
├── README.md                          # This file
├── specs/
│   └── 001-knowlayer-platform/
│       ├── spec.md                    # Full feature specification
│       ├── plan.md                    # Implementation plan
│       ├── tasks.md                   # Detailed task breakdown
│       └── checklists/
│           └── requirements.md
├── Documentation/
│   └── Abhinav.md                     # Internal documentation
└── backend/                           # (To be created)
    ├── app/
    │   ├── api/                       # FastAPI routes
    │   ├── core/                      # Domain logic
    │   ├── domain/                    # Entities & business rules
    │   ├── infra/                     # Storage & provider adapters
    │   ├── security/                  # Auth & authorization
    │   └── services/                  # Service layer
    ├── tests/
    │   ├── unit/                      # Unit tests
    │   ├── integration/               # Integration tests
    │   ├── contract/                  # Adapter contract tests
    │   └── security/                  # Security regression tests
    ├── migrations/                    # Database migrations
    ├── config/                        # Configuration files
    ├── requirements.txt               # Python dependencies
    └── main.py                        # Application entry point

streamlit_app/                         # (To be created)
├── app.py                             # Main Streamlit application
├── pages/                             # Multi-page UI
├── components/                        # Reusable UI components
└── services/                          # Client-side service layer
=======
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── routes/
│   │   │   ├── chat.py                # POST /api/chat
│   │   │   ├── organization.py        # Users, departments, projects, memberships
│   │   │   ├── documents.py           # Document management, upload, access
│   │   │   ├── explorer.py            # Organization Explorer data
│   │   │   ├── roles.py               # RBAC role management
│   │   │   └── authentication.py      # Login, token refresh, password change
│   │   ├── schemas/
│   │   │   ├── chat.py
│   │   │   ├── organization.py
│   │   │   ├── documents.py
│   │   │   ├── explorer.py
│   │   │   ├── profile.py
│   │   │   ├── roles.py
│   │   │   └── authentication.py
│   │   └── dependencies.py            # FastAPI DI: UoW, auth, authorization
│   ├── core/settings.py               # Environment-backed configuration
│   ├── domain/
│   │   ├── entities/
│   │   │   ├── document_models.py
│   │   │   └── organization_models.py
│   │   ├── ports/
│   │   │   ├── authorization_service.py
│   │   │   ├── authentication_service.py
│   │   │   ├── organization_repositories.py
│   │   │   ├── document_repository.py
│   │   │   ├── retrieval.py
│   │   │   ├── sequence_repository.py
│   │   │   └── unit_of_work.py
│   │   └── services/
│   │       ├── authorization_engine.py   # Central RBAC authorization engine
│   │       ├── authorization_service.py  # Legacy compatibility shim
│   │       ├── authentication_service.py
│   │       ├── session_memory_service.py
│   │       ├── llm_provider.py
│   │       ├── organization_errors.py
│   │       ├── permission_catalog.py
│   │       ├── business_id_generator.py  # Atomic business ID generation (MSS/DEPT/PROJ/DOC)
│   │       └── session_memory_service.py
│   ├── infrastructure/
│   │   ├── vector/chroma_client.py
│   │   ├── document/local_document_loader.py
│   │   ├── ingestion/provisioner.py
│   │   ├── llm/
│   │   │   ├── openrouter_client.py
│   │   │   ├── groq_client.py
│   │   │   └── fallback_llm_provider.py
│   │   ├── authentication/
│   │   │   ├── bootstrap.py             # Admin account provisioner
│   │   │   └── password_hasher.py       # PBKDF2-SHA256
│   │   ├── persistence/
│   │   │   ├── factory.py               # SQLAlchemy SessionFactory + lifespan init
│   │   │   ├── rbac_seed.py             # Seeds RBAC roles and permissions on startup
│   │   │   ├── sqlite/configuration.py
│   │   │   ├── postgres/configuration.py
│   │   │   └── sqlalchemy/
│   │   │       ├── models.py            # SQLAlchemy ORM mappings
│   │   │       ├── foundation_models.py # Role, Permission, RBAC join tables
│   │   │       ├── repositories.py      # All repository implementations
│   │   │       ├── session.py
│   │   │       └── unit_of_work.py
│   │   └── audit/authentication_events.py
│   └── use_cases/
│       ├── chat/
│       │   ├── query_orchestrator.py
│       │   ├── conversation_query_resolver.py
│       │   ├── retrieval_service.py
│       │   ├── provenance_service.py
│       │   └── session_memory.py
│       ├── organization/
│       │   ├── user_management.py
│       │   ├── project_management.py
│       │   ├── membership_management.py
│       │   ├── department_membership.py
│       │   ├── document_management.py
│       │   ├── document_access.py
│       │   ├── project_access.py
│       │   ├── role_management.py
│       │   ├── organization_explorer.py
│       │   └── profile.py
│       └── ingestion/document_processing.py
├── streamlit_app/
│   ├── app.py                          # Chat UI
│   ├── pages/
│   │   ├── users.py
│   │   ├── projects.py
│   │   ├── departments.py
│   │   ├── documents.py
│   │   ├── organization.py             # Organization Explorer
│   │   ├── explorer.py
│   │   ├── profile.py
│   │   └── roles.py
│   └── services/
│       ├── chat_service.py
│       ├── organization_service.py
│       ├── admin_api.py
│       ├── authentication_service.py
│       ├── explorer_api.py
│       ├── profile_api.py
│       ├── document_service.py
│       └── ui_helpers.py
├── tests/
│   ├── unit/                           # 46 test files
│   ├── contract/                       # 15 test files
│   └── integration/                    # 20 test files
├── Documentation/
│   ├── Workflows/                      # Workflow and security review docs
│   └── Team_logs/                      # Team daily logs
├── input/                              # Local source documents
├── scripts/
│   ├── ingest_documents.py
│   └── smoke_test.py
├── instance/knowlayer.db              # SQLite database (not committed)
├── .chroma/                           # Generated local vector store
├── .env                               # Local configuration and secrets, not committed
├── .env.example                       # Configuration template with placeholders
├── requirements.txt
├── setup.ps1                          # Launches the two services
├── ARCHITECTURE.md
└── README.md
>>>>>>> feature/sql-user-management
```

---

<<<<<<< HEAD
## Technology Stack
=======
- Windows PowerShell
- Python 3.12 or newer (tested with 3.14.7)
- At least one supported source document in `input/`
- Internet access on the first run so Python packages and the embedding model can be downloaded
- API keys in a local `.env` file for OpenRouter and Groq generation
>>>>>>> feature/sql-user-management

### Backend
- **Framework**: FastAPI (async web framework)
- **Language**: Python 3.11+
- **ORM**: SQLAlchemy (database abstraction)
- **Data Validation**: Pydantic (type safety & schema validation)
- **Testing**: pytest (unit & integration tests)

### Persistence
- **Relational DB**: PostgreSQL (application state & permissions)
- **Vector DB**: Vector database for embeddings and semantic search
- **Object Storage**: Blob storage for document files
- **Cache**: Redis or similar for session state and hot retrieval

### AI & Retrieval
- **LLM Provider**: OpenAI-compatible abstraction (support for multiple providers)
- **Local Fallback**: Optional local LLM support (e.g., Ollama, LM Studio)
- **Embeddings**: Vector embeddings for document semantic search
- **RAG Pattern**: Retrieval-Augmented Generation with citation tracking

<<<<<<< HEAD
### Frontend
- **UI Framework**: Streamlit (rapid interactive web apps)
- **HTTP Client**: Requests or httpx (backend communication)
- **State Management**: Streamlit session state

### Deployment
- **Target Platform**: Linux server
- **Process Management**: Gunicorn/Uvicorn for ASGI serving
- **Monitoring**: Structured logging & audit trails

---

## Getting Started

### Prerequisites

- Python 3.11 or higher
- PostgreSQL (or compatible database)
- Vector database access (e.g., Pinecone, Weaviate, or local alternative)
- LLM API access (e.g., OpenAI API key) or local LLM setup

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/AkaashSamson/Company_Bot.git
   cd Company_Bot
   ```

2. **Install Python dependencies**
   ```bash
   # Backend dependencies
   cd backend
   pip install -r requirements.txt
   
   # Streamlit app dependencies (if separate)
   cd ../streamlit_app
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   ```bash
   # Copy template and edit with your values
   cp .env.template .env
   ```

   Required variables:
   - `DATABASE_URL` - PostgreSQL connection string
   - `VECTOR_DB_URL` - Vector database connection
   - `LLM_API_KEY` - LLM provider API key
   - `LLM_PROVIDER` - Provider name (e.g., openai, anthropic)
   - `JWT_SECRET` - Authentication secret
   - `ENVIRONMENT` - dev, staging, or production

4. **Initialize the database**
   ```bash
   cd backend
   python -m alembic upgrade head
   ```

5. **Run the backend**
   ```bash
   cd backend
   python main.py
   # or with uvicorn directly:
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

6. **Run the Streamlit UI (in a new terminal)**
   ```bash
   cd streamlit_app
   streamlit run app.py
   # UI will be available at http://localhost:8501
   ```

---

## Usage

### For Employees

#### Ask a Policy Question
```
"What is the process for taking parental leave?"
→ System retrieves handbook excerpts and returns grounded answer with citations
```

#### Check Leave Balance
```
"How many annual leave days do I have remaining?"
→ System fetches current balance from HR system (authoritative source)
=======
```powershell
cd "C:\path\to\Company_Bot"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and provide valid `OPENROUTER_API_KEY` and `GROQ_API_KEY` values. The database defaults to `sqlite:///./instance/knowlayer.db` via `DATABASE_URL`. Set `ADMIN_USERNAME`, `ADMIN_INITIAL_PASSWORD`, and a private `AUTH_SECRET_KEY` before first startup.

Index the documents before the first chat run:

```powershell
.\.venv\Scripts\python.exe scripts\ingest_documents.py
>>>>>>> feature/sql-user-management
```

#### Hybrid Query
```
"How many annual leave days can I take and how many do I have left?"
→ System combines policy + employee data into one answer
```

#### Search Documentation
```
"Has anyone implemented a similar architecture for [X]?"
→ System searches project docs and returns relevant matches with citations
```

### API Examples

#### Query Endpoint
```bash
curl -X POST http://localhost:8000/api/query \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the process for remote work approval?",
    "context": {"user_id": "emp123", "department": "engineering"}
  }'
```

Response:
```json
{
  "answer": "Remote work requires manager approval...",
  "sources": [
    {
      "document_id": "policy-001",
      "title": "Remote Work Policy",
      "excerpt": "...",
      "page": 2,
      "confidence": 0.95
    }
  ],
  "citations": ["[1] Remote Work Policy, Page 2"],
  "authorization_status": "authorized"
}
```

---

## Key User Stories

### Priority 1 (MVP Critical)

**US-1: Policy Question with Citations**
- Employee asks about policy/handbook
- System retrieves authorized documents
- Answer includes citations and source metadata

**US-2: Employee-Specific Data from HR**
- Employee asks for leave balance, benefits, appraisal
- System routes to authoritative HR system
- Data is real-time, not from stale documents

**US-3: Hybrid Questions**
- Employee combines policy + personal data in one question
- System synthesizes answer with provenance from both sources
- No unauthorized data leakage

**US-4: Cross-Functional Search (P2)**
- Employee searches technical/project documentation
- System returns relevant matches filtered by role permissions
- Prior solutions and patterns are discoverable

---

## Security & Compliance

### Authorization Model

1. **Authentication**: Employee identity verified via SSO/JWT
2. **Authorization Evaluation**: Permission check before retrieval
3. **Document-Level Access**: Role-based filtering on all documents
4. **Employee-Level Access**: Only view own data or authorized records
5. **Pre-Retrieval Enforcement**: No data retrieved without permission

### Audit & Logging

Every interaction is logged with:
- Query text and intent
- User context (department, role, team)
- Retrieved documents and excerpts
- Model interactions and decisions
- Authorization decisions (allow/deny)
- Timestamp and request ID

Sensitive data is **never logged in cleartext**.

### Data Protection

- Personal/confidential records **never exposed** across permission boundaries
- LLM is **not treated as authoritative source** for sensitive facts
- Restricted content excluded from synthesis when user lacks permission
- Clear error messages when data is unavailable due to authorization

---

## Development

### Testing

Run the full test suite:
```bash
cd backend
pytest                     # Run all tests
pytest -v                  # Verbose output
pytest tests/unit/         # Run only unit tests
pytest tests/security/     # Run security regression tests
pytest tests/contract/     # Run adapter contract tests
```

### Code Quality

<<<<<<< HEAD
```bash
# Linting
pylint app/

# Type checking
mypy app/

# Formatting
black app/
=======
```text
User
  -> Streamlit chat or POST /api/chat
  -> Authentication token resolved to principal
  -> AuthorizationEngine resolves scoped projects and documents
  -> QueryOrchestrator
  -> bounded conversation query resolution when needed
  -> Chroma candidate retrieval with authorized project/document filter
  -> cosine-distance relevance filtering and evidence selection
  -> compact context assembly
  -> OpenRouter primary LLM
  -> Groq fallback when the primary provider fails
  -> grounded answer and citations from the same selected evidence
>>>>>>> feature/sql-user-management
```

### Development Workflow

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Write tests first (TDD approach)
3. Implement feature in domain layer
4. Add adapter/infrastructure code
5. Ensure security and authorization checks
6. Run full test suite
7. Submit PR for review

---

## Roadmap & Future Extensibility

### MVP Scope (Current)
✅ Authentication & authorization baseline  
✅ Document ingestion, parsing, chunking, metadata  
✅ Vector search for authorized retrieval  
✅ Permission-aware RAG question answering  
✅ Provenance & citations  
✅ Backend API layer  
✅ Streamlit UI  
✅ LLM provider abstraction  
✅ Basic observability & logging  

### Phase 2: Enterprise Connectors
- Real-time HR system integration (leave, performance, benefits)
- Jira integration (project status, engineering insights)
- Zoho and ERP system connectors
- Slack/Teams integration

### Phase 3: Advanced Features
- Multi-agent reasoning for complex workflows
- Cross-domain synthesis for business decisions
- Event-driven architecture for real-time updates
- Fine-tuned models for domain-specific accuracy
- Expanded retrieval modes

### Design Principle
**All future extensions are added via adapter interfaces without reworking core intelligence logic.**

---

## Contributing

Please refer to the feature specification and implementation plan in `/specs/001-knowlayer-platform/` for detailed requirements and design decisions.

### Code Style
- Python PEP 8 compliance
- Type hints on all functions
- Docstrings on all public methods
- Clear separation of domain, adapter, and infrastructure code

### PR Checklist
- [ ] Tests pass (`pytest`)
- [ ] Type checking passes (`mypy`)
- [ ] Code formatted (`black`)
- [ ] Security review (authorization checks present)
- [ ] Audit logging added for new endpoints
- [ ] Documentation updated

---

## Support & Questions

Refer to the full specification for:
- **Feature Details**: See `/specs/001-knowlayer-platform/spec.md`
- **Implementation Plan**: See `/specs/001-knowlayer-platform/plan.md`
- **Tasks & Checklist**: See `/specs/001-knowlayer-platform/tasks.md`

---

<<<<<<< HEAD
## License

[Add license information as needed]
=======
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
OPENROUTER_API_KEY=
GROQ_API_KEY=
LLM_MODEL=openrouter/anthropic/claude-3.5-sonnet
GROQ_MODEL=llama-3.1-8b-instant
DATABASE_URL=sqlite:///./instance/knowlayer.db
STREAMLIT_API_BASE_URL=http://127.0.0.1:8000
ADMIN_USERNAME=admin
ADMIN_INITIAL_PASSWORD=
DEFAULT_USER_PASSWORD=ChangeMe123!
AUTH_SECRET_KEY=change-this-development-secret
AUTH_TOKEN_EXPIRE_MINUTES=480
EMPLOYEE_ID_PREFIX=MSS
DEPARTMENT_ID_PREFIX=DEPT
PROJECT_ID_PREFIX=PROJ
DOCUMENT_ID_PREFIX=DOC
```

The `.env.example` template sets `GROQ_MODEL=openai/gpt-oss-20b` and provides placeholders for the API keys and `AUTH_SECRET_KEY`. Environment values override the code defaults. The application's local `.env` should use the confirmed available Groq model.

## Authentication and Bootstrap

Set `ADMIN_USERNAME`, `ADMIN_INITIAL_PASSWORD`, and a private `AUTH_SECRET_KEY` in `.env` before first startup. The database provisions the Admin account idempotently on application startup via `rbac_seed` and `bootstrap`. Log in through `/api/auth/login`, change the default password, create Managers with initial passwords, and let Managers onboard employees within their departments. When a new user is created without an initial password, `DEFAULT_USER_PASSWORD` is assigned, and the user must change it on first login. Passwords are stored as PBKDF2-SHA256 representations; never commit `.env`.

## Authorization

All authorization is centralized in `AuthorizationEngine`. The engine resolves identity, active status, RBAC roles and permissions, and then answers questions about document, project, and scope access. Streamlit pages contain no permission logic; every access decision originates from the backend.

Key invariants:
- Non-admin users may only manage users and memberships within their own department.
- Only administrators can change user roles or create users with the `admin` role.
- Document grants give document-level access but do not grant broad project-wide access.
- Deactivated users are rejected at every layer (authentication, engine, profile, explorer).
>>>>>>> feature/sql-user-management

---

<<<<<<< HEAD
**Project Status**: MVP in development  
**Last Updated**: 2026-09-01  
**Lead**: Akaash Samson
=======
Run all automated tests:

```powershell
# Compile check
.\.venv\Scripts\python.exe -m compileall -q app streamlit_app tests

# Unit and contract tests
.\.venv\Scripts\python.exe -m pytest tests\unit tests\contract -q -p no:cacheprovider

# Integration tests (requires seeded database)
.\.venv\Scripts\python.exe -m pytest tests\integration -q -p no:cacheprovider
```

The full suite currently passes **435 tests** across unit, contract, and integration layers, including 29 targeted authorization-bypass regression tests covering 15 security scenarios. See [Documentation/Workflows/security-authorization-review.md](Documentation/Workflows/security-authorization-review.md) for the complete security review report.

## Validation Commands

```powershell
.\.venv\Scripts\python.exe -m compileall -q app streamlit_app tests
.\.venv\Scripts\python.exe -m pytest tests\unit tests\contract -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest tests\integration -q -p no:cacheprovider
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

## Troubleshooting

**PowerShell blocks the script:** run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`.

**The UI says connection refused:** start FastAPI first and confirm `http://127.0.0.1:8000/health` returns `{"status":"ok"}`.

**The collection is empty:** confirm supported documents are in `input/`, then run the ingestion command again.

**The first run is slow:** Sentence Transformers downloads its embedding model once and may take several minutes.

**The primary provider fails:** the fallback provider is attempted automatically. Confirm `GROQ_API_KEY` is configured and `GROQ_MODEL` names an available Groq model.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - module layout, retrieval and evidence selection, LLM provider boundary, and authorization model.
- [Documentation/Workflows/](Documentation/Workflows/) - workflow guides for authentication, user/project/document management, RBAC, question answering, and the security review.
>>>>>>> feature/sql-user-management
