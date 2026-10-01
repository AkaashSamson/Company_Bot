# 🏗️ Code-Grinder Deep Dive: `app/infrastructure`

> **Mode**: Topic Driller — every adapter that makes the domain's contracts real.

---

## 🗺️ The Territory — 12 Subdirectories

```
app/infrastructure/
├── persistence/          ← SQLite + SQLAlchemy — the database layer
│   └── sqlalchemy/
│       ├── models.py          (100 lines) — ORM tables (core entities)
│       ├── foundation_models.py (113 lines) — ORM tables (RBAC + grants)
│       ├── session.py         (160 lines) — engine, migrations, FK hooks
│       ├── unit_of_work.py     (48 lines) — UoW concrete implementation
│       └── repositories.py   (25 KB) — 11 concrete repository classes
│   ├── factory.py             (startup orchestrator)
│   └── rbac_seed.py           (idempotent RBAC bootstrapper)
├── authentication/       ← PBKDF2 password hasher + admin bootstrapper
├── llm/                  ← 4 files: OpenRouter, Groq, Fallback, PromptCache
├── vector/               ← ChromaDB adapter
├── faq/                  ← 2 FAQ cache strategies
├── session/              ← In-memory session store
├── observability/        ← Langfuse, LangSmith, Phoenix, Null providers
├── logging/              ← ConversationLogger with atomic writes + redaction
├── audit/                ← Authentication event recorder
├── document/             ← Document file I/O
├── ingestion/            ← Document-to-vector pipeline
└── cache/                ← Dual-cache wrapper
```

---

## 🧠 The Mental Model First

The infrastructure layer has **one job**: fulfill every port contract defined in `app/domain/ports/` using real external systems.

```
DOMAIN PORTS (contracts)     INFRASTRUCTURE ADAPTERS (fulfillment)
────────────────────────     ────────────────────────────────────────
UnitOfWork              ←── SqlAlchemyUnitOfWork          (SQLite)
RetrievalPort           ←── ChromaVectorStore             (ChromaDB)
LLMProvider             ←── OpenRouterClient / GroqClient (HTTP APIs)
AuthenticationService   ←── AuthenticationServiceImpl     (JWT + PBKDF2)
SessionStorePort        ←── InMemorySessionStore          (dict in RAM)
ObservabilityPort       ←── LangfuseProvider / NullProvider
SequenceRepository      ←── SqlAlchemySequenceRepository
```

The domain never imports from infrastructure. Infrastructure DOES import from domain (to use entity classes and port interfaces). This is the **dependency arrow pointing inward**.

---

## 🚀 The Startup Sequence — How It All Wires Together

Before diving into each subsystem, understand the full startup order in `persistence/factory.py`:

```mermaid
sequenceDiagram
    participant F as factory.py
    participant S as session.py
    participant D as DB (SQLite)
    participant B as bootstrap.py
    participant R as rbac_seed.py
    participant V as ChromaDB
    participant O as observability

    F->>S: create_engine_and_session_factory(DATABASE_URL)
    S->>D: sqlite:///.../db.sqlite3
    Note over S: PRAGMA foreign_keys=ON (event listener)
    F->>S: initialize_database(engine)
    S->>D: Base.metadata.create_all()  ← creates tables
    S->>D: ALTER TABLE ... ADD COLUMN  ← schema migrations
    S->>D: _rebuild_legacy_table()     ← projects + documents rowid fix
    F->>B: bootstrap_admin(uow_factory, password_hasher)
    B->>D: INSERT INTO users (admin)  ← only if not exists
    F->>R: seed_rbac(uow_factory)
    R->>D: INSERT INTO permissions, roles  ← only missing ones
    F->>V: ChromaVectorStore(persist_dir)
    F->>O: build_observability_provider()
    F-->>app: returns {uow_factory, vector_store, llm, ...}
```

Every step is **idempotent** — safe to call on every restart. Nothing breaks if the data already exists.

---

## 🗄️ Subsystem 1: Persistence — `sqlalchemy/`

### 1a. The Two Model Files — Why Split?

There are two ORM model files. This is intentional:

| File | What's In It | Why Separate |
|------|-------------|-------------|
| `models.py` | Core entities: `UserRecord`, `DepartmentRecord`, `ProjectRecord`, `DocumentRecord`, `UserProjectRecord`, `BusinessIdSequenceRecord` | These were in the original schema |
| `foundation_models.py` | RBAC: `RoleRecord`, `PermissionRecord`, `RolePermissionRecord`, `DepartmentMemberRecord` + grant tables: `DocumentPermissionRecord`, `ProjectGrantRecord` | Added later as features grew |

Both files share the same `Base = DeclarativeBase()` from `models.py`. `foundation_models.py` imports and extends this base. This lets SQLAlchemy discover ALL tables in one `Base.metadata.create_all()` call.

### 1b. `models.py` — ORM Tables Annotated

```python
class UserRecord(Base):
    __tablename__ = "users"

    uid: Mapped[str] = mapped_column(String(128), primary_key=True)
    # ↑ Not an auto-increment int! String PK. Why?
    # Because "admin" is the UID for the seed admin, MSS-001 for first user.
    # Readable, traceable, URL-friendly.

    username: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True, default="")
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    # ↑ 320 chars = RFC 5321 max email length (64 local + 1 @ + 255 domain)

    employee_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True)
    # ↑ Nullable! Users created before the ID system don't have one.
    # The BusinessIdGenerator detects this and seeds from existing data.
```

