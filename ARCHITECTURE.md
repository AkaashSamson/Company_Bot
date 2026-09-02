# KnowLayer Platform: Modular Monolith Architecture

## Overview

KnowLayer is built as a **modular monolith**—a single deployable application organized into independent, loosely-coupled modules. This architecture allows each module to be:
- **Independently testable**: Each layer can be tested without external dependencies
- **Easily replaceable**: Implementations (e.g., vector DB, LLM provider) can be swapped with minimal refactoring
- **Logically organized**: Domain logic is separated from infrastructure concerns
- **Future-proof**: New features can be added to future versions without touching MVP code

---

## Folder Structure & Module Organization

```
Company_Bot/
├── app/                           # Core application logic (modular monolith)
│   ├── __init__.py
│   ├── main.py                    # FastAPI app entry point
│   ├── core/                      # Cross-cutting configuration
│   │   └── settings.py            # Environment + app configuration
│   ├── api/                       # HTTP contract layer (interface to external systems)
│   │   ├── routes/
│   │   │   └── chat.py            # Chat endpoint (US1, US2, US3)
│   │   └── schemas/
│   │       └── chat.py            # Pydantic request/response contracts
│   ├── domain/                    # Pure business logic & entities (no framework deps)
│   │   ├── entities/
│   │   │   ├── document_models.py # DocumentSource, DocumentChunk, VectorRecord, Message
│   │   │   └── chat_models.py     # QuerySession, RetrievedEvidence, AnswerResponse
│   │   └── services/
│   │       └── session_memory_service.py  # Bounded conversation window logic
│   ├── use_cases/                 # Application business logic (orchestration)
│   │   ├── chat/
│   │   │   ├── query_orchestrator.py       # Retrieval → Answer generation (US1)
│   │   │   ├── retrieval_service.py        # Query builder & retrieval abstraction
│   │   │   ├── provenance_service.py       # Citation building from results
│   │   │   └── session_memory.py           # LangChain ConversationWindowBufferMemory wrapper (US2)
│   │   └── ingestion/
│   │       └── document_processing.py      # Text extraction, chunking, embedding prep
│   └── infrastructure/            # Technology-specific adapters (pluggable)
│       ├── document/
│       │   └── local_document_loader.py    # Filesystem document enumeration
│       └── vector/
│           └── chroma_client.py            # Chroma DB persistence adapter
├── streamlit_app/                 # Streamlit frontend (separated UI)
│   ├── app.py                     # Main chat UI
│   ├── services/
│   │   └── chat_service.py        # HTTP client → backend API
│   └── state/
│       └── __pycache__
├── scripts/                       # Automation & utilities
│   ├── ingest_documents.py        # Batch document ingestion
│   └── smoke_test.py              # End-to-end validation
├── tests/                         # Test suite (mirrors app structure)
│   ├── unit/                      # Fast, isolated logic tests
│   ├── contract/                  # API schema/interface validation
│   └── integration/               # End-to-end flow tests
├── input/                         # Document storage (local)
│   └── Nexora_Employee_Handbook.docx
├── .chroma/                       # Chroma persistent vector DB
├── requirements.txt               # Dependencies
├── .env.example                   # Environment template
└── ARCHITECTURE.md                # This file
```

---

## Core Principles & Design Patterns

### 1. **Separation of Concerns**

Each layer has a single responsibility:

| Layer | Responsibility | Example |
|-------|-----------------|---------|
| **API** | HTTP contract, request validation, response serialization | `ChatRequest` → `ChatResponse` |
| **Domain** | Pure business logic, independent of framework/tech | `QuerySession`, `DocumentChunk` |
| **Use Cases** | Orchestration, workflow, interaction between domain objects | `QueryOrchestrator` coordinates retrieval + answering |
| **Infrastructure** | Technology-specific adapters (database, file system, LLM APIs) | `ChromaVectorStore`, `LocalDocumentLoader` |

### 2. **Dependency Injection & Inversion of Control**

Infrastructure implementations are **injected** into use cases, not hard-coded:

```python
# ✅ Good: Infrastructure injected
class QueryOrchestrator:
    def __init__(self):
        self.retrieval = RetrievalService()  # Can be swapped
        self.provenance = ProvenanceService()

# ❌ Bad: Direct dependency (not used)
class QueryOrchestrator:
    def __init__(self):
        self.chroma = chromadb.PersistentClient(...)  # Tightly coupled
```

