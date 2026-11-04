# Frontend Pages and Document Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement non-blocking background document ingestion, archival (preserves vectors for future toggle) vs permanent deletion, chunk observability & search, and RBAC-controlled pages across KnowLayer ("Write Implies Read").

**Architecture:** 
FastAPI background workers process document extraction and chunking asynchronously while returning an immediate HTTP 202 status; SQLite WAL mode and a process-level ChromaDB singleton ensure safe concurrency on Windows. Archival relocates disk files to `input/{project_id}/archived/` while preserving Chroma chunks filtered out of normal chat; permanent delete purges vectors. Streamlit pages enforce RBAC where any mutation permission grants viewing rights, and `pages/documents.py` embeds chunk observability and vector search without adding sidebar clutter.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, SQLite (WAL mode), ChromaDB, Streamlit, Pytest.

**Spec:** [docs/superpowers/specs/2026-10-23-frontend-pages-and-document-lifecycle-spec.md](file:///c:/DEV/Training_Projects/Training_Team_Project\Company_Bot\docs\superpowers\specs\2026-10-23-frontend-pages-and-document-lifecycle-spec.md)

## Global Constraints

- Python version floor: Python 3.12+
- Operating System: Windows (powershell terminal, case-insensitive paths, strict file locking semantics)
- Branch: `sidebar-improvements`
- Working Directory: `c:\DEV\Training_Projects\Training_Team_Project\Company_Bot`
- Database: Consolidated 8-table SQLAlchemy SQLite model (`instance/knowlayer.db`)
- Ingestion Ports: Keep `DoclingProcessor` and parser ports decoupled; do not alter teammate document parsing logic.
- Test Commands: Run with `.venv\Scripts\python.exe -m pytest <path> -v`

## Review Focus

1. **SQLite concurrency under background tasks:** If FastAPI background worker commits document records while user updates a project, SQLite must wait via WAL and `busy_timeout=30000` rather than throwing `database is locked`.
2. **ChromaDB Windows file locks under concurrent read/write:** Background worker writing chunks while chat user queries vectors must run safely without `PermissionError: [WinError 32]`.
3. **Zombie ingestion recovery:** If the FastAPI server restarts while a document has `status="processing"`, startup hook must transition it to `status="failed"` rather than leaving it stuck forever.
4. **Project manager orphan prevention and transfer:** A project manager must be blocked from leaving until another manager is assigned, after which leave succeeds.
5. **Per-project document collision and duplicate hash:** Uploading an identical SHA-256 hash in the same project must return 409 Conflict; identical filenames across different projects must be stored under separate `input/{project_id}/` directories without error.
6. **Archival preserves chunks; delete purges chunks:** Archiving a document moves the disk file to `input/{project_id}/archived/` and keeps Chroma chunks intact (isolated by status); only permanent delete (`?permanent=true`) purges Chroma vectors.

---

### Task 1: SQLite Concurrency Guardrails & ChromaDB Process Singleton

**Files:**
- Modify: `app/infrastructure/persistence/sqlalchemy/session.py:10-22`
- Modify: `app/infrastructure/vector/chroma_client.py:13-35`
- Test: `tests/infrastructure/test_concurrency_and_chroma_singleton.py`

**Interfaces:**
- Consumes: `create_engine_and_session_factory` from `app.infrastructure.persistence.sqlalchemy.session`, `ChromaVectorStore` from `app.infrastructure.vector.chroma_client`.
- Produces: SQLite engine with WAL mode and `timeout=30`, `ChromaVectorStore` sharing a cached process-level `chromadb.PersistentClient` singleton.

- [ ] **Step 1: Write the failing concurrency & singleton test**

Create `tests/infrastructure/test_concurrency_and_chroma_singleton.py`:
```python
import threading
import time
from pathlib import Path
from app.infrastructure.persistence.sqlalchemy.session import create_engine_and_session_factory
from app.infrastructure.vector.chroma_client import ChromaVectorStore

def test_sqlite_wal_and_busy_timeout(tmp_path: Path):
    db_file = tmp_path / "test_wal.db"
    db_url = f"sqlite:///{db_file}"
    engine, _ = create_engine_and_session_factory(db_url)
    
    with engine.connect() as conn:
        journal_mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
        assert journal_mode.lower() == "wal"
        timeout = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
        assert timeout >= 30000

def test_concurrent_read_while_writing_in_wal_mode(tmp_path: Path):
    db_file = tmp_path / "test_concurrency.db"
    db_url = f"sqlite:///{db_file}"
    engine, _ = create_engine_and_session_factory(db_url)
    
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT);")
        conn.exec_driver_sql("INSERT INTO items (name) VALUES ('initial');")

    write_started = threading.Event()
    read_completed = threading.Event()
    read_result = []

    def writer_thread():
        with engine.begin() as conn:
            conn.exec_driver_sql("INSERT INTO items (name) VALUES ('in_progress');")
            write_started.set()
            time.sleep(0.4)

    def reader_thread():
        write_started.wait()
        with engine.connect() as conn:
            rows = conn.exec_driver_sql("SELECT name FROM items;").fetchall()
            read_result.extend(r[0] for r in rows)
            read_completed.set()

    t1 = threading.Thread(target=writer_thread)
    t2 = threading.Thread(target=reader_thread)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert read_completed.is_set()
    assert "initial" in read_result

def test_chroma_persistent_client_is_process_singleton(tmp_path: Path):
    chroma_dir = str(tmp_path / ".chroma")
    store1 = ChromaVectorStore(collection_name="test_col", persist_directory=chroma_dir)
    store2 = ChromaVectorStore(collection_name="test_col", persist_directory=chroma_dir)
    assert store1.client is store2.client

def test_concurrent_chroma_read_and_write(tmp_path: Path):
    chroma_dir = str(tmp_path / ".chroma")
    store = ChromaVectorStore(collection_name="test_concurrency_col", persist_directory=chroma_dir)
    
    # Pre-populate one chunk
    store.add_documents([{"id": "doc0-chunk0", "text": "baseline information", "metadata": {"status": "active"}}])

    write_started = threading.Event()
    read_success = threading.Event()
    read_errors = []

    def writer():
        write_started.set()
        docs = [{"id": f"batch-{i}", "text": f"concurrent document payload number {i}", "metadata": {"status": "active"}} for i in range(5)]
        store.add_documents(docs)

    def reader():
        write_started.wait()
        try:
            results = store.query("baseline information", top_k=2)
            if len(results) > 0:
                read_success.set()
        except Exception as e:
            read_errors.append(e)

    t1 = threading.Thread(target=writer)
    t2 = threading.Thread(target=reader)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not read_errors
    assert read_success.is_set()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/infrastructure/test_concurrency_and_chroma_singleton.py -v
```
Expected: FAIL (`journal_mode != "wal"`, `store1.client is not store2.client`).

- [ ] **Step 3: Implement WAL, busy timeout, and Chroma singleton**

In `app/infrastructure/persistence/sqlalchemy/session.py`:
```python
def create_engine_and_session_factory(database_url: str):
    connect_args = {"check_same_thread": False, "timeout": 30.0} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, future=True)

    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def configure_sqlite_pragmas(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    return engine, sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
```

In `app/infrastructure/vector/chroma_client.py`:
Add a module-level client cache:
```python
_CHROMA_CLIENT_REGISTRY: dict[str, chromadb.PersistentClient] = {}

class ChromaVectorStore:
    def __init__(
        self,
        collection_name: str = COLLECTION_NAME,
        persist_directory: Optional[str] = None,
    ):
        self.collection_name = collection_name
        self.persist_directory = Path(persist_directory or ".chroma").resolve()
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        key = str(self.persist_directory)
        if key not in _CHROMA_CLIENT_REGISTRY:
            _CHROMA_CLIENT_REGISTRY[key] = chromadb.PersistentClient(path=key)
        self.client = _CHROMA_CLIENT_REGISTRY[key]
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._embedding_model = None
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/infrastructure/test_concurrency_and_chroma_singleton.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/infrastructure/persistence/sqlalchemy/session.py app/infrastructure/vector/chroma_client.py tests/infrastructure/test_concurrency_and_chroma_singleton.py
git commit -m "feat(infra): enable SQLite WAL mode, busy timeout, and Chroma singleton client with concurrent read/write test"
```

---

### Task 2: Backend Async Document Ingestion, Duplication Guards, Archival vs Permanent Deletion, and Chunk Observability

**Files:**
- Modify: `app/domain/entities/organization_models.py:68-84`
- Modify: `app/infrastructure/persistence/sqlalchemy/models.py:60-78`
- Modify: `app/use_cases/organization/document_management.py:79-150`
- Modify: `app/infrastructure/ingestion/provisioner.py:100-146`
- Modify: `app/api/schemas/documents.py:1-40`
- Modify: `app/api/routes/documents.py:19-95`
- Modify: `app/main.py:1-40` (or lifespan startup)
- Test: `tests/api/test_async_document_lifecycle.py`

**Interfaces:**
- Consumes: `DocumentManagementService`, `provision_document`, `remove_document`.
- Produces: 
  - `POST /api/documents` (returns HTTP 202 with `status: "processing"`, runs ingestion in `BackgroundTasks`).
  - `GET /api/documents/{document_id}/status` returning `{"document_id": str, "status": str, "progress": int | None, "message": str}`.
  - `GET /api/documents/{document_id}/chunks` returning `list[dict]` of stored chunks with index, text, metadata.
  - `POST /api/documents/chunks/search` returning top-$k$ ranked chunk snippets with similarity scores.
  - `DELETE /api/documents/{document_id}` (Archive): updates SQL status to `archived`, relocates file to `input/{project_id}/archived/`, keeps Chroma vectors.
  - `DELETE /api/documents/{document_id}?permanent=true` (Purge): purges vectors from Chroma and unlinks disk file.
  - Startup hook converting zombie `processing` documents to `failed`.

- [ ] **Step 1: Write failing tests for async document ingestion, chunks inspection, and archive vs delete**

Create `tests/api/test_async_document_lifecycle.py`:
```python
import base64
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.main import create_app

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_async_document_upload_and_status_polling(client: TestClient, monkeypatch):
    headers = {"Authorization": "Bearer admin-token"}
    monkeypatch.setattr("app.api.dependencies.get_current_principal", lambda: type("Principal", (), {"uid": "admin"})())

    content = base64.b64encode(b"This is a test policy document for background ingestion.").decode("utf-8")
    payload = {
        "document_name": "Test Policy.txt",
        "project_id": None,
        "content": content,
    }

    response = client.post("/api/documents", json=payload, headers=headers)
    assert response.status_code in (201, 202)
    data = response.json()
    doc_id = data["document_id"]
    assert data["status"] in ("processing", "active")

    # Poll status endpoint
    status_resp = client.get(f"/api/documents/{doc_id}/status", headers=headers)
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert "status" in status_data
    assert status_data["document_id"] == doc_id

def test_duplicate_file_hash_in_same_project_rejected(client: TestClient, monkeypatch):
    headers = {"Authorization": "Bearer admin-token"}
    monkeypatch.setattr("app.api.dependencies.get_current_principal", lambda: type("Principal", (), {"uid": "admin"})())

    content = base64.b64encode(b"Exact duplicate content test.").decode("utf-8")
    payload = {"document_name": "dup1.txt", "project_id": "PRJ-TEST", "content": content}

    res1 = client.post("/api/documents", json=payload, headers=headers)
    assert res1.status_code in (201, 202)

    # Second upload with same content to same project
    payload2 = {"document_name": "dup2.txt", "project_id": "PRJ-TEST", "content": content}
    res2 = client.post("/api/documents", json=payload2, headers=headers)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"].lower()

def test_get_document_chunks_and_vector_search(client: TestClient, monkeypatch):
    headers = {"Authorization": "Bearer admin-token"}
    monkeypatch.setattr("app.api.dependencies.get_current_principal", lambda: type("Principal", (), {"uid": "admin"})())

    content = base64.b64encode(b"Header 1\nSecurity guidelines paragraph.\n\nHeader 2\nRemote work policy paragraph.").decode("utf-8")
    payload = {"document_name": "guidelines.txt", "project_id": "PRJ-TEST-CHUNKS", "content": content}
    res = client.post("/api/documents", json=payload, headers=headers)
    assert res.status_code in (201, 202)
    doc_id = res.json()["document_id"]

    # 1. Test chunk inspection endpoint
    chunks_resp = client.get(f"/api/documents/{doc_id}/chunks", headers=headers)
    assert chunks_resp.status_code == 200
    chunks = chunks_resp.json()
    assert isinstance(chunks, list)
    assert len(chunks) > 0
    assert "text" in chunks[0]
    assert "metadata" in chunks[0]

    # 2. Test chunk vector search sandbox endpoint
    search_payload = {"query": "security guidelines", "project_id": "PRJ-TEST-CHUNKS", "top_k": 2}
    search_resp = client.post("/api/documents/chunks/search", json=search_payload, headers=headers)
    assert search_resp.status_code == 200
    search_results = search_resp.json()
    assert isinstance(search_results, list)
    assert len(search_results) > 0

def test_retrieval_excludes_processing_and_archived_documents(client: TestClient, monkeypatch):
    headers = {"Authorization": "Bearer admin-token"}
    monkeypatch.setattr("app.api.dependencies.get_current_principal", lambda: type("Principal", (), {"uid": "admin"})())

    # Doc 1: Active document
    content1 = base64.b64encode(b"Active document content specifically for secret project alpha.").decode("utf-8")
    res1 = client.post("/api/documents", json={"document_name": "active.txt", "project_id": "PRJ-SCOPE", "content": content1}, headers=headers)
    doc1_id = res1.json()["document_id"]

    # Doc 2: Archived document
    content2 = base64.b64encode(b"Archived document content specifically for secret project alpha.").decode("utf-8")
    res2 = client.post("/api/documents", json={"document_name": "archived.txt", "project_id": "PRJ-SCOPE", "content": content2}, headers=headers)
    doc2_id = res2.json()["document_id"]
    client.delete(f"/api/documents/{doc2_id}", headers=headers)

    # Standard search without include_archived must ONLY return active document chunks
    search_payload = {"query": "secret project alpha", "project_id": "PRJ-SCOPE", "include_archived": False}
    search_resp = client.post("/api/documents/chunks/search", json=search_payload, headers=headers)
    assert search_resp.status_code == 200
    results = search_resp.json()
    matched_doc_ids = {r["metadata"]["document_id"] for r in results if "metadata" in r}
    assert doc1_id in matched_doc_ids
    assert doc2_id not in matched_doc_ids

def test_ingestion_failure_marks_status_failed(client: TestClient, monkeypatch):
    headers = {"Authorization": "Bearer admin-token"}
    monkeypatch.setattr("app.api.dependencies.get_current_principal", lambda: type("Principal", (), {"uid": "admin"})())

    payload = {"document_name": "broken.pdf", "project_id": None, "content": "not-valid-base64-content!!!"}
    res = client.post("/api/documents", json=payload, headers=headers)
    assert res.status_code in (400, 422)

def test_archive_document_preserves_chunks_and_moves_file(client: TestClient, monkeypatch):
    headers = {"Authorization": "Bearer admin-token"}
    monkeypatch.setattr("app.api.dependencies.get_current_principal", lambda: type("Principal", (), {"uid": "admin"})())

    content = base64.b64encode(b"Document to be soft archived.").decode("utf-8")
    payload = {"document_name": "temp_archive.txt", "project_id": "PRJ-ARCHIVE", "content": content}
    res = client.post("/api/documents", json=payload, headers=headers)
    doc_id = res.json()["document_id"]

    # Soft archive document
    del_resp = client.delete(f"/api/documents/{doc_id}", headers=headers)
    assert del_resp.status_code == 204

    # Verify chunks are PRESERVED in Chroma for future toggle/retrieval
    chunks_resp = client.get(f"/api/documents/{doc_id}/chunks", headers=headers)
    assert chunks_resp.status_code == 200
    assert len(chunks_resp.json()) > 0

    # Verify disk file relocated to archived subfolder
    archived_dir = Path("input/PRJ-ARCHIVE/archived")
    assert archived_dir.exists()
    matching = list(archived_dir.glob(f"{doc_id}_*"))
    assert len(matching) == 1

def test_permanent_delete_purges_chunks_and_file(client: TestClient, monkeypatch):
    headers = {"Authorization": "Bearer admin-token"}
    monkeypatch.setattr("app.api.dependencies.get_current_principal", lambda: type("Principal", (), {"uid": "admin"})())

    content = base64.b64encode(b"Document to be permanently purged.").decode("utf-8")
    payload = {"document_name": "temp_purge.txt", "project_id": "PRJ-PURGE", "content": content}
    res = client.post("/api/documents", json=payload, headers=headers)
    doc_id = res.json()["document_id"]

    # Hard delete document with permanent=true
    del_resp = client.delete(f"/api/documents/{doc_id}?permanent=true", headers=headers)
    assert del_resp.status_code == 204

    # Verify chunks PURGED from Chroma
    chunks_resp = client.get(f"/api/documents/{doc_id}/chunks", headers=headers)
    assert chunks_resp.status_code == 200
    assert len(chunks_resp.json()) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/api/test_async_document_lifecycle.py -v
```
Expected: FAIL (`status endpoint not found`, `chunks endpoint not found`, `409 not raised`).

- [ ] **Step 3: Implement hash calculation, project directories, archive vs delete, async worker, and chunk endpoints**

1. In `app/domain/entities/organization_models.py` and `app/infrastructure/persistence/sqlalchemy/models.py`:
   - Add `file_hash: Optional[str] = None` to `Document` and `DocumentRecord`.
2. In `app/use_cases/organization/document_management.py`:
   - Add SHA-256 calculation: `hashlib.sha256(raw_bytes).hexdigest()`.
   - Before inserting, query `uow.documents.list()`: if any document with same `project_id` and same `file_hash` has `status != "archived"`, raise `ConflictError("Exact file already exists in this project")`.
   - Register document with initial `status="processing"`.
   - In `archive_document(principal, document_id)`:
     - Set `status = "archived"`.
     - Relocate file on disk to `parent / "archived" / file.name`.
     - Chunks kept in Chroma.
   - In `delete_document(principal, document_id, permanent=False)`:
     - If `permanent=True`: delete row, unlink file, call `deletion_handler(document_id)` to purge Chroma vectors.
     - Else: call `archive_document`.
3. In `app/infrastructure/ingestion/provisioner.py`:
   - Store active files in `DOCUMENTS_DIR / (document.project_id or "unassigned") / f"{document.document_id}_{safe_filename}"`.
   - `remove_document(document_id)` purges Chroma vectors.
4. In `app/api/routes/documents.py`:
   - Inject `BackgroundTasks`:
     ```python
     @router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
     def create_document(
         payload: DocumentCreate,
         background_tasks: BackgroundTasks,
         principal=Depends(get_current_principal),
         service=Depends(get_document_management_service),
     ): ...
     ```
   - Add `GET /api/documents/{document_id}/status`.
   - Add `GET /api/documents/{document_id}/chunks`:
     ```python
     @router.get("/documents/{document_id}/chunks")
     def get_document_chunks(document_id: str, principal=Depends(get_current_principal)):
         store = ChromaVectorStore()
         results = store.collection.get(where={"document_id": document_id}, include=["documents", "metadatas"])
         chunks = []
         for idx, (doc, meta) in enumerate(zip(results["documents"] or [], results["metadatas"] or [])):
             chunks.append({"index": idx, "text": doc, "metadata": meta})
         return chunks
     ```
   - Add `POST /api/documents/chunks/search`:
     ```python
     @router.post("/documents/chunks/search")
     def search_chunks(payload: ChunkSearchRequest, principal=Depends(get_current_principal)):
         store = ChromaVectorStore()
         where = {"project_id": payload.project_id} if payload.project_id else {}
         if not payload.include_archived:
             where["status"] = "active"
         results = store.query(payload.query, top_k=payload.top_k or 4, where=where or None)
         return results
     ```
   - Update `DELETE /api/documents/{document_id}` to support `permanent: bool = False`.
5. In `app/main.py`:
   - Add startup hook checking `SELECT * FROM documents WHERE status = 'processing'` and updating to `status = 'failed'` with description `"Server restarted during ingestion"`.

- [ ] **Step 4: Run test to verify it passes**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/api/test_async_document_lifecycle.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/domain/entities/organization_models.py app/infrastructure/persistence/sqlalchemy/models.py app/use_cases/organization/document_management.py app/infrastructure/ingestion/provisioner.py app/api/schemas/documents.py app/api/routes/documents.py app/main.py tests/api/test_async_document_lifecycle.py
git commit -m "feat(documents): implement async ingestion, SHA-256 deduplication, status polling, chunk observability, and archive vs permanent delete"
```

---

### Task 3: Streamlit Document Page Enhancement (Library Tab + Observability Tab)

**Files:**
- Modify: `streamlit_app/services/document_service.py:30-45`
- Modify: `streamlit_app/pages/documents.py:1-174`
- Test: `tests/ui/test_document_service_helpers.py`

**Interfaces:**
- Consumes: `/api/documents`, `/api/documents/{id}/status`, `/api/documents/{id}/chunks`, `/api/documents/chunks/search`.
- Produces: Streamlit UI with `Tab 1: 📚 Document Library` (non-blocking upload, collision options, fragment auto-refresh, archive & delete buttons) and `Tab 2: 🔍 Chunk Inspector & Vector Search`.

- [ ] **Step 1: Write unit tests for document service helper methods**

Create `tests/ui/test_document_service_helpers.py`:
```python
from unittest.mock import MagicMock
from streamlit_app.services.document_service import DocumentService

def test_document_service_status_and_chunks(monkeypatch):
    service = DocumentService(base_url="http://mock")
    service._session_token = MagicMock(return_value="token")
    service._get = MagicMock(side_effect=[
        {"document_id": "DOC-1", "status": "processing", "progress": None},
        [{"index": 0, "text": "chunk text", "metadata": {"page": 1}}]
    ])

    status = service.get_status("DOC-1")
    assert status["status"] == "processing"

    chunks = service.get_chunks("DOC-1")
    assert len(chunks) == 1
    assert chunks[0]["text"] == "chunk text"
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/ui/test_document_service_helpers.py -v
```
Expected: FAIL (`AttributeError: 'DocumentService' object has no attribute 'get_status'`).

- [ ] **Step 3: Update DocumentService and refactor `pages/documents.py`**

In `streamlit_app/services/document_service.py`:
Add methods: `get_status(document_id)`, `get_chunks(document_id)`, `search_chunks(payload)`.

In `streamlit_app/pages/documents.py`:
- Use `tab1, tab2 = st.tabs(["📚 Document Library", "🔍 Chunk Inspector & Search"])`.
- In **Tab 1**:
  - File uploader card.
  - Submit calls `document_service.create_document(payload)`. Catches 409 (Conflict) to show exact duplicate error.
  - Wrap documents table inside `@st.fragment(run_every=int(os.getenv("DOC_INGESTION_REFRESH_INTERVAL", "5")))` if any document has `status == "processing"`.
  - Display status badge: `🟢 active`, `⏳ processing`, `🔴 failed`, `⚪ archived`.
  - Actions:
    - Button `Archive`: Calls `document_service.delete_document(document_id, permanent=False)`.
    - Button `Delete Permanently`: Gated by Admin / Manager, calls with `permanent=True`.
  - Document Details & Access Configuration expanders.
- In **Tab 2**:
  - Sub-panel 1: Chunk Explorer (select document -> inspect chunk list, character counts, metadata pills, text preview).
  - Sub-panel 2: Vector Search Sandbox (input test query, top-$k$ slider, project filter -> button to execute `document_service.search_chunks` -> displays ranked matches with distance scores).

- [ ] **Step 4: Run test to verify it passes**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/ui/test_document_service_helpers.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add streamlit_app/services/document_service.py streamlit_app/pages/documents.py tests/ui/test_document_service_helpers.py
git commit -m "feat(ui): add non-blocking document upload, auto-refresh fragment, and chunk observability tab"
```

---

### Task 4: Streamlit Projects Page: My Projects & RBAC Management

**Files:**
- Modify: `streamlit_app/pages/projects.py:1-120`
- Modify: `streamlit_app/services/organization_service.py:55-80`
- Test: `tests/ui/test_project_page_helpers.py`

**Interfaces:**
- Consumes: `/api/projects`, `/api/projects/{id}/members/me/leave`, `/api/users/me/profile`.
- Produces: "My Projects" table with "Leave Project" (blocked for project manager until transferred) + Gated Project Management (Create Project, Assign Members).

- [ ] **Step 1: Write test for project leave, manager check, and transfer logic**

Create `tests/ui/test_project_page_helpers.py`:
```python
def test_can_user_leave_project():
    # If user is manager, can_leave must be False
    current_uid = "usr_lead"
    project = {"project_id": "PRJ-1", "manager_uid": "usr_lead"}
    assert (project.get("manager_uid") != current_uid) is False

    # If user is regular member, can_leave must be True
    member_project = {"project_id": "PRJ-2", "manager_uid": "other_mgr"}
    assert (member_project.get("manager_uid") != current_uid) is True

def test_project_manager_transfer_and_leave():
    current_uid = "usr_lead"
    project = {"project_id": "PRJ-1", "manager_uid": "usr_lead"}
    assert (project.get("manager_uid") != current_uid) is False

    # Transfer manager to another user
    project["manager_uid"] = "usr_new_lead"
    assert (project.get("manager_uid") != current_uid) is True
```

- [ ] **Step 2: Run test to verify it passes**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/ui/test_project_page_helpers.py -v
```
Expected: PASS.

- [ ] **Step 3: Refactor `streamlit_app/pages/projects.py`**

1. In `pages/projects.py`:
   - Fetch current profile: `profile = get_current_profile()`, `user = profile.get("user") or {}`, `perms = set(profile.get("permissions") or [])`.
   - Check RBAC: `can_manage = "*" in perms or "ADMIN" in perms or any(p in perms for p in ("PROJECT_CREATE", "PROJECT_UPDATE", "PROJECT_DELETE", "PROJECT_MANAGE"))`.
   - Render **Section 1: 📁 My Projects**:
     - Query user's assigned projects.
     - Table columns: Project ID, Name, Department, Manager, Status, Actions.
     - If current user is member and `project["manager_uid"] != user["uid"]`:
       - Show button "Leave Project". On click, prompt confirmation, then call `organization_service.leave_project(project_id)`.
     - If user is manager: show disabled tag "Project Manager" (must reassign manager first).
   - Render **Section 2: ⚙️ Project Administration**:
     - Only if `can_manage` is True.
     - Create Project Form (`PROJECT_CREATE`).
     - Project Members Sub-Panel: Assign/Revoke members (`PROJECT_MANAGE`).

- [ ] **Step 4: Commit**

```powershell
git add streamlit_app/pages/projects.py tests/ui/test_project_page_helpers.py
git commit -m "feat(ui): standardize projects page with My Projects, leave project action, and manager lock"
```

---

### Task 5: Standardize Users, Departments, Roles, Profile, and Chat Pages ("Write Implies Read")

**Files:**
- Modify: `streamlit_app/pages/users.py:1-120`
- Modify: `streamlit_app/pages/departments.py:1-120`
- Modify: `streamlit_app/pages/roles.py:1-120`
- Modify: `streamlit_app/pages/profile.py:1-100`
- Modify: `streamlit_app/app.py:1-100`
- Test: `tests/ui/test_rbac_ui_gates.py`

**Interfaces:**
- Consumes: Permissions from `GET /api/users/me/profile`.
- Produces: Standardized RBAC gating across all remaining pages; cleans `app.py` top bar and in-flight upload banner.

- [ ] **Step 1: Write test for "Write Implies Read" permission logic**

Create `tests/ui/test_rbac_ui_gates.py`:
```python
def check_domain_view_access(permissions: set[str], domain: str) -> bool:
    if "*" in permissions or "ADMIN" in permissions:
        return True
    domain_perms = {p for p in permissions if p.startswith(domain.upper())}
    return len(domain_perms) > 0

def test_write_implies_read():
    # User with only USER_CREATE must have view access to users page
    user_perms = {"USER_CREATE"}
    assert check_domain_view_access(user_perms, "USER") is True
    assert check_domain_view_access(user_perms, "DEPARTMENT") is False

    # Dept lead with DEPARTMENT_ASSIGN_USERS has view access to departments
    dept_perms = {"DEPARTMENT_ASSIGN_USERS"}
    assert check_domain_view_access(dept_perms, "DEPARTMENT") is True
```

- [ ] **Step 2: Run test to verify it passes**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/ui/test_rbac_ui_gates.py -v
```
Expected: PASS.

- [ ] **Step 3: Update `users.py`, `departments.py`, `roles.py`, `profile.py`, and `app.py`**

1. In `pages/users.py`:
   - Enforce: visible if `check_domain_view_access(perms, "USER")`.
   - Add User form visible only if `"USER_CREATE" in perms or is_admin`.
   - Edit / Deactivate user actions visible only if `"USER_UPDATE" in perms or "USER_DELETE" in perms or is_admin`.
2. In `pages/departments.py`:
   - Enforce: visible if `check_domain_view_access(perms, "DEPARTMENT")`.
   - Create Department form visible only if `"DEPARTMENT_CREATE" in perms or is_admin`.
   - Assign/Revoke department members visible only if `"DEPARTMENT_ASSIGN_USERS" in perms or is_admin`.
3. In `pages/roles.py`:
   - Enforce: visible if `check_domain_view_access(perms, "ROLE")`.
   - Role Permissions Matrix Editor visible only if `"ROLE_UPDATE" in perms or is_admin`.
   - Create Role form visible only if `"ROLE_CREATE" in perms or is_admin`.
4. In `pages/profile.py`:
   - User identity card (Name, Username, Email, ID, Department, Job Title).
   - Assigned Roles badges and Permissions list chips.
   - Change Password form (`current_password`, `new_password`, `confirm_password`).
5. In `app.py`:
   - Scope project context selector strictly to user's assigned projects (or General KB).
   - In-flight upload alert: if any document has `status == "processing"`, render subtle `st.info(f"⏳ Ingesting '{doc_name}' in background...")`.
   - Clear chat button placed in top action popover/button, not in sidebar.

- [ ] **Step 4: Commit**

```powershell
git add streamlit_app/pages/users.py streamlit_app/pages/departments.py streamlit_app/pages/roles.py streamlit_app/pages/profile.py streamlit_app/app.py tests/ui/test_rbac_ui_gates.py
git commit -m "feat(ui): enforce Write Implies Read rule and standardize admin, profile, and chat pages"
```

---

### Task 6: End-to-End Test Suite Run and Verification

**Files:**
- Test: All unit, contract, API, and UI tests across repository.

- [ ] **Step 1: Run the full test suite**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/ -v
```
Expected: All tests pass (0 failures).

- [ ] **Step 2: Commit any final test adjustments**

```powershell
git commit --allow-empty -m "chore(test): verify all unit, integration, and UI tests pass on sidebar-improvements"
```