```python
class ProjectRecord(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # ↑ INTEGER auto-increment PRIMARY KEY = the SQLite rowid.
    # Used internally for fast JOINs.

    project_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    # ↑ Business ID like "PROJ-001". Separate from the database PK.
    # This is why DocumentRepository has both get(doc_id) and get_by_internal_id(int).
```

```python
class BusinessIdSequenceRecord(Base):
    __tablename__ = "business_id_sequences"

    sequence_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    # e.g., "user", "department", "project", "document"
    prefix: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # e.g., "MSS", "DEPT", "PROJ", "DOC"
    last_value: Mapped[int] = mapped_column(nullable=False, default=0)
    # The current highest allocated number — updated atomically
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

### 1c. `foundation_models.py` — The Access Control Tables

```python
class ProjectGrantRecord(Base):
    __tablename__ = "project_grants"
    __table_args__ = (
        UniqueConstraint("project_id", "principal_type", "role_id", "user_id", name="uq_project_grant"),
        CheckConstraint(
            "principal_type IN ('role', 'user') AND ("
            "(principal_type = 'role' AND role_id IS NOT NULL AND user_id IS NULL) OR "
            "(principal_type = 'user' AND user_id IS NOT NULL AND role_id IS NULL)"
            ")",
            name="ck_project_grants_principal",
        ),
    )
```

**The `CheckConstraint` is the key insight here.** A project grant can be awarded to:
- A **role** (e.g., "all Architects get access to PROJ-003") — `principal_type='role'`, `role_id=5`, `user_id=NULL`
- A **user** (e.g., "MSS-007 specifically gets access to PROJ-003") — `principal_type='user'`, `user_id='MSS-007'`, `role_id=NULL`

The DB constraint enforces that you can't have BOTH `role_id` and `user_id` set (exclusive principal), and you can't have NEITHER set. This is a **data integrity rule expressed in SQL**, not just Python validation.

### 1d. `session.py` — The Migration Engine

This is the most technically sophisticated file in the persistence layer. It solves a hard problem: **how do you migrate an existing SQLite database without a migration framework like Alembic?**

**The approach: detect and apply column additions manually:**

```python
_COLUMN_ADDITIONS = {
    "users": {
        "username": "VARCHAR(128) NOT NULL DEFAULT ''",
        "password_representation": "VARCHAR(512) NOT NULL DEFAULT ''",
        "must_change_password": "BOOLEAN NOT NULL DEFAULT 0",
        "employee_id": "VARCHAR(64) NULL",
        # ... more columns
    },
    "departments": {
        "description": "VARCHAR(500) NULL",
        "default_billable": "VARCHAR(32) NOT NULL DEFAULT 'billable'",
    },
    # ... 5 more tables
}
```

**Migration logic in `initialize_database()`:**

```python
def initialize_database(engine) -> None:
    Path("instance").mkdir(exist_ok=True)

    # Step 1: Create ALL tables that don't exist yet
    Base.metadata.create_all(engine)

    if engine.url.drivername.startswith("sqlite"):
        with engine.begin() as connection:
            inspector = inspect(connection)
            for table, additions in _COLUMN_ADDITIONS.items():
                # Step 2: Get currently existing columns
                columns = {col["name"] for col in inspector.get_columns(table)}
                for name, definition in additions.items():
                    if name not in columns:
                        # Step 3: Add missing column (SQLite's ALTER TABLE is limited)
                        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))

            # Step 4: Backfill: set username = uid for any rows where it's blank
            connection.execute(text("UPDATE users SET username = uid WHERE username = ''"))
```

**The `_rebuild_legacy_table()` function** — the most clever piece:

SQLite does NOT support `ADD PRIMARY KEY` or `DROP COLUMN` on existing tables. The only way to add an integer primary key `id` to an existing `projects` table that was created without one is to:

1. Create `projects_new` with the `id` column
2. `INSERT INTO projects_new SELECT rowid, ... FROM projects` (rowid IS the hidden auto-increment!)
3. `DROP TABLE projects`
4. `ALTER TABLE projects_new RENAME TO projects`

```python
def _rebuild_legacy_table(engine, table_name, column_spec, index_statements):
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        existing = {col["name"] for col in inspect(connection).get_columns(table_name)}
        if "id" in existing:
            return   # ← Already migrated — idempotent guard

        # Select: use "rowid" alias for the new "id" column
        select_clause = ", ".join("rowid" if name == "id" else name for name in explicit)
        # ...creates _new table, copies data using rowid, drops old, renames new
```

> [!IMPORTANT]
> `isolation_level="AUTOCOMMIT"` is required for SQLite DDL (CREATE TABLE, DROP TABLE). SQLite can't do these inside a transaction. This is why the migration uses a separate `execution_options(isolation_level="AUTOCOMMIT")` connection, not the normal transactional session.

**The Foreign Keys Event Listener:**

```python
if database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
```

SQLite disables foreign key enforcement by default for backwards compatibility. This SQLAlchemy event fires on EVERY new connection from the pool and enables FK enforcement. Without this, `ondelete="CASCADE"` in `ProjectGrantRecord` would silently do nothing.

**`expire_on_commit=False`:**

```python
return engine, sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
```

> [!NOTE]
> SQLAlchemy's default: after `session.commit()`, all loaded objects are **expired** — accessing any attribute causes a new SELECT query. `expire_on_commit=False` disables this. In this app, objects are used after commit (the API returns them), so expiration would cause "DetachedInstanceError" since the session is already closed. This is the right choice for this pattern.

### 1e. `unit_of_work.py` — The Concrete UoW (48 lines)

```python
class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.session = None       # ← Not created at __init__!

    def __enter__(self):
        self.session = self.session_factory()    # ← Created HERE
        self.users = SqlAlchemyUserRepository(self.session)
        self.departments = SqlAlchemyDepartmentRepository(self.session)
        # ... 9 more repositories, all sharing the SAME session object
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.session is None:
            return
        if exc_type is not None:
            self.rollback()        # ← Exception: rollback
        self.session.close()       # ← Always close the session

    def commit(self):    self.session.commit()
    def rollback(self):  self.session.rollback()