This allows:
- **Testing**: Swap real DB with mock/stub
- **Future changes**: Replace Chroma with Pinecone without touching use case logic

### 3. **Data Flow Through Layers**

### **Request Flow (User Question → Answer)**

```
┌─────────────────────────────────────────────────────────────┐
│ 1. API Layer: Accept & Validate                             │
│    ChatRequest(question, session_id, conversation_history)  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Use Case Layer: Orchestrate                              │
│    QueryOrchestrator.answer(question)                       │
│    ├─ retrieval_service.retrieve(question) → [results]      │
│    ├─ provenance_service.build_citations(results) → []      │
│    └─ return { answer, citations }                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Infrastructure Layer: Execute                            │
│    ChromaVectorStore.query(question, top_k=3)               │
│    ├─ Embed question with SentenceTransformer               │
│    ├─ Query Chroma with cosine similarity                   │
│    └─ Return [{ text, metadata }, ...]                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. API Layer: Serialize & Return                            │
│    ChatResponse(                                            │
│      session_id,                                            │
│      answer,                                                │
│      citations=[Citation(...), ...]                         │
│    )                                                        │
└─────────────────────────────────────────────────────────────┘
```

### **Document Ingestion Flow**

```
┌──────────────────────────────────────────────────────────────┐
│ 1. Scripts Layer: Orchestrate Ingestion                      │
│    scripts/ingest_documents.py                               │
│    ├─ LocalDocumentLoader.list_documents()                   │
│    └─ DocumentProcessing.extract_text_from_document(doc)     │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ 2. Use Case Layer: Process                                   │
│    DocumentProcessing.chunk_text(text)                       │
│    ├─ Split by paragraphs and sentences                      │
│    ├─ Apply metadata (source, page, section)                 │
│    └─ Return [{ id, text, metadata }, ...]                   │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ 3. Infrastructure Layer: Persist                             │
│    ChromaVectorStore.add_documents(documents)                │
│    ├─ Embed each chunk with SentenceTransformer              │
│    ├─ Add to Chroma collection with metadata                 │
│    └─ Persist to .chroma/ directory                          │
└──────────────────────────────────────────────────────────────┘
```

---

## Key Module Details

### **Domain Layer** (`app/domain/`)

**Purpose**: Pure business entities and rules (framework-agnostic)

#### `entities/document_models.py`
```python
@dataclass
class DocumentChunk:
    id: str                      # Unique chunk identifier
    text: str                    # The actual text content
    metadata: Dict[str, Any]     # Source, page, section info

@dataclass
class VectorRecord:
    chunk: DocumentChunk
    embedding: List[float]
    similarity_score: float
```

**Why separate?** Domain models are reusable across:
- FastAPI endpoints (serialization via Pydantic)
- Use cases (orchestration logic)
- Infrastructure (database queries)
- Tests (mock data generation)

---

### **Use Case Layer** (`app/use_cases/`)

**Purpose**: Application business logic—orchestrates domain objects and infrastructure

#### `chat/query_orchestrator.py`
```python
class QueryOrchestrator:
    """Coordinates the flow: Retrieve policy → Build answer → Gather citations"""
    
    def answer(self, question: str):
        # 1. Retrieve relevant policy sections
        results = self.retrieval.retrieve(question, top_k=3)
        
        # 2. Build context-aware answer (heuristic for MVP)
        answer = self._generate_answer(question, results)
        
        # 3. Extract citations
        citations = self.provenance.build_citations(results)
        
        return { "answer": answer, "citations": citations }
```

**Why a separate orchestrator?**
- Easy to test: mock `RetrievalService` and `ProvenanceService`
- Easy to extend: add memory, add LLM provider, add search—just add methods
- Clear intent: "This class answers policy questions"

#### `chat/retrieval_service.py`
```python
class RetrievalService:
    """Abstraction over the vector database"""
    
    def __init__(self, collection_name=COLLECTION_NAME, persist_directory=None):
        self.store = ChromaVectorStore(...)  # Could be Pinecone, Weaviate, etc.
    
    def retrieve(self, query_text: str, top_k: int = 3):
        return self.store.query(query_text, top_k=top_k)
```

