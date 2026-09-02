# Implementation Plan: KnowLayer Platform

**Branch**: `001-knowlayer-platform` | **Date**: 2026-09-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-knowlayer-platform/spec.md`

## Summary

KnowLayer MVP 1 is a Streamlit-based HR policy Q&A assistant that answers questions from a single approved internal HR policy document. The project will use a modular monolith structure so the domain logic remains isolated from the UI, LLM provider, and storage implementation. The document source will live in a local folder, embeddings and retrieval will use Chroma DB, and the default model path will use OpenRouter with Groq as a supporting provider. Follow-up questions are required in MVP 1, so the chat flow will keep a short rolling conversation window per session using LangChain ConversationWindowBufferMemory to maintain contextual follow-up questions without storing a full conversation history beyond the configured window. The architecture is deliberately simple for v1 and intentionally designed for future expansion into more enterprise connectors and security controls.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: Streamlit, FastAPI, Pydantic, Chroma DB, sentence-transformers or a compatible embedding model, OpenRouter client, Groq client optional, LangChain, ConversationWindowBufferMemory, pytest, python-dotenv

**Storage**: Local folder for raw policy documents, Chroma DB for vector embeddings and retrieval metadata, local filesystem for generated artifacts and optional caches, in-memory conversational context per session using a short rolling window

**Testing**: pytest for unit tests, retrieval tests, and UI-level smoke tests

**Target Platform**: Local development environment and internal web deployment via Streamlit app with optional API backend

**Project Type**: Web application + modular backend service

**Performance Goals**: Fast interactive answers for standard policy lookup and Q&A; target response time in the low seconds for a single-document retrieval flow

**Constraints**: MVP 1 assumes all users are trusted internal users; no HR-system integration in v1; provenance and citations are mandatory; architecture must stay modular and provider-agnostic

**Scale/Scope**: Single approved HR policy document, small user base, minimal operational complexity, future-ready architecture

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- ✅ Modular monolith with isolated boundaries is preserved.
- ✅ Core domain logic remains independent from UI, LLM provider, and storage choices.
- ✅ Source-of-truth requirement is respected because the approved HR policy document is the only authoritative source in v1.
- ✅ Provenance and citation requirements are mandatory.
- ✅ Complexity remains intentionally limited to the MVP and avoids unnecessary enterprise complexity.
- ✅ Future security and HR integrations are explicitly deferred rather than being treated as v1 requirements.
- ✅ Testability is preserved through unit and retrieval-level validations.

## Project Structure

### Documentation (this feature)

```text
specs/001-knowlayer-platform/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── chat-api.md
├── tasks.md
└── checklists/
    └── requirements.md
```

### Source Code (repository root)

```text
app/
├── api/
│   ├── routes/
│   └── schemas/
├── core/
│   ├── config/
│   ├── settings/
│   └── logging/
├── domain/
│   ├── entities/
│   ├── value_objects/
│   ├── services/
│   └── ports/
├── infrastructure/
│   ├── llm/
│   ├── storage/
│   ├── vector/
│   └── document/
├── use_cases/
│   ├── chat/
│   └── ingestion/
├── utils/
├── main.py
└── __init__.py

streamlit_app/
├── app.py
├── pages/
├── components/
├── state/
├── services/
└── ui_helpers.py

tests/
├── contract/
├── integration/
├── unit/
├── fixtures/
└── data/

scripts/
├── ingest_documents.py
├── reset_vector_store.py
└── smoke_test.py

requirements.txt
.env.example
```

**Structure Decision**: A modular monolith is the default architecture. The project will be split into domain, use-case, infrastructure, and UI layers so the core logic can be changed or extended without rewriting the Streamlit interface or the LLM/storage adapters. The domain layer owns business rules and source contracts; infrastructure adapters handle Chroma, document loading, and model providers; the Streamlit layer stays thin and focused only on user interaction.

## Why this structure is appropriate for a new team

This structure is intentionally beginner-friendly:

- Domain layer: defines the business concepts such as document, chunk, retrieval result, and answer. It contains the rules that say how the system interprets a question and selects evidence.
- Use-case layer: orchestrates the workflow for a user action, such as ingesting a document or generating a response to a question.
- Infrastructure layer: adapts the app to external systems like Chroma DB, the local folder, and the LLM provider.
- API layer: exposes the backend contracts for internal callers or future UI integrations.
- Streamlit layer: is responsible only for displaying questions, handling chat state, and calling the backend logic.

This keeps responsibilities clean and reduces the chance that a new developer mixes UI concerns with storage, retrieval, or model logic.

For the chat experience, each session will maintain a rolling conversation memory of the most recent user/assistant turns so the bot can answer follow-up questions such as “What about parental leave?” or “How does that apply to me?” after an initial answer. This will be implemented through a lightweight LangChain ConversationWindowBufferMemory layer in the chat flow so the design remains simple while still supporting natural conversational continuity in v1.

## Complexity Tracking

> No constitution violations require justification for this MVP. The design stays within the acceptable complexity bounds by keeping the system to a single-document retrieval flow and a modular but not over-engineered structure.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