```

**The critical insight**: ALL 11 repositories share **the same `session` object**. This is what makes atomicity work. When you write to `uow.users` and `uow.projects` in the same `with uow:` block, both writes go into the same SQLAlchemy session → the same SQLite transaction. One `uow.commit()` commits everything together, or one exception rolls everything back.

### 1f. `rbac_seed.py` — The Idempotent RBAC Bootstrapper

```python
def seed_rbac(unit_of_work_factory, granted_by_uid=None):
    with unit_of_work_factory() as uow:
        permissions_by_name = {}

        # For each of the 25 defined permissions:
        for name, description in PERMISSION_DEFINITIONS:
            permission = uow.permissions.get_by_name(name)
            if permission is None:                  # ← Only create if missing
                permission = uow.permissions.save(Permission(None, name, description))
                permissions_created += 1
            permissions_by_name[name] = permission  # ← Cache for role assignment

        for definition in INITIAL_ROLE_DEFINITIONS:
            if uow.roles.get_by_name(definition["name"]) is not None:
                continue                            # ← Already exists → skip
            role = uow.roles.save(Role(...))
            permission_ids = [
                permissions_by_name[name].permission_id
                for name in resolve_role_permissions(definition["permissions"])
            ]
            uow.roles.set_permissions(role.role_id, permission_ids, granted_by_uid)
            roles_created += 1

        uow.commit()

    if permissions_created or roles_created:
        logger.info("rbac seed: permissions=%s roles=%s", permissions_created, roles_created)
```

**Idempotency** means: run this 100 times on the same database and the result is identical to running it once. The `if permission is None` and `if role is not None: continue` guards ensure no duplicates and no overwrites of admin-modified data.

---

## 🔐 Subsystem 2: Authentication — `authentication/`

### 2a. `password_hasher.py` — PBKDF2-SHA256

```python
class Pbkdf2PasswordHasher:
    ALGORITHM = "pbkdf2_sha256"
    ITERATIONS = 260_000   # OWASP 2023 recommendation for SHA-256
    SALT_SIZE = 16         # 128-bit salt

    def hash(self, password: str) -> str:
        salt = secrets.token_hex(self.SALT_SIZE)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), self.ITERATIONS)
        hash_b64 = base64.b64encode(dk).decode()
        return f"{self.ALGORITHM}${self.ITERATIONS}${salt}${hash_b64}"
        # Stored format: "pbkdf2_sha256$260000$<salt_hex>$<hash_b64>"

    def verify(self, password: str, stored: str) -> bool:
        try:
            algorithm, iterations_str, salt, stored_hash = stored.split("$", 3)
        except ValueError:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations_str))
        return hmac.compare_digest(
            base64.b64encode(dk).decode(),
            stored_hash,    # ← constant-time comparison (prevents timing attacks)
        )
```

**Three security decisions explained:**

1. **`secrets.token_hex()`** — Uses the OS's cryptographically secure random number generator (not `random`). Every user gets a unique 32-char hex salt, so two users with identical passwords produce completely different stored hashes.

2. **`260,000 iterations`** — OWASP's 2023 recommended minimum for PBKDF2-SHA256. High iteration count means even with a GPU, brute-forcing one hash takes ~0.1 seconds. Attacking 1 million users would take 100,000 GPU-seconds.

3. **`hmac.compare_digest()`** — Python's `==` on strings short-circuits on the first differing byte. An attacker could measure response time to guess characters one by one (timing attack). `compare_digest()` always compares ALL bytes in constant time.

### 2b. `bootstrap.py` — The Seed Admin

```python
def bootstrap_admin(unit_of_work_factory, password_hasher, username=ADMIN_USERNAME, password=ADMIN_INITIAL_PASSWORD):
    if not password:
        logger.warning("ADMIN_INITIAL_PASSWORD is not configured; seed admin will not be provisioned")
        return False   # ← Fail fast: can't create admin without a password

    with unit_of_work_factory() as uow:
        existing = uow.users.get_by_username(username)
        if existing:
            return False    # ← Idempotent: don't recreate the admin

        # Create the "Administration" department first (admin must belong to a dept)
        if not uow.departments.get("admin"):
            uow.departments.save(Department("admin", "Administration", ...))

        uow.users.save(User(
            "admin",            # ← uid is literally "admin" (not a generated ID)
            "Administrator",
            "admin@localhost",
            "Admin",
            "admin",            # ← department_id
            password_representation=password_hasher.hash(password),
            must_change_password=True,  # ← Force change on first login
        ))
        uow.commit()
        record_authentication_event("bootstrap", uid="admin", success=True)
        return True
