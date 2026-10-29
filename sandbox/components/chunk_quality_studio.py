"""
KnowLayer — 7-Parameter Chunk Quality Studio (Sandbox UI Component)
===================================================================
Visualizes the 7-Parameter, 3-Gate Chunk Quality Evaluation Pipeline tailored
to KnowLayer's specific architectural stack:
  - sentence-transformers/all-MiniLM-L6-v2 (256-token hard ceiling)
  - BAAI/bge-reranker-base (cross-encoder Top-4 reranker)
  - SEMANTIC_MERGE_SIMILARITY_THRESHOLD = 0.88
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import streamlit as st

from app.core.settings import (
    BASE_DIR,
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    RAG_RERANKER_MODEL,
    SEMANTIC_MERGE_SIMILARITY_THRESHOLD,
)
from sandbox.engine.chunk_quarantine_manager import (
    add_chunk_to_chroma,
    get_chroma_chunk_presence,
    is_chunk_in_chroma,
    load_quarantined_chunks,
    quarantine_chunk_from_chroma,
)

DEFAULT_REPORT_PATHS = [
    Path(BASE_DIR) / "test_results" / "trial_chunk_quality_report.json",
    Path(BASE_DIR) / "reports" / "chunk_quality_report.json",
    Path(BASE_DIR) / "chunk_quality_report.json",
    Path(BASE_DIR).parent / "chunk_quality_report.json",
]

# Parameter definitions and benchmarks
PARAMETER_DEFINITIONS = [
    {
        "id": "1_token_budget",
        "key": "1_token_budget (s_token)",
        "label": "1. Token Budget Utilization",
        "symbol": "s_token",
        "target": ">= 0.95",
        "target_val": 0.95,
        "tier": "Tier 1 — Deterministic",
        "desc": "Tests whether chunks fit inside all-MiniLM-L6-v2's hard 256-token window without silent truncation.",
        "danger_note": "Silent truncation drops all text past token 256 from the vector embedding.",
    },
    {
        "id": "2_boundary_integrity",
        "key": "2_boundary_integrity (s_bound)",
        "label": "2. Boundary & Structural Integrity",
        "symbol": "s_bound",
        "target": ">= 0.90",
        "target_val": 0.90,
        "tier": "Tier 1 — Deterministic",
        "desc": "Detects mid-sentence splits, unterminated clauses, orphan Markdown headings, and broken tables.",
        "danger_note": "Truncated sentences confuse both vector search and cross-encoder rerankers.",
    },
    {
        "id": "3_metadata_completeness",
        "key": "3_metadata_completeness (s_meta)",
        "label": "3. Metadata & Hierarchy Completeness",
        "symbol": "s_meta",
        "target": ">= 0.85",
        "target_val": 0.85,
        "tier": "Tier 1 — Deterministic",
        "desc": "Validates compliance with ChunkMetadata canonical contract (doc_id, project_id, hierarchy_path).",
        "danger_note": "Missing hierarchy prevents breadcrumb navigation and RBAC tenant isolation.",
    },
    {
        "id": "4_intra_coherence",
        "key": "4_intra_coherence (s_coh)",
        "label": "4. Intra-Chunk Semantic Coherence",
        "symbol": "s_coh",
        "target": ">= 0.60",
        "target_val": 0.60,
        "tier": "Tier 2 — Semantic",
        "desc": "Cosine similarity between consecutive sentences to verify the chunk addresses a single topic.",
        "danger_note": "Sudden topic drift (min sent sim < 0.22) creates muddled centroid embeddings.",
    },
    {
        "id": "5_inter_distinctiveness",
        "key": "5_inter_distinctiveness (s_dist)",
        "label": "5. Inter-Chunk Distinctiveness",
        "symbol": "s_dist",
        "target": ">= 0.90",
        "target_val": 0.90,
        "tier": "Tier 2 — Semantic",
        "desc": "Ensures adjacent chunks from the same document are distinct and below the 0.88 merge threshold.",
        "danger_note": "Pairs with sim >= 0.88 represent redundant stubs that dilute the Top-4 RAG context.",
    },
    {
        "id": "6_self_containment",
        "key": "6_self_containment (s_self)",
        "label": "6. Self-Containment & De-contextualization",
        "symbol": "s_self",
        "target": ">= 0.80",
        "target_val": 0.80,
        "tier": "Tier 3 — Contextual",
        "desc": "Flags dangling anaphora ('This policy...', 'They must...') and verifies injected heading prefixes.",
        "danger_note": "Chunks with unresolved pronouns retrieved standalone in Top-4 lose critical context.",
    },
    {
        "id": "7_retrievability_mrr",
        "key": "7_retrievability_mrr (s_ret)",
        "label": "7. Reverse-Query Retrievability",
        "symbol": "s_ret",
        "target": ">= 0.75 MRR",
        "target_val": 0.75,
        "tier": "Tier 3 — Contextual",
        "desc": "Gate 2 test: Synthetic questions retrieved through Bi-Encoder Top-15 -> BGE Reranker Top-4.",
        "danger_note": "Diagnoses whether chunks are invisible to vector search or demoted by cross-encoders.",
    },
]


def load_cached_report() -> Optional[Dict[str, Any]]:
    """Attempt to load a previously generated JSON report from disk."""
    for p in DEFAULT_REPORT_PATHS:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if "summary" in data and "mean_scores" in data:
                    return data
            except Exception:
                continue
    return None


def execute_evaluation(
    df_chunks: pd.DataFrame,
    sample_size: int = 15,
    enable_reranker: bool = False,
) -> Dict[str, Any]:
    """Run KnowLayerChunkEvaluator on chunks from the DataFrame."""
    from scripts.evaluate_chunking_quality import (
        ChunkRecord,
        KnowLayerChunkEvaluator,
    )

    records: List[ChunkRecord] = []
    for _, row in df_chunks.iterrows():
        meta = {
            "document_id": str(row.get("doc_id", "")),
            "project_id": str(row.get("project_id", "unassigned")),
            "source_filename": str(row.get("source", "unknown")),
            "chunk_index": int(row.get("chunk_index", 0) if "chunk_index" in row and pd.notna(row["chunk_index"]) else 0),
            "content_type": str(row.get("content_type", "text")),
            "hierarchy_path": row.get("hierarchy_path", ""),
            "section_heading": row.get("heading_text", ""),
            "page_number": int(row.get("page_number", 1) if "page_number" in row and pd.notna(row["page_number"]) else 1),
        }
        records.append(
            ChunkRecord(
                chunk_id=str(row["chunk_id"]),
                text=str(row["text"]),
                metadata=meta,
            )
        )

    evaluator = KnowLayerChunkEvaluator(enable_reranker=enable_reranker)
    report = evaluator.evaluate_corpus(records, sample_retrievability=sample_size)
    return report


def render_seven_parameter_quality_studio(df_chunks: pd.DataFrame) -> None:
    """Render the full 7-parameter chunk quality audit dashboard."""
    st.markdown("""
    <div style="background: linear-gradient(135deg, #090E1A 0%, #0F172A 100%); border: 1px solid #1E293B; border-radius: 8px; padding: 18px 22px; margin-bottom: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <h3 style="margin: 0 0 6px 0; font-weight: 700; color: #F8FAFC; letter-spacing: -0.01em;">
                    🎯 7-Parameter Chunk Quality & Retrieval-Fitness Engine
                </h3>
                <div style="color: #94A3B8; font-size: 0.88rem; line-height: 1.4;">
                    Evaluates chunks across 3 architectural tiers specifically calibrated for 
                    <code style="color: #38BDF8; background: #0B132B; padding: 2px 6px; border-radius: 4px;">all-MiniLM-L6-v2 (256-token limit)</code> and 
                    <code style="color: #A78BFA; background: #0B132B; padding: 2px 6px; border-radius: 4px;">BAAI/bge-reranker-base</code>.
                </div>
            </div>
            <div style="text-align: right;">
                <span style="background: #1E293B; color: #38BDF8; font-weight: 600; font-size: 0.78rem; padding: 4px 10px; border-radius: 12px; border: 1px solid #334155;">
                    3-GATE EVALUATION PIPELINE
                </span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # State management for report
    if "chunk_quality_7param_report" not in st.session_state:
        cached = load_cached_report()
        if cached:
            st.session_state["chunk_quality_7param_report"] = cached

    # Control Bar
    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([1.5, 1.2, 1.3, 1.0])
    with ctrl_col1:
        gate2_sample = st.select_slider(
            "Gate 2 Retrievability Sample Size",
            options=[0, 5, 15, 30, 50],
            value=5,
            help="Number of chunks to test through round-trip synthetic query generation and retrieval.",
            key="slider_7param_sample",
        )
    with ctrl_col2:
        use_reranker = st.checkbox(
            "Enable BGE Reranker in Gate 2",
            value=False,
            help="Reranks candidates with BAAI/bge-reranker-base to test cross-encoder alignment. (Takes longer)",
            key="chk_7param_reranker",
        )
    with ctrl_col3:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        run_audit_btn = st.button(
            "🚀 Run Live 7-Param Audit",
            type="primary",
            use_container_width=True,
            key="btn_run_7param_live",
        )
    with ctrl_col4:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        reload_cached_btn = st.button(
            "🔄 Load Report File",
            use_container_width=True,
            key="btn_load_7param_cached",
        )

    if reload_cached_btn:
        cached = load_cached_report()
        if cached:
            st.session_state["chunk_quality_7param_report"] = cached
            st.toast("Loaded cached report from disk!", icon="📄")
        else:
            st.warning("No cached report file found. Click 'Run Live 7-Param Audit' to compute.")

    # In-Place 5-Phase Chunk Normalizer Workbench
    with st.expander("🛠️ Deterministic In-Place Chunk Normalizer (Zero Data Loss + Noise Stripping + Standardization)", expanded=False):
        st.markdown("""
        **Pipeline Mechanics:**
        1. **Zero Data Loss Token Budgeting**: Chunks $> 256$ tokens are cleanly split; remaining tokens are pushed to the next chunk with hidden tags (`<!-- CUTOFF_START -->` / `<!-- CUTOFF_END -->`). Zero data is deleted.
        2. **Noise & Punctuation Stripping**: Strips repeated symbols, TOC leader dots, and repeated punctuation while safeguarding Markdown tables and headings.
        3. **Standardize Chunk Length**: Coalesces low-density micro-fragments and rebalances sentences across neighbors into the 80..220 token sweet spot.
        4. **Context Injected Anchors**: Injects `[Policy: ... | Section: ...]` and updates canonical metadata.
        """)
        n_col1, n_col2, n_col3 = st.columns([1, 1, 1.5])
        with n_col1:
            norm_ceiling = st.number_input("Hard Token Ceiling", min_value=100, max_value=250, value=245, step=5, key="norm_ui_ceiling")
        with n_col2:
            norm_min_frag = st.number_input("Min Density / Fragment Threshold", min_value=20, max_value=100, value=55, step=5, key="norm_ui_frag")
        with n_col3:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            run_norm_btn = st.button("⚡ Apply 5-Phase Normalization to Corpus", type="secondary", use_container_width=True, key="btn_apply_norm_ui")

        if run_norm_btn:
            if df_chunks.empty:
                st.error("No chunks available in ChromaDB to normalize.")
            else:
                with st.spinner("Applying deterministic 5-phase chunk normalization to ChromaDB..."):
                    try:
                        from app.infrastructure.document.chunk_normalizer import ChunkNormalizer, NormalizedChunk
                        from app.infrastructure.vector.chroma_client import ChromaVectorStore
                        
                        raw_list = [
                            NormalizedChunk(
                                chunk_id=str(row["chunk_id"]),
                                text=str(row["text"]),
                                metadata=dict(row.to_dict()),
                            )
                            for _, row in df_chunks.iterrows()
                        ]
                        normalizer = ChunkNormalizer(
                            hard_token_ceiling=norm_ceiling,
                            min_fragment_tokens=norm_min_frag,
                            enable_sentence_overlap=False,
                            enable_cutoff_tags=True,
                        )
                        normalized = normalizer.normalize_chunks(raw_list)
                        
                        # Apply to ChromaDB
                        store = ChromaVectorStore(collection_name=COLLECTION_NAME, persist_directory=str(BASE_DIR / ".chroma"))
                        existing_ids = store.collection.get().get("ids", [])
                        if existing_ids:
                            for b_idx in range(0, len(existing_ids), 500):
                                store.collection.delete(ids=existing_ids[b_idx : b_idx + 500])
                        
                        new_records = []
                        for c in normalized:
                            m = {}
                            for k, v in c.metadata.items():
                                if isinstance(v, (list, tuple)):
                                    m[k] = " > ".join(str(item) for item in v)
                                elif v is None:
                                    m[k] = ""
                                elif isinstance(v, (str, int, float, bool)):
                                    m[k] = v
                                else:
                                    m[k] = str(v)
                            new_records.append({"id": c.chunk_id, "text": c.text, "metadata": m})
                        
                        for b_idx in range(0, len(new_records), 100):
                            store.add_documents(new_records[b_idx : b_idx + 100])
                        
                        st.success(f"Successfully normalized and updated {len(normalized)} chunks in ChromaDB! Click 'Run Live 7-Param Audit' to see updated scores.")
                        st.rerun()
                    except Exception as err:
                        st.error(f"Normalization failed: {err}")


    if run_audit_btn:
        if df_chunks.empty:
            st.error("No chunks available in ChromaDB. Please ingest documents in Step 1 first.")
            return

        with st.spinner(f"Evaluating {len(df_chunks)} chunks through 7-parameter pipeline..."):
            try:
                new_report = execute_evaluation(
                    df_chunks,
                    sample_size=gate2_sample,
                    enable_reranker=use_reranker,
                )
                st.session_state["chunk_quality_7param_report"] = new_report
                # Save to disk as well
                out_path = Path(BASE_DIR) / "test_results" / "trial_chunk_quality_report.json"
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json.dumps(new_report, indent=2, default=str), encoding="utf-8")
                st.success("7-Parameter audit completed successfully!")
            except Exception as e:
                st.error(f"Audit execution failed: {e}")
                return

    report = st.session_state.get("chunk_quality_7param_report")
    if not report:
        st.info("💡 No audit report currently loaded. Click **'Run Live 7-Param Audit'** above or load an existing report.")
        return

    summary = report.get("summary", {})
    means = report.get("mean_scores", {})
    tstats = report.get("token_stats", {})
    flags = report.get("failure_flag_distribution", {})
    g2 = report.get("gate2_retrievability", {})
    worst_chunks = report.get("bottom_10_worst_chunks", [])

    cqi_score = summary.get("composite_quality_index", 0.0)
    grade = summary.get("quality_grade", "N/A")
    total_evaluated = summary.get("total_chunks_evaluated", 0)

    # -------------------------------------------------------------------------
    # Top KPI Row
    # -------------------------------------------------------------------------
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    
    grade_color = "#34D399" if cqi_score >= 85 else ("#FBBF24" if cqi_score >= 75 else "#EF4444")
    kpi1.metric(
        "Composite Quality (CQI)",
        f"{cqi_score:.1f} / 100",
        delta=f"Grade {grade.split(' ')[0]}",
        delta_color="normal" if cqi_score >= 80 else "inverse",
    )
    kpi2.metric(
        "Total Audited Chunks",
        f"{total_evaluated:,}",
        delta="100% Corpus Coverage",
    )
    
    trunc_count = tstats.get("exceeding_256_limit_count", 0)
    kpi3.metric(
        "Truncation Failures (>256)",
        f"{trunc_count}",
        delta=f"{(trunc_count / total_evaluated * 100):.1f}% silent clip" if total_evaluated else "0%",
        delta_color="inverse" if trunc_count > 0 else "normal",
    )

    sweet_pct = tstats.get("optimal_range_80_240_pct", 0.0)
    kpi4.metric(
        "Sweet Spot (80–240 tok)",
        f"{sweet_pct:.1f}%",
        delta=f"Median: {tstats.get('median_tokens', 0)} tok",
        delta_color="normal" if sweet_pct >= 60 else "inverse",
    )

    g2_mrr = g2.get("mean_mrr")
    kpi5.metric(
        "Gate 2 Retrievability",
        f"{g2_mrr:.3f} MRR" if g2_mrr is not None else "N/A",
        delta=f"{g2.get('chunks_sampled', 0)} Chunks Sampled",
        delta_color="normal" if g2_mrr and g2_mrr >= 0.75 else "off",
    )

    st.markdown("---")

    # -------------------------------------------------------------------------
    # Sub-tabs for deep inspection
    # -------------------------------------------------------------------------
    sub_tab1, sub_tab2, sub_tab3, sub_tab4, sub_tab5 = st.tabs([
        "📊 7 Core Parameter Scorecard",
        "📐 Token Budget & Truncation",
        "🚩 Diagnostic Failure Flags",
        "⚠️ Top 20 Worst Chunks & ChromaDB Restoration",
        "🔄 Gate 2 Retrieval Round-Trip",
    ])

    # -------------------------------------------------------------------------
    # SUB-TAB 1: 7 PARAMETER SCORECARD
    # -------------------------------------------------------------------------
    with sub_tab1:
        st.markdown("#### The 7 Core Architectural Parameters")
        st.caption("Each metric is calibrated against all-MiniLM-L6-v2 embedding geometry and BGE Cross-Encoder characteristics.")

        p_cols_row1 = st.columns(4)
        for i, p_def in enumerate(PARAMETER_DEFINITIONS[:4]):
            val = means.get(p_def["key"], 0.0)
            with p_cols_row1[i]:
                _render_parameter_card(p_def, val)

        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
        p_cols_row2 = st.columns(3)
        for i, p_def in enumerate(PARAMETER_DEFINITIONS[4:]):
            val = means.get(p_def["key"], 0.0)
            with p_cols_row2[i]:
                _render_parameter_card(p_def, val)

    # -------------------------------------------------------------------------
    # SUB-TAB 2: TOKEN BUDGET & TRUNCATION
    # -------------------------------------------------------------------------
    with sub_tab2:
        st.markdown("#### Token Distribution vs 256-Token Silent Truncation Limit")
        st.caption(
            "all-MiniLM-L6-v2 has a hard maximum sequence length of 256 word-piece tokens. "
            "Any tokens beyond 256 are discarded during embedding calculation without error!"
        )

        tb_c1, tb_c2, tb_c3, tb_c4 = st.columns(4)
        tb_c1.metric("Min / Max Tokens", f"{tstats.get('min_tokens', 0)} / {tstats.get('max_tokens', 0)}")
        tb_c2.metric("Mean Tokens", f"{tstats.get('mean_tokens', 0.0):.1f}")
        tb_c3.metric("P90 Tokens", f"{tstats.get('p90_tokens', 0)}")
        tb_c4.metric("Std Deviation", f"{tstats.get('std_tokens', 0.0):.1f}")

        if trunc_count > 0:
            st.error(
                f"🚨 **Critical Truncation Risk**: {trunc_count} chunks exceed the 256-token ceiling! "
                "These chunks suffer silent information loss in vector search. Enforce 200–220 token maximums in the chunker."
            )
        else:
            st.success("🟢 All chunks safely fit within the 256-token hard window.")

        # Token ranges breakdown table
        if not df_chunks.empty:
            tok_series = df_chunks["token_count"]
            ranges = [
                {"Zone": "🚨 Severe Truncation (> 256 tok)", "Count": (tok_series > 256).sum(), "Status": "FAIL (Silent Data Loss)"},
                {"Zone": "⚠️ Near Ceiling Warning (241–256 tok)", "Count": ((tok_series >= 241) & (tok_series <= 256)).sum(), "Status": "WARNING (Risk)"},
                {"Zone": "🟢 Optimal Sweet Spot (80–240 tok)", "Count": ((tok_series >= 80) & (tok_series <= 240)).sum(), "Status": "PASS (Ideal)"},
                {"Zone": "🟡 Below Sweet Spot (40–79 tok)", "Count": ((tok_series >= 40) & (tok_series < 80)).sum(), "Status": "ACCEPTABLE"},
                {"Zone": "🔴 Micro-Fragments (< 40 tok)", "Count": (tok_series < 40).sum(), "Status": "PENALTY (Consolidate)"},
            ]
            st.dataframe(pd.DataFrame(ranges), use_container_width=True)

    # -------------------------------------------------------------------------
    # SUB-TAB 3: DIAGNOSTIC FAILURE FLAGS
    # -------------------------------------------------------------------------
    with sub_tab3:
        st.markdown("#### Corpus Failure Flag Distribution")
        st.caption("Root-cause breakdown across all chunks. Use these findings to tune pre-ingestion processors.")

        flag_guidance = {
            "NO_INJECTED_HEADING_PREFIX": {
                "impact": "Chunks lack prepended hierarchy breadcrumbs (`[Leave Policy > Annual Leave]`).",
                "fix": "Enable bridge_linked_chunking.py or prepend hierarchy_path to chunk text.",
            },
            "NO_HIERARCHY_OR_SECTION": {
                "impact": "Metadata does not contain section heading or hierarchy breadcrumbs.",
                "fix": "Ensure Docling processor extracts heading hierarchy and attaches to ChunkMetadata.",
            },
            "LOW_COHERENCE": {
                "impact": "Mean consecutive-sentence similarity drops below 0.45.",
                "fix": "Align chunk boundaries with Markdown headings or paragraphs rather than token counts.",
            },
            "DANGLING_ANAPHORA_AT_START": {
                "impact": "Chunk begins with unresolved pronouns ('This', 'They', 'It') without context.",
                "fix": "Prepend parent section title to disambiguate the opening pronoun.",
            },
            "TOPIC_DRIFT_DETECTED": {
                "impact": "Consecutive sentences have near-orthogonal cosine similarity (< 0.22).",
                "fix": "Split the chunk at the paragraph boundary.",
            },
            "MICRO_FRAGMENT": {
                "impact": "Chunk is smaller than 40 tokens, lacking substantive information.",
                "fix": "Consolidate using semantic_merger.py with threshold 0.88.",
            },
            "HIGH_NEIGHBOR_SIMILARITY": {
                "impact": "Chunk is highly similar to its immediate neighbor (>= 0.80).",
                "fix": "Candidate for absorption via semantic_merger.py.",
            },
            "TRUNCATION_FAILURE": {
                "impact": "Chunk exceeds 256 word-piece tokens and is clipped by all-MiniLM-L6-v2.",
                "fix": "Reduce max chunk size in chunking_strategies.py to 220 tokens.",
            },
            "MID_SENTENCE_START": {
                "impact": "Chunk starts with lowercase letter or punctuation.",
                "fix": "Fix boundary splitter to respect sentence delimiters.",
            },
        }

        flag_rows = []
        for flg, cnt in flags.items():
            pct = (cnt / total_evaluated * 100) if total_evaluated else 0.0
            g_info = flag_guidance.get(flg, {"impact": "Quality defect", "fix": "Inspect chunk boundary"})
            flag_rows.append({
                "Failure Flag": flg,
                "Chunks Affected": cnt,
                "Corpus %": f"{pct:.1f}%",
                "RAG Retrieval Impact": g_info["impact"],
                "Recommended Architecture Fix": g_info["fix"],
            })

        if flag_rows:
            st.dataframe(pd.DataFrame(flag_rows), use_container_width=True)

    # -------------------------------------------------------------------------
    # SUB-TAB 4: TOP WORST CHUNKS & CHROMADB RESTORATION
    # -------------------------------------------------------------------------
    with sub_tab4:
        st.markdown("""
        <div style="margin-bottom: 12px;">
            <h4 style="margin: 0 0 4px 0; color: #F8FAFC; font-weight: 700;">
                🎯 Worst Scoring Chunks & ChromaDB Restoration Hub
            </h4>
            <div style="color: #94A3B8; font-size: 0.88rem;">
                Review the lowest-scoring chunks dragging down the Composite Quality Index (CQI).
                Inspect raw content and failure flags, and <b>add any chunk back to ChromaDB</b> if evaluated as <b>Good Enough</b>.
            </div>
        </div>
        """, unsafe_allow_html=True)

        ctrl_col1, ctrl_col2 = st.columns([1.5, 3.5])
        with ctrl_col1:
            worst_limit = st.selectbox(
                "Display Range",
                options=[20, 10, 50, 100],
                index=0,
                format_func=lambda n: f"Top {n} Worst Chunks",
                key="worst_chunks_display_limit",
            )

        all_cards = report.get("all_chunk_scorecards", [])
        if all_cards:
            sorted_worst = sorted(all_cards, key=lambda x: x.get("composite_intrinsic_score", 1.0))[:worst_limit]
        else:
            sorted_worst = (report.get("bottom_20_worst_chunks") or report.get("bottom_10_worst_chunks", []))[:worst_limit]

        if sorted_worst:
            worst_cids = [c["chunk_id"] for c in sorted_worst]
            chroma_status = get_chroma_chunk_presence(worst_cids)
            quarantined_dict = load_quarantined_chunks()

            in_chroma_count = sum(1 for cid in worst_cids if chroma_status.get(cid, False))
            quarantined_count = len(worst_cids) - in_chroma_count
            min_score = sorted_worst[0].get("composite_intrinsic_score", 0.0) if sorted_worst else 0.0

            stat1, stat2, stat3, stat4 = st.columns(4)
            stat1.metric("Worst Chunks Shown", f"{len(sorted_worst)}")
            stat2.metric(
                "Active in ChromaDB",
                f"{in_chroma_count}",
                delta="Indexed" if in_chroma_count > 0 else "0",
                delta_color="normal",
            )
            stat3.metric(
                "Quarantined / Missing",
                f"{quarantined_count}",
                delta="Excluded from RAG" if quarantined_count > 0 else "0",
                delta_color="inverse" if quarantined_count > 0 else "normal",
            )
            stat4.metric(
                "Lowest CQI Score",
                f"{min_score:.4f}",
                delta=f"Rank 1: {sorted_worst[0].get('chunk_id', '')[:20]}",
                delta_color="off",
            )

            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

            table_data = []
            for rank_idx, c in enumerate(sorted_worst, 1):
                cid = c.get("chunk_id", "")
                is_present = chroma_status.get(cid, False)
                status_text = "🟢 In ChromaDB" if is_present else ("🔴 Quarantined" if cid in quarantined_dict else "⚪ Missing")
                table_data.append({
                    "Rank": rank_idx,
                    "Chunk ID": cid,
                    "ChromaDB Status": status_text,
                    "Source Document": c.get("source_file"),
                    "Tokens": c.get("token_count"),
                    "Composite CQI": f"{c.get('composite_intrinsic_score', 0):.4f}",
                    "s_token": f"{c.get('s_token', 0):.2f}",
                    "s_bound": f"{c.get('s_bound', 0):.2f}",
                    "s_coh": f"{c.get('s_coh', 0):.2f}",
                    "s_dist": f"{c.get('s_dist', 0):.2f}",
                    "Failure Flags": ", ".join(c.get("failure_flags", []))[:65] + ("..." if len(", ".join(c.get("failure_flags", []))) > 65 else ""),
                })
            st.dataframe(pd.DataFrame(table_data), use_container_width=True, height=320)

            # Deep-Dive Chunk Inspector & Actions
            st.markdown("---")
            st.markdown("##### 🔬 Deep-Dive Chunk Inspector & ChromaDB Action")
            sel_cid = st.selectbox(
                "Select Worst Chunk to Review & Take Action",
                options=worst_cids,
                format_func=lambda cid: f"[{'🟢 In Chroma' if chroma_status.get(cid, False) else '🔴 Not in Chroma'}] {cid}",
                key="worst_chunk_inspector_select",
            )

            chosen_chunk = next((c for c in sorted_worst if c["chunk_id"] == sel_cid), None)
            if chosen_chunk:
                is_in_chroma_now = chroma_status.get(sel_cid, False)
                
                status_badge = (
                    '<span style="background: #064E3B; color: #6EE7B7; padding: 4px 10px; border-radius: 6px; font-weight: 600; font-size: 0.82rem; border: 1px solid #059669;">🟢 ACTIVE IN CHROMADB</span>'
                    if is_in_chroma_now
                    else '<span style="background: #7F1D1D; color: #FCA5A5; padding: 4px 10px; border-radius: 6px; font-weight: 600; font-size: 0.82rem; border: 1px solid #DC2626;">🔴 QUARANTINED / EXCLUDED FROM CHROMADB</span>'
                )

                st.markdown(f"""
                <div style="background: #0B132B; border: 1px solid #1E293B; border-radius: 8px; padding: 14px 18px; margin: 10px 0 16px 0;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-size: 1.05rem; font-weight: 700; color: #F8FAFC;">Chunk: <code>{chosen_chunk['chunk_id']}</code></span>
                        <span>{status_badge}</span>
                    </div>
                    <div style="color: #94A3B8; font-size: 0.86rem;">
                        <b>Source File:</b> <code>{chosen_chunk['source_file']}</code> &nbsp;|&nbsp; 
                        <b>Tokens:</b> {chosen_chunk['token_count']} &nbsp;|&nbsp; 
                        <b>Composite CQI:</b> <span style="color: #F59E0B; font-weight: 700;">{chosen_chunk['composite_intrinsic_score']:.4f}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Parameter Scores Row
                sc_c1, sc_c2, sc_c3, sc_c4, sc_c5, sc_c6 = st.columns(6)
                sc_c1.metric("Token Budget", f"{chosen_chunk.get('s_token', 0):.2f}")
                sc_c2.metric("Boundary", f"{chosen_chunk.get('s_bound', 0):.2f}")
                sc_c3.metric("Metadata", f"{chosen_chunk.get('s_meta', 0):.2f}")
                sc_c4.metric("Coherence", f"{chosen_chunk.get('s_coh', 0):.2f}")
                sc_c5.metric("Distinct", f"{chosen_chunk.get('s_dist', 0):.2f}")
                sc_c6.metric("Self-Contain", f"{chosen_chunk.get('s_self', 0):.2f}")

                flag_badges = " ".join([
                    f'<span style="background: #450A0A; color: #FECACA; padding: 3px 8px; border-radius: 4px; font-size: 0.78rem; font-weight: 600; border: 1px solid #991B1B;">{f}</span>'
                    for f in chosen_chunk.get("failure_flags", [])
                ])
                if flag_badges:
                    st.markdown(f"**Diagnostic Failure Flags**: {flag_badges}", unsafe_allow_html=True)

                # Locate chunk text
                found_text = None
                found_meta = {}
                if not df_chunks.empty:
                    match = df_chunks[df_chunks["chunk_id"] == sel_cid]
                    if not match.empty:
                        found_text = match.iloc[0]["text"]
                        found_meta = dict(match.iloc[0].to_dict())

                if not found_text and sel_cid in quarantined_dict:
                    found_text = quarantined_dict[sel_cid].get("text")
                    found_meta = quarantined_dict[sel_cid].get("metadata", {})

                if not found_text:
                    try:
                        from app.infrastructure.vector.chroma_client import ChromaVectorStore
                        st_temp = ChromaVectorStore(collection_name=COLLECTION_NAME, persist_directory=str(Path(BASE_DIR) / ".chroma"))
                        c_get = st_temp.collection.get(ids=[sel_cid], include=["documents", "metadatas"])
                        if c_get.get("documents"):
                            found_text = c_get["documents"][0]
                            found_meta = c_get["metadatas"][0] if c_get.get("metadatas") else {}
                    except Exception:
                        pass

                if not found_text:
                    found_text = chosen_chunk.get("text", "")

                # Text Content with inspection / editing option
                st.markdown("<div style='height: 6px;'></div>", unsafe_allow_html=True)
                chunk_content_input = st.text_area(
                    "Chunk Content (Inspect or Adjust before Adding Back)",
                    value=found_text or "(No text extracted)",
                    height=160,
                    key=f"chunk_content_area_{sel_cid}",
                )

                if chosen_chunk.get("synthetic_query"):
                    st.info(f"**Gate 2 Test Query**: `{chosen_chunk['synthetic_query']}`")

                # Action Buttons
                btn_col1, btn_col2, btn_col3 = st.columns([1.6, 1.6, 1.8])
                with btn_col1:
                    add_back_btn = st.button(
                        "✅ Add Back to ChromaDB (Good Enough)",
                        type="primary",
                        use_container_width=True,
                        help="Upserts this chunk back into ChromaDB with vector embeddings and marks it approved.",
                        key=f"btn_add_back_{sel_cid}",
                    )
                with btn_col2:
                    quarantine_btn = st.button(
                        "🗑️ Prune / Quarantine from ChromaDB",
                        type="secondary",
                        use_container_width=True,
                        help="Deletes chunk from ChromaDB to protect search quality and archives it in quarantine.",
                        key=f"btn_quarantine_{sel_cid}",
                    )
                with btn_col3:
                    if is_in_chroma_now:
                        st.caption("🟢 Currently active in ChromaDB. Click 'Prune' if you want to exclude it.")
                    else:
                        st.caption("🔴 Currently missing or quarantined. Click 'Add Back' to restore it.")

                if add_back_btn:
                    if not chunk_content_input.strip():
                        st.error("Cannot add an empty chunk to ChromaDB.")
                    else:
                        with st.spinner(f"Adding chunk '{sel_cid}' back to ChromaDB..."):
                            success, msg = add_chunk_to_chroma(
                                chunk_id=sel_cid,
                                text=chunk_content_input,
                                metadata=found_meta,
                                collection_name=COLLECTION_NAME,
                            )
                            if success:
                                st.toast(msg, icon="✅")
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

                if quarantine_btn:
                    with st.spinner(f"Quarantining chunk '{sel_cid}'..."):
                        success, msg = quarantine_chunk_from_chroma(
                            chunk_id=sel_cid,
                            text=chunk_content_input,
                            metadata=found_meta,
                            reason="Flagged as low quality in 7-Parameter Studio",
                            collection_name=COLLECTION_NAME,
                        )
                        if success:
                            st.toast(msg, icon="🗑️")
                            st.warning(msg)
                            st.rerun()
                        else:
                            st.error(msg)

            # Batch Operations Expander
            with st.expander("⚡ Batch Actions for Worst Chunks", expanded=False):
                st.markdown("Select multiple worst chunks to batch-restore or batch-quarantine in ChromaDB:")
                selected_batch_cids = st.multiselect(
                    "Select Chunks for Batch Operation",
                    options=worst_cids,
                    default=[],
                    key="batch_worst_chunks_multiselect",
                )
                b_act1, b_act2 = st.columns(2)
                with b_act1:
                    batch_add_btn = st.button(
                        "➕ Add Selected Back to ChromaDB (Good Enough)",
                        use_container_width=True,
                        key="btn_batch_add_worst",
                    )
                with b_act2:
                    batch_del_btn = st.button(
                        "🗑️ Quarantine Selected from ChromaDB",
                        use_container_width=True,
                        key="btn_batch_del_worst",
                    )

                if batch_add_btn:
                    if not selected_batch_cids:
                        st.warning("No chunks selected.")
                    else:
                        restored_cnt = 0
                        with st.spinner(f"Restoring {len(selected_batch_cids)} chunks to ChromaDB..."):
                            for cid in selected_batch_cids:
                                c_text = ""
                                c_meta = {}
                                if not df_chunks.empty:
                                    match = df_chunks[df_chunks["chunk_id"] == cid]
                                    if not match.empty:
                                        c_text = match.iloc[0]["text"]
                                        c_meta = dict(match.iloc[0].to_dict())
                                if not c_text and cid in quarantined_dict:
                                    c_text = quarantined_dict[cid].get("text", "")
                                    c_meta = quarantined_dict[cid].get("metadata", {})
                                if c_text:
                                    succ, _ = add_chunk_to_chroma(cid, c_text, c_meta, collection_name=COLLECTION_NAME)
                                    if succ:
                                        restored_cnt += 1
                        st.success(f"Successfully restored {restored_cnt} of {len(selected_batch_cids)} chunks to ChromaDB!")
                        st.rerun()

                if batch_del_btn:
                    if not selected_batch_cids:
                        st.warning("No chunks selected.")
                    else:
                        del_cnt = 0
                        with st.spinner(f"Quarantining {len(selected_batch_cids)} chunks..."):
                            for cid in selected_batch_cids:
                                c_text = ""
                                c_meta = {}
                                if not df_chunks.empty:
                                    match = df_chunks[df_chunks["chunk_id"] == cid]
                                    if not match.empty:
                                        c_text = match.iloc[0]["text"]
                                        c_meta = dict(match.iloc[0].to_dict())
                                succ, _ = quarantine_chunk_from_chroma(cid, c_text, c_meta, reason="Batch quarantined", collection_name=COLLECTION_NAME)
                                if succ:
                                    del_cnt += 1
                        st.warning(f"Successfully quarantined {del_cnt} of {len(selected_batch_cids)} chunks from ChromaDB.")
                        st.rerun()

    # -------------------------------------------------------------------------
    # SUB-TAB 5: GATE 2 RETRIEVAL ROUND-TRIP
    # -------------------------------------------------------------------------
    with sub_tab5:
        st.markdown("#### Gate 2: Reverse-Query Retrievability Diagnostics")
        st.caption(
            "Tests whether chunks can be discovered through the full 2-stage retrieval pipeline: "
            "Synthetic Query &rarr; Vector Top-15 &rarr; BGE Reranker Top-4."
        )

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Sampled Chunks", f"{g2.get('chunks_sampled', 0)}")
        r2.metric("Mean MRR@4", f"{g2.get('mean_mrr', 0.0):.3f}" if g2.get("mean_mrr") else "N/A")
        r3.metric("Rank-1 Direct Hits", f"{g2.get('rank_1_count', 0)}")
        r4.metric("Missed in Vector Top-15", f"{g2.get('missed_vector_count', 0)}", delta="Invisible to Search" if g2.get("missed_vector_count", 0) > 0 else "0 Misses")

        st.markdown("""
        <div style="background: #0D131F; border: 1px solid #1E293B; border-radius: 6px; padding: 14px; margin-top: 14px;">
            <div style="font-weight: 600; color: #F8FAFC; margin-bottom: 6px;">How Gate 2 Works:</div>
            <ol style="color: #94A3B8; font-size: 0.86rem; margin: 0; padding-left: 20px;">
                <li>Generates a realistic employee query targeting each sampled chunk using heading + key phrases.</li>
                <li>Performs cosine similarity search against the entire 606-chunk embedding matrix to identify Top-15 candidates.</li>
                <li>Reranks Top-15 candidates using <code>BAAI/bge-reranker-base</code> cross-encoder.</li>
                <li>Scores MRR (Mean Reciprocal Rank) based on the target chunk's final position in the Top-4 context window.</li>
            </ol>
        </div>
        """, unsafe_allow_html=True)


def _render_parameter_card(p_def: Dict[str, Any], val: float) -> None:
    """Helper to render an individual parameter metric card."""
    target_val = p_def["target_val"]
    is_pass = val >= target_val
    card_border = "#10B981" if is_pass else ("#F59E0B" if val >= target_val * 0.8 else "#EF4444")
    badge_bg = "#064E3B" if is_pass else ("#78350F" if val >= target_val * 0.8 else "#7F1D1D")
    badge_fg = "#A7F3D0" if is_pass else ("#FDE68A" if val >= target_val * 0.8 else "#FECACA")
    badge_text = "PASS" if is_pass else "NEEDS TUNING"

    st.markdown(f"""
    <div style="background: #0B111D; border: 1px solid {card_border}40; border-top: 3px solid {card_border}; border-radius: 6px; padding: 14px; min-height: 220px; display: flex; flex-direction: column; justify-content: space-between;">
        <div>
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
                <span style="font-weight: 700; color: #F8FAFC; font-size: 0.86rem; line-height: 1.2;">{p_def['label']}</span>
                <span style="background: {badge_bg}; color: {badge_fg}; font-size: 0.70rem; font-weight: 700; padding: 2px 6px; border-radius: 4px;">{badge_text}</span>
            </div>
            <div style="font-size: 0.72rem; color: #64748B; font-weight: 600; text-transform: uppercase; margin-bottom: 6px;">{p_def['tier']}</div>
            <div style="font-size: 0.76rem; color: #94A3B8; line-height: 1.35; margin-bottom: 10px;">{p_def['desc']}</div>
        </div>
        <div>
            <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px;">
                <span style="font-size: 1.35rem; font-weight: 700; color: #F8FAFC;">{val:.4f}</span>
                <span style="font-size: 0.76rem; color: #64748B;">Target: <b style="color: #CBD5E1;">{p_def['target']}</b></span>
            </div>
            <div style="font-size: 0.70rem; color: #EF4444; line-height: 1.25;">⚠️ {p_def['danger_note']}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
