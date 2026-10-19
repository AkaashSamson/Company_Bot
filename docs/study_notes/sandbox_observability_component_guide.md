# 📘 Sandbox & Observability: Complete Component & Architecture Guide

This comprehensive reference document covers **every single component** within the Sandbox & Observability ecosystem of the Company-Bot RAG system—from core evaluation engines to auxiliary diagnostic tools, UI subsystems, background scripts, and data banks.

---

## 📑 Complete Component Index

| # | Component / File | Category | Classification |
|---|---|---|---|
| **1** | [`run_sandbox.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/run_sandbox.py) | Launcher | Core Entrypoint |
| **2** | [`run_sandbox.ps1`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/run_sandbox.ps1) | Launcher | PowerShell Daemon |
| **3** | [`sandbox/sandbox_app.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/sandbox/sandbox_app.py) | UI Master Root | Central Application Router |
| **4** | [`sandbox/components/ragas_studio.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/sandbox/components/ragas_studio.py) (Mode 1: End-User Chat) | Core Evaluation | Conversational Auditor |
| **5** | [`sandbox/components/ragas_studio.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/sandbox/components/ragas_studio.py) (Mode 2: 145 Master Bank) | Core Evaluation | Automated Regression Matrix |
| **6** | [`sandbox/components/ragas_studio.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/sandbox/components/ragas_studio.py) (Mode 3: Custom Auditor) | Core Evaluation | Deep Needle-in-Haystack |
| **7** | [`sandbox/components/retrieval.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/sandbox/components/retrieval.py) | Core Diagnostics | Stage 1 Vector Search Inspector |
| **8** | [`sandbox/components/reranking.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/sandbox/components/reranking.py) | Core Diagnostics | Stage 2 Cross-Encoder Inspector |
| **9** | [`app/infrastructure/document/chunking_strategies.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/document/chunking_strategies.py) | Core Ingestion | 6 Chunking Algorithms |
| **10** | [`sandbox/components/ragas_eval.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/sandbox/components/ragas_eval.py) | Core Evaluation | Metric Pipeline Engine |
| **11** | [`app/infrastructure/eval/local_nli_evaluator.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/eval/local_nli_evaluator.py) | Core Evaluation | Zero-Cost Local NLI Engine |
| **12** | [`sandbox/components/generation.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/sandbox/components/generation.py) | Auxiliary | LLM Generation Harness |
| **13** | [`sandbox/components/grounding.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/sandbox/components/grounding.py) | Auxiliary | Evidence Grounding Inspector |
| **14** | [`sandbox/components/policy_eval.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/sandbox/components/policy_eval.py) | Auxiliary | Policy Constraint & Refusal Auditor |
| **15** | [`sandbox/ui/home_dashboard.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/sandbox/ui/home_dashboard.py) | UI Subsystem | Knowledge Base Health Dashboard |
| **16** | [`sandbox/ui/test_studio.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/sandbox/ui/test_studio.py) | UI Subsystem | Visual Test Suite Editor |
| **17** | [`sandbox/engine/orchestrator.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/sandbox/engine/orchestrator.py) | Execution Engine | Batch Execution Orchestrator |
| **18** | [`sandbox/engine/registry.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/sandbox/engine/registry.py) | Execution Engine | Metric & Module Registry |
| **19** | [`sandbox/engine/schema.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/sandbox/engine/schema.py) | Execution Engine | Pydantic Telemetry Schemas |
| **20** | [`sandbox/engine/persistence.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/sandbox/engine/persistence.py) | Persistence | SQLite Run Trace Database |
| **21** | [`sandbox/reports/unified_report.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/sandbox/reports/unified_report.py) | Reporting | Executive Markdown/HTML Synthesizer |
| **22** | [`scripts/evaluate_chunking_quality.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/scripts/evaluate_chunking_quality.py) | CLI Script | Chunk Quality Index Auditor |
| **23** | [`scripts/evaluate_response_nli_geval.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/scripts/evaluate_response_nli_geval.py) | CLI Script | Batch NLI & G-Eval CLI Runner |
| **24** | [`scripts/reingest_test_data.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/scripts/reingest_test_data.py) | CLI Script | ChromaDB Fast Re-Indexer |
| **25** | [`scripts/test_chunk_retrieval.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/scripts/test_chunk_retrieval.py) | CLI Script | Headless Vector Retrieval Tester |
| **26** | [`scripts/validate_rag_pipeline.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/scripts/validate_rag_pipeline.py) | CLI Script | End-to-End Pipeline Healthcheck |
| **27** | [`scripts/seed_faq_cache.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/scripts/seed_faq_cache.py) | Auxiliary Script | Redis FAQ Semantic Cache Warmer |
| **28** | [`scripts/clear_caches.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/scripts/clear_caches.py) | Auxiliary Script | Redis & Memory Cache Flusher |
| **29** | [`scripts/test_langfuse_end_to_end.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/scripts/test_langfuse_end_to_end.py) | Auxiliary Script | Telemetry & Tracing Verifier |
| **30** | [`scripts/test_rbac_cache_manual.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/scripts/test_rbac_cache_manual.py) | Auxiliary Script | RBAC Security & Tenant Isolation Tester |
| **31** | [`test_data/knowlayer_145_test_bank.json`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/test_data/knowlayer_145_test_bank.json) | Data Bank | 145 Master Benchmark Suite |
| **32** | [`sandbox/MANIFEST.md`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/sandbox/MANIFEST.md) | Documentation | Architectural Manifest & Topology |

---

## I. Launchers & Application Entry Points

---

### 1. `run_sandbox.py` (Python Environment Launcher)
* **What It Does**: Sets up Python path variables, verifies runtime virtual environments, detects available ports, and invokes Streamlit via `subprocess.run`.
* **Why We Have / Use It**: Provides a cross-platform, one-command launcher that works across Windows, macOS, and Linux without shell-specific quirks.
* **When to Use It**: When starting the sandbox from any terminal, VS Code task, or standard Python environment.
* **How It Works**:
  1. Resolves repository root directory and appends it to `sys.path`.
  2. Sets environment variables `STREAMLIT_SERVER_PORT=8502` and `STREAMLIT_BROWSER_GATHER_USAGE_STATS=false`.
  3. Executes `streamlit run sandbox/sandbox_app.py`.
* **How to Use It for Our App**:
  ```bash
  python run_sandbox.py
  ```

---

### 2. `run_sandbox.ps1` (PowerShell Daemon Launcher)
* **What It Does**: Native Windows PowerShell script that auto-detects `.venv\Scripts\Activate.ps1`, checks port `8502`, kills stale processes, and starts the sandbox.
* **Why We Have / Use It**: Windows users often encounter PowerShell execution policy or path issues when starting Streamlit; this script automates virtual environment activation.
* **When to Use It**: When developing locally on Windows PowerShell.
* **How It Works**:
  1. Checks if `.venv` exists; activates it in the current session.
  2. Checks `netstat -ano` for any zombie process bound to port 8502.
  3. Launches `streamlit run sandbox/sandbox_app.py --server.port 8502`.
* **How to Use It for Our App**:
  ```powershell
  ./run_sandbox.ps1
  ```

---

### 3. `sandbox/sandbox_app.py` (Central Streamlit Application & Routing Engine)
* **What It Does**: The single-page application router that powers the entire web interface. Manages the sidebar navigation, loads global CSS styling, connects to the ChromaDB vector database, and mounts each analysis tab.
* **Why We Have / Use It**: Gives teams a unified visual cockpit where retrieval engineers, prompt engineers, and QA analysts can collaborate without juggling disjointed command-line utilities.
* **When to Use It**: Throughout the development lifecycle—whenever inspecting chunks, testing queries, or optimizing hyperparameters.
* **How It Works**:
  1. Configures wide-mode Streamlit layout (`st.set_page_config(layout="wide")`).
  2. Injects custom CSS styling (dark glassmorphism, responsive metrics cards).
  3. Initializes `st.session_state` with model parameters (e.g. `openai/gpt-4o-mini`, temperature `0.0`, top-k `5`).
  4. Dispatches the selected sidebar navigation route to the corresponding component module.
* **How to Use It for Our App**:
  * Open browser at `http://localhost:8502`.
  * Use the left sidebar to jump between **Ragas Evaluation Studio**, **ChromaDB Chunks Explorer**, **Chunking Strategy Optimizer**, and **Test Studio**.

---

## II. Core Evaluation & Optimization Workspaces

---

### 4. `sandbox/components/ragas_studio.py` — Mode 1: 💬 Ask as Company End User
* **What It Does**: Simulates a live end-user asking company policy questions. Retrieves chunks from ChromaDB, applies cross-encoder reranking, invokes the LLM, and calculates real-time Faithfulness and Relevancy scores.
* **Why We Have / Use It**: Allows testing realistic employee interactions (including Hinglish, Kanglish, typos, and adversarial prompts) with immediate visibility into retrieved context and prompt tokens.
* **When to Use It**: When testing prompt adjustments, validating language consistency rules, or testing new policy queries before publishing test cases.
* **How It Works**:
  1. Accepts user query and target department/role metadata filters.
  2. Executes two-stage retrieval: dense vector search ($k_1=10$) followed by cross-encoder reranking ($k_2=5$).
  3. Injects the retrieved chunks into the `prompts.yaml` system instructions.
  4. Generates an answer via OpenRouter/OpenAI.
  5. Evaluates the answer against retrieved context using local NLI models and returns token counts and latencies.
* **How to Use It for Our App**:
  1. In the sidebar, select **1. 🔬 Ragas Evaluation Studio**.
  2. Switch the radio tab to **💬 Ask as Company End User**.
  3. Type a query (e.g., `"Can I carry forward leaves to next year?"` or `"casual leave carry forward aagatta?"`).
  4. Click **Run Query & Evaluate Live**.
  5. Inspect the generated response, retrieved chunks, and NLI scores.

---

### 5. `sandbox/components/ragas_studio.py` — Mode 2: 🧪 Benchmark Suites & 145 Master Question Bank
* **What It Does**: Runs batch evaluations across categorized test suites (e.g. Leave Policy, Travel Policy, Code of Conduct, Negative Scenarios) or the full 145-question bank.
* **Why We Have / Use It**: Manual spot-checking misses subtle regressions. Mode 2 ensures that changing a prompt or chunking setting doesn't break other policy answers.
* **When to Use It**: Prior to merging PRs, deploying pipeline updates, or releasing new document sets.
* **How It Works**:
  1. Loads `test_data/knowlayer_145_test_bank.json`.
  2. Filters tests by category (or selects all 145).
  3. Iterates through each test case: retrieves chunks, generates answers, and computes Faithfulness, Factual Correctness, and Answer Relevancy.
  4. Renders interactive summary KPI cards and a downloadable data table.
* **How to Use It for Our App**:
  1. In **Ragas Evaluation Studio**, choose **Mode 2: 🧪 Benchmark Suites**.
  2. Select test bank: `KnowLayer 145 Master Test Bank`.
  3. Choose category (e.g. `Negative / Out-of-Scope (Adversarial)` or `All 145 Cases`).
  4. Click **Start Automated Benchmark Run**.
  5. Export results as `.csv` or `.json` for documentation.

---

### 6. `sandbox/components/ragas_studio.py` — Mode 3: 🔬 Interactive Custom Query Auditor
* **What It Does**: Deep diagnostic tool for a single query. Takes a user question, expected ground-truth answer, and expected source document, then executes granular stage-by-stage auditing.
* **Why We Have / Use It**: When a benchmark test fails, Mode 3 isolates exactly where the failure occurred: Stage 1 retrieval, Stage 2 reranking, context truncation, or LLM hallucination.
* **When to Use It**: Whenever root-causing a specific test failure or debugging policy hallucinations.
* **How It Works**:
  1. Runs vector search and displays raw cosine/L2 distances for all candidate chunks.
  2. Runs cross-encoder and shows reranking score deltas ($\Delta$).
  3. Compares the generated answer to the ground truth using semantic cosine similarity and lexical overlap.
  4. Displays side-by-side prompt tokens and context window usage.
* **How to Use It for Our App**:
  1. In **Ragas Evaluation Studio**, choose **Mode 3: 🔬 Interactive Custom Query Auditor**.
  2. Paste question, expected text, and expected source file.
  3. Click **Run Deep Audit**.
  4. Review Stage 1 vs. Stage 2 rankings to verify if the correct chunk made the top-k cut.

---

### 7. `sandbox/components/retrieval.py` (Stage 1 Vector Search Inspector)
* **What It Does**: Connects to the local ChromaDB database (`chroma_db/`), exposes raw collection statistics, and displays chunk text, token lengths, and metadata.
* **Why We Have / Use It**: Ingestion bugs (e.g. truncated headers, bad splits, empty chunks) corrupt RAG before retrieval even starts. This tool exposes the raw storage layer.
* **When to Use It**: After ingesting new policy PDFs/DOCX files or when inspecting chunk boundaries.
* **How It Works**:
  1. Queries the ChromaDB client collection `knowlayer_policies`.
  2. Pulls all embeddings and metadata dictionaries (`source`, `chunk_index`, `department`).
  3. Computes token length distributions and highlights potential stub chunks (<50 tokens).
* **How to Use It for Our App**:
  1. In the sidebar, select **2. 🔍 ChromaDB Chunks Explorer**.
  2. Filter by document name (e.g. `Leave_Policy.pdf`).
  3. Search for keywords to verify how text was segmented.

---

### 8. `sandbox/components/reranking.py` (Stage 2 Cross-Encoder Inspector)
* **What It Does**: Evaluates cross-encoder rerankers (such as `cross-encoder/ms-marco-MiniLM-L-6-v2`) against bi-encoder vector retrieval.
* **Why We Have / Use It**: Dense vector embeddings often prioritize broad topical similarity over precise factual matching. Cross-encoders examine query and document tokens jointly to eliminate false-positive chunks.
* **When to Use It**: When fine-tuning top-k retrieval parameters or diagnosing why irrelevant policy sections outranked relevant ones.
* **How It Works**:
  1. Takes the top-$N$ chunks from vector search (e.g. $N=15$).
  2. Scores each `(query, chunk_text)` pair using the cross-encoder transformer.
  3. Re-sorts chunks in descending order of cross-encoder confidence and applies the cutoff threshold.
* **How to Use It for Our App**:
  * Incorporated automatically in **Mode 1** and **Mode 3** of Ragas Studio.
  * In the inspector tabs, toggle **Enable Stage 2 Reranking** to view before-and-after ranking shifts.

---

### 9. `app/infrastructure/document/chunking_strategies.py` (6 Chunking Algorithms)
* **What It Does**: Implements 6 distinct chunking algorithms to partition unstructured enterprise policy documents into semantically coherent vector chunks:
  1. **Hierarchical Header-Aware Chunking**: Splits text on Markdown/Document headings (`#`, `##`, `###`), preserving organizational hierarchy.
  2. **Semantic Similarity Boundary Chunking**: Computes sentence embeddings and places split boundaries where cosine similarity drops below a threshold.
  3. **Fixed-Size Sliding Window Chunking**: Token-based chunking with configurable overlap (e.g. 512 tokens with 64 token overlap).
  4. **Paragraph Boundary Chunking**: Natural paragraph splits based on double line-breaks (`\n\n`).
  5. **Agentic Proposition-Based Chunking**: Deconstructs complex sentences into atomic factual propositions before bundling.
  6. **Late Chunking Token Budget**: Chunks text at the transformer token level to maximize token budget efficiency.
* **Why We Have / Use It**: Chunking is the highest-leverage hyperparameter in RAG. Sub-optimal chunking either chops facts in half (loss of context) or creates massive chunks (context dilution).
* **When to Use It**: When onboarding new document types (tables, handbooks, structured legal policies) to determine the best splitting strategy.
* **How It Works**:
  1. Receives document text and token budget limits.
  2. Applies the selected segmentation algorithm.
  3. Formats chunk headers with breadcrumb metadata (e.g. `[Document > Section > Sub-section]`).
* **How to Use It for Our App**:
  1. In the sidebar, select **3. 🧩 Chunking Strategy Optimizer**.
  2. Use the **📄 Select Document to Test Chunking Strategies** dropdown to pick a policy file.
  3. Click **Benchmark All 6 Strategies** to compare chunk count, average tokens, Chunk Quality Index (CQI), and Needle Retention.

---

### 10. `sandbox/components/ragas_eval.py` (Metric Pipeline Engine)
* **What It Does**: Orchestrates the mathematical calculation of four primary RAG evaluation metrics:
  * **Faithfulness**: Proportion of claims in the generated response that are directly entailed by the retrieved context.
  * **Factual Correctness**: Alignment between the response and the verified ground-truth answer.
  * **Answer Relevancy**: Semantic closeness of the answer to the user's specific inquiry.
  * **Context Precision / Retention**: Whether the necessary ground-truth facts appeared in the retrieved chunks.
* **Why We Have / Use It**: Replaces subjective human opinions with reproducible mathematical metrics.
* **When to Use It**: Invoked automatically during Mode 1, Mode 2, and Mode 3 runs.
* **How It Works**:
  1. Breaks down generated responses into atomic claim statements.
  2. Pairs each claim against context chunks and evaluates entailment via the NLI engine.
  3. Produces normalized scores from `0.0` to `1.0`.
* **How to Use It for Our App**:
  * Set pass/fail score thresholds in the UI (e.g. Faithfulness $\ge 0.85$, Factual Correctness $\ge 0.80$).

---

### 11. `app/infrastructure/eval/local_nli_evaluator.py` (Zero-Cost Local NLI Engine)
* **What It Does**: Performs Natural Language Inference (Entailment, Neutral, Contradiction) locally using HuggingFace transformer models (`cross-encoder/nli-deberta-v3-small` or `nli-distilroberta-base`) without external API calls.
* **Why We Have / Use It**: Evaluating hundreds of benchmark questions with cloud LLMs (like GPT-4) incurs high API costs and latency. Local NLI evaluates claims at hundreds of sentences per second completely free and offline.
* **When to Use It**: Powers the automated Faithfulness and Hallucination detection in the sandbox and CI/CD pipelines.
* **How It Works**:
  1. Passes premise (retrieved chunk) and hypothesis (generated claim) through the local DeBERTa/DistilRoBERTa model.
  2. Returns softmax probabilities: `[P(Contradiction), P(Neutral), P(Entailment)]`.
  3. Scores claim as faithful if $P(\text{Entailment}) > 0.5$.
* **How to Use It for Our App**:
  * Automatically activated when running evaluation runs. If PyTorch with CUDA is available, it uses the GPU; otherwise, it falls back cleanly to optimized CPU inference.

---

## III. Auxiliary & Diagnostic Components (Non-Essential / Specialized)

---

### 12. `sandbox/components/generation.py` (LLM Generation Harness)
* **What It Does**: Manages LLM calls across multiple models (`gpt-4o`, `gpt-4o-mini`, `claude-3-haiku`, `mistral-small`), handles API retries, applies system prompts, and tracks token consumption.
* **Why We Have / Use It**: Centralizes generation logic to prevent fragmented API calling code across the different workbench tabs.
* **When to Use It**: Used internally by all evaluation modes and interactive query tabs.
* **How It Works**:
  1. Reads `OPENROUTER_API_KEY` or `OPENAI_API_KEY`.
  2. Builds chat completion payloads with specified temperature and max token limits.
  3. Extracts response text, completion tokens, prompt tokens, and total latency.
* **How to Use It for Our App**:
  * Change model and temperature in the sidebar; `generation.py` dispatches calls accordingly.

---

### 13. `sandbox/components/grounding.py` (Evidence Grounding Inspector)
* **What It Does**: Computes lexical containment, Jaccard n-gram overlap, and exact phrase citations between the retrieved chunks and the generated answer.
* **Why We Have / Use It**: Provides a fast, deterministic sanity check on whether the model actually quoted policy clauses or improvised wording.
* **When to Use It**: When inspecting query outputs in Mode 3 to highlight ungrounded phrases.
* **How It Works**:
  1. Tokenizes generated response and context into unigrams and bigrams.
  2. Highlights shared phrases in green and ungrounded claims in red.
  3. Calculates a Grounding Lexical Score between 0% and 100%.
* **How to Use It for Our App**:
  * Viewable in Mode 3 under the **"Grounding & Citation Analysis"** expandable drawer.

---

### 14. `sandbox/components/policy_eval.py` (Policy Constraint & Refusal Auditor)
* **What It Does**: Checks compliance with boundary constraints—such as confirming that out-of-scope, salary-confidential, or adversarial prompt injections are properly refused.
* **Why We Have / Use It**: Prevents the bot from fabricating answers or disclosing sensitive corporate data when users ask questions beyond the documents' scope.
* **When to Use It**: When evaluating the **Negative / Out-of-Scope** test category.
* **How It Works**:
  1. Inspects bot responses for polite refusal markers (e.g. `"The policy documents provided do not contain information related to your question"`).
  2. Marks the test `PASS` if the bot safely declines to answer, and `FAIL` if it hallucinates an answer.
* **How to Use It for Our App**:
  * Triggered automatically in Mode 2 when selecting the `Negative / Out-of-Scope` benchmark category.

---

## IV. UI Subsystems

---

### 15. `sandbox/ui/home_dashboard.py` (Knowledge Base Health Dashboard)
* **What It Does**: Renders the landing overview page showing total documents indexed, total vector chunks, database file sizes, and quick-action health status indicators.
* **Why We Have / Use It**: Gives teams immediate visual confirmation that the vector database is populated and ready before running queries.
* **When to Use It**: First tab viewed upon launching the sandbox.
* **How It Works**:
  1. Scans `test_data/` and `chroma_db/` on disk.
  2. Aggregates chunk counts and file sizes.
  3. Renders visual KPI metric cards.
* **How to Use It for Our App**:
  * Navigate to **Home** to verify system status or trigger a quick re-index.

---

### 16. `sandbox/ui/test_studio.py` (Visual Test Suite Editor)
* **What It Does**: Provides a web-based GUI to browse, search, filter, edit, and create test cases in `test_data/knowlayer_145_test_bank.json`.
* **Why We Have / Use It**: Eliminates the need to manually edit large JSON files in code editors, preventing formatting and JSON syntax errors.
* **When to Use It**: When HR policy updates introduce new rules or when adding new benchmark questions.
* **How It Works**:
  1. Loads `knowlayer_145_test_bank.json`.
  2. Displays an editable data grid with columns: `id`, `category`, `question`, `expected_answer`, `expected_doc`.
  3. Writes validated changes back to disk atomically.
* **How to Use It for Our App**:
  * Open **Test Studio** from the sidebar, edit a test case, and click **Save Changes to Disk**.

---

## V. Execution & Persistence Engine

---

### 17. `sandbox/engine/orchestrator.py` (Batch Execution Orchestrator)
* **What It Does**: Manages asynchronous multi-threaded execution of batch evaluation runs with progress tracking and rate-limiting.
* **Why We Have / Use It**: Running 145 evaluations sequentially takes too long; the orchestrator parallelizes evaluations while respecting API rate limits.
* **When to Use It**: Powers Mode 2 batch benchmarks.
* **How It Works**:
  1. Spawns a worker pool using Python's `concurrent.futures`.
  2. Distributes questions across workers with rate-limiting backoffs.
  3. Updates Streamlit progress bars in real time via callbacks.
* **How to Use It for Our App**:
  * Adjust concurrency slider (e.g. 1 to 5 threads) in the Mode 2 settings panel.

---

### 18. `sandbox/engine/registry.py` (Metric & Module Registry)
* **What It Does**: Plugin architecture registry that maps string identifiers to evaluator classes and chunking strategies.
* **Why We Have / Use It**: Decouples component implementation from the UI, allowing new metrics or chunking algorithms to be plugged in without modifying core UI code.
* **When to Use It**: When adding custom metrics or experimental chunkers.
* **How It Works**:
  * Uses Python decorators (`@register_evaluator("name")`) to register functions in a central dictionary.
* **How to Use It for Our App**:
  * Query `registry.get_evaluator("faithfulness")` or `registry.get_chunker("semantic")`.

---

### 19. `sandbox/engine/schema.py` (Pydantic Telemetry Schemas)
* **What It Does**: Defines strongly-typed Pydantic models for benchmark test cases, retrieval results, evaluation scores, and trace logs.
* **Why We Have / Use It**: Enforces strict data validation across components, catching schema mismatches before they break evaluations.
* **When to Use It**: Throughout the sandbox codebase for type annotations and JSON serialization.
* **How It Works**:
  * Defines classes like `TestCase`, `RetrievalResult`, `EvaluationScore`, and `RunTrace`.
* **How to Use It for Our App**:
  * Import models directly: `from sandbox.engine.schema import TestCase, RunTrace`.

---

### 20. `sandbox/engine/persistence.py` (SQLite Run Trace Database)
* **What It Does**: Persists test run history and evaluation scores into a local SQLite database (`sandbox/data/runs.db`).
* **Why We Have / Use It**: Keeps a durable record of historical evaluation scores across team sessions, enabling trend tracking over time.
* **When to Use It**: Automatically stores results after every evaluation run.
* **How It Works**:
  1. Creates SQLite tables for `runs` and `test_results` if they do not exist.
  2. Writes benchmark runs with timestamps, hyperparameters, and aggregated scores.
* **How to Use It for Our App**:
  * Historical runs can be reviewed and compared directly from the UI history tab.

---

### 21. `sandbox/reports/unified_report.py` (Executive Markdown/HTML Synthesizer)
* **What It Does**: Aggregates test run results into clean, executive-ready Markdown or HTML summary reports.
* **Why We Have / Use It**: Management and compliance teams need clear summary reports rather than raw JSON traces.
* **When to Use It**: After completing a benchmark run to share results with stakeholders.
* **How It Works**:
  1. Computes pass rates, category averages, and latency percentiles (P50, P95).
  2. Formats markdown tables and failure highlights.
* **How to Use It for Our App**:
  * Click **"Generate Executive Report"** in Mode 2 to download the formatted report.

---

## VI. Command-Line Scripts & Diagnostic Tools

---

### 22. `scripts/evaluate_chunking_quality.py` (Chunk Quality Index Auditor)
* **What It Does**: Headless CLI script that scans all chunks in ChromaDB and computes the Chunk Quality Index (CQI), stub counts (<50 tokens), and overflow counts (>500 tokens).
* **Why We Have / Use It**: Enables automated CI/CD checks to verify that newly ingested documents don't produce degraded chunks.
* **When to Use It**: In CI/CD pipelines or after bulk ingestion.
* **How It Works**:
  * Connects to ChromaDB, iterates through all chunk tokens, calculates the penalty formula, and outputs a formatted table.
* **How to Use It for Our App**:
  ```bash
  python scripts/evaluate_chunking_quality.py
  ```

---

### 23. `scripts/evaluate_response_nli_geval.py` (Batch NLI & G-Eval CLI Runner)
* **What It Does**: Runs offline batch evaluation of responses against ground truth using local NLI and G-Eval without starting the Streamlit server.
* **Why We Have / Use It**: Ideal for scheduled automated regression testing.
* **When to Use It**: In nightly automated test workflows.
* **How It Works**:
  * Reads test bank, invokes pipeline, runs local NLI checks, and writes results to a JSON artifact.
* **How to Use It for Our App**:
  ```bash
  python scripts/evaluate_response_nli_geval.py --test-file test_data/knowlayer_145_test_bank.json
  ```

---

### 24. `scripts/reingest_test_data.py` (ChromaDB Fast Re-Indexer)
* **What It Does**: Clears the current ChromaDB vector collection and re-ingests all policy documents from `test_data/`.
* **Why We Have / Use It**: Avoids manual document-by-document ingestion when updating policy sets.
* **When to Use It**: Whenever files in `test_data/` are updated, added, or removed.
* **How It Works**:
  1. Deletes existing ChromaDB collection `knowlayer_policies`.
  2. Reads PDFs and DOCX files from `test_data/`.
  3. Generates embeddings using `BAAI/bge-small-en-v1.5` and stores them in ChromaDB.
* **How to Use It for Our App**:
  ```bash
  python scripts/reingest_test_data.py
  ```

---

### 25. `scripts/test_chunk_retrieval.py` (Headless Vector Retrieval Tester)
* **What It Does**: CLI diagnostic tool to test semantic search queries directly against ChromaDB.
* **Why We Have / Use It**: Allows testing retrieval accuracy without launching the browser UI.
* **When to Use It**: For quick terminal-based retrieval debugging.
* **How It Works**:
  * Takes a query string argument, searches ChromaDB, and prints the top-$k$ retrieved chunks with similarity scores.
* **How to Use It for Our App**:
  ```bash
  python scripts/test_chunk_retrieval.py --query "carry forward privilege leave" --top-k 5
  ```

---

### 26. `scripts/validate_rag_pipeline.py` (End-to-End Pipeline Healthcheck)
* **What It Does**: Validates the full RAG pipeline (database connection, embeddings, retrieval, generation, and evaluation) in a single pass.
* **Why We Have / Use It**: Acts as a smoke test to confirm all subsystems are operational before starting development or testing.
* **When to Use It**: After installing dependencies or pulling updates from git.
* **How It Works**:
  * Runs a test query through each pipeline stage and asserts expected status codes and non-empty responses.
* **How to Use It for Our App**:
  ```bash
  python scripts/validate_rag_pipeline.py
  ```

---

### 27. `scripts/seed_faq_cache.py` (Redis FAQ Semantic Cache Warmer)
* **What It Does**: Pre-populates Redis with common HR questions and verified answers to enable instant responses for frequent queries.
* **Why We Have / Use It**: Speeds up response times and reduces LLM API costs for common questions like leave entitlements and holiday schedules.
* **When to Use It**: During initial environment provisioning or when common questions change.
* **How It Works**:
  * Reads common questions, computes query embeddings, and writes key-value pairs into Redis semantic cache.
* **How to Use It for Our App**:
  ```bash
  python scripts/seed_faq_cache.py
  ```

---

### 28. `scripts/clear_caches.py` (Redis & Memory Cache Flusher)
* **What It Does**: Flushes Redis semantic caches and Streamlit memory caches.
* **Why We Have / Use It**: Prevents stale answers from persisting after document or prompt updates.
* **When to Use It**: Whenever policies are re-indexed or prompts are changed.
* **How It Works**:
  * Connects to Redis and executes `FLUSHDB`, then resets Streamlit cache directories.
* **How to Use It for Our App**:
  ```bash
  python scripts/clear_caches.py
  ```

---

### 29. `scripts/test_langfuse_end_to_end.py` (Telemetry & Tracing Verifier)
* **What It Does**: Sends a test event to Langfuse and confirms that spans, tokens, and latency traces are logged properly.
* **Why We Have / Use It**: Verifies production observability connections without waiting for live user traffic.
* **When to Use It**: After configuring or rotating `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`.
* **How It Works**:
  * Emits an instrumented trace to the Langfuse API and asserts a `200 OK` response.
* **How to Use It for Our App**:
  ```bash
  python scripts/test_langfuse_end_to_end.py
  ```

---

### 30. `scripts/test_rbac_cache_manual.py` (RBAC Security & Tenant Isolation Tester)
* **What It Does**: Tests Role-Based Access Control (RBAC) and department filters to ensure users only retrieve documents authorized for their role.
* **Why We Have / Use It**: Validates security and privacy boundaries (e.g. engineering users cannot retrieve executive compensation documents).
* **When to Use It**: When testing multi-tenant isolation or updating access control policies.
* **How It Works**:
  * Executes identical queries across different user role tokens and verifies that unauthorized chunks are filtered out.
* **How to Use It for Our App**:
  ```bash
  python scripts/test_rbac_cache_manual.py
  ```

---

## VII. Data Banks & Test Suites

---

### 31. `test_data/knowlayer_145_test_bank.json` & `.csv` (145 Master Benchmark Suite)
* **What It Does**: The primary evaluation test bank containing 145 curated HR and operational test cases across 9 categories:
  1. Leave & Attendance Policy (Privilege, Casual, Sick, Maternity)
  2. Travel, Meals & Expense Reimbursement
  3. Benefits, Insurance & Medical Claims
  4. Code of Conduct & Workplace Ethics
  5. Performance Review & Probation Guidelines
  6. Resignation, Notice Period & Offboarding
  7. Multi-hop Reasoning Cases
  8. Code-mixed / Romanized Language Cases (Hinglish, Kanglish)
  9. Negative, Out-of-Scope & Adversarial Probes
* **Why We Have / Use It**: Serves as the ground-truth standard for assessing whether the RAG system is production-ready.
* **When to Use It**: In Mode 2 automated benchmark runs and CI/CD quality gates.
* **How It Works**:
  * Each record includes `id`, `category`, `question`, `expected_answer`, `expected_doc`, and `validation_rules`.
* **How to Use It for Our App**:
  * Loaded automatically by Ragas Studio Mode 2. Can be updated directly via the **Test Studio** UI tab.

---

### 32. `sandbox/MANIFEST.md` (Architectural Manifest & Topology)
* **What It Does**: Technical architectural specification documenting file structures, component dependencies, and design decisions.
* **Why We Have / Use It**: Onboards new engineers and documents architectural boundaries and conventions.
* **When to Use It**: Reference document when extending or refactoring sandbox modules.
* **How It Works**:
  * Markdown document mapping component relationships and interface contracts.
* **How to Use It for Our App**:
  * Review when adding new modules or updating dependencies.

---

## 🧭 Quick Reference: Team Troubleshooting Guide

| Goal / Issue | Recommended Component | Action |
|---|---|---|
| **Test a new user question interactively** | Mode 1: 💬 Ask as Company End User | Enter query, review generated response and live NLI scores |
| **Verify Indian language / Hinglish query handling** | Mode 1: 💬 Ask as Company End User | Test query in Romanized script; verify response matches input language |
| **Run full regression before merging PR** | Mode 2: 🧪 Benchmark Suites | Select `All 145 Cases`, click **Start Benchmark**, verify pass rate |
| **Diagnose why a query retrieved the wrong section** | Mode 3: 🔬 Custom Query Auditor | Inspect Stage 1 vs. Stage 2 rankings to pinpoint retrieval drops |
| **Find optimal chunk size for a new document** | 3. 🧩 Chunking Strategy Optimizer | Select document dropdown, click **Benchmark All 6 Strategies** |
| **Inspect raw chunks stored in ChromaDB** | 2. 🔍 ChromaDB Chunks Explorer | Filter by document name, inspect chunk size distribution |
| **Edit or add benchmark questions** | 4. 📝 Test Studio | Edit cases directly in the UI and click **Save Changes** |
| **Clear stale cache after document updates** | CLI Scripts | Run `python scripts/clear_caches.py` |