```

The admin's `must_change_password=True` is the security mechanism that forces the operator to set a real password after deploying. The `ADMIN_INITIAL_PASSWORD` from `.env` is only ever used once.

---

## 🤖 Subsystem 3: LLM Stack — `llm/`

The LLM stack has 4 files that compose like Russian dolls:

```
PromptLRUCache (semantic similarity cache)
    ↑ used by
FallbackLLMProvider (primary → fallback orchestrator)
    ↑ wraps
OpenRouterClient          GroqClient
(primary, Claude 3.5)     (fallback, Llama 3.1)
```

### 3a. `groq_client.py` — The Minimal Fallback (71 lines)

```python
class GroqClient(LLMProvider):
    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
    # ↑ OpenAI-compatible endpoint! Groq uses the same API shape as OpenAI.

    def __init__(self, api_key, model, timeout=60.0, max_tokens=400):
        # Persistent client — reuses TCP/TLS connection across calls
        self._client = httpx.Client(
            timeout=timeout,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )

    def generate(self, messages):
        response = self._client.post(self.BASE_URL, json={"model": ..., "messages": ..., "max_tokens": ...})

        if response.is_error:
            raise LLMProviderError(f"Groq returned HTTP {response.status_code}: {_sanitize_response_body(response.text)}")
            # ↑ sanitize_response_body strips API keys from error messages before logging!

        content = response.json()["choices"][0]["message"]["content"]
        if not content:
            raise LLMProviderError("Groq returned an empty response.")
        return content
```

**`httpx.Client` (not `requests`)** — `httpx` is the modern Python HTTP library. Using a **persistent client** means the TCP/TLS handshake is done ONCE per server lifecycle, not on every request. For a chat API called many times per second, this saves ~50-200ms per call.

**`_sanitize_response_body()`** — strips Bearer tokens and API keys from error strings before they're logged:
```python
sanitized = re.sub(r"(?i)bearer\s+[a-z0-9._-]+", "Bearer [REDACTED]", body)
sanitized = re.sub(r"(?i)(?:gsk_|sk-)[a-z0-9_-]+", "[REDACTED_KEY]", sanitized)
```

### 3b. `openrouter_client.py` — The Primary Client (224 lines)

Everything in Groq, PLUS three additional features:

**Feature 1: `_strip_reasoning()` — Post-processes thinking-model output**

```python
_THINKING_HEADER = re.compile(
    r"^(#+\s*)?"               # optional markdown heading
    r"(\d+[\.]\s*)?"           # optional "1."
    r"(\*{1,2})?"              # optional bold marker
    r"(analyze|analysis|thinking process|let me (look|check|find|search|examine)...)",
    re.IGNORECASE,
)

def _strip_reasoning(raw: str) -> str:
    # Step 1: Strip <think>...</think> XML tags (some models emit these)
    text = re.sub(r"<think(?:ing)?>.*?</think(?:ing)?>", "", raw, flags=re.DOTALL).strip()

    # Step 2: Find the LAST "thinking header" line
    # ("Analyze the context", "I need to check", "Formulate response")
    last_header_idx = -1
    for i, line in enumerate(text.splitlines()):
        if _THINKING_HEADER.search(line.strip()) or _INSTRUCTION_ECHO.search(line.strip()):
            last_header_idx = i

    # Step 3: Return only what comes AFTER the last thinking section
    if last_header_idx == -1:
        return text   # No thinking headers found — return as-is

    after = "\n".join(lines[last_header_idx + 1:]).strip()
    if not after:
        # Edge case: thinking was the entire output — return last paragraph
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
        return paragraphs[-1] if paragraphs else text

    return after
```

This is solving a real problem: some LLMs (especially reasoning/thinking variants) emit internal reasoning like "Let me analyze the document context first..." before the actual answer. This function strips the reasoning and returns only the final user-facing answer.

**Feature 2: Null-response retry**

```python
raw = data["choices"][0]["message"]["content"]

if not raw:
    # Retry once with user-only message
    # (some models return null when the system prompt is too long)
    payload["messages"] = [{"role": "user", "content": payload["messages"][-1]["content"]}]
    response = self._client.post(self.BASE_URL, json=payload)
    # ... repeat extraction
```

**Feature 3: Token tracking + LangSmith metadata**

```python
def _track_tokens(self, response_data: dict) -> None:
    usage = response_data.get("usage", {})
    tracker = get_token_tracker()    # ← singleton token tracker
    tracker.track(
        model=self.model,
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        session_id=self.session_id,
        cache_hit=False,
        provider="openrouter",
    )
```

### 3c. `fallback_llm_provider.py` — Chain of Responsibility (73 lines)

```python
class FallbackLLMProvider(LLMProvider):
    def generate(self, messages):
        # ── STEP 1: Semantic cache check ──
        cached_response = self.cache.get(messages)
        if cached_response is not None:
            logger.info("llm_call outcome=cache_hit provider=none")
            self._last_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "cache_hit": True}
            return cached_response   # ← Return without any API call

        # ── STEP 2: Try primary ──
        try:
            response = self.primary.generate(messages)
            if hasattr(self.primary, 'get_last_tokens'):
                self._last_tokens = self.primary.get_last_tokens()

        # ── STEP 3: Primary failed → try fallback ──
        except LLMProviderError as primary_error:
            logger.warning("llm_failure provider=primary error_type=%s", type(primary_error).__name__)
            try:
                response = self.fallback.generate(messages)
                if hasattr(self.fallback, 'get_last_tokens'):
                    self._last_tokens = self.fallback.get_last_tokens()

            # ── STEP 4: Both failed ──
            except LLMProviderError as fallback_error:
                raise LLMProviderError("Both primary and fallback LLM providers failed.") from fallback_error

        # ── STEP 5: Store in cache for future calls ──
        self.cache.put(messages, response)
        return response