**Why abstract?** In the future:
- Replace `ChromaVectorStore` with `PineconeVectorStore`
- RetrievalService doesn't change
- No other code needs to know

---

### **Infrastructure Layer** (`app/infrastructure/`)

**Purpose**: Technology-specific adapters (pluggable implementations)

#### `vector/chroma_client.py`
```python
class ChromaVectorStore:
    """Chroma-specific implementation (could be swapped for Pinecone, Weaviate, etc.)"""
    
    def __init__(self, collection_name, persist_directory):
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_or_create_collection(name=collection_name)
        self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    
    def query(self, query_text: str, top_k: int = 3):
        query_embedding = self.embedding_model.encode([query_text])
        result = self.collection.query(query_embeddings=[query_embedding], n_results=top_k)
        return [{ "text": doc, "metadata": meta } for doc, meta in zip(...)]
```

**Swappable design**: To use Pinecone instead:
1. Create `app/infrastructure/vector/pinecone_client.py`
2. Implement same interface: `query(query_text, top_k) → List[dict]`
3. Update `RetrievalService.__init__()` to use `PineconeVectorStore`
4. **All use cases and API remain unchanged**

#### `document/local_document_loader.py`
```python
class LocalDocumentLoader:
    """Enumerates documents from the local input/ folder"""
    
    SUPPORTED_EXTENSIONS = [".docx", ".txt", ".md", ".pdf"]
    
    def list_documents(self) -> List[DocumentSource]:
        # Find all .docx, .txt, .md files in input/
        return [DocumentSource(path=f, name=f.name) for f in input_dir.glob(...)]
    
    def get_document(self, name: str) -> bytes:
        # Load document binary content
        return (input_dir / name).read_bytes()
```

**Future extensibility**: To load from S3 or SharePoint:
1. Create `SharePointDocumentLoader` with same interface
2. Update ingestion script to swap loader
3. No other code changes needed

---

### **API Layer** (`app/api/`)

**Purpose**: HTTP contract (how external systems talk to the app)

#### `routes/chat.py`
```python
@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    # 1. Validate input (Pydantic)
    # 2. Call orchestrator
    orchestrator = QueryOrchestrator()
    result = orchestrator.answer(request.question)
    
    # 3. Serialize response (FastAPI/Pydantic)
    return ChatResponse(
        session_id=request.session_id,
        answer=result["answer"],
        citations=[Citation(...) for item in result["citations"]]
    )
```

**Why separate routes?** Easy to:
- Add new endpoints (e.g., `/search`, `/session/:id/history`)
- Test API contracts independently
- Version the API (`/api/v1/chat`, `/api/v2/chat`)

#### `schemas/chat.py`
```python
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    session_id: str = Field(default="default-session")
    conversation_history: Optional[List[ChatMessage]] = None

class Citation(BaseModel):
    source: str         # "NEXORA_Employee_Handbook.docx"
    section: str        # "Leave Policy"
    text: str          # "Employees are entitled to 20 days of annual leave..."

class ChatResponse(BaseModel):
    session_id: str
    answer: str
    citations: List[Citation]
```

**Why contracts matter?**
- Clear, testable interface between frontend and backend
- Pydantic auto-validates inputs (no garbage in, no crashes)
- API documentation auto-generated from schemas

---

### **Presentation Layer** (`streamlit_app/`)

**Purpose**: User-facing chat interface (separated from backend logic)

#### `app.py`
```python
# UI Layer: Render chat, accept input
user_input = st.chat_input("Ask about the HR policy...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    
    # Call backend via HTTP
    service = ChatService(base_url="http://localhost:8001")
    response = service.ask(user_input, session_id="streamlit-session")
    
    # Render response
    st.markdown(response["answer"])
    for citation in response["citations"]:
        st.caption(f"Source: {citation['source']} | Section: {citation['section']}")
```

**Why separate frontend?**
- UI can be swapped (replace Streamlit with React, Vue, etc.)
- Backend remains unchanged
- Can deploy frontend and backend independently

#### `services/chat_service.py`
```python
class ChatService:
    """HTTP client to the backend API"""
    
    def ask(self, question: str, session_id: str, history=None):
        payload = {
            "question": question,
            "session_id": session_id,
            "conversation_history": history or []
        }
        response = requests.post(f"{self.base_url}/api/chat", json=payload)
        return response.json()
```

---

## Configuration & Environment Management

