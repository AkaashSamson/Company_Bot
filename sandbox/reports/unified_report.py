"""
KnowLayer Test Studio — Unified 4-Level Report
==============================================
Renders Level 1 (Suite summary), Level 2 (Component metrics),
Level 3 (Failure analysis), and Level 4 (Execution trace) in Streamlit and text.
"""

from typing import Any, Dict, List
import streamlit as st
import pandas as pd
from sandbox.engine.schema import SuiteRunResult, TestCaseResult


def render_unified_run_report(run_result: SuiteRunResult):
    """
    Renders the unified 4-level test report in the Streamlit UI.
    """
    st.markdown("---")
    st.markdown("## 📊 Unified Run Report")

    # -------------------------------------------------------------
    # Level 1: Suite Summary
    # -------------------------------------------------------------
    st.markdown("### Level 1 · Suite Summary")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Overall Verdict", "✅ PASS" if run_result.pass_rate >= 80.0 else "❌ FAIL")
    with col2:
        st.metric("Pass Rate", f"{run_result.pass_rate:.1f}%")
    with col3:
        st.metric("Passed / Total", f"{run_result.passed} / {run_result.total_tests}")
    with col4:
        st.metric("Failed Cases", f"{run_result.failed}")
    with col5:
        st.metric("Execution Mode", run_result.config.execution_mode)

    st.caption(f"Run ID: `{run_result.run_id}` &nbsp;|&nbsp; Suite: `{run_result.suite_id}` &nbsp;|&nbsp; Completed: `{run_result.created_at}`")

    # -------------------------------------------------------------
    # Level 2: Component Metrics
    # -------------------------------------------------------------
    st.markdown("### Level 2 · Component Breakdown")
    comp_cols = st.columns(len(run_result.component_metrics) if run_result.component_metrics else 1)
    for col, (comp_name, metrics) in zip(comp_cols, run_result.component_metrics.items()):
        with col:
            st.markdown(f"**{comp_name.replace('_', ' ').title()}**")
            for k, v in metrics.items():
                label = k.replace("_", " ").title()
                val_str = f"{v}%" if "rate" in k or "recall" in k else str(v)
                st.caption(f"• {label}: **{val_str}**")

    # -------------------------------------------------------------
    # Level 3: Failed Test Analysis
    # -------------------------------------------------------------
    st.markdown("### Level 3 · Failed Test Analysis")
    if run_result.failed_cases:
        st.warning(f"Found {len(run_result.failed_cases)} failing test scenarios requiring attention:")
        for fc in run_result.failed_cases:
            with st.expander(f"❌ [{fc['id']}] Failed at stage: `{fc['failure_stage']}` — {fc['title']}"):
                st.markdown(f"**Question:** {fc.get('question', '')}")
                st.markdown("**Failed Assertions:**")
                for fa in fc.get("failed_assertions", []):
                    st.error(f"• **{fa.get('component')}.{fa.get('type')}**: {fa.get('message')}")
                    st.caption(f"&nbsp;&nbsp;Expected: `{fa.get('expected_value')}` &nbsp;|&nbsp; Actual: `{fa.get('actual_value')}`")
    else:
        st.success("🎉 All test assertions passed successfully across all enabled components!")

    # -------------------------------------------------------------
    # Level 4: Execution Trace & Inspection
    # -------------------------------------------------------------
    with st.expander("🔬 Level 4 · Full Execution Traces & Deep Diagnostics", expanded=True):
        st.caption("Detailed timing, chunk IDs, LLM outputs, Ragas evaluation scores, and diagnostic root-cause reports.")
        trace_data = []
        for tr in run_result.test_results:
            ragas_stage = tr.trace.stages.get("ragas_eval")
            faith = ragas_stage.outputs.get("faithfulness") if ragas_stage else None
            rel = ragas_stage.outputs.get("answer_relevancy") if ragas_stage else None
            fact = ragas_stage.outputs.get("factual_correctness") if ragas_stage else None

            trace_data.append({
                "Test ID": tr.test_id,
                "Status": tr.status,
                "Failure Stage": tr.failure_stage or "None",
                "Faithfulness": f"{faith:.2f}" if faith is not None else "-",
                "Relevancy": f"{rel:.2f}" if rel is not None else "-",
                "Factual Correctness": f"{fact:.2f}" if fact is not None else "-",
                "Total Latency (ms)": round(tr.metrics.get("latency_ms", 0.0), 1),
            })
        st.dataframe(pd.DataFrame(trace_data), use_container_width=True)

        st.markdown("#### 🔎 Interactive Case-by-Case Inspector")
        case_options = [tr.test_id for tr in run_result.test_results]
        selected_case_id = st.selectbox("Select Test Case to Inspect:", case_options)
        selected_tr = next((tr for tr in run_result.test_results if tr.test_id == selected_case_id), None)

        if selected_tr:
            c_left, c_right = st.columns([1, 1])
            with c_left:
                st.markdown(f"**Test ID:** `{selected_tr.test_id}` &nbsp; | &nbsp; **Status:** `{selected_tr.status}`")
                
                # Check stages
                ret_stage = selected_tr.trace.stages.get("retrieval")
                if ret_stage:
                    st.markdown("**Retrieved Chunks:**")
                    chunks = ret_stage.outputs.get("retrieved_chunks", [])
                    for i, ch in enumerate(chunks[:3]):
                        snippet = ch.get("text", "")[:180] + "..." if len(ch.get("text", "")) > 180 else ch.get("text", "")
                        st.caption(f"**Chunk {i+1}** (`{ch.get('doc_id')}`): {snippet}")

                gen_stage = selected_tr.trace.stages.get("generation")
                if gen_stage:
                    st.markdown("**LLM Generated Response:**")
                    st.info(gen_stage.outputs.get("generated_answer", "No answer generated."))

            with c_right:
                ragas_stage = selected_tr.trace.stages.get("ragas_eval")
                if ragas_stage:
                    st.markdown("**Ragas Evaluation Metrics:**")
                    m_cols = st.columns(4)
                    with m_cols[0]:
                        st.metric("Faithfulness", f"{ragas_stage.outputs.get('faithfulness', 0):.2f}")
                    with m_cols[1]:
                        st.metric("Relevancy", f"{ragas_stage.outputs.get('answer_relevancy', 0):.2f}")
                    with m_cols[2]:
                        st.metric("Precision", f"{ragas_stage.outputs.get('context_precision', 0):.2f}")
                    with m_cols[3]:
                        st.metric("Factuality", f"{ragas_stage.outputs.get('factual_correctness', 0):.2f}")

                    if ragas_stage.outputs.get("diagnosis"):
                        st.markdown("**Root-Cause Diagnosis (OpenRouter Evaluator):**")
                        st.warning(ragas_stage.outputs["diagnosis"])

                pol_stage = selected_tr.trace.stages.get("policy_eval")
                if pol_stage:
                    st.markdown(f"**Policy Compliance:** `prohibited_claim_free={pol_stage.outputs.get('prohibited_claim_free')}`")