```

The flow through a single `generate()` call:
```
cache.get(messages)  →  HIT  →  return immediately (0 API calls)
                     →  MISS →  primary.generate()  →  SUCCESS → cache.put() → return
                                                     →  FAIL   → fallback.generate() → SUCCESS → cache.put() → return
                                                                                      → FAIL   → raise
```

### 3d. `prompt_cache.py` — The Semantic LRU Cache (140 lines)

This is the most algorithmically sophisticated infrastructure file. It implements an LRU cache with **two hit modes**:

**Mode 1: Exact match** (O(1))
```python
def get(self, messages):
    key = self.make_key(messages)   # JSON serialize the messages list
    with self._lock:
        entry = self._entries.get(key)
        if entry is not None:
            self._entries.move_to_end(key)   # ← LRU: promote to most-recent
            return entry[0]   # entry = (response_text, embedding_vector)
```

**Mode 2: Semantic similarity** (O(N) — scans all cached entries)
```python
    query_vector = self._embed(key)    # Generate embedding for the query
    with self._lock:
        best_key = None
        best_score = 0.0
        for cached_key, (_, cached_vector) in self._entries.items():
            score = self._cosine_similarity(query_vector, cached_vector)
            if score > best_score:
                best_key = cached_key
                best_score = score

        if best_key and best_score >= self.similarity_threshold:
            self._entries.move_to_end(best_key)
            return self._entries[best_key][0]   # ← Semantic HIT
```

**Cosine similarity — pure Python (no numpy):**
```python
@staticmethod
def _cosine_similarity(left, right) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(v * v for v in left))
    right_norm = math.sqrt(sum(v * v for v in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)
```

**The `_embed()` method** — lazy model loading:
```python
def _embed(self, key: str) -> list[float]:
    if self._embedder is not None:   # Injected custom embedder (for tests)
        return list(self._embedder(key))

    # Extract user messages from the JSON key
    parsed = json.loads(key)
    embed_text = " ".join(
        msg.get("content", "")
        for msg in parsed
        if isinstance(msg, dict) and msg.get("role") == "user"
    ) or key

    if self._embedding_model is None:
        self._embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        # ↑ Lazy: model only loaded on first cache miss
    return self._embedding_model.encode(embed_text, convert_to_numpy=True).tolist()
```

**LRU eviction:**
```python
def put(self, messages, response):
    key = self.make_key(messages)
    vector = self._embed(key)
    with self._lock:
        self._entries[key] = (response, vector)
        self._entries.move_to_end(key)
        while len(self._entries) > self.maxsize:
            self._entries.popitem(last=False)   # ← Remove least-recently-used
```

`OrderedDict` maintains insertion order. `move_to_end()` moves an entry to the "most recent" end. `popitem(last=False)` removes from the "least recent" end. This is the classic O(1) LRU implementation.

**Why `RLock` instead of `Lock`?**

`RLock` (Reentrant Lock) allows the SAME thread to acquire the lock multiple times without deadlocking. In `get()`, if exact match fails, the lock is released before calling `_embed()` (which may be slow), then re-acquired for semantic search. If some code path calls `get()` recursively (e.g., in a log statement that triggers another cache lookup), `RLock` prevents deadlock.

---

## 🔍 Subsystem 4: Vector Store — `vector/`

### `chroma_client.py` — ChromaDB Adapter

```python
class ChromaVectorStore:
    def __init__(self, persist_dir: str = CHROMA_PERSIST_DIR, collection_name: str = CHROMA_COLLECTION):
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._embedder = SentenceTransformer(EMBEDDING_MODEL)
        self._collection = self._client.get_or_create_collection(collection_name)

    def query(self, query_text: str, top_k: int = 3, project_ids: Sequence[str] | None = None) -> list[dict]:
        query_embedding = self._embedder.encode(query_text).tolist()

        where_filter = None
        if project_ids is not None:
            if len(project_ids) == 1:
                where_filter = {"project_id": {"$eq": project_ids[0]}}
            else:
                where_filter = {"project_id": {"$in": list(project_ids)}}
                # ↑ ChromaDB metadata filter — restricts results to authorized projects

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter,
        )
        # Flatten and return as list of dicts
```

**The `project_ids` filter is the authorization enforcement point for RAG.** The `AuthorizationScope.project_ids` computed by the `AuthorizationEngine` is passed here as `where_filter`. An admin gets `project_ids=None` → no filter → all documents. A regular user gets `["PROJ-001", "PROJ-003"]` → only those documents are returned.

---

## 📚 Subsystem 5: FAQ Layer — `faq/`

Two different FAQ strategies, solving different problems:

### 5a. `faq_similarity_cache.py` — Semantic FAQ Cache (176 lines)

```
On startup:
1. Load all FAQ entries from JSON file
2. Embed ALL questions at once using SentenceTransformer batch encoding
3. Store as a float32 numpy matrix, shape (N_faqs, embedding_dim)