### `app/core/settings.py`

```python
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent.parent
    DOCUMENTS_DIR: str = str(BASE_DIR / "input")
    
    # Vector DB
    COLLECTION_NAME: str = "hr_policy_docs"
    CHROMA_PERSIST_DIR: str = str(BASE_DIR / ".chroma")
    
    # Embedding
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    
    # LLM Providers (for future use)
    OPENROUTER_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

settings = Settings()
```

**Why centralized?**
- Single source of truth for configuration
- Environment variables override defaults
- Easy to add new settings without scattering them across codebase
- Testable: can override settings in test fixtures

---

## Dependency Graph

```
┌─────────────────────────────────────────────────────────────┐
│ External Systems                                            │
├─────────────────────────────────────────────────────────────┤
│ • Streamlit Browser UI                                      │
│ • Local Filesystem (input/)                                 │
│ • Chroma DB (.chroma/)                                      │
│ • HuggingFace Hub (SentenceTransformer embeddings)          │
└─────────────────────────────────────────────────────────────┘
                            ↑
                   (HTTP calls, file I/O)
                            ↑
┌─────────────────────────────────────────────────────────────┐
│ API Layer (app/api/)                                        │
├─────────────────────────────────────────────────────────────┤
│ • Routes: /api/chat, /health                                │
│ • Schemas: ChatRequest, ChatResponse, Citation              │
│ • ↓ Depends on Use Cases                                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Use Case Layer (app/use_cases/)                             │
├─────────────────────────────────────────────────────────────┤
│ • QueryOrchestrator (orchestrates retrieval & answering)   │
│ • RetrievalService (queries the vector store)               │
│ • ProvenanceService (builds citations)                      │
│ • DocumentProcessing (chunks & embeds documents)            │
│ • SessionMemory (conversation state)                        │
│ • ↓ Depends on Domain & Infrastructure                      │
└─────────────────────────────────────────────────────────────┘
                   ↙                    ↘
┌──────────────────────┐    ┌──────────────────────┐
│ Domain Layer         │    │ Infrastructure Layer │
├──────────────────────┤    ├──────────────────────┤
│ (app/domain/)        │    │ (app/infrastructure/)│
│                      │    │                      │
│ Entities:            │    │ Adapters:            │
│ • DocumentChunk      │    │ • ChromaVectorStore  │
│ • QuerySession       │    │ • LocalDocumentLoad. │
│ • Message            │    │ • (Future: Pinecone) │
│                      │    │ • (Future: SharePt.) │
│ Services:            │    │ • (Future: OpenAI)   │
│ • SessionMemoryServ. │    │                      │
└──────────────────────┘    └──────────────────────┘
```

---

## Testing Strategy

Each layer is independently testable:

### **Unit Tests** (`tests/unit/`)
Test isolated business logic without external dependencies:
```python
def test_document_extraction():
    """Test document parsing (domain + use case logic)"""
    text = extract_text_from_document("Nexora_Employee_Handbook.docx")
    assert "NEXORA" in text
    assert len(text) > 100

def test_session_memory_bounded():
    """Test bounded conversation window (domain logic)"""
    memory = SessionMemoryService(max_messages=6)
    history = [msg1, msg2, msg3, msg4, msg5, msg6, msg7]
    recent = memory.get_recent_messages(history)
    assert len(recent) == 6  # Only last 6
```

### **Contract Tests** (`tests/contract/`)
Test API shape/schema (API layer):
```python
def test_chat_endpoint_returns_chat_response():
    """Test that /api/chat returns valid ChatResponse schema"""
    payload = { "question": "...", "session_id": "..." }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert "session_id" in body
    assert "answer" in body
    assert "citations" in body
    assert len(body["citations"]) >= 1
```

### **Integration Tests** (`tests/integration/`)
Test end-to-end workflows:
```python
def test_chat_api_end_to_end():
    """Test full flow: question → retrieval → answer + citations"""
    response = client.post("/api/chat", json={
        "question": "What is the leave policy?",
        "session_id": "test-session",
        "conversation_history": []
    })
    
    assert response.status_code == 200
    body = response.json()
    assert "leave" in body["answer"].lower() or len(body["citations"]) > 0
```

---

## Future Extensibility Points

