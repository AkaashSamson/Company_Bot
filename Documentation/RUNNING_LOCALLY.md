# KnowLayer HR Policy Chatbot

KnowLayer is a modular-monolith MVP that lets a user ask questions about one approved HR source document: the Nexora employee handbook. The application retrieves relevant chunks from a local Chroma vector database and returns an answer with source citations through a Streamlit chat interface.

## Current MVP

- Local document storage in `input/`
- DOCX, TXT, Markdown, and RST ingestion
- Text extraction and chunking with `python-docx` for DOCX files
- Local persistent Chroma database in `.chroma/`
- Sentence-transformer embeddings
- FastAPI chat endpoint at `/api/chat`
- Streamlit chat UI
- Citation rendering with source, section, and text excerpt
- Bounded conversation-history schema support
- Unit, contract, integration, and smoke-test scaffolding

The current answer orchestration uses deterministic MVP logic over retrieved evidence. OpenRouter and Groq configuration fields are present for future provider integration; they are not required to run the current local retrieval flow. Authentication, authorization, enterprise HR systems, hosted storage, and production security controls are future extensions.

## Project Structure

```text
Company_Bot/
├── app/
│   ├── main.py                         # FastAPI application and health endpoint
│   ├── api/
│   │   ├── routes/chat.py              # POST /api/chat
│   │   └── schemas/chat.py             # Request, response, and citation models
│   ├── core/settings.py                # Environment-backed configuration
│   ├── domain/
│   │   ├── entities/document_models.py # Document and chat domain models
│   │   └── services/session_memory_service.py
│   ├── infrastructure/
│   │   ├── document/local_document_loader.py
│   │   └── vector/chroma_client.py     # Persistent Chroma adapter
│   └── use_cases/
│       ├── chat/
│       │   ├── query_orchestrator.py   # Retrieval and answer workflow
│       │   ├── retrieval_service.py    # Retrieval abstraction
│       │   ├── provenance_service.py   # Citation assembly
│       │   └── session_memory.py       # Conversation memory wrapper
│       └── ingestion/document_processing.py
├── input/                              # Approved local source document(s)
├── scripts/
│   ├── ingest_documents.py             # Index documents into Chroma
│   └── smoke_test.py                   # Ingestion/retrieval/chat checks
├── streamlit_app/
│   ├── app.py                          # Chat UI
│   └── services/chat_service.py        # HTTP client for FastAPI
├── tests/
│   ├── unit/
│   ├── contract/
│   └── integration/
├── .chroma/                            # Generated local vector store
├── .env                                # Local configuration, not committed
├── requirements.txt
├── setup.ps1                           # One-command Windows setup and launch
└── ARCHITECTURE.md                     # Detailed architecture explanation
```

## Prerequisites

- Windows PowerShell
- Python 3.11 or newer
- The Nexora HR source document in `input/`
- Internet access on the first run so Python packages and the embedding model can be downloaded

No separate Chroma server is needed. This MVP uses `chromadb.PersistentClient` and stores the database locally in `.chroma/`.

## One-Command Setup

Open PowerShell in the project root:

```powershell
cd "C:\Users\AkaashSamsonAnandGud\OneDrive - McLaren Strategic Solutions US Inc\Documents\Training Projects\Company_Bot"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\setup.ps1
```

The script checks Python, creates `.venv`, installs `requirements.txt`, creates `.env` if needed, checks `input/`, ingests the document, and runs smoke/unit/contract tests. The embedding model may take time to download on the first run.

## Start the Product Automatically

Run the application:

```powershell
.\setup.ps1
```

This opens two PowerShell windows:

- FastAPI: `http://127.0.0.1:8000`
- Health check: `http://127.0.0.1:8000/health`
- Streamlit: `http://127.0.0.1:8501`

Keep both service windows open. Open the Streamlit URL and ask questions such as `What is the leave policy?`, `What are the working hours and attendance expectations?`, or `What does the handbook say about remote work?`. The assistant displays the retrieved source, section, and supporting text below the answer.

## Manual Run

Terminal 1, API:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2, UI:

```powershell
.\.venv\Scripts\Activate.ps1
python -m streamlit run streamlit_app/app.py
```

Run `.\setup.ps1` first if `.venv` does not exist.

## Re-ingest Documents

Document ingestion is not part of application startup. The existing Chroma index is reused. If the source document changes, run ingestion manually:

```powershell
.\.venv\Scripts\python.exe scripts\ingest_documents.py
```

For a clean rebuild, stop the applications, remove `.chroma/`, and ingest again:

```powershell
Remove-Item -Recurse -Force .chroma
.\.venv\Scripts\python.exe scripts\ingest_documents.py
```

## Validation Commands

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test.py
.\.venv\Scripts\python.exe -m pytest tests\unit tests\contract -v
.\.venv\Scripts\python.exe -m pytest tests\integration -v
```

## Configuration

The application reads `.env` through [app/core/settings.py](app/core/settings.py). The important local settings are:

```text
DOCUMENTS_DIR=input
COLLECTION_NAME=hr_policy_docs
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

`OPENROUTER_API_KEY`, `GROQ_API_KEY`, `LLM_MODEL`, and `GROQ_MODEL` are reserved for the planned provider integration. Do not commit `.env` or API keys.

## Troubleshooting

**PowerShell blocks the script:** run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`.

**The UI says connection refused:** start FastAPI first and confirm `http://127.0.0.1:8000/health` returns `{"status":"ok"}`.

**The collection is empty:** confirm the handbook is in `input/`, then run the ingestion command again.

**The first run is slow:** Sentence Transformers downloads its embedding model once and may take several minutes.

## Architecture and Roadmap

Read [ARCHITECTURE.md](ARCHITECTURE.md) for the modular-monolith layers, request and ingestion flows, testing strategy, and future extension points. Planned increments include live conversation-window use, a dedicated search experience, OpenRouter/Groq provider integration, and stronger production operational controls. These remain outside the current single-document MVP.