On search(question):
1. Embed the incoming question → shape (embedding_dim,)
2. scores = matrix @ query_vector  ← ONE matrix multiply! O(N) but vectorized
3. best_idx = argmax(scores)
4. if scores[best_idx] >= threshold: return entry  (HIT)
5. else: return None  (MISS)
```

```python
# Step 2: Batch encode at startup
raw: np.ndarray = model.encode(
    questions,
    convert_to_numpy=True,
    normalize_embeddings=True,   # ← Unit-normalizes each vector!
    show_progress_bar=False,
)
self._matrix = raw.astype(np.float32)   # N×D matrix
```

```python
# Step 2 in search: encode incoming question
query_vec = self._model.encode([question], normalize_embeddings=True)[0]

# Step 3: Matrix × vector = cosine similarities for ALL FAQs at once
scores: np.ndarray = self._matrix @ query_vec   # shape (N,)
```

> [!TIP]
> `normalize_embeddings=True` at both encode stages means the vectors are already unit length (magnitude = 1). Therefore `cosine_similarity(a, b) = dot_product(a, b)` exactly. The `@` operator IS the cosine similarity when both vectors are normalized. No division needed.

This is **much faster** than the `PromptLRUCache`'s pure-Python loop — numpy's matrix multiply uses BLAS routines (optimized C/Fortran code, often SIMD-accelerated).

### 5b. `json_faq_cache.py` — Legacy FAQ Cache (81 lines)

This is the older FAQ system — stores FAQs as a flat JSON file with two possible formats:

**New format** (`entries` key — structured):
```json
{
  "entries": [
    {"input": "What is the leave policy?", "output": "You get 15 days...", "input_vector": [...]}
  ]
}
```

**Legacy format** (`faqs` key — plain text):
```json
{"faqs": "19.1 What is the leave policy?\n15 days paid leave...\n\n19.2 How do I apply?..."}
```

The `migrate_to_entries()` method auto-converts legacy to structured format:
```python
def migrate_to_entries(self):
    # Parse numbered Q&A blocks using regex
    matches = list(re.finditer(r"(?m)^(19\.\d+|20\.)\s+(.+?)\n", text))
    # For each match: extract question + answer block, compute embedding, save
```

**`save()` uses atomic write:**
```python
def save(self, data):
    self.path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = self.path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_path.replace(self.path)   # ← Atomic rename on POSIX (and mostly on Windows)
```

`os.replace()` (and `Path.replace()`) is atomic on POSIX — either the old file exists or the new file exists, never a half-written state. Critical for crash safety.

---

## 🗂️ Subsystem 6: Session Store — `session/`

### `in_memory_session.py` — Thread-Safe Dict (≈60 lines)

```python
class InMemorySessionStore:
    def __init__(self, max_age_hours: float = SESSION_MAX_AGE_HOURS):
        self._sessions: dict[str, SessionData] = {}
        self._lock = threading.RLock()   # ← Same RLock pattern as the cache
        self.max_age_hours = max_age_hours

    def get(self, session_id: str) -> Optional[SessionData]:
        with self._lock:
            data = self._sessions.get(session_id)
            if data is None:
                return None
            # Check expiry inline
            age_hours = (datetime.now(timezone.utc) - data.last_activity).total_seconds() / 3600
            if age_hours > self.max_age_hours:
                del self._sessions[session_id]
                return None
            return data

    def purge_expired(self, max_age_hours: float) -> int:
        with self._lock:
            now = datetime.now(timezone.utc)
            expired = [
                sid for sid, data in self._sessions.items()
                if (now - data.last_activity).total_seconds() / 3600 > max_age_hours
            ]
            for sid in expired:
                del self._sessions[sid]
            return len(expired)
```

**Limitation**: This is lost on restart. Every time the app restarts, all sessions are gone. Users mid-conversation lose their history. The `SessionStorePort` was specifically designed so this could be swapped for Redis with zero domain-layer changes.

---

## 📊 Subsystem 7: Observability — `observability/`

### 7a. `null_provider.py` — The Null Object Pattern (59 lines)

```python
class NullSpan(TraceSpanPort):
    """Safe no-op span for tests and offline execution."""
    def end(self, outputs=None, error=None) -> None:
        self.outputs = outputs     # ← Still stores data (useful for test assertions)
        self.error = error
        self.is_ended = True       # ← Lets tests verify end() was called

    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type: self.end(error=str(exc_val))
        else: self.end()

class NullObservabilityProvider(BaseObservabilityProvider):
    def create_trace(self, name, ...): return NullSpan(name=name)
    def record_llm_call(self, ...): pass   # ← No network calls
    def flush(self): pass
```

The `NullSpan` still stores outputs even though it's "null" — this lets unit tests do:
```python
span = NullSpan()
span.end(outputs={"result": "ok"})
assert span.outputs == {"result": "ok"}
assert span.is_ended == True
```

### 7b. `tracer.py` — LangSmith Context Manager (129 lines)

```python
@contextmanager
def trace_step(name: str, inputs: dict | None = None, run_type: str = "chain"):
    if not (LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY):
        yield _NoOpSpan()   # ← Instant return if tracing disabled
        return

    try:
        from langsmith import Client
        client = Client()
        run = client.create_run(name=name, run_type=run_type, inputs=inputs or {})
        try:
            yield run    # ← Code inside `with trace_step(...)` runs here
        except Exception as exc:
            run.end(error=str(exc))
            client.update_run(run.id, error=str(exc))
            raise
        else:
            client.update_run(run.id)
    except ImportError:
        logger.warning("langsmith not installed — tracing skipped.")
        yield _NoOpSpan()   # ← Graceful degradation if package missing
    except Exception as exc:
        logger.warning("LangSmith trace_step failed: %s", exc)
        yield _NoOpSpan()   # ← Never crash the business logic due to tracing
