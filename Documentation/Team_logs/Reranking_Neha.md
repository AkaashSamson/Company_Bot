# Implementation of BGE Cross-Encoder Reranking

**Author:** Neha
**Objective:** Enhance the RAG pipeline's retrieval accuracy by implementing a BGE cross-encoder reranker. The reranker re-evaluates and sorts candidates returned by Chroma DB based on deep semantic pairs before passing the final top-K chunks to the LLM.

## Architectural Approach
The implementation strictly adheres to the existing **Modular Monolith + Ports and Adapters** architecture. The core retrieval logic is decoupled from the specific reranking model using an interface.

### 1. Domain Layer (Ports)
- **`app/domain/ports/reranker.py`**: Created the `RerankerPort` protocol. This ensures that the application use-cases remain agnostic to the specific cross-encoder library or external API being used.

### 2. Infrastructure Layer (Adapters)
- **`app/infrastructure/vector/bge_reranker.py`**: Implemented the `BgeReranker` adapter, which wraps the HuggingFace `sentence-transformers.CrossEncoder`.
  - **Mechanics**: It takes pairs of `[query, text]` and calculates logits. It then injects `_rerank_score`, `_new_rank`, and `_original_rank` back into the candidate metadata dictionaries.
  - **Resilience**: Inference is wrapped in a broad try-catch block. If the model fails (e.g. out of memory, tokenization error), it degrades gracefully, bypassing score injections and defaulting to the original Chroma semantic distance order.

### 3. Application Layer (Use Cases)
- **`app/use_cases/chat/retrieval_service.py`**: 
  - **Dependency Injection**: The `RetrievalService` constructor was updated to accept the optional `RerankerPort` adapter.
  - **Pipeline Placement**: Reranking occurs immediately after the raw Chroma vector search retrieves the `RAG_CANDIDATE_COUNT` pool of chunks.
  - **Selection Logic Updates**: Modified the `select_relevant` function. After redundancy filtering, it now prioritizes the `_new_rank` injected by the reranker (if available) over Chroma's standard `distance`. Standard distance rejection thresholds are still enforced to maintain fallback safety.

### 4. Configuration
- **`app/core/settings.py`**:
  - Increased `RAG_CANDIDATE_COUNT` to 13 (to provide a wide pool for the reranker).
  - Introduced `RAG_FINAL_K` set to 4 (the final amount sent to the LLM context).
  - Introduced `RAG_RERANKER_MODEL = "BAAI/bge-reranker-base"`.

## Testing and Evaluation
- **Unit Tests (`tests/unit/test_reranker.py`)**: Added robust mocking of the `CrossEncoder` to test edge cases: handling fewer than K candidates, graceful degradation during inference crashes, missing metadata, and empty candidate lists.
- **Evaluation Scripts (`scripts/evaluate_reranker_terminal.py`)**: Developed diagnostic scripts that expose the exact state of candidates across 3 stages:
  1. Chroma raw output
  2. BGE Cross-Encoder re-ordered output
  3. Final chunk selection post-filtering
- **Key finding during evaluation**: A perceived ranking issue with a "Grace Period" query was diagnosed and debunked. The reranker accurately identified that a seemingly generic "Scheduled Start Time" chunk actually contained the full, detailed Grace Period policy deeper within its text. Truncated terminal output in early evaluation tests hid this fact, but the reranker was performing perfectly on the raw data.
