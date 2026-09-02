# Neha — Embeddings

## Role Overview
Owns the document-to-vector pipeline: chunking, embedding generation, and the vector store schema that everything else in the RAG pipeline retrieves from. The quality of every answer starts here.

## Core Responsibilities
- **Document processing** — `app/use_cases/ingestion/document_processing.py`: text extraction and chunking (currently paragraph/sentence-based via `python-docx`).
- **Embedding generation** — `app/infrastructure/vector/chroma_client.py`: current model is `sentence-transformers/all-MiniLM-L6-v2`, configured in `app/core/settings.py` (`EMBEDDING_MODEL`).
- **Vector store schema** — chunk metadata design (source, section, page) that powers citations downstream.
- **Ingestion pipeline** — `scripts/ingest_documents.py`: batch (re-)indexing into the local Chroma collection (`hr_policy_docs`).
- **Retrieval tuning** — top-k, similarity metric, and collection configuration in `app/use_cases/chat/retrieval_service.py`.

## Current System Touchpoints
- `app/use_cases/ingestion/document_processing.py`
- `app/infrastructure/vector/chroma_client.py`
- `app/domain/entities/document_models.py` (`DocumentChunk`, `VectorRecord`)
- `scripts/ingest_documents.py`
- `.chroma/` (persisted collection)

## Research Topics to Improve Efficiency

1. **Embedding model benchmarking** — compare `all-MiniLM-L6-v2` (fast, small) against larger/domain-tuned models (e.g. `bge-base`, `e5-base`, OpenAI/Cohere embeddings) on retrieval accuracy vs latency/storage cost for HR-policy-style text.
2. **Chunking strategy** — fixed paragraph/sentence chunking vs semantic chunking (splitting on topic shifts) or sliding-window overlap; measure impact on retrieval precision, especially for policy documents with nested sections.
3. **Retrieval evaluation metrics** — establishing recall@k / MRR against a labeled set of "known good chunk for this question" pairs, so chunking/embedding changes can be measured objectively rather than by spot-checking.
4. **Hybrid retrieval** — combining dense vector search with sparse/keyword search (BM25) for exact-term queries (policy names, numeric thresholds like "20 days") where embeddings alone under-perform.
5. **Domain fine-tuning** — whether fine-tuning or few-shot-adapting an embedding model on internal HR/technical vocabulary meaningfully beats an off-the-shelf model, and whether that's worth the maintenance cost.
6. **Metadata-aware retrieval** — using chunk metadata (section, document type, department) as retrieval filters, not just citation display, once multiple documents and document types exist beyond the single handbook.
7. **Embedding versioning & re-indexing strategy** — how to swap embedding models or re-chunk without downtime, and how to detect "drift" between what's indexed and the current source documents.
8. **Multi-document / multi-format scaling** — current MVP handles one DOCX handbook; research chunking/embedding approaches for PDFs, technical docs, and larger document sets referenced in the Phase 3 roadmap (cross-functional search).

## Coordination Notes
- The `RetrievalService` interface is the contract with [Abhinav](Abhinav.md) — changes to top-k, scoring, or reranking should be discussed jointly since they affect answer quality directly.
- Moving off local Chroma to a managed vector DB is [Akaash](Akaash.md)'s infra call, but the schema/metadata design should be decided here first so migration is a lift-and-shift, not a redesign.
- Document-level authorization metadata (which [Roshan](Roshan.md) needs for permission filtering) should be captured in chunk metadata at ingestion time, not bolted on later.