### **1. Add Follow-Up Questions (US2)**
```python
# Modify chat flow to include memory
class QueryOrchestrator:
    def answer_with_history(self, question: str, session_id: str, history: List[Message]):
        # Load recent conversation context
        memory = SessionMemory()
        memory.add_messages(history)
        
        # Augment question with prior context
        augmented_q = memory.contextualize(question)
        
        # Retrieve & answer as before
        return self.answer(augmented_q)
```

### **2. Add Real LLM Answers (Instead of Heuristics)**
```python
class QueryOrchestrator:
    def answer(self, question: str):
        results = self.retrieval.retrieve(question)
        context = "\n".join([r["text"] for r in results])
        
        # Call LLM provider
        llm_provider = OpenRouterProvider(api_key=settings.OPENROUTER_API_KEY)
        answer = llm_provider.generate(
            prompt=f"Question: {question}\n\nContext: {context}",
            model="meta-llama/llama-2-70b"
        )
        
        return { "answer": answer, "citations": ... }
```

### **3. Add Search UI (US3)**
```python
# New route
@router.get("/api/search", response_model=SearchResults)
async def search(query: str, top_k: int = 5):
    orchestrator = QueryOrchestrator()
    results = orchestrator.retrieval.retrieve(query, top_k=top_k)
    return SearchResults(results=[...])

# New Streamlit page: streamlit_app/pages/search_policy.py
```

### **4. Swap Vector Database**
```python
# Create new adapter
class PineconeVectorStore:
    def __init__(self, index_name, namespace, api_key):
        self.client = pinecone.Index(index_name)
    
    def query(self, query_text: str, top_k: int = 3):
        # Pinecone-specific query logic
        return self.client.query(embeddings=[...], top_k=top_k)

# Update RetrievalService
class RetrievalService:
    def __init__(self, use_pinecone=False):
        if use_pinecone:
            self.store = PineconeVectorStore(...)
        else:
            self.store = ChromaVectorStore(...)
```

---

## Key Architectural Decisions & Trade-offs

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| **Modular Monolith** | Single deployment, independent modules, easy testing | Not microservices (less scalability, but simpler for MVP) |
| **Local Vector DB** | No external dependencies, fast POC | Limited to single-machine scaling (OK for MVP) |
| **Chroma** | Python-native, embedded option, fast to set up | Less mature than enterprise DBs (fine for MVP) |
| **Streamlit UI** | Rapid prototyping, built-in state management | Not suitable for complex multi-page apps (fine for MVP) |
| **Heuristic Answers** | Fast MVP without LLM provider setup | Less natural language (LLM planned for future) |
| **Local Document Storage** | Simple, no S3/SharePoint setup needed | Manual document upload (fine for MVP) |
| **Sentence-Transformers** | Small, fast embeddings, runs locally | Less nuanced than enterprise embeddings (fine for MVP) |

---

## Deployment & Scaling Path

### **MVP (Current)**
```
Single Machine
├─ FastAPI Backend (8001)
├─ Streamlit UI (8501)
├─ Chroma DB (.chroma/)
└─ Documents (input/)
```

### **Future: Scale Horizontally**
```
Cloud Deployment
├─ FastAPI → Cloud Run / ECS
│   └─ Scales horizontally
├─ Streamlit → Streamlit Cloud / Docker
├─ Chroma → Pinecone / Weaviate Cloud
│   └─ Managed vector DB
├─ Documents → S3 / GCS
│   └─ Centralized storage
└─ LLM APIs → OpenRouter / Azure OpenAI
    └─ Managed inference
```

### **Future: Microservices (If Needed)**
```
├─ Chat Service (current app/api/routes/chat.py)
├─ Ingestion Service (current scripts/ingest_documents.py)
├─ Retrieval Service (current app/use_cases/chat/retrieval_service.py)
└─ Memory Service (current app/use_cases/chat/session_memory.py)
```

Each could become its own microservice with shared message queue.

---

## Summary

The **modular monolith architecture** provides:

✅ **Clear separation of concerns**: API → Use Cases → Domain + Infrastructure  
✅ **Testability**: Each layer independently mockable  
✅ **Extensibility**: New features/providers added without touching existing code  
✅ **Simplicity**: Single deployable app (easier than microservices for MVP)  
✅ **Future-proof**: Can evolve to microservices or scale infrastructure as needed  

This design ensures KnowLayer can start simple and scale intelligently as requirements grow.
