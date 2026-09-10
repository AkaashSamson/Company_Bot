# KnowLayer Architecture

## Overview

KnowLayer is a modular monolith with clear boundaries between the API, use cases, domain services, infrastructure adapters, and Streamlit presentation layer. The current chat path is a document-grounded RAG flow with provider-independent LLM interfaces.

The core request path is:

```text
User
  -> Streamlit chat or FastAPI POST /api/chat
  -> QueryOrchestrator
  -> ConversationQueryResolver when the question depends on history
  -> RetrievalService
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
├── main.py
├── api/
│   ├── routes/chat.py                    # POST /api/chat
│   └── schemas/chat.py                   # Request/response models
├── core/settings.py                      # Environment configuration
├── domain/
│   ├── entities/document_models.py       # Document and chat data classes
│   └── services/session_memory_service.py# Bounded recent-message window
├── infrastructure/
│   ├── document/local_document_loader.py # Local input document enumeration
│   ├── vector/chroma_client.py           # Persistent Chroma adapter
│   └── llm/
│       ├── openrouter_client.py          # Primary LLM adapter
│       ├── groq_client.py                # Fallback LLM adapter
│       └── fallback_llm_provider.py      # Provider failover
└── use_cases/
    ├── chat/
    │   ├── query_orchestrator.py         # Chat workflow coordinator
    │   ├── conversation_query_resolver.py# Follow-up query resolution
    │   ├── retrieval_service.py          # Candidate/evidence selection
    │   └── provenance_service.py         # Citation assembly
    └── ingestion/document_processing.py  # Extraction and chunking
```

`streamlit_app/` is a separate presentation client. `scripts/ingest_documents.py` builds the local Chroma index, and `scripts/smoke_test.py` exercises the ingestion/retrieval/chat path.

## Request Flow

1. `ChatRequest` validates the question, session ID, and optional conversation history.
2. The route converts history messages to dictionaries and passes them to `QueryOrchestrator`.
3. `ConversationQueryResolver` asks `SessionMemoryService` for only the most recent six messages by default.
4. A standalone question bypasses rewriting. A likely dependent question is sent to the configured LLM with a small rewrite prompt and bounded history. The rewrite is used only as a retrieval query.
5. `RetrievalService` retrieves candidates for the full query and explicit query parts, then filters and selects evidence.
6. `QueryOrchestrator` joins only the selected evidence text into the document context.
7. The original user question, rather than the rewritten retrieval query, is included in the final answer-generation prompt.
8. `FallbackLLMProvider` tries OpenRouter first and Groq second if OpenRouter raises `LLMProviderError`.
9. `ProvenanceService` builds citations from the selected results. The API serializes those citations, and Streamlit renders exactly what the API returns.

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
RAG_DISTANCE_THRESHOLD=0.50
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
RAG_DISTANCE_THRESHOLD=0.50
RAG_DISTANCE_RELAXATION=0.05
RAG_MIN_DISTANCE_GAP=0.10
RAG_CANDIDATE_COUNT=5
RAG_MAX_EVIDENCE=3
RAG_MAX_CONTEXT_CHARS=12000
OPENROUTER_API_KEY=""
GROQ_API_KEY=""
LLM_MODEL=openrouter/anthropic/claude-3.5-sonnet
GROQ_MODEL=llama-3.1-8b-instant
```

The values above are the Python defaults from `app/core/settings.py`. In the checked-in `.env.example` and the local working configuration, `GROQ_MODEL` is overridden to `openai/gpt-oss-20b`, the confirmed available fallback model. The Python fallback default remains `llama-3.1-8b-instant`; it was not changed. Environment variables override the Python defaults.

## Testing

The current test layout is:

- `tests/unit/test_retrieval_selection.py`: Chroma distance preservation, absolute and relative relevance selection, lexical grounding rejection, duplicate removal, multi-part retrieval, evidence limits, and shared context/citation evidence.
- `tests/unit/test_conversation_query_resolver.py`: standalone questions, dependent follow-ups, bounded history, unrelated follow-ups, and multi-part follow-up rewriting.
- `tests/unit/test_llm_provider.py`: primary/fallback behavior and sanitized Groq provider errors.
- `tests/unit/test_session_memory.py`: bounded recent-message behavior.
- `tests/unit/test_document_ingestion.py`: document extraction and chunking.
- `tests/contract/test_chat_api_contract.py`: `/api/chat` response shape.
- `tests/integration/test_chat_e2e.py`: end-to-end chat requests and conversation-history requests.
- `scripts/smoke_test.py`: manual ingestion, retrieval, and chat checks.

Tests use mocks for provider-specific unit behavior. The integration tests exercise the application boundary and may require a populated local Chroma collection and configured providers.

## Extension Boundaries

The current architecture leaves these replaceable boundaries:

- Replace `ChromaVectorStore` without moving vector-store details into the use cases.
- Add document loaders without changing chat orchestration.
- Replace OpenRouter or Groq adapters while preserving `LLMProvider`.
- Replace Streamlit while preserving the FastAPI chat contract.

Authentication, authorization, enterprise HR integrations, hosted storage, and production operational controls are outside the current MVP.

## SQL Organization Flow

The persistence factory selects the configured relational adapter and supplies a SQLAlchemy Unit of Work. Repository ports expose User, Department, Project, Document, and UserProject operations without leaking SQLAlchemy into domain services. FastAPI dependencies construct use cases, routes translate domain failures into HTTP responses, and Streamlit pages use HTTP clients only.

Document registration stores a nullable project assignment. The document use case validates optional project scope, persists the active record, and can invoke the existing ingestion handler. Archiving changes lifecycle status rather than removing project history. During chat, authorization resolves the active project set before the retrieval adapter receives project filters; the LLM sees only selected evidence and citations are built from that same evidence.

Detailed sequence guides are maintained in [Documentation/Workflows/README.md](Documentation/Workflows/README.md).

Authentication is a replaceable domain boundary. A configured bootstrap operation creates one Admin account, the authentication service verifies PBKDF2 password representations and issues signed bearer tokens, and FastAPI resolves those tokens into trusted principals before protected operations. Streamlit stores only the returned session state and calls the authentication endpoints over HTTP.
