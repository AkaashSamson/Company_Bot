# Abhinav — RAG Model

## Role Overview
Owns the retrieval-augmented generation pipeline: turning a retrieved set of document chunks into a grounded, cited answer, and evolving the hybrid-synthesis logic that will combine policy knowledge with employee-specific data (US-1, US-2, US-3 in the spec).

## Core Responsibilities
- **Query orchestration** — `app/use_cases/chat/query_orchestrator.py`: the retrieve → generate → cite flow.
- **Answer generation** — replacing the current deterministic/heuristic answer logic with real LLM calls (OpenRouter / Groq), including prompt design and context assembly.
- **Provenance & citations** — `app/use_cases/chat/provenance_service.py`: ensuring every answer traces back to a source, section, and excerpt.
- **Conversation memory** — `app/use_cases/chat/session_memory.py` and `app/domain/services/session_memory_service.py`: bounded conversation windows, follow-up question handling (US2).
- **Hybrid question answering** — future work combining document retrieval with authoritative HR-system lookups into one synthesized, provenance-tagged answer.
- **RAG evaluation** — defining what "correct" and "grounded" mean for this system, and building repeatable tests for it.

## Current System Touchpoints
- `app/use_cases/chat/query_orchestrator.py`
- `app/use_cases/chat/retrieval_service.py`
- `app/use_cases/chat/provenance_service.py`
- `app/use_cases/chat/session_memory.py`
- `app/core/settings.py` (`OPENROUTER_API_KEY`, `GROQ_API_KEY`, `LLM_MODEL`, `GROQ_MODEL` — reserved, not yet wired up)

## Research Topics to Improve Efficiency

1. **LLM provider integration** — design the `LLMProvider` abstraction (OpenRouter/Groq now, others later) so `QueryOrchestrator` never hard-codes a vendor. Compare latency/cost/quality across candidate models for short, grounded HR-policy answers.
2. **Grounding and hallucination control** — prompt strategies that force the model to answer only from retrieved context, and to say "not found in policy" when evidence is weak. Look at faithfulness-focused prompting and answer-verification passes.
3. **Retrieval quality → answer quality** — hybrid retrieval (dense + BM25/keyword) and cross-encoder reranking of the top-k chunks before they reach the LLM, since current retrieval is pure vector similarity.
4. **RAG evaluation frameworks** — RAGAS or similar (faithfulness, answer relevancy, context precision/recall) so improvements can be measured instead of eyeballed, tied into `tests/integration`.
5. **Context window management** — chunk selection/compression strategy as top-k grows or documents multiply, so prompts stay small and cheap.
6. **Multi-hop / hybrid synthesis** — how to combine a policy-document answer with a real-time HR-system fact (e.g. leave policy + leave balance) into one coherent, dual-cited response without either source contaminating the other's authorization scope.
7. **Conversation-aware retrieval** — using session memory to rewrite follow-up questions ("what about for contractors?") into standalone retrieval queries.
8. **Caching** — memoizing answers/retrievals for repeated or near-duplicate questions to cut LLM cost and latency.

## Coordination Notes
- Retrieval-side changes (embedding model, chunking) belong to [Neha](Neha.md) — align on the `RetrievalService` interface so changes there don't break orchestration.
- Auth/permission gating of retrieved content belongs to [Roshan](Roshan.md) — hybrid answers must never merge unauthorized sources.
- LLM API keys, rate limits, and cost monitoring in production are [Akaash](Akaash.md)'s deployment concern.
