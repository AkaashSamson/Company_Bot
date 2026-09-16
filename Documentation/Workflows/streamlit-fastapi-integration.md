# Streamlit to FastAPI Integration

All management and chat pages are thin HTTP clients. They share `STREAMLIT_API_BASE_URL`, defaulting to `http://127.0.0.1:8000`.

| Page | Client | FastAPI surface |
|---|---|---|
| Chat | `ChatService` | `/api/chat` |
| Users | `OrganizationService` | `/api/users`, `/api/departments` |
| Projects | `OrganizationService` | `/api/projects`, project membership endpoints |
| Documents | `DocumentService` plus `OrganizationService` | `/api/documents`, `/api/projects` |

FastAPI owns authentication, validation, authorization, persistence, transactions, and ingestion orchestration. Streamlit owns forms, page state, loading/error/success messages, and rendering API responses. No page imports SQLAlchemy, Chroma, or local persistence code.
