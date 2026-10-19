"""
KnowLayer Test Studio — Step-by-Step Integrated Home Command Center
===================================================================
A guided 5-step operational workflow integrating all platform capabilities:
  Step 1 · Document Ingestion & Chunking
  Step 2 · Chunk Quality Index (CQI) Diagnostics
  Step 3 · Chunk Explorer & Semantic Lookup
  Step 4 · Two-Stage Retrieval & Reranking Funnel
  Step 5 · Test Studio & Orchestrated Benchmark
"""

from typing import Any, Dict, List
import streamlit as st
import pandas as pd

from app.core.settings import BASE_DIR
from sandbox.engine.schema import TestCase, RunConfig
from sandbox.engine.orchestrator import RunOrchestrator
from sandbox.engine.persistence import save_suite_run, list_recent_runs
from sandbox.components.retrieval import get_engine_vector_store
from sandbox.components.reranking import execute_reranking
from sandbox.ui.test_studio import load_test_cases


def render_home_dashboard(df_chunks: pd.DataFrame):
    """
    Renders the unified step-by-step operational workflow with usage guides for every stage.
    """
    st.markdown("### 🏠 KnowLayer Step-by-Step Command Center")
    st.caption("A guided end-to-end workflow taking you from raw document ingestion to release verdict without getting lost.")

    benchmark_path = BASE_DIR / "test_data" / "rag_benchmark_questions.json"
    all_cases = load_test_cases(benchmark_path) if benchmark_path.exists() else []
    recent_runs = list_recent_runs(limit=5)
    latest_run = recent_runs[0] if recent_runs else None

    # Calculate CQI metrics
    total_chunks = len(df_chunks)
    optimal_chunks = 0
    stub_chunks = 0
    overflow_chunks = 0
    cqi_score = 0.0

    if not df_chunks.empty and "token_count" in df_chunks.columns:
        optimal_chunks = int((df_chunks["token_count"].between(50, 250)).sum())
        stub_chunks = int((df_chunks["token_count"] < 35).sum())
        overflow_chunks = int((df_chunks["token_count"] > 256).sum())
        cqi_score = round((optimal_chunks / total_chunks * 100), 1) if total_chunks > 0 else 0.0

    # -------------------------------------------------------------
    # Step-by-Step Progress Pipeline Bar
    # -------------------------------------------------------------
    st.markdown("""
    <div style="background:#0F172A; border:1px solid #1E293B; border-radius:8px; padding:12px 18px; margin-bottom:20px;">
        <span style="color:#38BDF8; font-weight:700;">Execution Flow:</span>
        &nbsp;&nbsp;<b>Step 1</b> Ingestion &rarr;
        &nbsp;<b>Step 2</b> Quality Audit &rarr;
        &nbsp;<b>Step 3</b> Explorer &rarr;
        &nbsp;<b>Step 4</b> 2-Stage Funnel &rarr;
        &nbsp;<b>Step 5</b> Test Studio & Release Gate
    </div>
    """, unsafe_allow_html=True)

    # -------------------------------------------------------------
    # STEP 1: Document Ingestion & Store Sync
    # -------------------------------------------------------------
    with st.container():
        st.markdown("#### 📁 Step 1 · Document Ingestion & Knowledge Base Status")
        st.info(
            "💡 **Usage Guide — Step 1:** "
            "Ingestion parses source policy files (`.docx`, `.pdf`, `.txt`) and splits them into clean chunks. "
            "Embedding models (such as `all-MiniLM-L6-v2`) truncate texts beyond **256 tokens**, so chunks must be budget-constrained. "
            "Verify here that all curated documents are indexed in ChromaDB before running queries.",
            icon="ℹ️"
        )
        col_s1_a, col_s1_b, col_s1_c, col_s1_d = st.columns(4)
        with col_s1_a:
            st.metric("Total Indexed Vectors", f"{total_chunks:,}")
        with col_s1_b:
            indexed_sources = len(df_chunks["source"].unique()) if not df_chunks.empty else 0
            st.metric("Active Policy Documents", f"{indexed_sources} Files")
        with col_s1_c:
            st.metric("Embedder Model Limit", "256 Tokens (Max)")
        with col_s1_d:
            st.metric("RBAC Scopes Protected", "4 Docs (Project 121)")

    st.markdown("---")

    # -------------------------------------------------------------
    # STEP 2: Chunk Quality Diagnostics (CQI)
    # -------------------------------------------------------------
    with st.container():
        st.markdown("#### 📊 Step 2 · Chunk Quality Index (CQI) Diagnostics")
        st.info(
            "💡 **Usage Guide — Step 2:** "
            "Audit your chunk health before testing retrieval. "
            "**Stub Chunks (<35 tokens)** lack sufficient semantic meaning and cause false vector matches. "
            "**Overflow Chunks (>256 tokens)** suffer silent truncation at embedding time. "
            "Aim for a CQI Score of **>85%** optimal chunks (50–250 tokens).",
            icon="ℹ️"
        )
        col_s2_a, col_s2_b = st.columns([1, 1])
        with col_s2_a:
            st.markdown(f"**Overall CQI Health Score: {cqi_score}%**")
            st.progress(cqi_score / 100.0)
            st.caption(f"Optimal Chunks (50–250 tokens): **{optimal_chunks:,} / {total_chunks:,}**")
        with col_s2_b:
            st.write(f"• **Stub Fragments (< 35 tokens):** {stub_chunks:,} ({(stub_chunks/total_chunks*100) if total_chunks else 0:.1f}%)")
            st.write(f"• **Overflow Chunks (> 256 tokens):** {overflow_chunks:,} ({(overflow_chunks/total_chunks*100) if total_chunks else 0:.1f}%)")

        if stub_chunks > 0:
            with st.expander(f"🔍 Drill-down: Inspect {stub_chunks} Stub Fragments"):
                st.caption("These micro-fragments should be merged with adjacent paragraphs during document chunking.")
                st.dataframe(
                    df_chunks[df_chunks["token_count"] < 35][["chunk_id", "token_count", "source", "text"]].head(4),
                    use_container_width=True
                )

    st.markdown("---")

    # -------------------------------------------------------------
    # STEP 3: Live Chunk Explorer & Text Lookup
    # -------------------------------------------------------------
    with st.container():
        st.markdown("#### 🔍 Step 3 · Chunk Explorer & Metadata Lookup")
        st.info(
            "💡 **Usage Guide — Step 3:** "
            "Inspect individual chunk records to verify that policy headings, section metadata, and RBAC project tags are preserved. "
            "Type a keyword below (e.g. `probation`, `harassment`, `leave balance`) to see exactly how text is chunked in ChromaDB.",
            icon="ℹ️"
        )
        col_s3_q, col_s3_doc = st.columns([2, 1])
        with col_s3_q:
            search_term = st.text_input("Search Text or Keyword Across Chunks", placeholder="e.g. carry forward leave, probation duration, notice period")
        with col_s3_doc:
            doc_filter = st.selectbox(
                "Filter by Document",
                ["All Documents"] + (sorted(df_chunks["source"].unique().tolist()) if not df_chunks.empty else [])
            )

        if search_term.strip() and not df_chunks.empty:
            filtered = df_chunks[df_chunks["text"].str.contains(search_term.strip(), case=False, na=False)]
            if doc_filter != "All Documents":
                filtered = filtered[filtered["source"] == doc_filter]

            st.write(f"Found **{len(filtered)} matching chunks** for `{search_term.strip()}`:")
            for _, r in filtered.head(3).iterrows():
                with st.expander(f"🧩 `{r['chunk_id']}` ({r['token_count']} tok) &nbsp;|&nbsp; Source: *{r['source']}*"):
                    st.write(r["text"])
                    st.caption(f"Document ID: `{r.get('doc_id', '')}` | Department: `{r.get('department', '')}` | Project Scope: `{r.get('project_id', '')}`")

    st.markdown("---")

    # -------------------------------------------------------------
    # STEP 4: Two-Stage Retrieval & Reranker Funnel
    # -------------------------------------------------------------
    with st.container():
        st.markdown("#### 🎯 Step 4 · Two-Stage Retrieval & Reranking Funnel")
        st.info(
            "💡 **Usage Guide — Step 4:** "
            "Enterprise RAG operates in two stages: "
            "1. **Bi-Encoder Similarity Search:** Extracts top-13 candidate chunks quickly via cosine similarity in ChromaDB. "
            "2. **Cross-Encoder Reranking (`bge-reranker-base`):** Deeply rescores `(Query, Passage)` token pairs to place the true answer ('needle') into the top 3–4 context slots. "
            "Test any query or preset policy scenario below to observe how rank positions shift.",
            icon="ℹ️"
        )

        preset_options = [
            "What is the standard probation period for new employees?",
            "What is the process for approving an employee leave application in the portal?",
            "Can a manager reject a leave application if project deadlines are pending?",
            "What steps should a manager take when an employee reports sexual harassment?",
            "How many privilege leaves can be carried forward each calendar year?",
        ]
        col_f1, col_f2 = st.columns([2.5, 1.5])
        with col_f1:
            sel_preset = st.selectbox("Choose Preset Policy Question or Enter Below", ["Custom Query..."] + preset_options)
            query_val = "" if sel_preset == "Custom Query..." else sel_preset
            live_query = st.text_input("Question to evaluate in Funnel", value=query_val, placeholder="e.g. Can unused casual leave be encashed?")
        with col_f2:
            role_choice = st.selectbox("Simulate User RBAC Scope", ["ALL", "EMPLOYEE", "MANAGER", "HR"])
            top_k_select = st.slider("Target Context Passages (Top-K)", min_value=2, max_value=6, value=4)

        if live_query.strip():
            with st.spinner("Executing Stage 1 Vector Search and Stage 2 Cross-Encoder Reranking..."):
                store = get_engine_vector_store()
                project_filter = ["121", "unassigned", "default"] if role_choice == "EMPLOYEE" else None

                # Stage 1: Retrieval
                s1_candidates = store.query(query_text=live_query, top_k=13, project_ids=project_filter)
                
                # Stage 2: Rerank
                tc_obj = TestCase(
                    id="QUICK-EVAL",
                    title=live_query[:50],
                    input={"question": live_query, "role": role_choice},
                )
                s2_out = execute_reranking(
                    test_case=tc_obj,
                    candidates=s1_candidates,
                    top_k=top_k_select,
                )

            col_fun1, col_fun2 = st.columns(2)
            with col_fun1:
                st.markdown(f"**Stage 1: Bi-Encoder Candidates ({len(s1_candidates)} retrieved, Top 4 shown):**")
                for i, c in enumerate(s1_candidates[:4], 1):
                    st.caption(f"#{i} `{c['id']}` (Score: {c.get('score', 0):.3f}) — *{c.get('metadata', {}).get('source', '')}*")
            with col_fun2:
                st.markdown(f"**Stage 2: Cross-Encoder Rescored Context (Top {top_k_select}):**")
                for i, c in enumerate(s2_out.get("reranked_chunks", []), 1):
                    st.markdown(f"**#{i}** `{c['id']}` (Score: {c.get('_rerank_score', 0):.4f}) &nbsp;|&nbsp; *{c.get('metadata', {}).get('source', '')}*")
                    st.caption(f"{c.get('text', '')[:130]}...")

    st.markdown("---")

    # -------------------------------------------------------------
    # STEP 5: Test Studio & Orchestrated Release Gate
    # -------------------------------------------------------------
    with st.container():
        st.markdown("#### 🧪 Step 5 · Test Studio & Orchestrated Benchmark")
        st.info(
            "💡 **Usage Guide — Step 5:** "
            "The final step evaluates end-to-end quality and governance. "
            "The **Run Orchestrator** runs test cases through the full pipeline (Retrieval &rarr; Reranking &rarr; Generation &rarr; Grounding &rarr; Ragas Evaluation &rarr; Policy Compliance). "
            "If an assertion fails, it pinpoints the exact failure stage and alerts you if any prohibited claims leaked. "
            "All results are persisted to SQLite for regression tracking.",
            icon="ℹ️"
        )

        col_run1, col_run2 = st.columns([1, 1])
        with col_run1:
            st.markdown(f"**Available Test Data:** **{len(all_cases)} Curated Benchmark Scenarios**")
            st.caption("Includes Manager/HR policy playbooks (`MGR-01` to `MGR-20`), procedural workflows, and hallucination guards.")
            
            if st.button("🚀 Run 5-Case Quick Smoke Test", type="primary"):
                smoke_cases = all_cases[:5]
                config = RunConfig(
                    execution_mode="local_models",
                    components=["retrieval", "reranking", "generation", "policy_eval"],
                    llm_provider="local_heuristic",
                )
                orch = RunOrchestrator(config)
                with st.spinner("Executing orchestrated smoke test..."):
                    res = orch.run_suite(smoke_cases)
                    save_suite_run(res)
                st.success(f"Smoke test complete! Result: **{res.passed}/{res.total_tests} passed ({res.pass_rate}%)**")
                st.rerun()

        with col_run2:
            st.markdown("**Historical Test Studio Runs in SQLite:**")
            if recent_runs:
                df_hist = pd.DataFrame(recent_runs)[["run_id", "created_at", "total_tests", "pass_rate", "execution_mode"]]
                st.dataframe(df_hist.head(3), use_container_width=True)
                st.caption("💡 Switch to the **🎯 Step 5: Test Studio** tab for full component toggles, 4-level reports, and side-by-side regression comparisons.")
            else:
                st.info("No recorded test runs yet. Run your first smoke test using the button on the left!")