```

The `traceable` **decorator** variant:
```python
@traceable(name="FAQ Cache Search", run_type="retriever")
def search(question: str) -> dict | None:
    ...
```

Both `trace_step()` (context manager) and `@traceable` (decorator) degrade gracefully to no-ops when LangSmith is unavailable. **The observability layer never breaks the business logic.**

---

## 📝 Subsystem 8: Logging — `logging/`

### `conversation_logger.py` — The Atomic Redacting Logger (189 lines)

Three problems solved:

**Problem 1: Credential Leakage**

```python
PATTERNS = [
    (re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]+)", re.IGNORECASE), r"Bearer [REDACTED]"),
    (re.compile(r"\b(sk-[A-Za-z0-9_\-]{16,})\b"), REDACTED_TEXT),
    (re.compile(r"\b(gsk_[A-Za-z0-9_\-]{16,})\b"), REDACTED_TEXT),
    # Generic: api_key: "secret", password="secret"
    (re.compile(r"(?i)\b(api[_-]?key|secret|password|token|auth[_-]?token)\b\s*[:=]\s*(['"]?)([^\s'",;]+)\2"),
     r"\1: [REDACTED]"),
    # Basic auth in URLs: https://user:pass@host
    (re.compile(r"(https?://)([^:\s]+):([^@\s]+)@"), r"\1[REDACTED]:[REDACTED]@"),
]
```

`redact()` runs: first exact-string replacement for known API keys, then regex patterns.

**Problem 2: File Collision**

```python
def _generate_log_path(self, employee_id: str, timestamp: datetime) -> Path:
    base_ts = timestamp.strftime("%Y%m%d_%H%M%S")
    filename = f"{employee_id}_{base_ts}.json"   # "MSS-001_20240115_143022.json"
    target_path = self.log_dir / filename

    if not target_path.exists():
        return target_path    # ← No collision

    # Collision: same employee, same second (fast typist or batch test)
    counter = 1
    while True:
        candidate = self.log_dir / f"{employee_id}_{base_ts}_{counter}.json"
        if not candidate.exists():
            return candidate    # ← "MSS-001_20240115_143022_1.json"
        counter += 1
```

**Problem 3: Crash Safety (Atomic Write)**

```python
def _write_atomic(self, target_path: Path, log_data: dict) -> None:
    self.log_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Create temp file IN THE SAME DIRECTORY as the target
    # (same-directory ensures temp and target are on same filesystem → rename is atomic)
    temp_fd, temp_path_str = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=str(self.log_dir))
    temp_path = Path(temp_path_str)

    try:
        # Step 2: Write to temp file
        with open(temp_fd, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)

        # Step 3: Atomically rename to final path
        os.replace(temp_path, target_path)   # ← ATOMIC on POSIX

    except Exception:
        if temp_path.exists():
            try: temp_path.unlink()   # ← Clean up temp on failure
            except OSError: pass
        raise
```

> [!IMPORTANT]
> **Same-directory temp file** is critical. `os.replace()` is only atomic when source and destination are on the same filesystem/volume. `tempfile.mkstemp(dir=str(self.log_dir))` ensures this. If you wrote to `/tmp/` and then `os.replace()` to the log dir on a different volume, it would be a copy+delete (not atomic).

**Isolation**: `log_conversation()` wraps everything in a broad `try/except`. Logging failures are swallowed and logged at ERROR level, but never propagated to the caller. A broken log directory never crashes a chat response.

---

## 🏭 Subsystem 9: Startup Factory — `persistence/factory.py`

```python
def create_infrastructure(settings) -> InfrastructureComponents:
    # 1. Database
    engine, session_factory = create_engine_and_session_factory(settings.DATABASE_URL)
    initialize_database(engine)
    uow_factory = lambda: SqlAlchemyUnitOfWork(session_factory)

    # 2. Auth
    password_hasher = Pbkdf2PasswordHasher()
    bootstrap_admin(uow_factory, password_hasher)

    # 3. RBAC
    seed_rbac(uow_factory)

    # 4. Business IDs
    id_generator = build_business_id_generator(
        user_prefix=settings.USER_ID_PREFIX,          # "MSS"
        department_prefix=settings.DEPARTMENT_PREFIX, # "DEPT"
        project_prefix=settings.PROJECT_PREFIX,       # "PROJ"
        document_prefix=settings.DOCUMENT_PREFIX,     # "DOC"
    )

    # 5. LLM Stack
    openrouter = OpenRouterClient(...)
    groq = GroqClient(...)
    llm = FallbackLLMProvider(primary=openrouter, fallback=groq)

    # 6. Vector Store
    vector_store = ChromaVectorStore(persist_dir=settings.CHROMA_PERSIST_DIR)

    # 7. Observability
    observability = build_observability_provider()

    # 8. FAQ
    faq_cache = FAQSimilarityCache(faq_path=settings.FAQ_JSON_PATH)

    return InfrastructureComponents(uow_factory, llm, vector_store, id_generator, ...)
