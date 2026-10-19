"""
KnowLayer Test Studio — Interactive Test Studio UI Tab
======================================================
Provides the unified workbench where developers select a test suite, configure components,
run orchestrations, inspect 4-level reports, and compare runs for regressions.
"""

import json
from pathlib import Path
from typing import Any, Dict, List
import streamlit as st
import pandas as pd

from sandbox.engine.schema import TestCase, RunConfig, SuiteRunResult
from sandbox.engine.orchestrator import RunOrchestrator
from sandbox.engine.persistence import save_suite_run, list_recent_runs, compare_two_runs, get_run_by_id
from sandbox.reports.unified_report import render_unified_run_report
from app.core.settings import BASE_DIR


def load_test_cases(benchmark_file: Path) -> List[TestCase]:
    """Loads and converts legacy or canonical test cases into standard TestCase objects."""
    if not benchmark_file.exists():
        return []
    with open(benchmark_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [TestCase.from_legacy_benchmark(item) for item in data]


def render_test_studio_tab(df_chunks: pd.DataFrame):
    st.subheader("🧪 Step 5 · Test Studio & Orchestrated Benchmarks")
    st.info(
        "💡 **Usage Guide — Step 5:** "
        "The central release gate for your RAG application. "
        "Select a test suite (e.g. 187 benchmark cases or `MGR-` manager scenarios), choose which components to run "
        "(Retrieval, Reranking, Generation, Grounding & Ragas Evaluation, Policy Playbooks), and execute an orchestrated test. "
        "Inspect the 4-level diagnostic report to pinpoint failures, and use 'History & Regression Gates' to compare against past baselines.",
        icon="ℹ️",
    )
    st.caption("One test definition · Multiple evaluation components · One unified report")

    # Suite selector
    suite_options = {
        "📋 KnowLayer Master Test Bank (145 cases across 12 Categories)": "knowlayer_145_test_bank.json",
        "🌟 KnowLayer 300 End-User HR Policy Suite (300 questions: Positive, Negative, Edge)": "end_user_hr_300_benchmark.json",
        "🏢 Enterprise RAG Benchmark Suite (187 questions)": "rag_benchmark_questions.json",
    }
    selected_suite_label = st.selectbox("Select Test Suite", list(suite_options.keys()), index=0)
    suite_filename = suite_options[selected_suite_label]
    benchmark_path = BASE_DIR / "test_data" / suite_filename

    all_cases = load_test_cases(benchmark_path)

    if not all_cases:
        st.error(f"No benchmark test cases found at {benchmark_path}")
        return

    # Two main sub-views: "Run Studio" and "History & Regressions"
    view_mode = st.radio(
        "Studio View",
        ["🚀 Run Execution Studio", "📜 Run History & Regression Gates"],
        horizontal=True,
    )

    if view_mode == "🚀 Run Execution Studio":
        col_cfg1, col_cfg2 = st.columns([1, 1])

        with col_cfg1:
            st.markdown("#### 1. Test Suite Selection & Filters")
            cat_list = sorted(list({c.category for c in all_cases}))
            categories = [f"All Categories ({len(all_cases)})"] + cat_list
            selected_cat = st.selectbox("Category Filter", categories)

            # Role filter
            role_list = sorted(list({c.input.role for c in all_cases if c.input.role}))
            roles = ["All Roles"] + role_list
            selected_role = st.selectbox("Role Filter", roles)

            filtered_cases = all_cases
            if not selected_cat.startswith("All Categories"):
                filtered_cases = [c for c in filtered_cases if c.category == selected_cat]
            if selected_role != "All Roles":
                filtered_cases = [c for c in filtered_cases if c.input.role == selected_role]

            st.info(f"📋 **{len(filtered_cases)}** test cases match active filter criteria.")

            # Sample subset selector for fast testing
            run_sample_size = st.slider(
                "Max Test Cases to Run (Speed dial)",
                min_value=1,
                max_value=len(filtered_cases),
                value=min(10, len(filtered_cases)),
                help="Start with 10 from each category to verify assertions before running the full set.",
            )
            cases_to_run = filtered_cases[:run_sample_size]


        with col_cfg2:
            st.markdown("#### 2. Component Selection")
            run_retrieval = st.checkbox("🔍 Vector Retrieval (Bi-Encoder)", value=True)
            run_reranking = st.checkbox("🎯 Cross-Encoder Reranker (BGE)", value=True)
            run_generation = st.checkbox("🤖 Response Generation (LLM)", value=True)
            run_grounding = st.checkbox("🛡️ Grounding & Hallucination Guard", value=True)
            run_policy = st.checkbox("📋 Policy Playbook & Compliance (Prohibited Claims / Abstention)", value=True)
            run_ragas = st.checkbox("📊 Ragas Response Quality & Edge Evaluator (OpenRouter)", value=True)

            active_components = []
            if run_retrieval: active_components.append("retrieval")
            if run_reranking: active_components.append("reranking")
            if run_generation: active_components.append("generation")
            if run_grounding: active_components.append("grounding")
            if run_policy: active_components.append("policy_eval")
            if run_ragas: active_components.append("ragas_eval")

            st.markdown("#### 3. Execution Environment")
            exec_mode = st.selectbox(
                "Execution Mode",
                ["remote_provider_allowed", "local_models", "offline_strict"],
                index=0,
                help="remote_provider_allowed enables OpenRouter for generation and Ragas evaluation.",
            )
            provider = "local_heuristic" if exec_mode != "remote_provider_allowed" else "openrouter"

        run_btn = st.button("⚡ Execute Test Run", type="primary", use_container_width=True)
        if run_btn:
            suite_id = "knowlayer_hr_300" if "300" in selected_suite_label else "enterprise_187"
            config = RunConfig(
                suite_id=suite_id,
                execution_mode=exec_mode,
                components=active_components,
                llm_provider=provider,
            )

            orchestrator = RunOrchestrator(config)
            warnings = orchestrator.preflight_check(cases_to_run)
            for w in warnings:
                st.warning(w)

            p_bar = st.progress(0.0)
            status_text = st.empty()

            def progress_hook(idx: int, total: int, msg: str):
                p_bar.progress((idx + 1) / total)
                status_text.caption(msg)

            with st.spinner("Executing orchestrated evaluation pipeline..."):
                run_res = orchestrator.run_suite(cases_to_run, progress_callback=progress_hook)
                save_suite_run(run_res)
                st.session_state["latest_studio_run"] = run_res

            st.success(f"Execution complete! Run persisted to SQLite and artifacts: `{run_res.run_id}`")

        latest_run = st.session_state.get("latest_studio_run")
        if latest_run:
            render_unified_run_report(latest_run)

    else:
        # History & Regressions View
        st.markdown("#### 📜 Recent Test Studio Runs")
        recent_runs = list_recent_runs(limit=10)
        if not recent_runs:
            st.info("No runs recorded in SQLite history yet. Execute a run in the Execution Studio tab!")
            return

        df_runs = pd.DataFrame(recent_runs)
        st.dataframe(df_runs[["run_id", "created_at", "total_tests", "passed", "failed", "pass_rate", "execution_mode"]], use_container_width=True)

        st.markdown("#### 🔍 Side-by-Side Regression Analysis")
        run_ids = [r["run_id"] for r in recent_runs]
        if len(run_ids) >= 2:
            col_cmp1, col_cmp2 = st.columns(2)
            with col_cmp1:
                baseline_id = st.selectbox("Baseline Run", run_ids, index=1)
            with col_cmp2:
                current_id = st.selectbox("Current / Candidate Run", run_ids, index=0)

            cmp_res = compare_two_runs(baseline_id, current_id)
            delta = cmp_res.get("delta_pass_rate", 0)
            st.metric(
                "Pass Rate Delta",
                f"{cmp_res.get('run_b', {}).get('pass_rate', 0)}%",
                delta=f"{delta:+.1f}% vs baseline",
            )

            if cmp_res.get("regressions"):
                st.error(f"🚨 Regressions Detected ({len(cmp_res['regressions'])} tests failed that previously passed):")
                st.write(cmp_res["regressions"])
            else:
                st.success("✅ Zero regressions detected between these two runs.")

            if cmp_res.get("improvements"):
                st.info(f"✨ Improvements Detected ({len(cmp_res['improvements'])} tests now passing):")
                st.write(cmp_res["improvements"])
        else:
            st.info("Execute at least 2 runs to enable regression gating.")

        st.markdown("---")
        st.markdown("#### 🔬 Inspect Any Historical Run Report")
        inspect_run_id = st.selectbox("Select Run ID to Inspect:", run_ids, key="inspect_hist_run_select")
        if st.button("📖 View Full 4-Level Report for Selected Run", key="btn_inspect_hist_run"):
            run_data = get_run_by_id(inspect_run_id)
            if run_data:
                try:
                    reconstituted = SuiteRunResult.model_validate(run_data)
                    render_unified_run_report(reconstituted)
                except Exception as e:
                    st.error(f"Failed to reconstitute run trace: {e}")
            else:
                st.warning("Trace file not found for this run.")
