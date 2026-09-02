# Research: KnowLayer MVP 1

## Decision

- Document storage: local folder
- Vector database: Chroma DB
- Primary LLM provider: OpenRouter
- Supporting provider: Groq
- Conversation memory: LangChain ConversationWindowBufferMemory with a short rolling window for session continuity
- Scope: single approved HR policy document, Streamlit-based Q&A chatbot with follow-up support
- User model: all users are trusted internal users for MVP 1
- Forbidden in v1: HR-system integration, employee-specific data retrieval, auth/authorization enforcement, and multi-source enterprise synthesis

## Rationale

This MVP is intentionally narrow and high-value: it delivers a grounded HR policy chatbot using one internal document. Using a local folder keeps setup low-friction, and Chroma DB matches the requirement for lightweight vector retrieval without introducing a heavier database stack. OpenRouter gives a good abstraction layer for LLM access, while Groq can serve as a supporting/fallback provider if needed. This keeps the implementation simple while preserving the architecture so future providers and enterprise connectors can be added later.

## Alternatives considered

### Local folder vs relational storage
- Local folder was selected because the project has only one source document and the MVP is not meant to require enterprise-grade document management.
- Relational storage was rejected as unnecessary complexity for v1.

### Chroma DB vs Pinecone / FAISS / pgvector
- Chroma DB was selected because it is lightweight, developer-friendly, and works well for a local or internal prototype.
- Pinecone was considered but is less aligned with a simple local-first MVP.
- FAISS is viable for embeddings but requires more direct operational management and is usually less feature-rich for app-level metadata.
- pgvector is a strong option for later enterprise work, but it adds more system complexity than this v1 requires.

### OpenRouter vs direct provider SDKs
- OpenRouter was selected to provide a clean abstraction layer and flexible provider swapping.
- Direct provider SDKs were evaluated but would make provider changes more coupled to the app code.

### Groq vs local fallback model
- Groq was selected as the supporting provider because it is fast and convenient for experimentation.
- Local fallback models were considered but not chosen as the main provider path due to setup complexity and hardware variability.

## Architecture implications

The design decision to keep a local document folder and Chroma DB does not lock the system into a single technology forever. The infrastructure layer will abstract the document loader and vector store behind interfaces so future replacement with cloud object storage or a different vector database is possible without affecting the domain layer.

For conversational continuity, a LangChain ConversationWindowBufferMemory pattern is a good fit because it provides a short, bounded window of recent messages without requiring a full persistence model in v1. This supports follow-up questions such as “What about parental leave?” while keeping the MVP lightweight and simple.

The architecture will continue to keep the LLM provider behind a provider abstraction so OpenRouter and Groq can be swapped or combined without changing the use-case logic.

## Deferred decisions for future phases

- Identity and authorization framework
- HR payroll/leave/benefits integration
- Employee-specific record access and permissions
- Multi-document enterprise search and synthesis
- Audit/security controls for production deployment