```

---

## 📐 Cross-Cutting Infrastructure Patterns

| Pattern | Where Used | Why |
|---------|-----------|-----|
| **`RLock` (Reentrant Lock)** | `PromptLRUCache`, `FAQSimilarityCache`, `InMemorySessionStore` | Thread-safe shared state; re-entrant prevents deadlock in recursive call paths |
| **`httpx.Client` (persistent)** | `OpenRouterClient`, `GroqClient` | TCP/TLS handshake amortized across many requests |
| **Lazy model loading** | `PromptLRUCache._embed()`, `FAQSimilarityCache._search()` | `SentenceTransformer` takes 1-3s to load; defer until first use |
| **`expire_on_commit=False`** | `session.py` → `sessionmaker` | Objects usable after commit; prevents `DetachedInstanceError` in API responses |
| **Atomic file write** | `ConversationLogger`, `JsonFAQCache` | `write_to_temp → os.replace()` ensures no half-written files survive crashes |
| **Idempotent bootstrapping** | `rbac_seed.py`, `bootstrap_admin()` | Safe to re-run on every startup; `if exists: skip` guards throughout |
| **`secrets.token_hex()`** | `Pbkdf2PasswordHasher.hash()` | CSPRNG for salt generation (not `random`) |
| **`hmac.compare_digest()`** | `Pbkdf2PasswordHasher.verify()` | Constant-time comparison prevents timing attacks |
| **`CheckConstraint` in ORM** | `ProjectGrantRecord`, `DocumentPermissionRecord` | DB-level principal exclusivity enforced in SQL, not just Python |

---

## 🔥 Drill Questions

### Q1: `session.py` uses `expire_on_commit=False`. What would break if you removed it?

> **A**: After `uow.commit()`, SQLAlchemy would mark all loaded ORM objects as "expired." The `__exit__()` method then calls `session.close()`. After that, accessing any attribute on a returned entity (e.g., `user.name` in a route handler) would trigger a `DetachedInstanceError` — the session is closed, so SQLAlchemy can't lazy-load the expired attribute. With `expire_on_commit=False`, attributes retain their values after commit, so the API layer can safely serialize them.

### Q2: `initialize_database()` uses `_rebuild_legacy_table()`. Why can't it just use `ALTER TABLE projects ADD COLUMN id INTEGER PRIMARY KEY`?

> **A**: SQLite doesn't support `ALTER TABLE ... ADD PRIMARY KEY`. It also doesn't support adding a `NOT NULL` column to an existing table that has rows (since existing rows would have `NULL` for the new column, violating the constraint). The only way to fundamentally change a table's schema in SQLite is the "create-new, copy-data, drop-old, rename" dance. The `_rebuild_legacy_table()` uses SQLite's hidden `rowid` (which was always there as the implicit integer PK) to populate the new `id` column.

### Q3: `FAQSimilarityCache` uses `normalize_embeddings=True` and then `matrix @ query_vec` for similarity. `PromptLRUCache` normalizes manually with a cosine similarity formula. Why the difference?

> **A**: `FAQSimilarityCache` uses **numpy** (a C library) and can normalize entire matrices at once efficiently. It pre-normalizes the FAQ matrix at startup, so search is just a dot product — `O(N)` but vectorized BLAS operations. `PromptLRUCache` uses **pure Python** loops and can't use numpy's batch operations because it stores individual (response, vector) tuples, not a matrix. It can't pre-build a matrix because entries arrive one at a time. The different implementations reflect the different data structure constraints.

### Q4: `FallbackLLMProvider.generate()` catches `LLMProviderError` but NOT `Exception`. What happens if `OpenRouterClient.generate()` throws a `RuntimeError`?

> **A**: A `RuntimeError` bypasses the `except LLMProviderError` handler and propagates directly to the `QueryOrchestrator`. The fallback `GroqClient` is **never tried**. This is intentional — `RuntimeError` indicates a programming error, not a network failure. Only known failure modes (`LLMProviderError`) trigger failover. Unexpected exceptions should surface immediately so they can be fixed.

### Q5: `ConversationLogger._write_atomic()` creates the temp file with `tempfile.mkstemp(dir=str(self.log_dir))`. Why `dir=log_dir` and not the default temp dir?

> **A**: `os.replace()` is only atomic when source and destination are on the **same filesystem/volume**. If the temp file were in `/tmp/` (default) and the log dir were on a different drive, the rename would become a copy-then-delete operation. A crash mid-copy would leave a partially-written file at the destination — exactly what atomic writes are designed to prevent. Same-directory temp ensures single-filesystem rename.

### Q6: The `GroqClient` uses `_sanitize_response_body()` before logging HTTP errors. Why not just log `response.text` directly?

> **A**: Error responses from LLM APIs often echo back parts of the request, including authorization headers. For example, a "429 Too Many Requests" response from Groq might include the `Authorization: Bearer gsk_...` header value in the error body. Logging that raw text would write API keys to disk logs (and potentially to observability systems like Langfuse/LangSmith). The sanitizer strips all Bearer tokens and API key patterns before the string is ever passed to `logger.warning()`.

### Q7: Why does `SqlAlchemyUnitOfWork.__exit__()` NOT call `commit()` — only `rollback()` on exceptions?

> **A**: This is the explicit commit pattern. The domain contract says "you must call `uow.commit()` to persist changes." If `__exit__()` auto-committed on success, bugs where developers forgot to call `commit()` would silently persist data — or worse, partially-constructed state would be committed before validation completed. By requiring explicit `commit()`, any missed commit is caught as "data was not saved" — a visible bug. The only automatic behavior is `rollback()` on exceptions, preventing partial writes from surviving errors.
