"""
KnowLayer Developer Sandbox & Observability Suite
===================================================
A standalone, lightweight Streamlit workbench for inspecting and validating:
  1. Golden Test Data & ChromaDB Store Re-ingestion (Wipe & Re-index 12 Golden Docs)
  2. Live ChromaDB Chunks Explorer (Search by Chunk ID or text, filter, inspect, and CSV export)
  3. Chunk Quality Index (CQI) Diagnostics & Fragmentation Audit (with Stub Chunk ID inspector)
  4. 2-Stage Retrieval & Reranker Funnel (Bi-Encoder similarity -> BGE Cross-Encoder with Chunk IDs)
  5. Ground-Truth RAG Validation Benchmark Suite (Recall@k with required_chunk_ids)
# Hot-reload trigger: Language Consistency Rules updated
Port: 8502 (Standalone - does not require FastAPI or Docker)
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Add project root to sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Remove current directory from sys.path to avoid local module shadowing
_CURR_DIR = str(Path(__file__).resolve().parent)
if _CURR_DIR in sys.path:
    sys.path.remove(_CURR_DIR)

# pyrefly: ignore[missing-import]
import streamlit as st
# pyrefly: ignore[missing-source-for-stubs]
import pandas as pd
# pyrefly: ignore[missing-import, missing-source-for-stubs]
import numpy as np
# pyrefly: ignore[missing-source-for-stubs]
from app.core.settings import BASE_DIR, COLLECTION_NAME, EMBEDDING_MODEL
from app.infrastructure.vector.chroma_client import ChromaVectorStore
from app.infrastructure.vector.reranker_factory import get_reranker
from app.domain.entities.organization_models import Document
from app.infrastructure.ingestion.provisioner import provision_document
from app.infrastructure.document.processor_factory import build_document_processor
from app.use_cases.ingestion.document_processing import build_chunk_records_from_processed
from app.use_cases.chat.query_intent_classifier import get_query_intent_classifier
from app.infrastructure.document.chunking_strategies import (
    CHUNK_STRATEGIES_META,
    apply_chunking_strategy,
    estimate_tokens,
    ChunkRecord,
)
from app.infrastructure.document.bridge_linked_chunking import link_store_records_with_bridges
from app.infrastructure.document.plaintext_processor import extract_text_from_bytes
from sandbox.ui.test_studio import render_test_studio_tab
from sandbox.ui.home_dashboard import render_home_dashboard
from sandbox.components.ragas_studio import render_ragas_metrics_studio
from sandbox.components.ragas_eval import execute_ragas_evaluation
from sandbox.engine.schema import TestCase, TestInput, GoldEvidence, ExpectedBehavior
from sandbox.engine.ocr_vlm_scorer import audit_chunks_batch, audit_chunk_record
from app.infrastructure.ingestion.semantic_merger import (
    SemanticChunkMerger,
    SemanticMergeConfig,
    MergeResult,
    semantic_merge_chunk_records,
)
import importlib
import sandbox.engine.chunk_quality_framework
importlib.reload(sandbox.engine.chunk_quality_framework)
from sandbox.engine.chunk_quality_framework import (
    audit_corpus_comprehensive,
    audit_single_chunk,
    MetricResult,
    ChunkAuditReport,
    CorpusAuditReport,
)
CHUNK_QUALITY_METRICS_CATALOG = getattr(sandbox.engine.chunk_quality_framework, "CHUNK_QUALITY_METRICS_CATALOG", [])
get_metrics_catalog_dataframe = getattr(sandbox.engine.chunk_quality_framework, "get_metrics_catalog_dataframe", lambda: pd.DataFrame())
from sandbox.components.chunk_quality_studio import render_seven_parameter_quality_studio



# Page Configuration
st.set_page_config(
    page_title="KnowLayer • RAG & Chunk Sandbox",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling — Bespoke Anti-Slop Studio Design System
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

    /* Global Typography & Base Tokens */
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    code, pre, .chunk-id-tag, .font-mono {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Executive Studio Header */
    .workbench-header {
        background: #0D131F;
        border: 1px solid #1E293B;
        border-radius: 8px;
        padding: 1.2rem 1.6rem;
        margin-bottom: 1.4rem;
    }
    .brand-row {
        display: flex;
        align-items: center;
        gap: 0.8rem;
        margin-bottom: 0.35rem;
    }
    .brand-badge {
        background: #0284C7;
        color: #FFFFFF;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        padding: 3px 8px;
        border-radius: 4px;
    }
    .brand-title {
        font-size: 1.55rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        color: #F8FAFC;
    }
    .brand-version {
        font-size: 0.78rem;
        color: #64748B;
        font-weight: 500;
        margin-left: auto;
        font-family: 'JetBrains Mono', monospace;
    }
    .brand-subline {
        color: #94A3B8;
        font-size: 0.92rem;
        font-weight: 400;
        line-height: 1.45;
    }

    /* Sidebar Studio Branding */
    .sidebar-brand {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.4rem 0 1rem 0;
        margin-bottom: 0.6rem;
        border-bottom: 1px solid #1E293B;
    }
    .sidebar-logo {
        background: #0284C7;
        color: #FFFFFF;
        font-weight: 800;
        font-size: 1.05rem;
        width: 36px;
        height: 36px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 6px;
    }
    .sidebar-title {
        color: #F8FAFC;
        font-weight: 700;
        font-size: 1.0rem;
        line-height: 1.2;
    }
    .sidebar-sub {
        color: #64748B;
        font-size: 0.75rem;
        font-weight: 500;
    }

    /* Precision Telemetry Metrics (st.metric override) */
    div[data-testid="stMetric"] {
        background: #0D131F !important;
        border: 1px solid #1E293B !important;
        border-radius: 6px !important;
        padding: 12px 16px !important;
        box-shadow: none !important;
    }
    div[data-testid="stMetricLabel"] p {
        font-size: 0.76rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
        color: #94A3B8 !important;
        font-weight: 600 !important;
        margin-bottom: 4px !important;
    }
    div[data-testid="stMetricValue"] div {
        font-size: 1.45rem !important;
        font-weight: 700 !important;
        color: #F8FAFC !important;
        font-variant-numeric: tabular-nums !important;
    }

    /* Tabs Elevation */
    div[data-baseweb="tab-list"] {
        gap: 4px !important;
        background: #090D16 !important;
        padding: 4px !important;
        border-bottom: 1px solid #1E293B !important;
        margin-bottom: 1.2rem !important;
    }
    button[data-baseweb="tab"] {
        padding: 8px 16px !important;
        border-radius: 4px !important;
        font-size: 0.88rem !important;
        font-weight: 500 !important;
        color: #94A3B8 !important;
        background: transparent !important;
        border: none !important;
        transition: color 0.15s ease !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #F8FAFC !important;
        font-weight: 600 !important;
        background: #1E293B !important;
        border-bottom: 2px solid #38BDF8 !important;
    }

    /* Container & Card Framing */
    .metric-card {
        background: #0D131F;
        border: 1px solid #1E293B;
        border-radius: 6px;
        padding: 1rem;
        text-align: center;
    }
    .chunk-card {
        background: #0D131F;
        border: 1px solid #1E293B;
        border-radius: 6px;
        padding: 1.1rem;
        margin-bottom: 0.8rem;
    }
    .defect-card {
        background: #090E17;
        border: 1px solid #1E293B;
        border-radius: 6px;
        padding: 12px 16px;
        margin-bottom: 10px;
    }
    .defect-card.sev-critical, .defect-card.sev-high {
        border-left: 3px solid #EF4444;
    }
    .defect-card.sev-medium, .defect-card.sev-low {
        border-left: 3px solid #F59E0B;
    }
    .defect-quote {
        background: #040711;
        border: 1px solid #1E293B;
        border-radius: 4px;
        padding: 6px 10px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.8rem;
        color: #94A3B8;
        margin: 6px 0;
    }

    /* Dimension Health Cards */
    .dimension-card {
        background: #0B111D;
        border: 1px solid #1E293B;
        border-radius: 6px;
        padding: 12px 14px;
        margin-bottom: 8px;
    }
    .dimension-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 4px;
    }
    .dimension-title {
        font-weight: 700;
        font-size: 0.88rem;
        color: #F8FAFC;
    }
    .dimension-sub {
        color: #94A3B8;
        font-size: 0.73rem;
        line-height: 1.35;
        min-height: 32px;
        margin-bottom: 6px;
    }
    .dimension-stat-row {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
    }
    .dimension-pct {
        font-size: 1.3rem;
        font-weight: 700;
        color: #F8FAFC;
        font-variant-numeric: tabular-nums;
        font-family: 'JetBrains Mono', monospace;
    }
    .dimension-affected {
        font-size: 0.75rem;
        font-weight: 600;
    }

    /* Disposition Badges */
    .badge-disp-open { background: #1E293B; color: #CBD5E1; padding: 2px 6px; border-radius: 4px; font-size: 0.72rem; font-weight: 600; }
    .badge-disp-under-review { background: #78350F; color: #FDE68A; padding: 2px 6px; border-radius: 4px; font-size: 0.72rem; font-weight: 600; }
    .badge-disp-approved { background: #064E3B; color: #6EE7B7; padding: 2px 6px; border-radius: 4px; font-size: 0.72rem; font-weight: 600; }
    .badge-disp-needs-re-ocr { background: #4C1D95; color: #DDD6FE; padding: 2px 6px; border-radius: 4px; font-size: 0.72rem; font-weight: 600; }
    .badge-disp-needs-re-chunk { background: #831843; color: #FBCFE8; padding: 2px 6px; border-radius: 4px; font-size: 0.72rem; font-weight: 600; }
    .badge-disp-dismissed { background: #1E293B; color: #64748B; padding: 2px 6px; border-radius: 4px; font-size: 0.72rem; font-weight: 600; }

    /* Refined Status Badges */
    .badge-optimal {
        background: #064E3B;
        color: #34D399;
        padding: 2px 7px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.75rem;
        letter-spacing: 0.02em;
    }
    .badge-stub {
        background: #78350F;
        color: #FBBF24;
        padding: 2px 7px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.75rem;
        letter-spacing: 0.02em;
    }
    .badge-overflow {
        background: #7F1D1D;
        color: #F87171;
        padding: 2px 7px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.75rem;
        letter-spacing: 0.02em;
    }
    .chunk-id-tag {
        font-family: 'JetBrains Mono', monospace;
        background: #0F172A;
        color: #38BDF8;
        padding: 2px 6px;
        border-radius: 4px;
        border: 1px solid #0284C7;
        font-weight: 600;
        font-size: 0.82rem;
    }

    /* Tables & Expanders */
    div[data-testid="stExpander"] {
        border: 1px solid #1E293B !important;
        border-radius: 6px !important;
        background: #0D131F !important;
    }
    div[data-testid="stExpander"] summary {
        color: #F1F5F9 !important;
        font-weight: 600 !important;
        padding: 10px 14px !important;
    }

    /* Inputs & Select Boxes */
    div[data-baseweb="input"], div[data-baseweb="select"] {
        background: #0A0E17 !important;
        border-color: #1E293B !important;
        border-radius: 5px !important;
    }
    div[data-baseweb="input"]:focus-within, div[data-baseweb="select"]:focus-within {
        border-color: #0284C7 !important;
    }
</style>
""", unsafe_allow_html=True)


# Project Scopes Mapping for Golden Documents
PROJECT_SCOPES = {
    "TEST-001.docx": "121",
    "DOC-002.docx": "121",
    "DOC-003.docx": "121",
    "DOC-006.docx": "121",
}


def get_chunk_disposition(chunk_id: str) -> dict:
    if "chunk_dispositions" not in st.session_state:
        st.session_state["chunk_dispositions"] = {}
    return st.session_state["chunk_dispositions"].get(chunk_id, {"status": "Open", "notes": ""})


def set_chunk_disposition(chunk_id: str, status: str, notes: str = ""):
    if "chunk_dispositions" not in st.session_state:
        st.session_state["chunk_dispositions"] = {}
    st.session_state["chunk_dispositions"][chunk_id] = {
        "status": status,
        "notes": notes,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_disposition_badge_html(status: str) -> str:
    s_clean = status.lower().replace(" ", "-")
    cls_map = {
        "open": "badge-disp-open",
        "under-review": "badge-disp-under-review",
        "approved": "badge-disp-approved",
        "needs-re-ocr": "badge-disp-needs-re-ocr",
        "needs-re-chunk": "badge-disp-needs-re-chunk",
        "dismissed": "badge-disp-dismissed",
    }
    css_class = cls_map.get(s_clean, "badge-disp-open")
    return f'<span class="{css_class}">{status.upper()}</span>'


@st.cache_resource
def get_chroma_store():
    return ChromaVectorStore(
        collection_name=COLLECTION_NAME,
        persist_directory=str(BASE_DIR / ".chroma"),
    )


@st.cache_resource
def get_cached_reranker():
    return get_reranker()


@st.cache_data(ttl=15)
def load_all_chunks():
    store = get_chroma_store()
    try:
        data = store.collection.get(include=["documents", "metadatas"])
    except Exception as e:
        # Auto-recover from stale cached handle or recreated collections
        try:
            get_chroma_store.clear()
            store = get_chroma_store()
            data = store.refresh_collection().get(include=["documents", "metadatas"])
        except Exception as e2:
            st.error(f"Failed to fetch chunks from ChromaDB: {e2}")
            return pd.DataFrame()

    try:
        records = []
        ids = data.get("ids", [])
        documents = data.get("documents", [])
        metadatas = data.get("metadatas", [])
        for chunk_id, text, meta in zip(ids, documents, metadatas):
            meta = meta or {}
            tokens = len(text.split())
            records.append({
                "chunk_id": chunk_id,
                "text": text,
                "token_count": tokens,
                "char_count": len(text),
                "doc_id": meta.get("doc_id", meta.get("document_id", "unknown")),
                "source": meta.get("source", "unknown"),
                "department": meta.get("department", "unassigned"),
                "classification": meta.get("classification", "Public"),
                "project_id": str(meta.get("project_id", "unassigned")),
                "hierarchy_path": str(meta.get("hierarchy_path", "")),
                "heading_text": str(meta.get("heading_text", "")),
                "produced_by": str(meta.get("produced_by", "")),
                "route": str(meta.get("route", "")),
                "content_type": str(meta.get("content_type", "text")),
                "layout_type": str(meta.get("layout_type", "")),
                "bbox": str(meta.get("bbox", "")),
                "is_table": bool(meta.get("is_table", False)),
            })
        return pd.DataFrame(records)
    except Exception as e:
        st.error(f"Failed to parse chunks from ChromaDB: {e}")
        return pd.DataFrame()



def get_golden_files_info():
    data_dir = _REPO_ROOT / "test_data"
    supported_ext = {".docx", ".pdf", ".txt", ".md"}
    items = []
    if data_dir.exists():
        for f in sorted(data_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in supported_ext and f.name != "MANIFEST.md":
                sz_kb = f.stat().st_size / 1024
                sz_str = f"{sz_kb / 1024:.2f} MB" if sz_kb > 1024 else f"{sz_kb:.1f} KB"
                items.append({
                    "Filename": f.name,
                    "Type": f.suffix.upper().lstrip("."),
                    "Size": sz_str,
                    "Chunk ID Pattern": f"{f.stem}-*",
                    "Scope": PROJECT_SCOPES.get(f.name, "unassigned"),
                })
    return items


def wipe_and_reingest_golden_docs(progress_bar, status_text, enable_semantic_merging: bool = True):
    """Safely wipe collection and cleanly index all documents from test_data/."""
    data_dir = _REPO_ROOT / "test_data"
    get_chroma_store.clear()
    store = get_chroma_store()
    try:
        store.client.delete_collection(name=store.collection_name)
    except Exception:
        pass

    store.refresh_collection()
    get_chroma_store.clear()
    st.cache_data.clear()

    supported_ext = {".docx", ".pdf", ".txt", ".md"}
    doc_files = [
        f for f in sorted(data_dir.iterdir())
        if f.is_file() and f.suffix.lower() in supported_ext and f.name != "MANIFEST.md"
    ]
    processor = build_document_processor()
    total_chunks = 0
    t0 = time.time()
    summary = []

    for idx, f in enumerate(doc_files):
        status_text.text(f"Ingesting [{idx+1}/{len(doc_files)}]: {f.name}...")
        p_id = PROJECT_SCOPES.get(f.name, "unassigned")
        doc_entity = Document(
            document_id=f.stem,
            document_name=f.name,
            project_id=p_id,
            original_filename=f.name,
            file_type=f.suffix.lower().lstrip("."),
            version="1.0",
        )
        t_file = time.time()
        chunks_cnt = provision_document(
            source_path=f,
            document=doc_entity,
            store=store,
            processor=processor,
            enable_semantic_merging=enable_semantic_merging,
        )
        el = time.time() - t_file
        total_chunks += chunks_cnt
        summary.append({
            "Document": f.name,
            "Chunk ID Range": f"{f.stem}-0 .. {f.stem}-{chunks_cnt-1}" if chunks_cnt > 0 else "None",
            "Scope": p_id,
            "Chunks": chunks_cnt,
            "Time (s)": round(el, 2),
        })
        progress_bar.progress((idx + 1) / len(doc_files))

    elapsed = time.time() - t0
    status_text.empty()
    get_chroma_store.clear()
    st.cache_data.clear()
    st.cache_resource.clear()
    return total_chunks, elapsed, summary


def process_document_to_chunks(
    raw_bytes: bytes,
    file_name: str,
    doc_id: str,
    department: str = "Human Resources",
    classification: str = "Internal",
    project_id: str = "unassigned",
    version: str = "1.0",
    enable_semantic_merging: bool = False,
    merge_config: Optional[SemanticMergeConfig] = None,
    chunking_strategy: Optional[str] = None,
    target_tokens: Optional[int] = None,
    overlap_pct: Optional[int] = None,
) -> tuple[list[dict], Optional[MergeResult]]:
    """Parse document, optionally apply custom chunking strategy and semantic merging, and construct canonical chunk records."""
    processor = build_document_processor()
    resolved_file_type = Path(file_name).suffix.lower().lstrip(".")

    if chunking_strategy and chunking_strategy != "canonical_processor" and chunking_strategy in CHUNK_STRATEGIES_META:
        try:
            full_text = extract_text_from_bytes(raw_bytes, file_name)
        except Exception:
            processed = processor.process(raw_bytes, file_name)
            full_text = "\n\n".join(c.text for c in processed.chunks)

        strat_meta = CHUNK_STRATEGIES_META[chunking_strategy]
        tokens = target_tokens or strat_meta["optimal_tokens"]
        overlap = overlap_pct if overlap_pct is not None else strat_meta["default_overlap_pct"]

        strat_chunks = apply_chunking_strategy(
            strategy_key=chunking_strategy,
            text=full_text,
            target_tokens=tokens,
            overlap_pct=overlap,
            doc_prefix=doc_id,
        )

        records = [
            {
                "id": f"{doc_id}-{idx}",
                "text": sc.text,
                "metadata": {
                    "document_id": doc_id,
                    "doc_id": doc_id,
                    "source_filename": file_name,
                    "source": file_name,
                    "page_number": 1,
                    "chunk_index": idx,
                    "chunk_id": f"{doc_id}-{idx}",
                    "token_count": sc.token_count,
                    "department": department,
                    "classification": classification,
                    "project_id": project_id,
                    "version": version,
                    "file_type": resolved_file_type,
                    "strategy": getattr(sc, "strategy", getattr(sc, "strategy_name", "unknown")),
                    "heading_text": sc.heading_hierarchy or "",
                    "hierarchy_path": sc.heading_hierarchy or "",
                    "content_type": "text",
                    "parent_id": getattr(sc, "parent_id", None) or (sc.metadata.get("parent_id") if hasattr(sc, "metadata") else None),
                    "parent_text": getattr(sc, "parent_text", None) or (sc.metadata.get("parent_text") if hasattr(sc, "metadata") else None),
                },
            }
            for idx, sc in enumerate(strat_chunks)
        ]
    else:
        processed = processor.process(raw_bytes, file_name)
        records = build_chunk_records_from_processed(
            processed,
            document_id=doc_id,
            project_id=project_id,
            source=file_name,
            file_type=resolved_file_type,
            version=version,
        )
        for r in records:
            r["metadata"]["doc_id"] = doc_id
            r["metadata"]["department"] = department
            r["metadata"]["classification"] = classification
            r["metadata"]["project_id"] = project_id
            r["metadata"]["source"] = file_name
            r["metadata"]["version"] = version
            hp = r["metadata"].get("hierarchy_path")
            if isinstance(hp, (list, tuple)):
                r["metadata"]["hierarchy_path"] = " > ".join(str(x) for x in hp)
            elif hp is None:
                r["metadata"]["hierarchy_path"] = ""

    merge_res = None
    if enable_semantic_merging and len(records) > 1:
        cfg = merge_config or SemanticMergeConfig(scope_field="document_id")
        records, merge_res = semantic_merge_chunk_records(records, config=cfg)

    # Establish Doubly Linked List pointers and typed boundary bridges across all chunks
    if records:
        records = link_store_records_with_bridges(records, doc_id=doc_id)

    return records, merge_res


def render_golden_data_and_ingestion(df_chunks: pd.DataFrame):
    st.subheader("📁 Step 1 · Document Ingestion & Chunk Provisioning")
    st.info(
        "💡 **Usage Guide — Step 1:** "
        "Upload raw policy documents (`.docx`, `.pdf`, `.txt`) or inspect existing golden documents. "
        "Choose appropriate chunking strategies with token budgets (<=256 tokens) to prevent silent model truncation. "
        "Use the safety-guarded button below if you need a clean re-index of the ChromaDB collection.",
        icon="ℹ️",
    )
    st.caption("Manage curated golden documents in `test_data/`, wipe & re-index ChromaDB, or provision custom test policies.")

    # Overview Metrics
    golden_files = get_golden_files_info()
    stored_doc_ids = df_chunks["source"].unique().tolist() if not df_chunks.empty else []

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Golden Documents", f"{len(golden_files)} files")
    m2.metric("ChromaDB Active Chunks", f"{len(df_chunks):,}")
    m3.metric("Indexed Sources", f"{len(stored_doc_ids)}")
    m4.metric("Scoping Protection", "4 RBAC Docs (121)")

    st.markdown("---")

    # Section 1: Golden Document Catalog & One-Click Wipe & Reingest
    st.markdown("### 📚 Golden Dataset Catalog & Store Reset")
    st.markdown("Wipe the entire Chroma vector store and re-ingest all curated test documents with canonical metadata and RBAC scoping.")

    c_btn, c_chk = st.columns([1.2, 2.8])
    with c_chk:
        safety_agreed = st.checkbox(
            "⚠️ Confirm destructive operation: wipe all vectors in collection `hr_policy_docs`",
            value=False,
            help="Prevents accidental vector store loss during benchmarking.",
        )
        enable_semantic_merging_golden = st.toggle(
            "🔀 Apply Semantic Chunk Merging on Ingestion",
            value=True,
            help="Consolidate micro-fragments and stub chunks (<250 chars) into similar parent chunks before indexing to ChromaDB.",
            key="toggle_semantic_merging_golden",
        )
    with c_btn:
        wipe_confirmed = st.button(
            "🧹 Wipe Store & Re-ingest All Golden Documents",
            type="primary",
            disabled=not safety_agreed,
            use_container_width=True,
        )

    if wipe_confirmed and safety_agreed:
        with st.status("Executing clean ChromaDB wipe and re-indexing...", expanded=True) as status_box:
            prog_bar = st.progress(0)
            status_txt = st.empty()
            total_chunks, elapsed, summary = wipe_and_reingest_golden_docs(
                prog_bar,
                status_txt,
                enable_semantic_merging=enable_semantic_merging_golden,
            )
            status_box.update(label=f"Ingestion complete: {total_chunks} chunks indexed in {elapsed:.2f}s!", state="complete")

        st.success(f"🎉 Successfully re-indexed **{len(summary)} documents** into ChromaDB ({total_chunks} chunks stored) in {elapsed:.2f}s!")
        st.dataframe(pd.DataFrame(summary), use_container_width=True)
        st.rerun()

    # Catalog Table & Manifest Preview
    col_cat1, col_cat2 = st.columns([1.4, 0.6])
    with col_cat1:
        st.markdown("**Documents in `test_data/`:**")
        df_golden = pd.DataFrame(golden_files)
        if not df_chunks.empty:
            df_golden["Chroma Status"] = df_golden["Filename"].apply(
                lambda fn: "Indexed" if fn in stored_doc_ids else "Not Indexed"
            )
            def compute_cid_range(fn):
                matched = df_chunks[df_chunks["source"] == fn]
                if not matched.empty:
                    cids = matched["chunk_id"].tolist()
                    return f"{cids[0]} .. {cids[-1]}"
                return f"{Path(fn).stem}-*"
            df_golden["Chunk ID Range"] = df_golden["Filename"].apply(compute_cid_range)
            col_order = ["Filename", "Chunk ID Range", "Chunk ID Pattern", "Type", "Size", "Chroma Status", "Scope"]
            valid_cols = [c for c in col_order if c in df_golden.columns]
            df_golden = df_golden[valid_cols]
        st.dataframe(df_golden, use_container_width=True, height=210)

    with col_cat2:
        manifest_path = _REPO_ROOT / "test_data" / "MANIFEST.md"
        with st.expander("📖 View Catalog Manifest (`MANIFEST.md`)", expanded=False):
            if manifest_path.exists():
                st.markdown(manifest_path.read_text(encoding="utf-8"))
            else:
                st.info("MANIFEST.md not found.")

    if not df_chunks.empty:
        with st.expander("👁️ Preview Existing Chunks in ChromaDB", expanded=True):
            st.caption("Browse, inspect, and verify chunks already indexed in ChromaDB without needing to re-upload or re-process.")

            c_doc_pick, c_filter_pick = st.columns([2, 1.5])
            with c_doc_pick:
                idx_docs = sorted(df_chunks["source"].dropna().unique().tolist())
                chosen_idx_doc = st.selectbox(
                    "Select Indexed Document to Preview",
                    idx_docs,
                    format_func=lambda s: f"{s} ({len(df_chunks[df_chunks['source'] == s])} chunks)",
                    key="step1_doc_select",
                )
            with c_filter_pick:
                filter_text = st.text_input(
                    "Search within Document Chunks",
                    placeholder="Search Chunk ID or text...",
                    key="step1_existing_filter",
                )

            matched_rows = df_chunks[df_chunks["source"] == chosen_idx_doc].copy().reset_index(drop=True)

            if filter_text.strip():
                f_kw = filter_text.strip().lower()
                display_rows = matched_rows[
                    matched_rows["chunk_id"].str.lower().str.contains(f_kw) |
                    matched_rows["text"].str.lower().str.contains(f_kw) |
                    matched_rows["hierarchy_path"].astype(str).str.lower().str.contains(f_kw)
                ].copy().reset_index(drop=True)
            else:
                display_rows = matched_rows

            if display_rows.empty:
                st.warning(f"No chunks in '{chosen_idx_doc}' matched the search query '{filter_text}'.")
            else:
                # Summary metrics row for this document
                tok_counts = [len(t.split()) for t in display_rows["text"]]
                avg_tok = sum(tok_counts) / len(tok_counts) if tok_counts else 0
                max_tok = max(tok_counts) if tok_counts else 0
                compliant_cnt = sum(1 for t in tok_counts if t <= 256)
                compliance_pct = (compliant_cnt / len(tok_counts)) * 100 if tok_counts else 0
                first_cid = display_rows.iloc[0]["chunk_id"]
                last_cid = display_rows.iloc[-1]["chunk_id"]
                cid_span = f"`{first_cid}` .. `{last_cid}`" if len(display_rows) > 1 else f"`{first_cid}`"

                cm1, cm2, cm3, cm4, cm5 = st.columns(5)
                cm1.metric("Indexed Chunks", f"{len(display_rows)}", f"of {len(matched_rows)}" if len(display_rows) != len(matched_rows) else None)
                cm2.metric("Avg Token Length", f"{avg_tok:.1f} tok")
                cm3.metric("Max Token Length", f"{max_tok} tok", delta="Over 256!" if max_tok > 256 else "Within Budget", delta_color="inverse" if max_tok > 256 else "normal")
                cm4.metric("Token Compliance", f"{compliance_pct:.1f}%", f"{compliant_cnt}/{len(tok_counts)}")
                cm5.metric("Chunk ID Span", f"{len(display_rows)} chunks", help=f"Span: {cid_span}")

                # Chunk selector & step buttons
                st.markdown("---")
                nav_col1, nav_col2, nav_col3 = st.columns([1.5, 3.5, 1.5])

                # Manage chunk navigation index in session state
                doc_state_key = f"step1_chunk_idx_{chosen_idx_doc}"
                if doc_state_key not in st.session_state:
                    st.session_state[doc_state_key] = 0

                # Ensure within bounds
                if st.session_state[doc_state_key] >= len(display_rows):
                    st.session_state[doc_state_key] = 0

                with nav_col1:
                    st.write("")
                    st.write("")
                    if st.button("⬅️ Previous Chunk", key="btn_prev_existing_chunk", disabled=(st.session_state[doc_state_key] <= 0), use_container_width=True):
                        st.session_state[doc_state_key] = max(0, st.session_state[doc_state_key] - 1)
                        st.rerun()

                with nav_col2:
                    chunk_options = [
                        (idx, f"#{idx+1} · {row['chunk_id']} ({len(row['text'].split())} tok) — {row.get('heading_text') or row.get('hierarchy_path') or row['text'][:50]}...")
                        for idx, row in display_rows.iterrows()
                    ]
                    selected_opt_idx = st.selectbox(
                        f"Select Chunk to Preview ({st.session_state[doc_state_key] + 1} of {len(display_rows)})",
                        options=[idx for idx, _ in chunk_options],
                        index=st.session_state[doc_state_key],
                        format_func=lambda idx: dict(chunk_options)[idx],
                        key="step1_chunk_selector_box",
                    )
                    st.session_state[doc_state_key] = selected_opt_idx

                with nav_col3:
                    st.write("")
                    st.write("")
                    if st.button("Next Chunk ➡️", key="btn_next_existing_chunk", disabled=(st.session_state[doc_state_key] >= len(display_rows) - 1), use_container_width=True):
                        st.session_state[doc_state_key] = min(len(display_rows) - 1, st.session_state[doc_state_key] + 1)
                        st.rerun()

                # Current chunk details
                curr_row = display_rows.iloc[st.session_state[doc_state_key]]
                c_tokens = len(curr_row["text"].split())
                c_chars = len(curr_row["text"])
                c_hierarchy = curr_row.get("hierarchy_path", "")
                c_heading = curr_row.get("heading_text", "")
                c_scope = curr_row.get("project_id", "unassigned")
                c_dept = curr_row.get("department", "Human Resources")
                c_class = curr_row.get("classification", "Internal")

                # Visual badges bar
                st.markdown(f"""
                <div style="background-color: #0E1726; border: 1px solid #1E293B; border-radius: 8px; padding: 12px 16px; margin: 10px 0;">
                    <div style="display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px;">
                        <div>
                            <span style="background: #0284C7; color: white; padding: 3px 8px; border-radius: 4px; font-weight: 700; font-size: 0.82rem; font-family: monospace;">🧩 {curr_row['chunk_id']}</span>
                            &nbsp;<span style="background: #1E293B; color: #94A3B8; padding: 3px 8px; border-radius: 4px; font-size: 0.78rem;">Chunk {st.session_state[doc_state_key] + 1} of {len(display_rows)}</span>
                        </div>
                        <div style="font-size: 0.8rem; color: #94A3B8;">
                            📏 <b style="color: {'#38BDF8' if c_tokens <= 256 else '#EF4444'};">{c_tokens} tokens</b> &nbsp;|&nbsp; 
                            🔤 {c_chars} chars &nbsp;|&nbsp; 
                            📁 Project: <code>{c_scope}</code> &nbsp;|&nbsp; 
                            🏢 Dept: <code>{c_dept}</code> &nbsp;|&nbsp; 
                            🔒 Classification: <code>{c_class}</code>
                        </div>
                    </div>
                    {f'<div style="font-size: 0.83rem; color: #38BDF8; margin-top: 4px;">🧭 <b>Heading Breadcrumbs:</b> <code>{c_hierarchy or c_heading}</code></div>' if (c_hierarchy or c_heading) else ''}
                </div>
                """, unsafe_allow_html=True)

                st.text_area(
                    label=f"Chunk Content ({curr_row['chunk_id']})",
                    value=curr_row["text"],
                    height=180,
                    disabled=True,
                    key=f"preview_chunk_text_{curr_row['chunk_id']}",
                )

                with st.expander("🔍 View Raw Chunk Metadata JSON", expanded=False):
                    chunk_meta = {
                        "chunk_id": curr_row["chunk_id"],
                        "doc_id": curr_row.get("doc_id", ""),
                        "source": curr_row.get("source", ""),
                        "tokens": c_tokens,
                        "chars": c_chars,
                        "hierarchy_path": c_hierarchy,
                        "heading_text": c_heading,
                        "project_id": c_scope,
                        "department": c_dept,
                        "classification": c_class,
                        "produced_by": curr_row.get("produced_by", ""),
                        "route": curr_row.get("route", ""),
                        "content_type": curr_row.get("content_type", "text"),
                    }
                    st.json(chunk_meta)

                # Chunk Inventory Table for this document
                with st.expander(f"📋 View All {len(display_rows)} Chunks in `{chosen_idx_doc}` (Table)", expanded=False):
                    tbl_data = []
                    for i, r in display_rows.iterrows():
                        tbl_data.append({
                            "Index": i + 1,
                            "Chunk ID": r["chunk_id"],
                            "Tokens": len(r["text"].split()),
                            "Heading / Hierarchy": r.get("hierarchy_path") or r.get("heading_text") or "-",
                            "Snippet": r["text"][:100] + ("..." if len(r["text"]) > 100 else ""),
                        })
                    st.dataframe(pd.DataFrame(tbl_data), use_container_width=True, height=220)

                # Dual Actions Row
                col_act1, col_act2 = st.columns([1.5, 1.5])
                with col_act1:
                    if st.button("🔬 Load into Full 6-Dimension Quality Audit Workspace", key="btn_load_step1_audit", type="primary", use_container_width=True):
                        recs = [
                            {
                                "id": r["chunk_id"],
                                "text": r["text"],
                                "metadata": {
                                    "doc_id": r.get("doc_id", ""),
                                    "source": r.get("source", ""),
                                    "hierarchy_path": r.get("hierarchy_path", ""),
                                    "heading_text": r.get("heading_text", ""),
                                    "project_id": r.get("project_id", "unassigned"),
                                    "department": r.get("department", "Human Resources"),
                                    "classification": r.get("classification", "Internal"),
                                }
                            }
                            for _, r in matched_rows.iterrows()
                        ]
                        st.session_state["active_chunk_results"] = {
                            "records": recs,
                            "doc_id": matched_rows.iloc[0].get("doc_id", Path(chosen_idx_doc).stem),
                            "source": chosen_idx_doc,
                            "persisted": True,
                            "time_sec": 0.0,
                        }
                        st.success(f"Loaded {len(recs)} chunks of '{chosen_idx_doc}' into the Quality Audit workspace below!")
                        st.rerun()

                with col_act2:
                    if st.button("🧪 Pre-fill Benchmark Test with this Document", key="btn_prefill_bench_from_preview", use_container_width=True):
                        all_ids = matched_rows["chunk_id"].tolist()
                        st.session_state["benchmark_prefill"] = {
                            "expected_document": chosen_idx_doc,
                            "doc_id": matched_rows.iloc[0].get("doc_id", Path(chosen_idx_doc).stem),
                            "chunk_ids": all_ids[:2] if len(all_ids) >= 2 else all_ids,
                            "all_chunk_ids": all_ids,
                            "project_id": matched_rows.iloc[0].get("project_id", "unassigned"),
                        }
                        st.success(f"Pre-filled benchmark draft for '{chosen_idx_doc}'! Switch to Tab 5 (🧪 RAG Benchmark Suite) to finalize.")
    else:
        st.info("ℹ️ ChromaDB is currently empty. Re-ingest golden documents above or add a custom document below to preview chunks.")

    st.markdown("---")

    # Section 2: Ingest Single / Custom Document
    st.markdown("### ➕ Add / Chunk Custom Document")
    st.caption("Upload a new file or draft policy text to inspect chunk boundaries and optionally persist to ChromaDB.")

    col_input, col_meta = st.columns([1.1, 0.9])

    with col_input:
        input_mode = st.radio(
            "Input Mode",
            ["📁 File Upload (.docx, .pdf, .txt, .md)", "✍️ Paste Plaintext / Markdown"],
            horizontal=True,
        )

        raw_bytes = None
        detected_filename = ""
        suggested_doc_id = ""

        if "File Upload" in input_mode:
            uploaded_file = st.file_uploader(
                "Select File",
                type=["docx", "pdf", "txt", "md", "rst"],
                help="Supports DOCX, PDF, Markdown, Plain Text",
            )
            if uploaded_file is not None:
                raw_bytes = uploaded_file.getvalue()
                detected_filename = uploaded_file.name
                suggested_doc_id = Path(detected_filename).stem.replace(" ", "_")
        else:
            pasted_text = st.text_area(
                "Document Content",
                height=180,
                placeholder="# Remote Work & Attendance Policy 2026\n\n## Section 1: Eligibility\nAll full-time employees who have completed probation may request hybrid work...",
            )
            default_pasted_name = st.text_input("Virtual Filename", value="New_Policy.md")
            if pasted_text.strip():
                raw_bytes = pasted_text.strip().encode("utf-8")
                detected_filename = default_pasted_name.strip() or "pasted_document.md"
                suggested_doc_id = Path(detected_filename).stem.replace(" ", "_")

    with col_meta:
        st.markdown("**Metadata & RBAC Scoping**")
        doc_id = st.text_input(
            "Document ID (Unique Identifier)",
            value=suggested_doc_id or "NEW_DOC_001",
            help="Alphanumeric identifier used to scope chunks in ChromaDB",
        )
        source_name = st.text_input(
            "Display Source Filename",
            value=detected_filename or f"{doc_id}.docx",
            help="Filename stored in chunk metadata for citations",
        )
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            department = st.selectbox(
                "Department",
                ["Human Resources", "Engineering", "Operations", "Finance", "Legal", "IT & Security", "Executive"],
                index=0,
            )
            classification = st.selectbox(
                "Classification",
                ["Internal", "Confidential", "Public", "Restricted"],
                index=0,
            )
        with col_m2:
            project_id = st.text_input(
                "Project Scope (RBAC)",
                value="unassigned",
                help="'unassigned' is accessible to all employees; specific IDs (e.g. '121') enforce confidential RBAC",
            )
            version = st.text_input("Version", value="1.0")

        # Semantic Chunk Merging Toggle & Options
        st.markdown("---")
        st.markdown("##### 🔀 Semantic Chunk Merging (Pairwise Consolidation)")
        col_sm_t, col_sm_info = st.columns([1.6, 2.4])
        with col_sm_t:
            enable_custom_semantic_merging = st.toggle(
                "Apply Semantic Chunk Merging",
                value=True,
                help="Consolidates micro-fragments and stub chunks (<250 chars) into similar parent chunks before indexing.",
                key="toggle_custom_semantic_merging",
            )
        with col_sm_info:
            if enable_custom_semantic_merging:
                st.caption("🟢 **Enabled**: Micro-fragments (<250 chars) will be consolidated into similar parent chunks (<=1200 chars).")
            else:
                st.caption("⚪ **Disabled**: Standard chunking only (no fragment consolidation).")

        custom_merge_cfg = None
        if enable_custom_semantic_merging:
            with st.expander("⚙️ Advanced Semantic Merging Parameters (Optional)", expanded=False):
                col_sp1, col_sp2 = st.columns(2)
                with col_sp1:
                    custom_sim_thresh = st.slider("Cosine Similarity Threshold", 0.70, 0.99, 0.88, 0.01, key="custom_merge_sim")
                    custom_x_cap = st.number_input("Max Merged Length (X chars)", 400, 3000, 1200, 100, key="custom_merge_x")
                with col_sp2:
                    custom_y_absorber = st.number_input("Absorber Limit (Y chars)", 200, 2000, 800, 50, key="custom_merge_y")
                    custom_z_candidate = st.number_input("Candidate Max (Z chars)", 50, 800, 250, 25, key="custom_merge_z")
                custom_merge_cfg = SemanticMergeConfig(
                    max_chunk_chars=int(custom_x_cap),
                    absorber_max_chars=int(custom_y_absorber),
                    candidate_max_chars=int(custom_z_candidate),
                    similarity_threshold=float(custom_sim_thresh),
                    scope_field="document_id",
                    enabled=True,
                )

    # Chunking Strategy & Optimal Token Budget Controls
    st.markdown("---")
    st.markdown("##### 🧩 Chunking Strategy & Optimal Token Budget")
    st.caption("Select the algorithm used to segment text and configure token sizing budgets. Embedder models silently truncate beyond 256 tokens.")

    strat_options = ["canonical_processor"] + list(CHUNK_STRATEGIES_META.keys())
    strat_labels = {
        "canonical_processor": "🏛️ Canonical Processor (Docling / Structured Parser Port)",
        **{k: CHUNK_STRATEGIES_META[k]["name"] for k in CHUNK_STRATEGIES_META}
    }

    def _on_ingest_strat_change():
        sk = st.session_state.get("ingest_strat_select")
        if sk in CHUNK_STRATEGIES_META:
            st.session_state["ingest_token_budget"] = min(250, CHUNK_STRATEGIES_META[sk]["optimal_tokens"])
            st.session_state["ingest_overlap_pct"] = CHUNK_STRATEGIES_META[sk]["default_overlap_pct"]

    col_cs1, col_cs2, col_cs3 = st.columns([1.6, 1.2, 0.8])
    with col_cs1:
        chosen_ingest_strat = st.selectbox(
            "Select Chunking Strategy",
            options=strat_options,
            format_func=lambda k: strat_labels.get(k, k),
            key="ingest_strat_select",
            on_change=_on_ingest_strat_change,
            help="Choose the algorithm used to segment the document during ingestion.",
        )

    if "ingest_token_budget" not in st.session_state:
        st.session_state["ingest_token_budget"] = 220
    if "ingest_overlap_pct" not in st.session_state:
        st.session_state["ingest_overlap_pct"] = 10

    with col_cs2:
        ingest_token_budget = st.slider(
            "Optimal Token Budget per Chunk",
            min_value=50,
            max_value=500,
            value=st.session_state["ingest_token_budget"],
            step=10,
            key="ingest_token_budget_slider",
            help="Target approximate tokens. Sentences are never cut mid-thought: soft boundary snapping ensures complete syntactic structures.",
        )
    with col_cs3:
        ingest_overlap_pct = st.slider(
            "Context Overlap (%)",
            min_value=0,
            max_value=30,
            value=st.session_state["ingest_overlap_pct"],
            step=5,
            key="ingest_overlap_pct_slider",
            help="Context lookback carryover into adjacent chunks.",
        )

    # Informational Callout Banner for Ingestion Strategy
    if chosen_ingest_strat in CHUNK_STRATEGIES_META:
        strat_info = CHUNK_STRATEGIES_META[chosen_ingest_strat]
        st.markdown(f"""
        <div style="background-color: #0E1726; border-left: 4px solid #0284C7; padding: 10px 14px; border-radius: 6px; margin-bottom: 15px;">
            <div style="font-weight: 600; color: #38BDF8;">💡 {strat_info['name']}</div>
            <div style="font-size: 0.88rem; color: #CBD5E1; margin-top: 3px;">
                <b>Recommended Range:</b> {strat_info['recommended_range']} &nbsp;|&nbsp; 
                <b>Best For:</b> {strat_info['best_for']}
            </div>
            <div style="font-size: 0.8rem; color: #94A3B8; margin-top: 4px;">
                🛡️ <b>Embedder Context Limit Notice:</b> Model <code>all-MiniLM-L6-v2</code> has a maximum sequence window of 256 tokens. Target budget ({ingest_token_budget} tokens) ensures high retrieval fidelity without silent truncation.
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background-color: #0E1726; border-left: 4px solid #10B981; padding: 10px 14px; border-radius: 6px; margin-bottom: 15px;">
            <div style="font-weight: 600; color: #34D399;">🏛️ Canonical Processor Active (Docling Layout-Aware)</div>
            <div style="font-size: 0.88rem; color: #CBD5E1; margin-top: 3px;">
                Runs layout-aware parsing through Docling: TableFormer structural table recovery, multi-column reading order, OCR, hierarchical heading breadcrumbs, and header/footer artifact suppression.
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Action Buttons
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])

    with col_btn1:
        btn_preview = st.button("👁️ Preview Chunks (Dry Run)", use_container_width=True)
    with col_btn2:
        btn_ingest = st.button("⚡ Ingest & Persist to ChromaDB", type="primary", use_container_width=True)
    with col_btn3:
        if st.session_state.get("active_chunk_results") is not None:
            if st.button("🧹 Clear Chunk View", use_container_width=True):
                st.session_state["active_chunk_results"] = None
                st.rerun()

    if btn_preview or btn_ingest:
        if not raw_bytes:
            st.error("Please upload a file or paste document text before chunking.")
            return

        with st.spinner("Processing document chunks..."):
            t_start = time.time()
            try:
                records, merge_res = process_document_to_chunks(
                    raw_bytes=raw_bytes,
                    file_name=source_name,
                    doc_id=doc_id,
                    department=department,
                    classification=classification,
                    project_id=project_id,
                    version=version,
                    enable_semantic_merging=enable_custom_semantic_merging,
                    merge_config=custom_merge_cfg,
                    chunking_strategy=chosen_ingest_strat,
                    target_tokens=ingest_token_budget,
                    overlap_pct=ingest_overlap_pct,
                )
                elapsed = time.time() - t_start

                if btn_ingest:
                    # Persist copy to test_data/
                    try:
                        save_file = _REPO_ROOT / "test_data" / source_name
                        save_file.write_bytes(raw_bytes)
                    except Exception:
                        pass

                    # Upsert to ChromaDB
                    store = get_chroma_store()
                    store.delete_document_chunks(doc_id)
                    store.add_documents(records)
                    st.cache_data.clear()

                    st.session_state["active_chunk_results"] = {
                        "records": records,
                        "doc_id": doc_id,
                        "source": source_name,
                        "persisted": True,
                        "time_sec": elapsed,
                        "semantic_merging_applied": enable_custom_semantic_merging,
                        "merge_report": merge_res,
                    }
                    ingest_msg = f"🎉 Ingested **{source_name}** ({doc_id}) into ChromaDB! Created **{len(records)}** chunks in {elapsed:.2f}s."
                    if merge_res and merge_res.absorbed_chunks_count > 0:
                        ingest_msg += f" (🔀 Merged {merge_res.absorbed_chunks_count} micro-fragments, -{merge_res.reduction_percentage:.1f}%)"
                    st.success(ingest_msg)
                    st.rerun()
                else:
                    st.session_state["active_chunk_results"] = {
                        "records": records,
                        "doc_id": doc_id,
                        "source": source_name,
                        "persisted": False,
                        "time_sec": elapsed,
                        "semantic_merging_applied": enable_custom_semantic_merging,
                        "merge_report": merge_res,
                    }
                    prev_msg = f"Generated preview of **{len(records)}** chunks for **{source_name}** in {elapsed:.2f}s (Dry Run)."
                    if merge_res and merge_res.absorbed_chunks_count > 0:
                        prev_msg += f" 🔀 Semantic merging consolidated {merge_res.absorbed_chunks_count} micro-fragments (-{merge_res.reduction_percentage:.1f}%)."
                    st.info(prev_msg)

            except Exception as e:
                st.error(f"Ingestion failed: {e}")
                return

    # Render Chunk Inspector if results exist
    active_res = st.session_state.get("active_chunk_results")
    if active_res:
        records = active_res["records"]
        persisted = active_res["persisted"]
        doc_label = active_res["source"]

        st.markdown("---")
        header_title = f"### 🧩 Generated Chunks for: `{doc_label}`"
        if persisted:
            header_title += " *(Saved to ChromaDB)*"
        else:
            header_title += " *(Dry Run Preview)*"
        st.markdown(header_title)

        if records:
            tok_counts = [len(r["text"].split()) for r in records]
            under_budget = sum(1 for t in tok_counts if t <= 256)
            budget_pct = (under_budget / len(records)) * 100
            avg_tokens = sum(tok_counts) / len(tok_counts)
            max_tokens = max(tok_counts)
            has_hierarchy = sum(1 for r in records if r["metadata"].get("hierarchy_path") or r["metadata"].get("section_heading"))

            cm1, cm2, cm3, cm4, cm5 = st.columns(5)
            cm1.metric("Total Chunks", len(records))
            cm2.metric("Avg Token Length", f"{avg_tokens:.1f} tok")
            cm3.metric("Max Token Length", f"{max_tokens} tok", delta="Over 256!" if max_tokens > 256 else "Within Budget", delta_color="inverse" if max_tokens > 256 else "normal")
            cm4.metric("Token Compliance", f"{budget_pct:.1f}%", f"{under_budget}/{len(records)}")
            cm5.metric("Breadcrumbs Detected", f"{has_hierarchy}/{len(records)}")

            merge_report = active_res.get("merge_report")
            applied = active_res.get("semantic_merging_applied", False)
            if applied and merge_report and merge_report.absorbed_chunks_count > 0:
                st.caption(f"🔀 **Semantic Chunk Merging Active:** {merge_report.absorbed_chunks_count} micro-fragments were absorbed into parent chunks ({merge_report.reduction_percentage:.1f}% reduction).")
            elif applied:
                st.caption("🔀 **Semantic Chunk Merging Active:** 0 micro-fragments required merging (all chunks were sufficiently distinct or above candidate limit).")

            # Generated Chunk IDs Manifest for Newly Added Document
            all_ids = [r["id"] for r in records]
            id_range_str = f"{all_ids[0]} .. {all_ids[-1]}" if len(all_ids) > 1 else all_ids[0]
            with st.expander(f"📋 Generated Chunk IDs Manifest ({len(records)} Chunk IDs: `{id_range_str}`)", expanded=True):
                st.markdown(f"**Document ID:** `{active_res['doc_id']}` &nbsp;|&nbsp; **Source:** `{doc_label}` &nbsp;|&nbsp; **Total Chunks:** `{len(records)}`")
                col_mc1, col_mc2 = st.columns(2)
                with col_mc1:
                    st.markdown("**Comma-separated Chunk IDs (for quick copy):**")
                    st.code(", ".join(all_ids), language="text")
                with col_mc2:
                    st.markdown("**JSON Array of Chunk IDs:**")
                    st.code(json.dumps(all_ids, indent=2), language="json")

                if st.button("🧪 Pre-fill Benchmark Question for this Document", key="btn_prefill_bench", type="secondary", use_container_width=True):
                    st.session_state["benchmark_prefill"] = {
                        "expected_document": doc_label,
                        "doc_id": active_res["doc_id"],
                        "chunk_ids": all_ids[:2] if len(all_ids) >= 2 else all_ids,
                        "all_chunk_ids": all_ids,
                        "project_id": records[0].get("metadata", {}).get("project_id", "unassigned") if records else "unassigned",
                    }
                    st.success(f"Configured benchmark test draft for '{doc_label}'! Switch to Tab 5 (🧪 RAG Benchmark Suite) to add your validation test question.")

            # Comprehensive 6-Dimension Chunk Quality & Anti-Pollution Audit
            audit_report = audit_corpus_comprehensive(records)
            clean_cnt = sum(1 for cr in audit_report.chunk_reports if cr.overall_status == 'pass')
            report_by_id = {cr.chunk_id: cr for cr in audit_report.chunk_reports}

            with st.expander(
                f"🔬 Chunk Quality Audit (6 Dimensions): Grade {audit_report.composite_grade} ({audit_report.composite_score:.1f}%) "
                f"[🔴 Blockers: {audit_report.hard_failures_count} | 🟡 Warnings: {audit_report.warnings_count} | 🟢 Clean: {clean_cnt}/{len(records)}]",
                expanded=audit_report.hard_failures_count > 0 or audit_report.warnings_count > 0,
            ):
                st.markdown("#### 📊 Six Dimensions of Chunk Quality")
                qm1, qm2, qm3, qm4 = st.columns(4)
                qm1.metric("Composite Quality", f"{audit_report.composite_score:.1f}%", f"Grade {audit_report.composite_grade}")
                qm2.metric("Hard Blockers (P0)", f"{audit_report.hard_failures_count}", delta="Blocking" if audit_report.hard_failures_count > 0 else "0 Violations", delta_color="inverse" if audit_report.hard_failures_count > 0 else "normal")
                qm3.metric("Heuristic Warnings", f"{audit_report.warnings_count}", delta="Review Advised" if audit_report.warnings_count > 0 else "Clean", delta_color="inverse" if audit_report.warnings_count > 0 else "normal")
                qm4.metric("Clean Chunks", f"{clean_cnt}/{len(records)}", f"{(clean_cnt/len(records))*100:.1f}% pristine")

                # Dimension Compliance Grid (2 rows x 3 columns)
                st.markdown("**Dimension Health:**")
                dim_names = [
                    ("text_integrity", "1. Text Integrity"),
                    ("structural_quality", "2. Structure"),
                    ("semantic_quality", "3. Semantics"),
                    ("source_fidelity", "4. Fidelity"),
                    ("chunk_relationships", "5. Relationships"),
                    ("security_auditability", "6. Security & RBAC"),
                ]
                for row_start in range(0, len(dim_names), 3):
                    row_cols = st.columns(3)
                    for col_idx, (dim_key, dim_title) in enumerate(dim_names[row_start : row_start + 3]):
                        d_score = audit_report.dimension_scores.get(dim_key, 100.0)
                        d_status = audit_report.dimension_status.get(dim_key, "pass")
                        status_emoji = "🟢" if d_status == "pass" else ("🟡" if d_status == "warning" else "🔴")
                        with row_cols[col_idx]:
                            st.caption(f"{status_emoji} **{dim_title}**")
                            st.markdown(f"**{d_score:.0f}%**")

                if audit_report.hard_failures_count > 0:
                    st.error("🚨 **HARD VALIDATION FAILURES DETECTED:** One or more chunks contain blocking defects (missing metadata, null bytes, severed conditional rules, or exposed credentials). Review before persisting to vector store.")

                # Actionable Findings Table addressing the 3 Critical Questions
                st.markdown("#### 📋 Actionable Findings (3-Question Diagnostic)")
                filter_choice = st.radio(
                    "Filter Findings View",
                    ["Issues Only (Failures & Warnings)", "🔴 Hard Blockers Only", "🟡 Heuristic Warnings Only", "All Evaluated Metrics"],
                    horizontal=True,
                    key="filter_active_chunk_quality_v2",
                )

                all_metric_rows = []
                for cr in audit_report.chunk_reports:
                    for m in cr.metrics:
                        if filter_choice == "Issues Only (Failures & Warnings)" and m.status not in ("fail", "warning"):
                            continue
                        elif filter_choice == "🔴 Hard Blockers Only" and (m.status != "fail" or m.check_type != "hard_validation"):
                            continue
                        elif filter_choice == "🟡 Heuristic Warnings Only" and (m.status != "warning" and m.check_type == "hard_validation"):
                            continue

                        chunk_text_lookup = {cr.chunk_id: cr.text for cr in audit_report.chunk_reports}
                        chunk_raw = chunk_text_lookup.get(m.chunk_id, "")
                        chunk_quote = m.quoted_text or (chunk_raw[:130].replace("\n", " ").strip() + ("..." if len(chunk_raw) > 130 else ""))

                        all_metric_rows.append({
                            "Chunk ID": m.chunk_id,
                            "Dimension": m.dimension.replace("_", " ").title(),
                            "Metric": m.metric_name,
                            "Type": m.check_type.replace("_", " ").title(),
                            "Severity": m.severity.upper(),
                            "Status": m.status.upper(),
                            "What is Wrong (Evidence)": m.evidence or "N/A (Check Passed)",
                            "Quoted Chunk (Where it Comes From)": f'"{chunk_quote}"',
                            "Why It Matters (RAG Impact)": m.explanation or "Preserves grounding and retrieval fidelity.",
                            "Recommended Action": m.recommended_action or "No action needed.",
                        })

                if all_metric_rows:
                    df_metrics = pd.DataFrame(all_metric_rows)
                    st.dataframe(df_metrics, use_container_width=True, height=240)
                else:
                    st.success("🎉 No issues found matching this filter! All chunks meet quality benchmarks.")

            st.markdown("#### Interactive Chunk Explorer")
            chunk_options = [
                f"[{r['id']}] Chunk #{idx} ({len(r['text'].split())} tok) - {r['metadata'].get('section_heading') or r['metadata'].get('section', '')}"
                for idx, r in enumerate(records)
            ]
            selected_idx = st.selectbox("Select Chunk to Inspect (by Chunk ID)", range(len(records)), format_func=lambda i: chunk_options[i])

            chosen_record = records[selected_idx]
            chosen_tokens = len(chosen_record["text"].split())
            meta = chosen_record["metadata"]

            chosen_ann = audit_chunk_record(chosen_record)
            if chosen_ann.chunk_type == "OCR":
                type_badge = f'<span class="badge-optimal" style="background:#0284C7;color:#E0F2FE;">📷 OCR ({chosen_ann.quality_score:.1f}%)</span>'
            elif chosen_ann.chunk_type in ("VLM", "HYBRID_OCR_VLM"):
                type_badge = f'<span class="badge-optimal" style="background:#7C3AED;color:#EDE9FE;">👁️ VLM ({chosen_ann.quality_score:.1f}%)</span>'
            else:
                type_badge = '<span class="badge-optimal" style="background:#334155;color:#F1F5F9;">📄 TEXT</span>'

            if chosen_tokens > 256:
                badge_html = f'<span class="badge-overflow">🔴 OVERFLOW ({chosen_tokens} tokens > 256)</span>'
            elif chosen_tokens < 30:
                badge_html = f'<span class="badge-stub">🟡 SHORT STUB ({chosen_tokens} tokens < 30)</span>'
            else:
                badge_html = f'<span class="badge-optimal">🟢 OPTIMAL DENSITY ({chosen_tokens} tokens)</span>'

            col_cid, col_cnav = st.columns([2, 1])
            with col_cid:
                st.markdown(f"#### 🧩 Chunk ID: `{chosen_record['id']}`")
                st.code(chosen_record["id"], language="text")
            with col_cnav:
                st.markdown("**Adjacent Chunk IDs:**")
                if selected_idx > 0:
                    st.caption(f"⬅️ Prev: `{records[selected_idx-1]['id']}`")
                if selected_idx < len(records) - 1:
                    st.caption(f"➡️ Next: `{records[selected_idx+1]['id']}`")

            layout_tag = ""
            if meta.get("layout_type"):
                layout_tag = f" &nbsp;|&nbsp; 📐 **Layout:** <code>{meta.get('layout_type')}</code>"
            if meta.get("bbox"):
                layout_tag += f" &nbsp;|&nbsp; 📍 **BBox:** <code>{meta.get('bbox')}</code>"
            st.markdown(f"**Chunk Status:** {badge_html} &nbsp;|&nbsp; {type_badge}{layout_tag} &nbsp;|&nbsp; **Length:** `{len(chosen_record['text'])} chars` &nbsp;|&nbsp; **Document:** `{meta.get('source', '')}`", unsafe_allow_html=True)

            # 3-Question Quality Diagnostic for Selected Chunk
            selected_report = report_by_id.get(chosen_record["id"]) or audit_single_chunk(chosen_record)
            failed_metrics = [m for m in selected_report.metrics if m.status in ("fail", "warning")]

            if failed_metrics:
                st.markdown("##### 🔬 Chunk Defect Analysis (3-Question Diagnostic)")
                for m in failed_metrics:
                    sev_class = f"sev-{m.severity.lower()}"
                    sev_color = "#DC2626" if m.severity in ("critical", "high") else "#D97706"
                    sev_badge = f'<span style="background:{sev_color};color:#FFFFFF;padding:2px 7px;border-radius:4px;font-weight:700;font-size:0.72rem;letter-spacing:0.04em;">{m.severity.upper()}</span>'
                    item_quote = m.quoted_text or (chosen_record["text"][:140].replace("\n", " ").strip() + ("..." if len(chosen_record["text"]) > 140 else ""))
                    st.markdown(f"""
                    <div class="defect-card {sev_class}">
                        <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
                            {sev_badge}
                            <span style="font-weight:700; color:#F8FAFC; font-size:0.92rem;">{m.metric_name}</span>
                            <span style="color:#64748B; font-size:0.76rem; font-weight:500;">({m.check_type.replace('_', ' ').title()}) · Dimension: {m.dimension.replace('_', ' ').title()}</span>
                        </div>
                        <div style="color:#E2E8F0; font-size:0.86rem; margin-bottom:5px;"><b>1. What is wrong:</b> <code style="color:#FCA5A5; background:#1E1523; padding:2px 6px; border-radius:3px;">{m.evidence}</code></div>
                        <div class="defect-quote">💬 <b>Quoted Chunk Source:</b> "{item_quote}"</div>
                        <div style="color:#CBD5E1; font-size:0.85rem; margin-bottom:4px;"><b>2. Why it matters for RAG:</b> {m.explanation}</div>
                        <div style="color:#38BDF8; font-size:0.85rem; font-weight:500;"><b>3. Recommended action:</b> {m.recommended_action}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.success("🟢 **Pristine Chunk:** Passes all 6 dimensions with zero integrity, boundary, semantic, or security defects.")

            if meta.get("hierarchy_path"):
                st.info(f"🧭 **Heading Hierarchy:** `{meta['hierarchy_path']}`")
            elif meta.get("section_heading"):
                st.info(f"🧭 **Section Heading:** `{meta['section_heading']}`")

            st.text_area(label="Chunk Content", value=chosen_record["text"], height=160, disabled=True, label_visibility="collapsed", key=f"doc_browser_chunk_content_{chosen_record.get('chunk_id', 'main')}")

            with st.expander("🔍 View Raw Chunk Metadata JSON", expanded=False):
                st.json(meta)

            # Tabular view with explicit Chunk ID column
            st.markdown("#### Complete Chunk Inventory")
            table_rows = []
            for i, r in enumerate(records):
                t_cnt = len(r["text"].split())
                m = r["metadata"]
                table_rows.append({
                    "Chunk ID": r["id"],
                    "Index": i,
                    "Tokens": t_cnt,
                    "Chars": len(r["text"]),
                    "Section": m.get("section_heading", "N/A"),
                    "Snippet": r["text"][:80] + ("..." if len(r["text"]) > 80 else ""),
                })
            st.dataframe(pd.DataFrame(table_rows), use_container_width=True, height=240)

            if persisted:
                st.markdown("---")
                st.markdown("#### 🎯 Instant Retrieval Probe")
                probe_col1, probe_col2 = st.columns([3, 1])
                with probe_col1:
                    probe_query = st.text_input("Probe Query", placeholder="e.g. What is the annual leave allowance?", key="probe_q_input")
                with probe_col2:
                    probe_k = st.selectbox("Top K Candidates", [2, 3, 5], index=1)

                if st.button("Run Probe Query", key="probe_btn"):
                    if probe_query.strip():
                        store = get_chroma_store()
                        probe_results = store.query(query_text=probe_query, top_k=probe_k)
                        if probe_results:
                            st.markdown(f"**Retrieved {len(probe_results)} Candidates:**")
                            for prank, pr in enumerate(probe_results, start=1):
                                pm = pr.get("metadata", {})
                                is_this_doc = (pm.get("document_id") == active_res["doc_id"] or pm.get("source") == active_res["source"])
                                doc_tag = "🌟 [NEWLY ADDED DOC]" if is_this_doc else f"[{pm.get('source', 'Existing')}]"
                                st.markdown(f"**Rank {prank}:** `{doc_tag}` 🧩 **Chunk ID:** `{pr.get('id')}` &nbsp;|&nbsp; Score: `{pr.get('score', 0):.4f}` &nbsp;|&nbsp; Distance: `{pr.get('distance', 0)}`")
                                st.caption(pr.get("text", "")[:140] + "...")
                        else:
                            st.warning("No candidates returned.")
            else:
                st.markdown("---")
                st.markdown("#### 🧪 In-Memory Dry Run Probe")
                st.caption("Probe generated chunks directly before committing to ChromaDB.")
                dry_probe_q = st.text_input("Dry Run Keyword Probe", placeholder="Search text in preview chunks...", key="dry_probe_input")
                if dry_probe_q.strip():
                    matching = [r for r in records if dry_probe_q.lower() in r["text"].lower() or dry_probe_q.lower() in r["id"].lower()]
                    if matching:
                        st.success(f"Found {len(matching)} matching chunks in preview:")
                        for mr in matching[:3]:
                            st.markdown(f"🧩 **Chunk ID:** `{mr['id']}` &nbsp;|&nbsp; Section: `{mr['metadata'].get('section_heading', 'General')}` &nbsp;|&nbsp; Tokens: `{len(mr['text'].split())}`")
                            st.caption(mr["text"][:140] + "...")
                    else:
                        st.info("No preview chunks match the query term.")

    # Section 3: Delete Document from ChromaDB
    st.markdown("---")
    with st.expander("🗑️ Delete / Manage Documents in ChromaDB", expanded=False):
        if not df_chunks.empty:
            existing_docs = sorted(df_chunks["doc_id"].unique().tolist())
            del_doc = st.selectbox("Select Document ID to Remove", existing_docs)
            del_count = len(df_chunks[df_chunks["doc_id"] == del_doc])
            st.caption(f"Permanently delete all **{del_count}** chunks for `{del_doc}` (`{del_doc}-*`) from ChromaDB.")
            if st.button("Delete Document Chunks", type="secondary"):
                store = get_chroma_store()
                store.delete_document_chunks(del_doc)
                st.cache_data.clear()
                st.success(f"Removed all chunks for document `{del_doc}`.")
                st.rerun()
        else:
            st.info("ChromaDB is currently empty.")


def render_chunk_explorer(df: pd.DataFrame):
    st.subheader("🔍 Step 3 · ChromaDB Chunk Explorer")
    st.info(
        "💡 **Usage Guide — Step 3:** "
        "Inspect, search, and verify chunks stored inside the local ChromaDB vector store. "
        "Filter by document, department, or project scope (e.g. Project 121 for RBAC). "
        "Confirm that chunk boundaries keep policy headers and context intact.",
        icon="ℹ️",
    )
    st.caption("Inspect, filter, and search all active chunks stored in the local vector collection by Chunk ID or text.")

    active_res = st.session_state.get("active_chunk_results")
    if active_res:
        a_src = active_res["source"]
        a_records = active_res["records"]
        a_ids = [r["id"] for r in a_records]
        id_span = f"`{a_ids[0]}` .. `{a_ids[-1]}`" if len(a_ids) > 1 else f"`{a_ids[0]}`"
        status_tag = "Persisted in ChromaDB" if active_res.get("persisted") else "Dry Run Preview"
        st.info(f"✨ **Active Document in Session:** `{a_src}` ({len(a_records)} chunks) &nbsp;|&nbsp; **Chunk IDs:** {id_span} &nbsp;|&nbsp; **Status:** {status_tag}")

    if df.empty:
        st.warning("ChromaDB collection is empty. Click 'Wipe Store & Re-ingest All Golden Documents' in Tab 1.")
        return

    # Filters
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        sources = ["All"] + sorted(df["source"].unique().tolist())
        selected_source = st.selectbox("Document Source", sources)
    with col_f2:
        scopes = ["All"] + sorted(df["project_id"].unique().tolist())
        selected_scope = st.selectbox("Project Scope", scopes)
    with col_f3:
        departments = ["All"] + sorted(df["department"].unique().tolist())
        selected_dept = st.selectbox("Department", departments)
    with col_f4:
        search_query = st.text_input("Search Chunk ID / Text", placeholder="e.g. DOC-001-0, probation, POSH-31...")

    # Filter application
    filtered = df.copy()
    if selected_source != "All":
        filtered = filtered[filtered["source"] == selected_source]
    if selected_scope != "All":
        filtered = filtered[filtered["project_id"] == selected_scope]
    if selected_dept != "All":
        filtered = filtered[filtered["department"] == selected_dept]
    if search_query:
        filtered = filtered[
            filtered["text"].str.contains(search_query, case=False, na=False) |
            filtered["chunk_id"].str.contains(search_query, case=False, na=False)
        ]

    col_count, col_exp = st.columns([3, 1])
    with col_count:
        st.markdown(f"**Showing {len(filtered)} of {len(df)} chunks**")
    with col_exp:
        csv_chunks = filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Export Filtered (CSV)",
            data=csv_chunks,
            file_name="filtered_chunks.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # Display preview table with explicit Chunk ID column
    df_explorer_display = filtered.rename(columns={
        "chunk_id": "Chunk ID",
        "source": "Document Source",
        "token_count": "Tokens",
        "project_id": "Project Scope",
        "department": "Department",
    })
    st.dataframe(
        df_explorer_display[["Chunk ID", "Document Source", "Tokens", "Project Scope", "Department"]],
        use_container_width=True,
        height=220,
    )

    # Detailed chunk view
    st.markdown("### Chunk Inspector")
    if not filtered.empty:
        def _fmt_filtered_chunk(cid: str) -> str:
            m = filtered[filtered["chunk_id"] == cid]
            if not m.empty:
                r = m.iloc[0]
                t_cnt = r["token_count"]
                hdr = r.get("heading_text") or r.get("hierarchy_path") or ""
                if not hdr and "text" in r:
                    hdr = r["text"][:38].replace("\n", " ").strip() + "..."
                return f"[{cid}] ({t_cnt} tok) - {hdr}"
            return cid

        selected_chunk_id = st.selectbox("Select Chunk to Inspect", filtered["chunk_id"].tolist(), format_func=_fmt_filtered_chunk)
        chunk_row = filtered[filtered["chunk_id"] == selected_chunk_id].iloc[0]

        col_cid, col_cnav = st.columns([2, 1])
        with col_cid:
            st.markdown(f"### 📄 Inspecting Chunk: `{chunk_row['chunk_id']}`")
            st.code(chunk_row["chunk_id"], language="text")
        with col_cnav:
            cur_cid = chunk_row["chunk_id"]
            if "-" in cur_cid:
                prefix, idx_str = cur_cid.rsplit("-", 1)
                if idx_str.isdigit():
                    idx_val = int(idx_str)
                    prev_id = f"{prefix}-{idx_val - 1}"
                    next_id = f"{prefix}-{idx_val + 1}"
                    has_prev = not df[df["chunk_id"] == prev_id].empty
                    has_next = not df[df["chunk_id"] == next_id].empty
                    st.markdown("**Adjacent Chunk IDs:**")
                    if has_prev:
                        st.caption(f"⬅️ Prev: `{prev_id}`")
                    if has_next:
                        st.caption(f"➡️ Next: `{next_id}`")

        # Disposition & Telemetry row
        cur_disp = get_chunk_disposition(selected_chunk_id)
        disp_badge_html = get_disposition_badge_html(cur_disp.get("status", "Open"))

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Token Count", f"{chunk_row['token_count']} tok")
        c2.metric("Document ID", str(chunk_row['doc_id']))
        c3.metric("Project Scope", str(chunk_row['project_id']))
        c4.metric("Review Disposition", cur_disp.get("status", "Open"))

        tokens = chunk_row["token_count"]
        if tokens > 256:
            density_badge = '<span class="badge-overflow">🔴 OVERFLOW (> 256 tokens - HARD LIMIT)</span>'
        elif tokens > 220:
            density_badge = '<span class="badge-stub" style="background:#78350F;color:#FDE68A;">🟡 TARGET BUDGET EXCEEDED (> 220 tok)</span>'
        elif tokens < 20:
            density_badge = '<span class="badge-stub">🟡 SHORT STUB (< 20 tokens)</span>'
        else:
            density_badge = '<span class="badge-optimal">🟢 OPTIMAL DENSITY (20-220 tokens)</span>'

        st.markdown(
            f"**Density Profile:** {density_badge} &nbsp;|&nbsp; "
            f"**Governance Status:** {disp_badge_html} &nbsp;|&nbsp; "
            f"**Document:** `{chunk_row.get('source', '')}`",
            unsafe_allow_html=True,
        )

        # 3-Question Quality Diagnostic for Selected Chunk
        chosen_rec = {
            "id": chunk_row["chunk_id"],
            "text": chunk_row["text"],
            "metadata": {
                "doc_id": chunk_row.get("doc_id", ""),
                "source": chunk_row.get("source", ""),
                "hierarchy_path": chunk_row.get("hierarchy_path", ""),
                "heading_text": chunk_row.get("heading_text", ""),
                "project_id": chunk_row.get("project_id", "unassigned"),
                "department": chunk_row.get("department", "Human Resources"),
                "classification": chunk_row.get("classification", "Internal"),
                "produced_by": chunk_row.get("produced_by", ""),
                "content_type": chunk_row.get("content_type", "text"),
                "route": chunk_row.get("route", ""),
            }
        }
        chunk_audit = audit_single_chunk(chosen_rec, target_window=256)
        failed_checks = [m for m in chunk_audit.metrics if m.status in ("fail", "warning")]

        # Action bar: Reviewer Decision + Step 4 Funnel Link
        col_disp_act, col_funnel_act = st.columns([2.2, 1.8])
        with col_disp_act:
            with st.expander(f"📝 Reviewer Decision ({cur_disp.get('status', 'Open')})", expanded=False):
                d_c1, d_c2 = st.columns([1.2, 2.0])
                with d_c1:
                    disp_opts = ["Open", "Under Review", "Approved", "Needs Re-OCR", "Needs Re-Chunk", "Dismissed"]
                    sel_new_disp = st.selectbox(
                        "Set Disposition",
                        disp_opts,
                        index=disp_opts.index(cur_disp.get("status", "Open")) if cur_disp.get("status", "Open") in disp_opts else 0,
                        key=f"exp_disp_sel_{selected_chunk_id}",
                    )
                with d_c2:
                    sel_new_note = st.text_input("Reviewer Notes", value=cur_disp.get("notes", ""), placeholder="e.g. Approved exception for table chunk.", key=f"exp_note_in_{selected_chunk_id}")
                if st.button("Save Decision", key=f"btn_save_exp_disp_{selected_chunk_id}"):
                    set_chunk_disposition(selected_chunk_id, sel_new_disp, sel_new_note)
                    st.success("Decision saved!")
                    st.rerun()
        with col_funnel_act:
            st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
            if st.button("🎯 Simulate in Retrieval Funnel (Step 4)", key=f"btn_exp_to_funnel_{selected_chunk_id}", type="primary"):
                st.session_state["custom_funnel_target"] = selected_chunk_id
                probe_q = chunk_row["text"].split("\n")[0][:80].strip()
                if not probe_q or len(probe_q) < 10:
                    probe_q = f"What is detailed in chunk {selected_chunk_id}?"
                st.session_state["custom_funnel_q"] = probe_q
                st.session_state["funnel_workspace_pending"] = "🎯 2-Stage Retrieval & Needle Tester"
                st.success(f"Loaded `{selected_chunk_id}` into Step 4 Funnel! Switch to Tab 4 to test.")

        # Quality Findings Panel
        if failed_checks:
            st.markdown("##### 🔬 Quality Findings Panel")
            for m in failed_checks:
                sev_class = f"sev-{m.severity.lower()}"
                sev_color = "#DC2626" if m.severity in ("critical", "high") else "#D97706"
                sev_badge = f'<span style="background:{sev_color};color:#FFFFFF;padding:2px 7px;border-radius:4px;font-weight:700;font-size:0.72rem;letter-spacing:0.04em;">{m.severity.upper()}</span>'
                quote_val = m.quoted_text or (chunk_row["text"][:140].replace("\n", " ").strip() + ("..." if len(chunk_row["text"]) > 140 else ""))
                st.markdown(f"""
                <div class="defect-card {sev_class}">
                    <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
                        {sev_badge}
                        <span style="font-weight:700; color:#F8FAFC; font-size:0.92rem;">{m.metric_name}</span>
                        <span style="color:#64748B; font-size:0.76rem; font-weight:500;">({m.check_type.replace('_', ' ').title()}) · Dimension: {m.dimension.replace('_', ' ').title()}</span>
                    </div>
                    <div style="color:#E2E8F0; font-size:0.86rem; margin-bottom:5px;"><b>1. What is wrong:</b> <code style="color:#FCA5A5; background:#1E1523; padding:2px 6px; border-radius:3px;">{m.evidence}</code></div>
                    <div class="defect-quote">💬 <b>Quoted Chunk Source:</b> "{quote_val}"</div>
                    <div style="color:#CBD5E1; font-size:0.85rem; margin-bottom:4px;"><b>2. Why it matters for RAG:</b> {m.explanation}</div>
                    <div style="color:#38BDF8; font-size:0.85rem; font-weight:500;"><b>3. Recommended action:</b> {m.recommended_action}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("🟢 **Pristine Chunk:** Passes all 6 dimensions with zero integrity, boundary, semantic, or security defects.")

        if chunk_row["hierarchy_path"]:
            st.info(f"🧭 **Heading Hierarchy:** `{chunk_row['hierarchy_path']}`")

        # Chunk Content with Highlighted Suspicious Text (if any)
        st.markdown("**Chunk Content:**")
        chunk_text_display = chunk_row["text"]
        highlighted_html = chunk_text_display
        for m in failed_checks:
            if m.quoted_text and m.quoted_text in highlighted_html and len(m.quoted_text) > 4:
                highlighted_html = highlighted_html.replace(
                    m.quoted_text,
                    f'<mark style="background:#7F1D1D; color:#FECACA; padding:1px 4px; border-radius:3px; font-weight:600;">{m.quoted_text}</mark>'
                )

        if highlighted_html != chunk_text_display:
            with st.expander("👁️ View with Highlighted Defect Text", expanded=True):
                st.markdown(f'<div style="background:#090E17; border:1px solid #1E293B; border-radius:4px; padding:12px; font-family:\'JetBrains Mono\', monospace; font-size:0.88rem; line-height:1.5; color:#E2E8F0; white-space:pre-wrap;">{highlighted_html}</div>', unsafe_allow_html=True)

        st.text_area(
            label="Raw Text",
            value=chunk_row["text"],
            height=140,
            disabled=True,
            label_visibility="collapsed",
        )

        # Source Document Context Comparison
        source_doc_path = _REPO_ROOT / "test_data" / chunk_row["source"]
        if source_doc_path.exists():
            with st.expander(f"📄 Source Document Context Comparison (`{chunk_row['source']}`)", expanded=False):
                st.caption(f"Source file size: **{source_doc_path.stat().st_size / 1024:.1f} KB** on disk.")
                st.info("Compare the stored chunk text against the original document context to verify extraction fidelity.")

        with st.expander("🔍 View Raw Chunk Metadata JSON", expanded=False):
            st.json({
                "chunk_id": chunk_row["chunk_id"],
                "source": chunk_row["source"],
                "hierarchy_path": chunk_row["hierarchy_path"],
                "heading_text": chunk_row["heading_text"],
                "classification": chunk_row["classification"],
            })


def render_quality_diagnostics(df: pd.DataFrame):
    if df.empty:
        st.warning("ChromaDB is currently empty. Please index documents in Step 1 first.")
        return

    tab_7param, tab_6dim = st.tabs([
        "🎯 7-Parameter Retrieval-Fitness Evaluator (3-Gate Pipeline)",
        "🔬 6-Dimension Defect Registry & Reviewer Dispositions (65 Metrics)",
    ])

    with tab_7param:
        render_seven_parameter_quality_studio(df)

    with tab_6dim:
        _render_6dimension_quality_workbench(df)


def _render_6dimension_quality_workbench(df: pd.DataFrame):
    st.markdown("""
    <div style="margin-bottom: 1.2rem;">
        <h3 style="margin-bottom: 4px; font-weight: 700; letter-spacing: -0.01em; color: #F8FAFC;">Step 2 · Chunk Quality Inspection Workbench</h3>
        <div style="color: #94A3B8; font-size: 0.9rem;">Comprehensive, explainable quality auditing across 6 core dimensions with actionable defect evidence, reviewer dispositions, and direct retrieval funnel simulation.</div>
    </div>
    """, unsafe_allow_html=True)

    if df.empty:
        st.warning("ChromaDB is currently empty. Please index documents in Step 1 first.")
        return

    # Document Scope Filter
    doc_list = sorted(df["source"].dropna().unique().tolist())
    doc_filter_options = ["All Documents (Entire Collection)"] + doc_list

    c_scope1, c_scope2 = st.columns([2.5, 1.5])
    with c_scope1:
        selected_audit_doc = st.selectbox(
            "📄 Select Document Scope to Audit",
            options=doc_filter_options,
            format_func=lambda s: f"🌐 {s}" if s.startswith("All") else f"📄 {s} ({len(df[df['source'] == s])} chunks)",
            key="quality_audit_doc_dropdown",
            help="Filter the 6-dimension scorecard, defect registry, and deep-dive inspection to a specific document or inspect the entire collection.",
        )
    with c_scope2:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if selected_audit_doc == "All Documents (Entire Collection)":
            audit_subset_df = df.copy().reset_index(drop=True)
            st.caption(f"Auditing all **{len(audit_subset_df):,} chunks** across {len(doc_list)} documents.")
        else:
            audit_subset_df = df[df["source"] == selected_audit_doc].copy().reset_index(drop=True)
            st.caption(f"Auditing **{len(audit_subset_df):,} chunks** in `{selected_audit_doc}`.")

    # Execute Full 6-Dimension Audit
    audit_raw_records = [
        {"id": row["chunk_id"], "text": row["text"], "metadata": {
            "produced_by": row.get("produced_by", ""),
            "route": row.get("route", ""),
            "content_type": row.get("content_type", "text"),
            "doc_id": row.get("doc_id", ""),
            "source": row.get("source", ""),
            "hierarchy_path": row.get("hierarchy_path", ""),
            "heading_text": row.get("heading_text", ""),
            "project_id": row.get("project_id", "unassigned"),
        }}
        for _, row in audit_subset_df.iterrows()
    ]
    audit_chroma = audit_corpus_comprehensive(audit_raw_records, target_window=256)
    
    chunks_audited = len(audit_subset_df)
    review_needed_cnt = sum(1 for cr in audit_chroma.chunk_reports if cr.overall_status in ("fail", "warning"))
    critical_defects_cnt = audit_chroma.hard_failures_count
    source_fidelity = audit_chroma.dimension_scores.get("source_fidelity", 100.0)

    # --------------------------------------------------------------------------
    # Section 1: Executive Summary Cards
    # --------------------------------------------------------------------------
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Chunks Audited", f"{chunks_audited:,}", f"{len(doc_list)} Source Files" if selected_audit_doc.startswith("All") else "1 Document")
    m2.metric(
        "Chunks Requiring Review",
        f"{review_needed_cnt:,}",
        delta=f"{(review_needed_cnt / chunks_audited * 100):.1f}% of corpus" if chunks_audited else "0%",
        delta_color="inverse" if review_needed_cnt > 0 else "normal",
    )
    m3.metric(
        "Critical Defects (Blockers)",
        f"{critical_defects_cnt}",
        delta="Blocking Ingestion" if critical_defects_cnt > 0 else "0 Hard Failures",
        delta_color="inverse" if critical_defects_cnt > 0 else "normal",
    )
    clean_chunks_cnt = max(0, chunks_audited - review_needed_cnt)
    clean_pct = (clean_chunks_cnt / chunks_audited * 100) if chunks_audited else 100.0
    m4.metric(
        "Composite Quality",
        f"{audit_chroma.composite_score:.1f}%",
        delta=f"Grade {audit_chroma.composite_grade} · {clean_pct:.1f}% Clean" if chunks_audited else "0%",
        delta_color="normal" if audit_chroma.composite_score >= 75 else "inverse",
    )

    st.markdown("---")

    # --------------------------------------------------------------------------
    # Section 2: Audit Dimensions Grid
    # --------------------------------------------------------------------------
    st.markdown("#### 1. Audit Dimensions")
    st.caption("Quantitative pass rates, defect counts, and explainability across the 6 Core Quality Dimensions.")

    dimension_meta = [
        ("text_integrity", "1. Text Integrity", "OCR noise, symbol anomalies, malformed characters", "TextIntegrityValidator"),
        ("structural_quality", "2. Structure", "Length budgets, boundaries, headings, tables", "StructuralQualityAuditor"),
        ("semantic_quality", "3. Semantics", "Coherence, context, missing conditions", "SemanticCoherenceAuditor"),
        ("source_fidelity", "4. Source Fidelity", "Lost text, altered values, extraction errors", "SourceFidelityAuditor"),
        ("chunk_relationships", "5. Relationships", "Duplicates, overlap, neighboring chunks", "RelationshipCorpusAuditor"),
        ("security_auditability", "6. Security & RBAC", "Required fields, source versions, access labels", "SecurityMetadataValidator"),
    ]

    # Render Audit Dimensions in 2 rows of 3 columns
    for row_start in range(0, len(dimension_meta), 3):
        row_cols = st.columns(3)
        for col_idx, (dim_key, dim_title, dim_sub, _) in enumerate(dimension_meta[row_start : row_start + 3]):
            d_score = audit_chroma.dimension_scores.get(dim_key, 100.0)
            d_status = audit_chroma.dimension_status.get(dim_key, "pass")
            status_emoji = "🟢" if d_status == "pass" else ("🟡" if d_status == "warning" else "🔴")
            
            # Count chunks affected by this specific dimension
            dim_affected = sum(
                1 for cr in audit_chroma.chunk_reports
                if any(m.dimension == dim_key and m.status in ("fail", "warning") for m in cr.metrics)
            )
            affected_color = "#34D399" if dim_affected == 0 else ("#FBBF24" if d_status == "warning" else "#F87171")

            with row_cols[col_idx]:
                st.markdown(f"""
                <div class="dimension-card">
                    <div class="dimension-header">
                        <span class="dimension-title">{dim_title}</span>
                        <span>{status_emoji}</span>
                    </div>
                    <div class="dimension-sub">{dim_sub}</div>
                    <div class="dimension-stat-row">
                        <span class="dimension-pct">{d_score:.0f}%</span>
                        <span class="dimension-affected" style="color: {affected_color};">
                            {dim_affected} affected
                        </span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # Section 3: Findings Queue & Defect Registry
    # --------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("#### 2. Findings Queue & Defect Registry")
    st.caption("Unified, filterable queue of chunk-level findings with reviewer disposition tracking and direct funnel simulation.")

    # Flatten all findings across reports
    raw_findings = []
    for cr in audit_chroma.chunk_reports:
        for m in cr.metrics:
            if m.status in ("fail", "warning"):
                disp = get_chunk_disposition(m.chunk_id)
                chunk_quote = m.quoted_text or (cr.text[:130].replace("\n", " ").strip() + ("..." if len(cr.text) > 130 else ""))
                raw_findings.append({
                    "chunk_id": m.chunk_id,
                    "source": cr.metadata.get("source", "unknown"),
                    "dimension": m.dimension,
                    "dimension_label": m.dimension.replace("_", " ").title(),
                    "metric_name": m.metric_name,
                    "check_type": m.check_type,
                    "severity": m.severity.upper(),
                    "severity_raw": m.severity,
                    "disposition": disp.get("status", "Open"),
                    "reviewer_notes": disp.get("notes", ""),
                    "evidence": m.evidence or "N/A",
                    "quoted_text": chunk_quote,
                    "possible_cause": m.possible_cause or "Extraction noise or boundary splitting mismatch.",
                    "verification_step": m.verification_step or "Compare against original source document text.",
                    "explanation": m.explanation or "Potential context degradation in RAG.",
                    "recommended_action": m.recommended_action or "Review chunk text.",
                    "revalidation_action": m.revalidation_action or "Re-audit after ingestion update.",
                })

    if raw_findings:
        col_flt1, col_flt2, col_flt3, col_flt4 = st.columns(4)
        with col_flt1:
            sev_filter = st.selectbox(
                "Filter by Severity",
                ["All Severities", "CRITICAL", "HIGH", "MEDIUM", "LOW"],
                key="findings_sev_filter",
            )
        with col_flt2:
            dim_opts = ["All Dimensions"] + sorted(list({f["dimension_label"] for f in raw_findings}))
            dim_filter = st.selectbox("Filter by Dimension", dim_opts, key="findings_dim_filter")
        with col_flt3:
            disp_opts = ["All Dispositions", "Open", "Under Review", "Approved", "Needs Re-OCR", "Needs Re-Chunk", "Dismissed"]
            disp_filter = st.selectbox("Filter by Disposition", disp_opts, key="findings_disp_filter")
        with col_flt4:
            f_search = st.text_input("Search in Findings", placeholder="e.g. OCR, symbol, boundary, DOC-001...", key="findings_search_kw")

        filtered_findings = raw_findings
        if sev_filter != "All Severities":
            filtered_findings = [f for f in filtered_findings if f["severity"] == sev_filter]
        if dim_filter != "All Dimensions":
            filtered_findings = [f for f in filtered_findings if f["dimension_label"] == dim_filter]
        if disp_filter != "All Dispositions":
            filtered_findings = [f for f in filtered_findings if f["disposition"] == disp_filter]
        if f_search.strip():
            kw = f_search.strip().lower()
            filtered_findings = [
                f for f in filtered_findings
                if kw in f["chunk_id"].lower()
                or kw in f["metric_name"].lower()
                or kw in f["evidence"].lower()
                or kw in f["source"].lower()
            ]

        st.caption(f"Displaying **{len(filtered_findings)} of {len(raw_findings)} findings**:")

        # Summary Display Table
        df_findings_table = pd.DataFrame([
            {
                "Chunk ID": f["chunk_id"],
                "Source Document": f["source"],
                "Dimension": f["dimension_label"],
                "Issue / Metric": f["metric_name"],
                "Severity": f["severity"],
                "Disposition": f["disposition"],
                "Quoted Chunk Source": f'"{f["quoted_text"]}"',
                "What is Wrong (Evidence)": f["evidence"],
            }
            for f in filtered_findings
        ])
        st.dataframe(df_findings_table, use_container_width=True, height=260)

        # Quick Disposition Updater & Inspector Pre-selection
        with st.expander("⚡ Quick Disposition Manager (Assign Disposition to Flagged Chunk)", expanded=False):
            f_chunk_ids = sorted(list({f["chunk_id"] for f in filtered_findings}))
            if f_chunk_ids:
                q_col1, q_col2, q_col3 = st.columns([1.5, 1.2, 2.0])
                with q_col1:
                    target_disp_cid = st.selectbox("Select Chunk ID to Update", f_chunk_ids, key="quick_disp_cid_select")
                with q_col2:
                    current_disp = get_chunk_disposition(target_disp_cid).get("status", "Open")
                    new_disp_val = st.selectbox(
                        "Assign Disposition",
                        ["Open", "Under Review", "Approved", "Needs Re-OCR", "Needs Re-Chunk", "Dismissed"],
                        index=["Open", "Under Review", "Approved", "Needs Re-OCR", "Needs Re-Chunk", "Dismissed"].index(current_disp) if current_disp in ["Open", "Under Review", "Approved", "Needs Re-OCR", "Needs Re-Chunk", "Dismissed"] else 0,
                        key="quick_disp_val_select",
                    )
                with q_col3:
                    new_disp_note = st.text_input("Reviewer Notes", value=get_chunk_disposition(target_disp_cid).get("notes", ""), placeholder="e.g. Confirmed scan noise; scheduled for re-OCR", key="quick_disp_note_input")
                
                if st.button("💾 Save Disposition & Notes", key="btn_save_quick_disp"):
                    set_chunk_disposition(target_disp_cid, new_disp_val, new_disp_note)
                    st.success(f"Updated disposition for `{target_disp_cid}` &rarr; **{new_disp_val}**")
                    st.rerun()
    else:
        st.success(f"🎉 Pristine Corpus: All {chunks_audited} chunks meet all 6-dimension quality standards with zero defects!")

    # --------------------------------------------------------------------------
    # Section 3: Evidence-Focused Deep-Dive Workspace
    # --------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("#### 3. Evidence-Focused Diagnostic Workspace")
    st.caption("Deep-dive into exact triggering characters, root causes, reviewer verification steps, and retrieval impact simulation.")

    chunk_id_list = audit_subset_df["chunk_id"].tolist()
    if chunk_id_list:
        # Build status lookup map from audit_chroma reports
        chunk_report_map = {cr.chunk_id: cr for cr in audit_chroma.chunk_reports}

        # Quality groupings
        fail_cids = [cid for cid in chunk_id_list if chunk_report_map.get(cid) and chunk_report_map[cid].overall_status == "fail"]
        warn_cids = [cid for cid in chunk_id_list if chunk_report_map.get(cid) and chunk_report_map[cid].overall_status == "warning"]
        pass_cids = [cid for cid in chunk_id_list if chunk_report_map.get(cid) and chunk_report_map[cid].overall_status == "pass"]
        issues_cids = [cid for cid in chunk_id_list if chunk_report_map.get(cid) and chunk_report_map[cid].overall_status in ("fail", "warning")]

        # Dimension-level defect groupings
        dim_defect_groups = {}
        for dim_key, dim_title, _, _ in dimension_meta:
            matched = [
                cr.chunk_id for cr in audit_chroma.chunk_reports
                if cr.chunk_id in chunk_id_list and any(m.dimension == dim_key and m.status in ("fail", "warning") for m in cr.metrics)
            ]
            if matched:
                dim_defect_groups[f"🔬 {dim_title} ({len(matched)})"] = matched

        # Build quality group options dictionary
        quality_group_options = {
            f"🌐 All Chunks ({len(chunk_id_list)})": chunk_id_list,
            f"🔴 Hard Blockers ({len(fail_cids)})": fail_cids,
            f"🟡 Warnings / Review Advised ({len(warn_cids)})": warn_cids,
            f"⚠️ All Defective Chunks ({len(issues_cids)})": issues_cids,
            f"🟢 Pristine / Clean ({len(pass_cids)})": pass_cids,
        }
        quality_group_options.update(dim_defect_groups)

        def _format_chunk_opt(cid: str) -> str:
            match_rows = audit_subset_df[audit_subset_df["chunk_id"] == cid]
            if not match_rows.empty:
                r_data = match_rows.iloc[0]
                idx = audit_subset_df.index[audit_subset_df["chunk_id"] == cid].tolist()[0]
                tok = r_data["token_count"]
                hdr = r_data.get("heading_text") or r_data.get("hierarchy_path") or ""
                if not hdr and "text" in r_data:
                    hdr = r_data["text"][:38].replace("\n", " ").strip() + "..."
                doc_prefix = f"[{r_data['source'][:14]}..] " if selected_audit_doc.startswith("All") else ""
                disp_tag = f"[{get_chunk_disposition(cid).get('status', 'Open')}] "
                
                # Quality badge indicator
                cr = chunk_report_map.get(cid)
                q_status = cr.overall_status if cr else "pass"
                q_emoji = "🔴" if q_status == "fail" else ("🟡" if q_status == "warning" else "🟢")

                return f"{q_emoji} {disp_tag}{doc_prefix}[{cid}] #{idx} ({tok} tok) - {hdr}"
            return cid

        col_q_grp, col_c_sel, col_funnel_btn = st.columns([1.3, 1.8, 1.0])
        with col_q_grp:
            selected_quality_group_label = st.selectbox(
                "🏷️ Group by Quality",
                options=list(quality_group_options.keys()),
                index=0,
                key="audit_quality_group_dropdown",
                help="Filter chunks by quality status (blockers, warnings, pristine) or specific dimension defects.",
            )

        active_group_cids = quality_group_options[selected_quality_group_label]

        with col_c_sel:
            if not active_group_cids:
                st.info(f"0 chunks in group: {selected_quality_group_label}")
                selected_cid = None
            else:
                selected_cid = st.selectbox(
                    "🧩 Select Chunk to Deep-Dive",
                    options=active_group_cids,
                    format_func=_format_chunk_opt,
                    key="audit_single_chunk_selector",
                )

        with col_funnel_btn:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button(
                "🎯 Send to Funnel",
                key="btn_send_to_funnel",
                type="primary",
                disabled=selected_cid is None,
                help="Load this chunk as a probe needle into Step 4: 2-Stage Retrieval & Funnel tester",
                use_container_width=True,
            ):
                st.session_state["custom_funnel_target"] = selected_cid
                # Extract first clean clause as test probe query
                chosen_probe_row = audit_subset_df[audit_subset_df["chunk_id"] == selected_cid].iloc[0]
                first_line = chosen_probe_row["text"].split("\n")[0][:80].strip()
                if not first_line or len(first_line) < 10:
                    first_line = "What information is detailed in " + selected_cid
                st.session_state["custom_funnel_q"] = first_line
                st.session_state["funnel_workspace_pending"] = "🎯 2-Stage Retrieval & Needle Tester"
                st.success(f"Loaded `{selected_cid}` into Step 4 Funnel! Switch to 'Step 4: 2-Stage Retrieval & Funnel' tab to execute.")

        if selected_cid:
            chosen_row = audit_subset_df[audit_subset_df["chunk_id"] == selected_cid].iloc[0]
            chosen_idx = audit_subset_df.index[audit_subset_df["chunk_id"] == selected_cid].tolist()[0]

            chosen_record = {
                "id": chosen_row["chunk_id"],
                "text": chosen_row["text"],
                "metadata": {
                    "doc_id": chosen_row.get("doc_id", ""),
                    "source": chosen_row.get("source", ""),
                    "hierarchy_path": chosen_row.get("hierarchy_path", ""),
                    "heading_text": chosen_row.get("heading_text", ""),
                    "project_id": chosen_row.get("project_id", "unassigned"),
                    "department": chosen_row.get("department", "Human Resources"),
                    "classification": chosen_row.get("classification", "Internal"),
                    "produced_by": chosen_row.get("produced_by", ""),
                    "content_type": chosen_row.get("content_type", "text"),
                    "route": chosen_row.get("route", ""),
                }
            }

            audit_res = audit_single_chunk(chosen_record, target_window=256)
            ocr_vlm_ann = audit_chunk_record(chosen_record)
            current_disposition = get_chunk_disposition(selected_cid)

            # Badges
            tok_count = chosen_row["token_count"]
            if tok_count > 256:
                density_badge = f'<span class="badge-overflow">🔴 OVERFLOW ({tok_count} > 256 tok - HARD LIMIT)</span>'
            elif tok_count > 220:
                density_badge = f'<span class="badge-stub" style="background:#78350F;color:#FDE68A;">🟡 TARGET BUDGET EXCEEDED ({tok_count} > 220 tok)</span>'
            elif tok_count < 20:
                density_badge = f'<span class="badge-stub">🟡 STUB FRAGMENT ({tok_count} < 20 tok)</span>'
            else:
                density_badge = f'<span class="badge-optimal">🟢 OPTIMAL DENSITY ({tok_count} tok)</span>'

            if ocr_vlm_ann.chunk_type == "OCR":
                type_badge = f'<span class="badge-optimal" style="background:#0284C7;color:#E0F2FE;">📷 OCR ({ocr_vlm_ann.quality_score:.1f}%)</span>'
            elif ocr_vlm_ann.chunk_type in ("VLM", "HYBRID_OCR_VLM"):
                type_badge = f'<span class="badge-optimal" style="background:#7C3AED;color:#EDE9FE;">👁️ VLM ({ocr_vlm_ann.quality_score:.1f}%)</span>'
            else:
                type_badge = '<span class="badge-optimal" style="background:#334155;color:#F1F5F9;">📄 TEXT</span>'

            if audit_res.overall_status == "fail":
                status_badge = '<span class="badge-overflow" style="background:#DC2626;color:#FEF2F2;">🔴 HARD BLOCKER</span>'
            elif audit_res.overall_status == "warning":
                status_badge = '<span class="badge-stub" style="background:#D97706;color:#FFFBEB;">🟡 REVIEW REQUIRED</span>'
            else:
                status_badge = '<span class="badge-optimal" style="background:#059669;color:#ECFDF5;">🟢 PRISTINE (PASS)</span>'

            disp_badge = get_disposition_badge_html(current_disposition.get("status", "Open"))

            st.markdown(
                f"**Quality Status:** {status_badge} &nbsp;|&nbsp; {density_badge} &nbsp;|&nbsp; {type_badge} &nbsp;|&nbsp; "
                f"**Disposition:** {disp_badge} &nbsp;|&nbsp; **Document:** `{chosen_row.get('source', '')}`",
                unsafe_allow_html=True,
            )

            # Reviewer Decision Panel
            with st.container():
                st.markdown("""
                <div style="background:#0B111D; border:1px solid #1E293B; border-radius:6px; padding:12px 16px; margin: 10px 0 16px 0;">
                    <div style="font-weight:700; color:#F8FAFC; margin-bottom:8px; font-size:0.9rem;">📝 Reviewer Disposition & Governance</div>
                """, unsafe_allow_html=True)
                r_c1, r_c2, r_c3 = st.columns([1.3, 2.2, 0.8])
                with r_c1:
                    cur_st = current_disposition.get("status", "Open")
                    all_st_opts = ["Open", "Under Review", "Approved", "Needs Re-OCR", "Needs Re-Chunk", "Dismissed"]
                    new_st = st.selectbox(
                        "Set Reviewer Disposition",
                        all_st_opts,
                        index=all_st_opts.index(cur_st) if cur_st in all_st_opts else 0,
                        key="inspect_pane_disp_select",
                    )
                with r_c2:
                    new_notes = st.text_input(
                        "Reviewer Notes",
                        value=current_disposition.get("notes", ""),
                        placeholder="e.g. Scanned OCR symbol noise verified against PDF page 3; marked for re-OCR.",
                        key="inspect_pane_notes_input",
                    )
                with r_c3:
                    st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
                    if st.button("Save Decision", key="btn_save_pane_disp", use_container_width=True):
                        set_chunk_disposition(selected_cid, new_st, new_notes)
                        st.success("Decision recorded!")
                        st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

            # Explainable Defect Analysis with 6-Item Breakdown
            failed_metrics = [m for m in audit_res.metrics if m.status in ("fail", "warning")]
            if failed_metrics:
                st.markdown("##### 🔬 Explainable Defect Evidence (Root Cause & Verification)")
                for m in failed_metrics:
                    sev_class = f"sev-{m.severity.lower()}"
                    sev_color = "#DC2626" if m.severity in ("critical", "high") else "#D97706"
                    sev_badge = f'<span style="background:{sev_color};color:#FFFFFF;padding:2px 7px;border-radius:4px;font-weight:700;font-size:0.72rem;letter-spacing:0.04em;">{m.severity.upper()}</span>'
                    item_quote = m.quoted_text or (chosen_row["text"][:140].replace("\n", " ").strip() + ("..." if len(chosen_row["text"]) > 140 else ""))
                    
                    st.markdown(f"""
                    <div class="defect-card {sev_class}">
                        <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
                            {sev_badge}
                            <span style="font-weight:700; color:#F8FAFC; font-size:0.94rem;">Finding: {m.metric_name}</span>
                            <span style="color:#64748B; font-size:0.76rem; font-weight:500;">({m.check_type.replace('_', ' ').title()}) · Dimension: {m.dimension.replace('_', ' ').title()}</span>
                        </div>
                        <div style="color:#E2E8F0; font-size:0.86rem; margin-bottom:5px;">
                            <b>1. Evidence (Trigger Condition):</b> <code style="color:#FCA5A5; background:#1E1523; padding:2px 6px; border-radius:3px;">{m.evidence}</code>
                        </div>
                        <div class="defect-quote">
                            💬 <b>Source Quote:</b> "{item_quote}"
                        </div>
                        <div style="color:#CBD5E1; font-size:0.85rem; margin-bottom:5px;">
                            <b>2. Possible Cause:</b> {m.possible_cause or "OCR extraction noise, PDF font encoding failure, or unconstrained paragraph splitting."}
                        </div>
                        <div style="color:#CBD5E1; font-size:0.85rem; margin-bottom:5px;">
                            <b>3. Verification Step:</b> {m.verification_step or "Compare stored chunk text against original page layout in source file."}
                        </div>
                        <div style="color:#CBD5E1; font-size:0.85rem; margin-bottom:5px;">
                            <b>4. Why it Matters for RAG:</b> {m.explanation}
                        </div>
                        <div style="color:#38BDF8; font-size:0.85rem; margin-bottom:5px;">
                            <b>5. Recommended Action:</b> {m.recommended_action}
                        </div>
                        <div style="color:#34D399; font-size:0.85rem;">
                            <b>6. Revalidation:</b> {m.revalidation_action or "Re-ingest the corrected file and verify that this defect drops from the findings queue."}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.success("🟢 **Pristine Chunk:** Passes all 6 dimensions with zero integrity, boundary, semantic, or security defects.")

            if chosen_row.get("hierarchy_path"):
                st.info(f"🧭 **Heading Hierarchy:** `{chosen_row['hierarchy_path']}`")
            elif chosen_row.get("heading_text"):
                st.info(f"🧭 **Heading Text:** `{chosen_row['heading_text']}`")

            st.text_area(label="Chunk Content", value=chosen_row["text"], height=160, disabled=True, label_visibility="collapsed", key=f"qual_diag_chunk_content_{chosen_row.get('chunk_id', 'qual')}")

            with st.expander("🔍 View Raw Chunk Metadata JSON", expanded=False):
                st.json({
                    "chunk_id": chosen_row["chunk_id"],
                    "source": chosen_row["source"],
                    "token_count": int(chosen_row["token_count"]),
                    "doc_id": chosen_row.get("doc_id", ""),
                    "project_id": chosen_row.get("project_id", ""),
                    "department": chosen_row.get("department", ""),
                    "classification": chosen_row.get("classification", ""),
                    "hierarchy_path": chosen_row.get("hierarchy_path", ""),
                    "heading_text": chosen_row.get("heading_text", ""),
                })

    # --------------------------------------------------------------------------
    # Section 4: Token Budget & Distribution Analytics
    # --------------------------------------------------------------------------
    st.markdown("---")
    with st.expander("📊 4. Token Budget & Distribution Analytics", expanded=False):
        st.markdown("##### Token Budgets vs Model Hard Limits")
        st.caption("Configured chunk target budget: **200–220 tokens** (optimal passage granularity) &nbsp;|&nbsp; Embedder hard context limit: **256 tokens** (`all-MiniLM-L6-v2` silent clipping threshold).")
        
        cqi_total = len(audit_subset_df)
        cqi_under_hard = (audit_subset_df["token_count"] <= 256).sum()
        cqi_within_target = (audit_subset_df["token_count"] <= 220).sum()
        cqi_stubs = (audit_subset_df["token_count"] < 20).sum()

        tb1, tb2, tb3 = st.columns(3)
        tb1.metric("Within Model Hard Limit (<=256)", f"{cqi_under_hard}/{cqi_total}", f"{(cqi_under_hard/cqi_total*100):.1f}% safe")
        tb2.metric("Within Target Budget (<=220)", f"{cqi_within_target}/{cqi_total}", f"{(cqi_within_target/cqi_total*100):.1f}% target optimal")
        tb3.metric("Stub Micro-Fragments (<20)", f"{cqi_stubs}", delta="Review Required" if cqi_stubs > 0 else "0 Stubs", delta_color="inverse" if cqi_stubs > 0 else "normal")

        st.markdown("##### Token Length Distribution")
        st.bar_chart(audit_subset_df["token_count"].value_counts().sort_index())

        st.markdown("##### Document-Level Chunking Quality Breakdown")
        doc_groups = df.groupby("source")
        doc_summary = []
        for src, group in doc_groups:
            toks = group["token_count"]
            stubs_cnt = (toks < 20).sum()
            comp_pct = (toks <= 256).mean() * 100
            first_cid = group["chunk_id"].iloc[0] if not group.empty else "N/A"
            last_cid = group["chunk_id"].iloc[-1] if not group.empty else "N/A"
            cid_range = f"{first_cid} .. {last_cid}" if first_cid != last_cid else first_cid
            doc_summary.append({
                "Document": src,
                "Chunk ID Range": cid_range,
                "Chunk ID Prefix": f"{Path(str(src)).stem}-*",
                "Chunks": len(group),
                "Mean Tokens": round(toks.mean(), 1),
                "Max Tokens": int(toks.max()),
                "Stubs (<20)": int(stubs_cnt),
                "Budget Compliance": f"{comp_pct:.1f}%",
            })
        st.dataframe(pd.DataFrame(doc_summary), use_container_width=True)

    # --------------------------------------------------------------------------
    # Section 5: Semantic Chunk Merging Simulator (Rahul Jangir Paradigm)
    # --------------------------------------------------------------------------
    st.markdown("---")
    with st.expander("🔀 5. Semantic Chunk Merging Simulator (Pairwise Noise & Fragment Consolidation)", expanded=False):
        st.markdown("##### Pairwise Semantic Chunk Merging Simulator")
        st.caption(
            "Consolidate micro-fragments (<= Z chars) into substantial absorbers (<= Y chars) up to a hard budget (<= X chars) "
            "based on semantic cosine similarity (>= Threshold), with strict tenant/document boundary isolation."
        )

        col_p1, col_p2, col_p3, col_p4 = st.columns(4)
        with col_p1:
            sim_threshold = st.slider(
                "Similarity Threshold (Cosine)",
                min_value=0.70,
                max_value=0.99,
                value=0.88,
                step=0.01,
                help="Minimum cosine similarity required between candidate and absorber to trigger a merge. Higher values prevent semantic drift.",
                key="merger_sim_threshold",
            )
        with col_p2:
            x_max_cap = st.number_input(
                "X: Max Chunk Cap (chars)",
                min_value=400,
                max_value=5000,
                value=1200,
                step=100,
                help="Hard character limit on the resulting merged chunk. Kept at ~240 tokens to prevent embedder context overflow.",
                key="merger_x_cap",
            )
        with col_p3:
            y_absorber_max = st.number_input(
                "Y: Absorber Limit (chars)",
                min_value=200,
                max_value=3000,
                value=800,
                step=50,
                help="Maximum size of chunks eligible to absorb smaller fragments.",
                key="merger_y_absorber",
            )
        with col_p4:
            z_candidate_max = st.number_input(
                "Z: Merge Candidate (chars)",
                min_value=50,
                max_value=1000,
                value=250,
                step=25,
                help="Maximum size of small chunks/stubs eligible to be absorbed into parent chunks.",
                key="merger_z_candidate",
            )

        col_run1, col_run2 = st.columns([1.5, 3.5])
        with col_run1:
            run_merger_btn = st.button("▶ Run Merge Simulation", key="btn_run_semantic_merger", use_container_width=True)
        with col_run2:
            st.caption(f"Will simulate on **{len(audit_subset_df)} chunks** currently in scope (`{selected_audit_doc}`).")

        if run_merger_btn:
            sim_input_records = [
                {
                    "id": row["chunk_id"],
                    "text": row["text"],
                    "metadata": {
                        "document_id": row.get("doc_id") or row.get("source", "unknown"),
                        "source": row.get("source", "unknown"),
                        "page_number": row.get("page_number", 1),
                        "token_count": int(row.get("token_count", 0)),
                    },
                }
                for _, row in audit_subset_df.iterrows()
            ]

            sim_cfg = SemanticMergeConfig(
                max_chunk_chars=int(x_max_cap),
                absorber_max_chars=int(y_absorber_max),
                candidate_max_chars=int(z_candidate_max),
                similarity_threshold=float(sim_threshold),
                scope_field="document_id",
                enabled=True,
            )

            with st.spinner("Computing embeddings and evaluating pairwise similarities..."):
                surviving_recs, merge_res = semantic_merge_chunk_records(sim_input_records, config=sim_cfg)
                orig_avg_chars = sum(len(r["text"]) for r in sim_input_records) / len(sim_input_records) if sim_input_records else 0
                st.session_state["sim_merge_results"] = {
                    "surviving": surviving_recs,
                    "report": merge_res,
                    "input_count": len(sim_input_records),
                    "orig_avg_chars": orig_avg_chars,
                }

        merge_data = st.session_state.get("sim_merge_results")
        if merge_data:
            m_rep = merge_data["report"]
            surviving = merge_data["surviving"]
            in_count = merge_data["input_count"]
            out_count = len(surviving)
            orig_avg_chars = merge_data.get("orig_avg_chars", 0)

            st.markdown("##### 📈 Simulation Outcomes & Impact")
            m_c1, m_c2, m_c3, m_c4 = st.columns(4)
            m_c1.metric(
                "Chunks Retained",
                f"{out_count} / {in_count}",
                f"-{m_rep.reduction_percentage:.1f}% reduction",
                delta_color="normal" if out_count < in_count else "off",
            )
            m_c2.metric(
                "Fragments Consolidated",
                f"{m_rep.absorbed_chunks_count}",
                delta=f"{m_rep.absorbed_chunks_count} stubs merged",
                delta_color="normal" if m_rep.absorbed_chunks_count > 0 else "off",
            )
            
            new_avg_chars = sum(len(r["text"]) for r in surviving) / out_count if out_count else 0
            m_c3.metric(
                "Avg Chunk Length",
                f"{new_avg_chars:.0f} chars",
                f"+{new_avg_chars - orig_avg_chars:.0f} chars",
            )
            m_c4.metric("Pairwise Merges Triggered", f"{len(m_rep.actions)}")

            if m_rep.actions:
                st.markdown("##### 🔍 Consolidated Merge Audit Trail")
                actions_rows = [
                    {
                        "Target Chunk ID": a.target_id,
                        "Absorbed Chunk ID": a.absorbed_id,
                        "Cosine Similarity": f"{a.similarity:.2%}",
                        "Length Evolution (chars)": f"{a.target_original_len} + {a.absorbed_len} &rarr; {a.merged_len}",
                        "Target Preview": a.target_preview,
                        "Absorbed Fragment Preview": a.absorbed_preview,
                    }
                    for a in m_rep.actions
                ]
                st.dataframe(pd.DataFrame(actions_rows), use_container_width=True)

                with st.expander("🔬 Inspect Consolidated Chunk Previews", expanded=False):
                    for a in m_rep.actions:
                        target_rec = next((r for r in surviving if r["id"] == a.target_id), None)
                        if target_rec:
                            st.markdown(f"**Merged Chunk `{a.target_id}`** (absorbed `{a.absorbed_id}` | sim: {a.similarity:.2%}):")
                            st.text_area(f"text_{a.target_id}_{a.absorbed_id}", value=target_rec["text"], height=100, disabled=True, label_visibility="collapsed")
                            st.caption(f"Metadata Lineage: `merged_chunk_ids`: {target_rec['metadata'].get('merged_chunk_ids')} | `pages`: {target_rec['metadata'].get('page_number')}")
            else:
                st.info("ℹ️ No chunks met both the candidate size (< Z) and cosine similarity (>= Threshold) criteria. Try lowering the similarity threshold or increasing candidate size Z.")

    # --------------------------------------------------------------------------
    # Section 6: Master 65-Metric Specification & Coverage Catalog
    # --------------------------------------------------------------------------
    st.markdown("---")
    with st.expander("📖 6. Complete 65-Metric Quality Framework Specification & Coverage Catalog", expanded=False):
        st.markdown("##### Enterprise 6-Dimension Quality Framework (65 Metrics)")
        st.caption(
            "Every metric addresses the Three Critical Questions: "
            "(1) What is wrong with this chunk? (2) Why does it matter for RAG? (3) What action should be taken? "
            "Distinguishes Hard Validations (deterministic blockers) from Heuristics (statistical rules) and Model Judgments."
        )

        catalog_df = get_metrics_catalog_dataframe()

        col_cat1, col_cat2, col_cat3, col_cat4 = st.columns(4)
        with col_cat1:
            cat_dim_filter = st.selectbox(
                "Filter Dimension",
                ["All Dimensions"] + sorted(catalog_df["Dimension"].unique().tolist()),
                key="cat_dim_filter_select",
            )
        with col_cat2:
            cat_prio_filter = st.selectbox(
                "Filter Priority",
                ["All Priorities", "P0", "P1", "P2"],
                key="cat_prio_filter_select",
            )
        with col_cat3:
            cat_type_filter = st.selectbox(
                "Filter Check Type",
                ["All Types", "Hard Validation", "Heuristic", "Model Based"],
                key="cat_type_filter_select",
            )
        with col_cat4:
            cat_search = st.text_input("Search Metric", placeholder="e.g. symbol, boundary, table, OCR...", key="cat_search_kw")

        filtered_cat_df = catalog_df
        if cat_dim_filter != "All Dimensions":
            filtered_cat_df = filtered_cat_df[filtered_cat_df["Dimension"] == cat_dim_filter]
        if cat_prio_filter != "All Priorities":
            filtered_cat_df = filtered_cat_df[filtered_cat_df["Priority"] == cat_prio_filter]
        if cat_type_filter != "All Types":
            filtered_cat_df = filtered_cat_df[filtered_cat_df["Check Type"] == cat_type_filter]
        if cat_search.strip():
            kw_c = cat_search.strip().lower()
            filtered_cat_df = filtered_cat_df[
                filtered_cat_df["Metric Name"].str.lower().str.contains(kw_c)
                | filtered_cat_df["Display Label"].str.lower().str.contains(kw_c)
                | filtered_cat_df["What it Measures"].str.lower().str.contains(kw_c)
                | filtered_cat_df["Why We Need It"].str.lower().str.contains(kw_c)
            ]

        c_stat1, c_stat2, c_stat3, c_stat4 = st.columns(4)
        c_stat1.metric("Catalog Size", f"{len(catalog_df)} Metrics", "6 Quality Dimensions")
        c_stat2.metric("P0 Critical Blockers", f"{(catalog_df['Priority'] == 'P0').sum()}", "Hard Ingestion Gates")
        c_stat3.metric("P1 Quality Audits", f"{(catalog_df['Priority'] == 'P1').sum()}", "Heuristic & Structural")
        c_stat4.metric("Showing in View", f"{len(filtered_cat_df)} of {len(catalog_df)}", f"{cat_dim_filter[:18]}")

        st.dataframe(filtered_cat_df, use_container_width=True, height=340)

    # Download Audit CSV
    st.markdown("---")
    csv_data = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Download Full Chunk Quality Audit (CSV)",
        data=csv_data,
        file_name="chunk_quality_audit.csv",
        mime="text/csv",
    )


def render_ragas_evaluation_card(eval_res: dict, llm_response: str = ""):
    """Reusable report card component for Ragas evaluation results."""
    if not eval_res:
        return

    is_p = eval_res.get("passed", False)
    faith = eval_res.get("faithfulness", 0.0)
    fact = eval_res.get("factual_correctness", 0.0)
    rel = eval_res.get("answer_relevancy", 0.0)
    prec = eval_res.get("context_precision", 0.8)
    rec = eval_res.get("context_recall", 0.85)
    diagnosis = eval_res.get("diagnosis", "")
    evaluator_used = eval_res.get("evaluator_used", "OpenRouter")
    latency = eval_res.get("latency_ms", 0.0)

    if llm_response:
        st.markdown("##### 🤖 LLM-Generated Response (Audited)")
        st.info(llm_response)

    if is_p:
        st.success("🎯 **FINAL VERDICT: PASSED (Faithful & Grounded)** — All claims are supported by the context without hallucination!")
    else:
        st.error("❌ **FINAL VERDICT: FAILED (Hallucination / Low Grounding Risk Detected!)**")

    st.caption(f"**Evaluator Engine:** `{evaluator_used}` &nbsp;|&nbsp; **Latency:** `{latency:.1f}ms`")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Faithfulness", f"{faith:.2f}", delta="Grounded" if faith >= 0.70 else "Low Grounding", delta_color="normal" if faith >= 0.70 else "inverse")
    m2.metric("Factual Correctness", f"{fact:.2f}", delta="Aligned" if fact >= 0.65 else "Misaligned", delta_color="normal" if fact >= 0.65 else "inverse")
    m3.metric("Answer Relevancy", f"{rel:.2f}", delta="Direct" if rel >= 0.70 else "Indirect", delta_color="normal" if rel >= 0.70 else "inverse")
    m4.metric("Context Precision", f"{prec:.2f}")
    m5.metric("Context Recall", f"{rec:.2f}")

    st.markdown("##### 🔍 Evaluator Diagnosis & Reasoning")
    st.info(diagnosis)


# Backward-compatible alias
render_geval_nli_report_card = render_ragas_evaluation_card



def render_direct_custom_geval_nli(df_chunks: pd.DataFrame):
    """Direct playground for auditing queries with Ragas metrics (replaces legacy NLI)."""
    render_ragas_metrics_studio(df_chunks)


@st.cache_data(ttl=300)
def get_cached_document_text(file_path_str: str) -> str:
    path = Path(file_path_str)
    if not path.exists():
        return ""
    try:
        return extract_text_from_bytes(path.read_bytes(), path.name)
    except Exception as e:
        return f"Error extracting document text: {e}"


def run_dynamic_2stage_retrieval(
    query: str,
    chunks: list,
    top_k_candidates: int = 10,
    top_k_rerank: int = 4,
) -> dict:
    """Run in-memory 2-stage retrieval (Bi-Encoder + Cross-Encoder) over dynamically generated chunks."""
    if not chunks or not query.strip():
        return {
            "candidates": [],
            "cand_subset": [],
            "reranked": [],
            "stage1_time": 0.0,
            "stage2_time": 0.0,
        }

    store = get_chroma_store()
    reranker = get_cached_reranker()

    t0 = time.time()
    # 1. Bi-Encoder Stage: encode query and chunk texts
    q_emb = store.embedding_model.encode([query], convert_to_numpy=True)
    c_texts = [c.text for c in chunks]
    c_embs = store.embedding_model.encode(c_texts, convert_to_numpy=True)

    norm_q = np.linalg.norm(q_emb)
    norm_c = np.linalg.norm(c_embs, axis=1)
    norm_c[norm_c == 0] = 1e-9
    if norm_q == 0:
        norm_q = 1e-9
    sims = np.dot(c_embs, q_emb.T).flatten() / (norm_c * norm_q)

    candidates = []
    for i, c in enumerate(chunks):
        s = float(sims[i])
        candidates.append({
            "id": c.id,
            "text": c.text,
            "score": round(s, 4),
            "distance": round(float(1.0 - s), 4),
            "metadata": getattr(c, "metadata", {}),
            "token_count": getattr(c, "token_count", len(c.text.split())),
            "heading_hierarchy": getattr(c, "heading_hierarchy", ""),
        })
    candidates.sort(key=lambda x: x["score"], reverse=True)
    stage1_time = (time.time() - t0) * 1000

    cand_subset = candidates[:top_k_candidates]

    # 2. Stage 2: Cross-Encoder Reranker
    t1 = time.time()
    reranked = reranker.rerank(query=query, candidates=cand_subset, top_k=top_k_rerank)
    stage2_time = (time.time() - t1) * 1000

    return {
        "candidates": candidates,
        "cand_subset": cand_subset,
        "reranked": reranked,
        "stage1_time": stage1_time,
        "stage2_time": stage2_time,
    }


def generate_dynamic_rag_llm_response(
    query: str,
    retrieved_chunks: list[dict],
    needle_text: str = "",
    case_metadata: dict | None = None,
) -> dict:
    """Format retrieved chunks into a prompt and generate a response using the configured LLM."""
    if not retrieved_chunks:
        return {
            "response": "No chunks retrieved to answer the question.",
            "latency_s": 0.0,
            "context_tokens": 0,
            "context_chars": 0,
            "needle_grounded": False,
            "model": "None",
            "system_prompt": "",
            "user_prompt": "",
            "error": "No chunks retrieved",
            "prohibited_leaks": [],
            "evidence_hits": [],
            "required_topics": [],
        }

    from app.use_cases.chat.rag_context_builder import RAGContextBuilder
    from app.infrastructure.llm.openrouter_client import OpenRouterClient
    from app.core.settings import LLM_MODEL

    builder = RAGContextBuilder()
    sys_p = builder.build_system_prompt()
    user_p = builder.build_user_prompt(
        question=query,
        context_chunks=retrieved_chunks,
    )

    context_chars = sum(len(c.get("text", "")) for c in retrieved_chunks)
    context_tokens = sum(c.get("token_count", len(c.get("text", "").split())) for c in retrieved_chunks)

    t0 = time.time()
    try:
        client = OpenRouterClient()
        resp = client.generate([
            {"role": "system", "content": sys_p},
            {"role": "user", "content": user_p},
        ]).strip()
        latency_s = round(time.time() - t0, 2)
        err = None
    except Exception as e:
        resp = f"LLM generation failed: {e}"
        latency_s = round(time.time() - t0, 2)
        err = str(e)

    needle_grounded = False
    clean_n = needle_text.strip().lower()
    if clean_n and not err:
        if clean_n in resp.lower():
            needle_grounded = True
        else:
            words = [w for w in re.findall(r"\b\w+\b", clean_n) if len(w) > 2 or w.isdigit()]
            matching_words = [w for w in words if w in resp.lower()]
            if len(matching_words) >= max(1, int(len(words) * 0.6)):
                needle_grounded = True

    # Multi-dimensional Policy Evaluation (Prohibited Claims & Evidence Coverage)
    prohibited_leaks = []
    evidence_hits = []
    required_topics = []
    if case_metadata and not err:
        required_topics = case_metadata.get("required_evidence_topics", [])
        for t in required_topics:
            t_terms = [w.lower() for w in re.findall(r"\b\w+\b", t) if len(w) > 3]
            match_t = sum(1 for w in t_terms if w in resp.lower())
            if t_terms and match_t >= max(1, int(len(t_terms) * 0.4)):
                evidence_hits.append(t)

        prohib = case_metadata.get("prohibited_claims", [])
        for p in prohib:
            p_terms = [w.lower() for w in re.findall(r"\b\w+\b", p) if len(w) > 3]
            match_c = sum(1 for w in p_terms if w in resp.lower())
            if p_terms and match_c >= max(2, int(len(p_terms) * 0.65)):
                prohibited_leaks.append(p)

    return {
        "response": resp,
        "latency_s": latency_s,
        "context_tokens": context_tokens,
        "context_chars": context_chars,
        "needle_grounded": needle_grounded,
        "model": LLM_MODEL,
        "system_prompt": sys_p,
        "user_prompt": user_p,
        "error": err,
        "prohibited_leaks": prohibited_leaks,
        "evidence_hits": evidence_hits,
        "required_topics": required_topics,
    }


def render_chunking_strategy_optimizer(df_chunks: pd.DataFrame):
    """Dynamic chunking strategy experimenter and needle optimizer for 2-stage retrieval."""
    st.subheader("🧩 Dynamic Chunking Strategy & Needle Optimizer")
    st.caption("Experiment with 6 advanced chunking strategies and approximate token budgets to find the empirical optimum for needle retrieval.")

    data_dir = _REPO_ROOT / "test_data"
    golden_files = []
    if data_dir.exists():
        supported_ext = {".docx", ".pdf", ".txt", ".md"}
        golden_files = sorted([f.name for f in data_dir.iterdir() if f.is_file() and f.suffix.lower() in supported_ext and f.name != "MANIFEST.md"])

    # Load benchmark presets for instant testing
    benchmark_path = data_dir / "rag_benchmark_questions.json"
    bench_cases = []
    if benchmark_path.exists():
        try:
            with open(benchmark_path, "r", encoding="utf-8") as f:
                bench_cases = json.load(f)
        except Exception:
            bench_cases = []

    # Mode selector
    opt_mode = st.radio(
        "Select Experimentation Mode:",
        ["📋 Benchmark Presets (Recommended)", "✏️ Custom Document & Needle Query"],
        horizontal=True,
        key="opt_mode_radio",
    )

    doc_text = ""
    selected_doc_name = ""
    default_query = "What is the standard probation period duration for new employees?"
    default_needle = "probation period of 90 calendar days"

    if opt_mode == "📋 Benchmark Presets (Recommended)":
        doc_family_filter = st.selectbox(
            "Filter Test Cases by Document Family:",
            [
                "All Documents (187 Questions)",
                "👔 Manager & HR Policy Playbook (20 Questions)",
                "NEXORA TECHNOLOGIES PVT (Handbook - 30 Questions)",
                "HR_Policy_Manual (30 Questions)",
                "POSH_Policy (30 Questions)",
                "DOC-001 (Onboarding Guide - 30 Questions)",
                "TEST-001 / DOC-004 (Architecture & RBAC - 30 Questions)",
                "Baseline Ground Truth (RAG-VAL-01 .. 17)",
            ],
            key="opt_bench_doc_filter",
        )

        filtered_cases = bench_cases
        if "Manager" in doc_family_filter:
            filtered_cases = [c for c in bench_cases if c.get("id", "").startswith("MGR-")]
        elif "NEXORA" in doc_family_filter:
            filtered_cases = [c for c in bench_cases if c.get("id", "").startswith("NEX-")]
        elif "HR_Policy_Manual" in doc_family_filter:
            filtered_cases = [c for c in bench_cases if c.get("id", "").startswith("HRM-")]
        elif "POSH" in doc_family_filter:
            filtered_cases = [c for c in bench_cases if c.get("id", "").startswith("POSH-")]
        elif "DOC-001" in doc_family_filter:
            filtered_cases = [c for c in bench_cases if c.get("id", "").startswith("ONB-")]
        elif "TEST-001" in doc_family_filter:
            filtered_cases = [c for c in bench_cases if c.get("id", "").startswith("ARC-")]
        elif "Baseline" in doc_family_filter:
            filtered_cases = [c for c in bench_cases if c.get("id", "").startswith("RAG-VAL-")]

        if not filtered_cases:
            filtered_cases = bench_cases

        preset_options = [
            f"[{c['id']}] {c['question'][:75]}... (Doc: {c.get('expected_document', 'Handbook')})"
            for c in filtered_cases
        ]

        def _sync_case_to_inputs(case_obj):
            if not case_obj:
                return
            st.session_state["opt_query_input"] = case_obj.get("question", "")
            cid = case_obj.get("id", "")
            if case_obj.get("expected_needle") is not None:
                st.session_state["opt_needle_input"] = case_obj["expected_needle"]
            elif cid == "RAG-VAL-01":
                st.session_state["opt_needle_input"] = "18 days of Annual Leave"
            elif cid == "RAG-VAL-02":
                st.session_state["opt_needle_input"] = "probation for six months"
            else:
                exp_kw = case_obj.get("expected_answer_keywords", [])
                st.session_state["opt_needle_input"] = exp_kw[0] if exp_kw else "policy"

            exp_doc = case_obj.get("expected_document", "").lower()
            for gf in golden_files:
                if exp_doc in gf.lower() or gf.lower().startswith(exp_doc[:6]):
                    st.session_state["opt_doc_select"] = gf
                    break

        def _on_bench_preset_change():
            chosen = st.session_state.get("opt_bench_preset_select", "")
            for c in bench_cases:
                if c["id"] in chosen:
                    _sync_case_to_inputs(c)
                    break

        # If not initialized or preset changed outside filter, initialize
        curr_preset = st.session_state.get("opt_bench_preset_select", "")
        if curr_preset not in preset_options and preset_options:
            st.session_state["opt_bench_preset_select"] = preset_options[0]
            _sync_case_to_inputs(filtered_cases[0])
        elif ("opt_query_input" not in st.session_state or "opt_needle_input" not in st.session_state) and filtered_cases:
            _sync_case_to_inputs(filtered_cases[0])

        selected_preset = st.selectbox(
            "Select Benchmark Test Case:",
            options=preset_options,
            key="opt_bench_preset_select",
            on_change=_on_bench_preset_change,
        )

        col_d, col_q = st.columns([1, 2])
        with col_d:
            if "opt_doc_select" not in st.session_state and golden_files:
                st.session_state["opt_doc_select"] = "NEXORA TECHNOLOGIES PVT.docx" if "NEXORA TECHNOLOGIES PVT.docx" in golden_files else golden_files[0]
            selected_doc_name = st.selectbox("Source Document from test_data/", golden_files, key="opt_doc_select")
        with col_q:
            query = st.text_input("Benchmark Query", key="opt_query_input")

        target_needle = st.text_input(
            "🎯 Expected Target Needle (Phrase/Sentence inside Document to Assert)",
            key="opt_needle_input",
            help="The specific sentence or factual phrase inside the document that contains the true answer. The system will assert whether the chunk containing this needle is retrieved.",
        )

        active_bench_case = None
        for c in bench_cases:
            if c.get("id") and f"[{c['id']}]" in selected_preset:
                active_bench_case = c
                break

        if active_bench_case and ("answerability" in active_bench_case or "test_type" in active_bench_case):
            ans = active_bench_case.get("answerability", "DIRECT")
            ans_color = {
                "DIRECT": "#10B981",
                "SYNTHESIZABLE": "#3B82F6",
                "INSUFFICIENT": "#F59E0B",
                "CONFLICTING": "#EF4444",
            }.get(ans, "#6B7280")
            ttype = active_bench_case.get("test_type", "normal").upper()

            with st.expander("📋 Policy Test Specification & Multi-Dimensional Criteria", expanded=True):
                st.markdown(f"""
                <div style="display: flex; gap: 10px; margin-bottom: 8px;">
                    <span style="background: {ans_color}22; border: 1px solid {ans_color}; color: {ans_color}; padding: 3px 12px; border-radius: 12px; font-weight: 600; font-size: 0.82rem;">
                        Answerability: {ans}
                    </span>
                    <span style="background: #334155; border: 1px solid #475569; color: #E2E8F0; padding: 3px 12px; border-radius: 12px; font-weight: 600; font-size: 0.82rem;">
                        Test Dimension: {ttype}
                    </span>
                </div>
                """, unsafe_allow_html=True)
                if active_bench_case.get("required_evidence_topics"):
                    topics_html = " ".join([f"<code style='color: #60A5FA; background: #0F172A; padding: 2px 6px; border-radius: 4px; margin-right: 4px;'>{t}</code>" for t in active_bench_case["required_evidence_topics"]])
                    st.markdown(f"**Required Policy Elements:** {topics_html}", unsafe_allow_html=True)
                if active_bench_case.get("prohibited_claims"):
                    prohib_html = " ".join([f"<code style='color: #F87171; background: #0F172A; padding: 2px 6px; border-radius: 4px; margin-right: 4px;'>{p}</code>" for p in active_bench_case["prohibited_claims"]])
                    st.markdown(f"**Prohibited Claims (Hallucination Guard):** {prohib_html}", unsafe_allow_html=True)
                if active_bench_case.get("notes"):
                    st.caption(f"ℹ️ **Policy Context:** {active_bench_case['notes']}")
    else:
        active_bench_case = None
        # Custom Mode
        col_c1, col_c2 = st.columns([1, 1])
        with col_c1:
            custom_doc_mode = st.radio("Document Source:", ["Select Golden Document", "Upload File", "Paste Text"], horizontal=True)
            if custom_doc_mode == "Select Golden Document":
                selected_doc_name = st.selectbox("Document", golden_files, key="opt_custom_doc_select")
            elif custom_doc_mode == "Upload File":
                up_file = st.file_uploader("Upload Policy / Manual", type=["docx", "pdf", "txt", "md"])
                if up_file:
                    selected_doc_name = up_file.name
                    doc_text = extract_text_from_bytes(up_file.getvalue(), up_file.name)
            else:
                selected_doc_name = "Pasted_Policy.md"
                doc_text = st.text_area("Document Text", height=150, placeholder="# Enter policy markdown or text...")

        with col_c2:
            query = st.text_input("Custom Query", value="How many days of annual leave are employees entitled to?", key="opt_custom_q")
            target_needle = st.text_input("🎯 Expected Target Needle (Phrase/Sentence to Assert)", value="18 days of paid annual leave", key="opt_custom_needle")

    st.markdown("---")
    st.markdown("### ⚙️ Chunking Strategy & Optimal Token Budget")

    # Document Selection Dropdown for Chunking Strategies
    doc_options = golden_files if golden_files else ["NEXORA TECHNOLOGIES PVT.docx"]
    
    # Sync selected document
    default_doc_idx = 0
    if selected_doc_name in doc_options:
        default_doc_idx = doc_options.index(selected_doc_name)

    col_doc_pick, col_doc_stat = st.columns([1.8, 1.2])
    with col_doc_pick:
        chosen_chunk_doc = st.selectbox(
            "📄 Select Document to Test Chunking Strategies:",
            options=doc_options,
            index=default_doc_idx,
            key="opt_chunking_doc_dropdown",
            help="Select any company policy, handbook, or architecture document from test_data/ to apply and evaluate chunking strategies on.",
        )
        if chosen_chunk_doc:
            selected_doc_name = chosen_chunk_doc
            doc_path = data_dir / selected_doc_name
            doc_text = get_cached_document_text(str(doc_path))

    with col_doc_stat:
        if doc_text and not doc_text.startswith("Error"):
            w_count = len(doc_text.split())
            approx_tokens = int(w_count * 1.33)
            doc_ext = selected_doc_name.split(".")[-1].upper() if "." in selected_doc_name else "DOC"
            st.metric(
                label=f"Document Token Size ({doc_ext})",
                value=f"~{approx_tokens:,} tokens",
                delta=f"{w_count:,} words"
            )
        else:
            st.metric("Document Token Size", "0 tokens", "Not loaded")

    if not doc_text or doc_text.startswith("Error"):
        st.warning(f"Unable to load document text for `{selected_doc_name}`. Please check file path or select another document.")
        return

    strat_keys = list(CHUNK_STRATEGIES_META.keys())

    def _on_opt_strat_change():
        sk = st.session_state.get("opt_strat_select")
        if sk in CHUNK_STRATEGIES_META:
            st.session_state["opt_token_budget"] = CHUNK_STRATEGIES_META[sk]["optimal_tokens"]
            st.session_state["opt_overlap_budget"] = CHUNK_STRATEGIES_META[sk]["default_overlap_pct"]

    col_s1, col_s2, col_s3 = st.columns([1.6, 1.2, 0.8])
    with col_s1:
        selected_strat_key = st.selectbox(
            "Select Chunking Strategy:",
            options=strat_keys,
            format_func=lambda k: CHUNK_STRATEGIES_META[k]["name"],
            key="opt_strat_select",
            on_change=_on_opt_strat_change,
            help="Choose the algorithm used to segment the document.",
        )

    meta = CHUNK_STRATEGIES_META[selected_strat_key]

    if "opt_token_budget" not in st.session_state:
        st.session_state["opt_token_budget"] = meta["optimal_tokens"]
    if "opt_overlap_budget" not in st.session_state:
        st.session_state["opt_overlap_budget"] = meta["default_overlap_pct"]

    with col_s2:
        token_budget = st.slider(
            "Optimal Token Budget per Chunk:",
            min_value=50,
            max_value=1000,
            step=25,
            key="opt_token_budget",
            help="Approximate target token count. Sentences are never cut off mid-thought: soft boundary snapping ensures complete syntactic structures.",
        )
    with col_s3:
        overlap_pct = st.slider(
            "Overlap (%):",
            min_value=0,
            max_value=30,
            step=5,
            key="opt_overlap_budget",
            help="Context lookback carryover into adjacent chunks.",
        )

    # Informational Callout Banner
    st.markdown(f"""
    <div style="background-color: #1E293B; border-left: 4px solid #3B82F6; padding: 10px 14px; border-radius: 6px; margin-bottom: 15px;">
        <div style="font-weight: 600; color: #60A5FA;">💡 {meta['name']}</div>
        <div style="font-size: 0.9rem; color: #CBD5E1; margin-top: 3px;">
            <b>Recommended Optimal Budget:</b> ~{meta['optimal_tokens']} tokens (Range: {meta['recommended_range']}) &nbsp;|&nbsp; 
            <b>Primary Strength:</b> {meta['best_for']}
        </div>
        <div style="font-size: 0.82rem; color: #94A3B8; margin-top: 4px;">
            🛡️ <b>Soft Sentence Snapping Active:</b> The token count ({token_budget} tokens) is treated as an approximate sizing budget. Chunks are snapped to complete sentences and discourse boundaries so no clauses, anaphoric pronouns, or numbers are severed mid-thought.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Generate Chunks for Active Strategy
    active_chunks = apply_chunking_strategy(
        strategy_key=selected_strat_key,
        text=doc_text,
        target_tokens=token_budget,
        overlap_pct=overlap_pct,
        doc_prefix=meta["short_name"][:4].upper(),
    )

    # Locate Target Needle in Generated Chunks
    clean_needle = target_needle.strip()
    needle_in_raw_doc = clean_needle.lower() in doc_text.lower() if clean_needle else False
    needle_matches = []
    if clean_needle:
        for idx, c in enumerate(active_chunks):
            if clean_needle.lower() in c.text.lower():
                needle_matches.append((idx, c))

    if clean_needle and not needle_in_raw_doc:
        st.error(f"""
        ❌ **Target Needle Not Found in Document!**
        The expected needle phrase `"{clean_needle}"` does **not exist** inside `{selected_doc_name}`.
        * **Why tests fail with ❌ MISSED:** A chunk can never be asserted or retrieved as containing the needle if the text is not in the document!
        * **Quick Fix:**
          - For **Annual Leave**: Enter `"18 days of Annual Leave"` (present in `{selected_doc_name}`).
          - For **Probation**: Enter `"probation for six months"` (in `{selected_doc_name}`, probation duration is **six months**, not 90 calendar days).
        """)
        if st.button(f"🎯 Auto-Pick Sample Needle from {selected_doc_name}", key="btn_autopick_sample_needle"):
            import re
            sentences = [s.strip() for s in re.split(r'[.\n]+', doc_text) if len(s.strip().split()) >= 4 and len(s.strip().split()) <= 12]
            if sentences:
                picked = sentences[min(2, len(sentences)-1)]
                st.session_state["opt_needle_input"] = picked
                st.session_state["opt_custom_needle"] = picked
                st.rerun()

    # Chunking Telemetry Metrics
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    m_col1.metric("Total Chunks Generated", f"{len(active_chunks)} chunks")
    avg_tokens = int(np.mean([c.token_count for c in active_chunks])) if active_chunks else 0
    m_col2.metric("Mean Tokens / Chunk", f"~{avg_tokens} tok", delta=f"{avg_tokens - token_budget:+d} vs target")
    min_tok = min(c.token_count for c in active_chunks) if active_chunks else 0
    max_tok = max(c.token_count for c in active_chunks) if active_chunks else 0
    m_col3.metric("Token Span (Min / Max)", f"{min_tok} .. {max_tok} tok")

    needle_status_txt = f"Found in Chunk #{needle_matches[0][0] + 1}" if needle_matches else "Phrase not in doc"
    m_col4.metric(
        "Needle Detection Status",
        needle_status_txt,
        delta="Captured Cleanly" if needle_matches else "Missing Needle",
        delta_color="normal" if needle_matches else "inverse",
    )

    # Live Chunk Inspector Expander
    with st.expander(f"🔎 Inspect Generated Chunks under {meta['short_name']} ({len(active_chunks)} Chunks)", expanded=False):
        st.caption("Review how document paragraphs were sliced. Chunks containing the expected needle are highlighted in green.")
        for idx, c in enumerate(active_chunks[:30], 1):
            is_needle = any(idx - 1 == m[0] for m in needle_matches)
            border_style = "border: 2px solid #10B981; background: #064E3B22;" if is_needle else "border: 1px solid #334155;"
            badge = " 🎯 [CONTAINS TARGET NEEDLE]" if is_needle else ""
            h_info = f" | Section: `{c.heading_hierarchy}`" if c.heading_hierarchy else ""
            st.markdown(f"""
            <div style="{border_style} padding: 10px; border-radius: 6px; margin-bottom: 8px;">
                <div style="font-weight: 600; color: {'#34D399' if is_needle else '#94A3B8'}; font-size: 0.85rem;">
                    Chunk #{idx} ({c.id}) • {c.token_count} tokens{h_info}{badge}
                </div>
                <div style="font-size: 0.9rem; color: #E2E8F0; margin-top: 4px;">{c.text}</div>
            </div>
            """, unsafe_allow_html=True)
        if len(active_chunks) > 30:
            st.caption(f"... and {len(active_chunks) - 30} more chunks omitted from preview.")

    st.markdown("---")
    st.markdown("### 🎯 2-Stage Retrieval & Needle Assertion Workbench")

    col_k1, col_k2, col_role = st.columns(3)
    with col_k1:
        cand_k = st.slider("Stage 1 Bi-Encoder Candidates (K)", 3, 20, 8, key="opt_slider_cand_k")
    with col_k2:
        final_k = st.slider("Stage 2 Reranked Output (K)", 1, 8, 3, key="opt_slider_final_k")
    with col_role:
        st.selectbox("Role Scope", ["Employee (Public)", "Project Lead (Scoped 121)"], key="opt_role_scope")

    col_opt_llm1, col_opt_llm2 = st.columns([1, 1])
    with col_opt_llm1:
        gen_llm_single = st.checkbox(
            "🤖 Generate LLM Response with Retrieved Chunks",
            value=True,
            key="opt_check_llm_single",
            help="Feed the retrieved chunks into the LLM to inspect how this chunk size & strategy affects final answer generation.",
        )
    with col_opt_llm2:
        gen_llm_all = st.checkbox(
            "🤖 Generate LLM Responses in All-6 Benchmark",
            value=True,
            key="opt_check_llm_all",
            help="Generate LLM responses across all 6 chunking strategies side-by-side to compare answer synthesis and factual grounding.",
        )

    col_act1, col_act2 = st.columns([1, 1])
    with col_act1:
        btn_run_single = st.button("🚀 Run 2-Stage Retrieval on This Strategy", type="primary", use_container_width=True, key="btn_run_opt_single")
    with col_act2:
        btn_compare_all = st.button("🏆 Benchmark All 6 Chunking Strategies (Find Optimal)", type="secondary", use_container_width=True, key="btn_run_opt_all")

    # Execution 1: Single Strategy 2-Stage Retrieval
    if btn_run_single:
        with st.spinner("Executing Bi-Encoder search and Cross-Encoder reranking over dynamic chunks..."):
            ret_res = run_dynamic_2stage_retrieval(
                query=query,
                chunks=active_chunks,
                top_k_candidates=cand_k,
                top_k_rerank=final_k,
            )
            llm_res = None
            if gen_llm_single:
                with st.spinner(f"🤖 Synthesizing LLM answer from retrieved chunks ({meta['short_name']} ~{token_budget} tok)..."):
                    llm_res = generate_dynamic_rag_llm_response(
                        query=query,
                        retrieved_chunks=ret_res["reranked"],
                        needle_text=clean_needle,
                        case_metadata=active_bench_case,
                    )
            st.session_state["dynamic_funnel_bundle"] = {
                "query": query,
                "strategy_key": selected_strat_key,
                "strategy_name": meta["short_name"],
                "token_budget": token_budget,
                "chunks": active_chunks,
                "needle_matches": needle_matches,
                "clean_needle": clean_needle,
                "ret_res": ret_res,
                "cand_k": cand_k,
                "final_k": final_k,
                "llm_result": llm_res,
                "active_case": active_bench_case,
            }
            st.session_state.pop("dynamic_compare_bundle", None)

    # Execution 2: Compare All 6 Strategies
    if btn_compare_all:
        with st.status("Evaluating all 6 Chunking Strategies against target needle...", expanded=True) as status_box:
            leaderboard_rows = []
            for sk, s_meta in CHUNK_STRATEGIES_META.items():
                status_box.update(label=f"Benchmarking {s_meta['short_name']} (~{s_meta['optimal_tokens']} tok)...")
                strat_chunks = apply_chunking_strategy(
                    strategy_key=sk,
                    text=doc_text,
                    target_tokens=s_meta["optimal_tokens"],
                    overlap_pct=s_meta["default_overlap_pct"],
                    doc_prefix=s_meta["short_name"][:4].upper(),
                )

                # Needle ID in this strategy
                strat_needle_id = None
                for c in strat_chunks:
                    if clean_needle.lower() in c.text.lower():
                        strat_needle_id = c.id
                        break

                strat_res = run_dynamic_2stage_retrieval(
                    query=query,
                    chunks=strat_chunks,
                    top_k_candidates=cand_k,
                    top_k_rerank=final_k,
                )

                cands = strat_res["candidates"]
                reranked = strat_res["reranked"]

                s1_rank = next((i for i, c in enumerate(cands, 1) if c["id"] == strat_needle_id), None)
                s2_rank = next((i for i, r in enumerate(reranked, 1) if r["id"] == strat_needle_id), None)
                s2_score = reranked[s2_rank - 1]["_rerank_score"] if s2_rank else None
                s1_score = cands[s1_rank - 1]["score"] if s1_rank else None

                # Generate LLM response if requested
                strat_llm = None
                if gen_llm_all:
                    status_box.update(label=f"🤖 Synthesizing LLM answer for {s_meta['short_name']} (~{s_meta['optimal_tokens']} tok)...")
                    strat_llm = generate_dynamic_rag_llm_response(
                        query=query,
                        retrieved_chunks=reranked,
                        needle_text=clean_needle,
                        case_metadata=active_bench_case,
                    )

                # Compute CQI for this strategy
                stubs = sum(1 for c in strat_chunks if c.token_count < 50)
                overflows = sum(1 for c in strat_chunks if c.token_count > 500)
                tot = len(strat_chunks)
                cqi = max(0, 100 - int(((2.0 * stubs + 1.5 * overflows) / tot) * 100)) if tot > 0 else 0

                if s2_rank == 1:
                    verdict = "🎯 BULLSEYE #1"
                    score_order = 100.0 + (s2_score or 0.0)
                elif s2_rank is not None:
                    verdict = f"✅ TOP-{final_k} (#{s2_rank})"
                    score_order = 50.0 - s2_rank + (s2_score or 0.0)
                elif s1_rank is not None:
                    verdict = f"⚠️ S1: #{s1_rank} (Demoted)"
                    score_order = 10.0 - s1_rank
                else:
                    verdict = "❌ MISSED"
                    score_order = -10.0

                leaderboard_rows.append({
                    "Strategy": s_meta["name"],
                    "Short Name": s_meta["short_name"],
                    "Target Tokens": f"~{s_meta['optimal_tokens']}",
                    "Chunks": tot,
                    "Needle in Doc": "✅ Yes" if strat_needle_id else "❌ No",
                    "Stage 1 Rank": f"#{s1_rank}" if s1_rank else "Miss",
                    "Stage 1 Cosine": f"{s1_score:.4f}" if s1_score else "N/A",
                    "Stage 2 Rank": f"#{s2_rank}" if s2_rank else "Dropped",
                    "Rerank Score": f"{s2_score:.4f}" if s2_score else "N/A",
                    "CQI Score": f"{cqi}%",
                    "Verdict": verdict,
                    "_score_order": score_order,
                    "_raw_score": s2_score or -999.0,
                    "_cqi": cqi,
                    "meta": s_meta,
                    "llm_result": strat_llm,
                    "reranked_chunks": reranked,
                })

            leaderboard_rows.sort(key=lambda x: (x["_score_order"], x["_raw_score"], x["_cqi"]), reverse=True)
            status_box.update(label="All 6 Chunking Strategies Evaluated Successfully!", state="complete")
            st.session_state["dynamic_compare_bundle"] = leaderboard_rows
            st.session_state.pop("dynamic_funnel_bundle", None)

    # Render Compare All Leaderboard
    cmp_bundle = st.session_state.get("dynamic_compare_bundle")
    if cmp_bundle:
        st.markdown("---")
        st.subheader("🏆 Chunking Strategy Empirical Leaderboard")
        st.caption(f"Tested query: *'{query}'* | Target needle: *'{clean_needle}'*")

        winner = cmp_bundle[0]
        st.success(f"""
        ### 🥇 Optimal Chunking Strategy: **{winner['Strategy']}**
        * **Verdict**: `{winner['Verdict']}` &nbsp;|&nbsp; **Rerank Score**: `{winner['Rerank Score']}` &nbsp;|&nbsp; **Chunks Generated**: `{winner['Chunks']}` &nbsp;|&nbsp; **CQI Quality**: `{winner['CQI Score']}`
        * **Why it won**: {winner['meta']['best_for']} With an optimal budget of **{winner['Target Tokens']} tokens**, it preserved the complete semantic premise around the needle without boundary severance, maximizing the Cross-Encoder all-to-all attention score.
        """)

        display_df = pd.DataFrame([{
            "Rank": f"#{i}",
            "Strategy": r["Short Name"],
            "Target Budget": r["Target Tokens"],
            "Chunks": r["Chunks"],
            "Needle Captured": r["Needle in Doc"],
            "Stage 1 (Bi-Encoder)": r["Stage 1 Rank"],
            "Stage 2 (Cross-Encoder)": r["Stage 2 Rank"],
            "Rerank Score": r["Rerank Score"],
            "CQI Index": r["CQI Score"],
            "Verdict": r["Verdict"],
            "LLM Needle Grounded": ("✅ Grounded" if r.get("llm_result", {}).get("needle_grounded") else "⚠️ Omitted") if r.get("llm_result") else "N/A",
            "LLM Latency": f"{r['llm_result']['latency_s']}s" if r.get("llm_result") else "N/A",
        } for i, r in enumerate(cmp_bundle, 1)])

        st.dataframe(display_df, use_container_width=True)

        # Render Side-by-Side LLM Response Comparison Across All 6 Strategies
        has_llm_bench = any(r.get("llm_result") for r in cmp_bundle)
        if has_llm_bench:
            st.markdown("---")
            st.subheader("🤖 Side-by-Side LLM Response Comparison Across Strategies")
            st.caption("Inspect how chunking strategy and token size directly alter the final synthesized answer and factual fidelity.")

            strat_tabs = st.tabs([f"{r['Short Name']} ({r['Target Tokens']})" for r in cmp_bundle])
            for i, (tab, r) in enumerate(zip(strat_tabs, cmp_bundle)):
                with tab:
                    l_res = r.get("llm_result")
                    if not l_res:
                        st.info("LLM response was not generated for this strategy.")
                        continue

                    tc1, tc2, tc3, tc4 = st.columns(4)
                    tc1.metric("Chunking Strategy", r["Short Name"])
                    tc2.metric("Target Token Budget", r["Target Tokens"])
                    tc3.metric("Rerank Score", r["Rerank Score"], delta=r["Verdict"])
                    tc4.metric(
                        "Needle Grounded in LLM",
                        "✅ Confirmed" if l_res["needle_grounded"] else "⚠️ Not Detected",
                        delta=f"Latency {l_res['latency_s']}s",
                        delta_color="normal" if l_res["needle_grounded"] else "inverse",
                    )

                    st.markdown("#### 💬 Synthesized Answer:")
                    border_c = "#10B981" if l_res["needle_grounded"] else "#F59E0B"
                    bg_c = "#064E3B15" if l_res["needle_grounded"] else "#78350F15"
                    st.markdown(f"""
                    <div style="border: 2px solid {border_c}; background-color: {bg_c}; border-radius: 8px; padding: 14px 18px; margin-bottom: 12px;">
                        <div style="font-size: 0.98rem; line-height: 1.6; color: #F1F5F9;">
                            {l_res['response']}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    with st.expander(f"📦 Retrieved Chunks Fed as Context ({len(r.get('reranked_chunks', []))} chunks, ~{l_res['context_tokens']} tokens)", expanded=False):
                        for c_i, ch in enumerate(r.get("reranked_chunks", []), 1):
                            s_badge = f"Score: `{round(ch.get('_rerank_score', 0.0), 4)}`"
                            tok_cnt = ch.get("token_count", len(ch.get("text", "").split()))
                            st.markdown(f"**Chunk #{c_i} (`{ch.get('id', 'N/A')}`)** • {s_badge} • ~{tok_cnt} tokens")
                            st.text_area(f"cmp_chunk_{i}_{c_i}", value=ch.get("text", ""), height=90, disabled=True, label_visibility="collapsed")

    # Render Single Strategy Results
    bundle = st.session_state.get("dynamic_funnel_bundle")
    if bundle:
        st.markdown("---")
        s_query = bundle["query"]
        s_name = bundle["strategy_name"]
        s_tokens = bundle["token_budget"]
        s_needle = bundle["clean_needle"]
        s_matches = bundle["needle_matches"]
        s_res = bundle["ret_res"]
        s_cand_k = bundle.get("cand_k", 8)
        s_final_k = bundle.get("final_k", 3)

        cands = s_res["candidates"]
        cand_sub = s_res["cand_subset"]
        reranked = s_res["reranked"]

        target_chunk_id = s_matches[0][1].id if s_matches else None

        s1_rank = next((i for i, c in enumerate(cands, 1) if c["id"] == target_chunk_id), None)
        s2_rank = next((i for i, r in enumerate(reranked, 1) if r["id"] == target_chunk_id), None)
        s1_score = cands[s1_rank - 1]["score"] if s1_rank else None
        s2_score = reranked[s2_rank - 1]["_rerank_score"] if s2_rank else None

        st.subheader(f"🎯 Needle Assertion Report: {s_name} (~{s_tokens} tokens)")

        if s2_rank == 1:
            st.success(f"🎯 **BULLSEYE HIT!** Needle chunk `{target_chunk_id}` was ranked **#1** by BGE Cross-Encoder (Score: `{s2_score:.4f}`). This chunking strategy delivers optimal retrieval precision!")
        elif s2_rank is not None:
            st.info(f"✅ **NEEDLE RETRIEVED!** Needle chunk `{target_chunk_id}` was fetched in Top-{s_final_k} at **Rank #{s2_rank}** (Score: `{s2_score:.4f}`).")
        elif s1_rank is not None:
            st.warning(f"⚠️ **RERANKER DEMOTION:** Needle chunk `{target_chunk_id}` was found in Stage 1 Bi-Encoder (Rank #{s1_rank}, Cosine: `{s1_score:.4f}`), but Cross-Encoder demoted it outside Top-{s_final_k}.")
        else:
            st.error(f"❌ **BI-ENCODER MISS:** Target needle chunk was NOT found in the Top-{s_cand_k} candidates. Consider adjusting token budget or adding overlap.")

        # Metric cards
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Strategy", s_name)
        c1_val = f"Rank #{s1_rank}" if s1_rank else "MISS"
        c2.metric("Stage 1 Bi-Encoder", c1_val, delta=f"Cosine {s1_score:.4f}" if s1_score else "Missed")
        c2_val = f"Rank #{s2_rank}" if s2_rank else "DROPPED"
        c3.metric("Stage 2 Cross-Encoder", c2_val, delta=f"Score {s2_score:.4f}" if s2_score else "Demoted")
        top_id = reranked[0]["id"] if reranked else "None"
        c4.metric("Top-1 Retrieved Chunk", top_id, delta="Bullseye Match" if top_id == target_chunk_id else "Alternative Top-1")

        # Side-by-side comparison
        with st.expander("🔍 Side-by-Side: Expected Needle Chunk vs Actual Top-1 Retrieved Chunk", expanded=True):
            cmp_left, cmp_right = st.columns(2)
            with cmp_left:
                st.markdown(f"#### 🎯 Target Needle Chunk (`{target_chunk_id or 'Not Found'}`)")
                target_text = s_matches[0][1].text if s_matches else "Needle phrase not found in document"
                st.text_area("Needle Content", value=target_text, height=170, disabled=True, label_visibility="collapsed", key="retrieval_probe_needle_content")
            with cmp_right:
                st.markdown(f"#### 🥇 Actual Top-1 Retrieved (`{top_id}`)")
                top_text = reranked[0]["text"] if reranked else "No chunks retrieved"
                st.text_area("Actual Top-1 Content", value=top_text, height=170, disabled=True, label_visibility="collapsed", key="retrieval_probe_top1_content")

        # Stage 1 & Stage 2 Tables
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.markdown(f"**Stage 1: Top-{s_cand_k} Bi-Encoder Candidates (`{s_res['stage1_time']:.1f}ms`)**")
            cand_rows = [{
                "Rank": i,
                "Match": "🎯 TARGET" if c["id"] == target_chunk_id else "",
                "ID": c["id"],
                "Cosine": c["score"],
                "Tokens": c["token_count"],
                "Snippet": c["text"][:60] + "...",
            } for i, c in enumerate(cand_sub, 1)]
            st.dataframe(pd.DataFrame(cand_rows), use_container_width=True)

        with col_t2:
            st.markdown(f"**Stage 2: Top-{s_final_k} Cross-Encoder Reranked (`{s_res['stage2_time']:.1f}ms`)**")
            rerank_rows = [{
                "Final Rank": i,
                "Match": "🎯 TARGET" if r["id"] == target_chunk_id else "",
                "ID": r["id"],
                "Score": round(r.get("_rerank_score", 0.0), 4),
                "Tokens": r.get("token_count", len(r["text"].split())),
                "Snippet": r["text"][:60] + "...",
            } for i, r in enumerate(reranked, 1)]
            st.dataframe(pd.DataFrame(rerank_rows), use_container_width=True)

        # Step 4: Render LLM Generated Response using Retrieved Chunks
        st.markdown("---")
        st.subheader(f"🤖 LLM Generated Response ({s_name} • ~{s_tokens} tokens)")
        st.caption(f"Synthesized answer using the top {len(reranked)} Cross-Encoder chunks (~{s_tokens} token budget per chunk).")

        llm_res = bundle.get("llm_result")
        if not llm_res:
            col_gen_now, _ = st.columns([1, 2])
            with col_gen_now:
                if st.button("🤖 Generate LLM Response from Retrieved Chunks", type="primary", use_container_width=True, key="btn_gen_single_llm_now"):
                    with st.spinner("Calling LLM with retrieved context chunks..."):
                        llm_res = generate_dynamic_rag_llm_response(
                            query=s_query,
                            retrieved_chunks=reranked,
                            needle_text=s_needle,
                            case_metadata=bundle.get("active_case"),
                        )
                        st.session_state["dynamic_funnel_bundle"]["llm_result"] = llm_res
                        st.rerun()

        if llm_res:
            # Metric badges
            lc1, lc2, lc3, lc4 = st.columns(4)
            lc1.metric("LLM Latency", f"{llm_res['latency_s']}s")
            lc2.metric("Context Budget Fed", f"~{llm_res['context_tokens']} tokens", delta=f"{len(reranked)} chunks")
            lc3.metric("Model", llm_res["model"])
            is_grounded = llm_res["needle_grounded"]
            lc4.metric(
                "Needle Grounded in Answer",
                "✅ Confirmed" if is_grounded else "⚠️ Not Detected",
                delta="Factual Match" if is_grounded else "Potential Omission",
                delta_color="normal" if is_grounded else "inverse",
            )

            # Response Display Box
            border_col = "#10B981" if is_grounded else "#F59E0B"
            bg_col = "#064E3B15" if is_grounded else "#78350F15"
            grounded_badge = (
                f'<span style="background-color: #065F46; color: #6EE7B7; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 600;">🎯 Needle Fact Reflected: "{s_needle}"</span>'
                if is_grounded else
                f'<span style="background-color: #92400E; color: #FDE68A; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 600;">⚠️ Needle Fact Not Explicitly Detected</span>'
            )

            st.markdown(f"""
            <div style="border: 2px solid {border_col}; background-color: {bg_col}; border-radius: 8px; padding: 14px 18px; margin-top: 10px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <div style="font-weight: 700; color: #F1F5F9; font-size: 0.95rem;">💬 Synthesized Answer</div>
                    {grounded_badge}
                </div>
                <div style="font-size: 1.0rem; line-height: 1.6; color: #E2E8F0;">
                    {llm_res['response']}
                </div>
            </div>
            """, unsafe_allow_html=True)

            if llm_res.get("prohibited_leaks"):
                for leak in llm_res["prohibited_leaks"]:
                    st.markdown(f'<div style="background-color: #7F1D1D; border: 1px solid #EF4444; color: #FECACA; padding: 6px 12px; border-radius: 6px; margin-top: 6px; font-size: 0.85rem;">🚨 <b>Prohibited Claim Detected (Policy Breach):</b> <code>{leak}</code></div>', unsafe_allow_html=True)

            if llm_res.get("required_topics"):
                cov_hits = len(llm_res.get("evidence_hits", []))
                cov_tot = len(llm_res["required_topics"])
                cov_pct = int((cov_hits / cov_tot) * 100) if cov_tot > 0 else 0
                st.markdown(f'<div style="font-size: 0.85rem; color: #93C5FD; margin-top: 6px;">📋 <b>Policy Evidence Coverage:</b> {cov_hits}/{cov_tot} mandatory elements grounded ({cov_pct}%)</div>', unsafe_allow_html=True)

            with st.expander("🔍 Inspect Exact System & User Prompts Sent to LLM", expanded=False):
                p_c1, p_c2 = st.columns(2)
                with p_c1:
                    st.markdown("**System Prompt**")
                    st.text_area("sys_prompt", value=llm_res.get("system_prompt", ""), height=120, disabled=True, label_visibility="collapsed")
                with p_c2:
                    st.markdown(f"**User Prompt ({llm_res['context_tokens']} tokens context)**")
                    st.text_area("user_prompt", value=llm_res.get("user_prompt", ""), height=120, disabled=True, label_visibility="collapsed")


def render_retrieval_funnel(df_chunks: pd.DataFrame):
    st.subheader("🎯 Step 4 · Two-Stage Retrieval & Reranking Funnel")
    st.info(
        "💡 **Usage Guide — Step 4:** "
        "Test how candidate passages flow through the 2-stage retrieval pipeline. "
        "Stage 1 uses Bi-Encoder embeddings (`all-MiniLM-L6-v2`) to pull 13 candidates. "
        "Stage 2 uses Cross-Encoder (`bge-reranker-base`) joint attention to rescore and promote the needle passage to the top 4. "
        "Select an interactive workspace below to optimize chunking or inspect candidate rank shifts.",
        icon="ℹ️",
    )
    funnel_options = [
        "📊 Ragas Metric Evaluation & Benchmark Studio",
        "🎯 2-Stage Retrieval & Needle Tester",
        "🧩 Dynamic Chunking Strategy & Needle Optimizer",
    ]

    # Handle pending workspace transition BEFORE widget instantiation to prevent StreamlitWidgetAlreadyInstantiatedError
    if "funnel_workspace_pending" in st.session_state:
        pending_ws = st.session_state.pop("funnel_workspace_pending")
        if pending_ws in funnel_options:
            st.session_state["funnel_workspace_radio"] = pending_ws

    current_ws = st.session_state.get("funnel_workspace_radio", funnel_options[0])
    if current_ws not in funnel_options:
        current_ws = funnel_options[0]

    # Persistent segmented selection to guarantee zero tab jumping on any button click
    workspace_choice = st.radio(
        "Select Testing Workspace:",
        funnel_options,
        index=funnel_options.index(current_ws),
        horizontal=True,
        key="funnel_workspace_radio",
        help="Switch between Ragas metric evaluation (Faithfulness, Factual Correctness, Relevancy), 2-stage vector retrieval & needle testing, and dynamic chunking strategy optimization.",
    )

    if workspace_choice == "📊 Ragas Metric Evaluation & Benchmark Studio":
        render_ragas_metrics_studio(df_chunks)
        return

    if workspace_choice == "🧩 Dynamic Chunking Strategy & Needle Optimizer":
        render_chunking_strategy_optimizer(df_chunks)
        return

    # 2-Stage Retrieval & Needle Tester Mode
    st.subheader("🎯 Interactive Retrieval & Reranker Funnel")
    st.caption("Inspect candidate funnel from Bi-Encoder similarity through BGE Cross-Encoder reranking, with automated Chunk ID Needle Assertion.")

    with st.expander("🧩 Want to play with different chunking strategies & optimal tokens on this needle?", expanded=False):
        st.caption("Test how different chunking strategies (Hierarchical, Recursive Sliding Window, Semantic Paragraph, Sentence Window) impact retrieval rank and needle detection for this query.")
        def _jump_to_optimizer():
            st.session_state["funnel_workspace_pending"] = "🧩 Dynamic Chunking Strategy & Needle Optimizer"

        st.button("🚀 Open in Chunking Strategy Optimizer", key="btn_jump_to_optimizer", on_click=_jump_to_optimizer)

    active_res = st.session_state.get("active_chunk_results")

    # Load benchmark questions for quick needle testing presets
    benchmark_path = _REPO_ROOT / "test_data" / "rag_benchmark_questions.json"
    bench_cases = []
    if benchmark_path.exists():
        try:
            with open(benchmark_path, "r", encoding="utf-8") as f:
                bench_cases = json.load(f)
        except Exception:
            bench_cases = []

    needle_cases = [c for c in bench_cases if c.get("required_chunk_ids")]

    # Mode Selection: Custom Input vs Benchmark Presets
    funnel_mode = st.radio(
        "Select Query & Test Mode:",
        ["✏️ Custom Query & Target Needle", "📋 Load from Benchmark Presets"],
        horizontal=True,
        key="funnel_mode_radio",
        help="Choose 'Custom Query' to freely type any question and test retrieval without preset interference.",
    )

    if funnel_mode == "✏️ Custom Query & Target Needle":
        if "custom_funnel_q" not in st.session_state:
            st.session_state["custom_funnel_q"] = "What is the standard probation period duration for new employees?"
        if "custom_funnel_target" not in st.session_state:
            st.session_state["custom_funnel_target"] = "NEXORA TECHNOLOGIES PVT-12"

        col_q, col_target = st.columns([2, 1])
        with col_q:
            query = st.text_input(
                "✏️ Custom Test Query",
                key="custom_funnel_q",
                placeholder="Type any custom user query...",
                help="Type any arbitrary question to probe vector retrieval and reranking.",
            )
        with col_target:
            target_chunk_input = st.text_input(
                "🎯 Expected Target Chunk ID(s) (Optional)",
                key="custom_funnel_target",
                placeholder="e.g. NEXORA TECHNOLOGIES PVT-57 (leave empty for pure probe)",
                help="Enter one or more comma-separated Chunk IDs to assert against retrieval results. Leave empty for pure exploration.",
            )

        def _set_custom_needle(cid: str):
            st.session_state["custom_funnel_target"] = cid

        # Quick Chunk ID Browser helper for custom mode
        with st.expander("🔎 Browse All Available Chunk IDs from Active Vector Store", expanded=False):
            if not df_chunks.empty:
                st.caption("Search or select an indexed chunk to view its content or set as expected needle:")
                search_needle = st.text_input("Filter Chunks by keyword / prefix", placeholder="e.g. leave, probation, DOC-001", key="search_custom_needle_filter")
                filtered_cids = df_chunks
                if search_needle.strip():
                    filtered_cids = df_chunks[
                        df_chunks["chunk_id"].str.contains(search_needle, case=False, na=False) |
                        df_chunks["text"].str.contains(search_needle, case=False, na=False)
                    ]
                if not filtered_cids.empty:
                    pick_cid = st.selectbox("Select Chunk ID to View", filtered_cids["chunk_id"].tolist(), key="pick_custom_cid_helper")
                    picked_row = filtered_cids[filtered_cids["chunk_id"] == pick_cid].iloc[0]
                    st.markdown(f"**Chunk ID:** `{picked_row['chunk_id']}` &nbsp;|&nbsp; **Document:** `{picked_row['source']}` &nbsp;|&nbsp; **Tokens:** `{picked_row['token_count']}`")
                    st.caption(picked_row["text"][:160] + "...")
                    st.button(
                        f"🎯 Set `{picked_row['chunk_id']}` as Expected Target Needle",
                        key="btn_pick_custom_needle",
                        on_click=_set_custom_needle,
                        args=(picked_row["chunk_id"],),
                    )
                else:
                    st.info("No matching chunks found.")
            else:
                st.info("ChromaDB is empty.")

    else:
        # Preset Mode
        preset_labels = [
            f"[{c['id']}] {c['question'][:55]}... (Target: {', '.join(c.get('required_chunk_ids', []))})"
            for c in needle_cases
        ]

        if "preset_funnel_q" not in st.session_state:
            st.session_state["preset_funnel_q"] = "What is the standard probation period duration for new employees?"
        if "preset_funnel_target" not in st.session_state:
            st.session_state["preset_funnel_target"] = "NEXORA TECHNOLOGIES PVT-12"

        def _on_preset_change():
            chosen = st.session_state.get("ret_preset_choice", "")
            for c in needle_cases:
                if c["id"] in chosen:
                    st.session_state["preset_funnel_q"] = c.get("question", "")
                    st.session_state["preset_funnel_target"] = ", ".join(c.get("required_chunk_ids", []))
                    break

        selected_preset = st.selectbox(
            "🎯 Quick Benchmark Test Presets (Pre-configured Query & Target Chunk ID)",
            options=preset_labels,
            key="ret_preset_choice",
            on_change=_on_preset_change,
            help="Select a benchmark case to automatically populate the test query and its expected target chunk ID.",
        )

        col_q, col_target = st.columns([2, 1])
        with col_q:
            query = st.text_input("Benchmark Test Query", key="preset_funnel_q")
        with col_target:
            target_chunk_input = st.text_input(
                "🎯 Expected Target Chunk ID(s)",
                key="preset_funnel_target",
                help="Target Chunk ID from benchmark test case.",
            )

        def _set_preset_needle(cid: str):
            st.session_state["preset_funnel_target"] = cid

        # Suggestion notice only in preset mode
        active_target = target_chunk_input.strip()
        q_words = set(query.lower().replace("?", "").replace(",", "").split())
        meaningful_q_words = q_words - {"what", "is", "the", "how", "do", "we", "get", "to", "for", "a", "an", "in", "of", "are", "many", "may", "can", "i"}
        suggested_case = None
        if meaningful_q_words:
            for c in needle_cases:
                b_words = set(c.get("question", "").lower().replace("?", "").split())
                if meaningful_q_words.intersection(b_words):
                    suggested_case = c
                    break

        if suggested_case:
            s_id = ", ".join(suggested_case.get("required_chunk_ids", []))
            if not active_target:
                st.info(f"💡 **Suggested Target Chunk for this query:** `{s_id}` (matches benchmark `[{suggested_case['id']}] {suggested_case['question']}`)")
                st.button(f"🎯 Set Expected Target to `{s_id}`", key="btn_apply_sug", on_click=_set_preset_needle, args=(s_id,))
            elif active_target != s_id and not any(cid.strip() in active_target for cid in suggested_case.get("required_chunk_ids", [])):
                st.warning(f"⚠️ **Target Mismatch Notice:** Your query relates to *'{suggested_case.get('question')}'* (which targets `{s_id}`), but your expected target is set to `{active_target}`.")
                st.button(f"🔄 Switch Expected Target to `{s_id}`", key="btn_switch_sug", on_click=_set_preset_needle, args=(s_id,))

    expected_target_ids = [cid.strip() for cid in target_chunk_input.split(",") if cid.strip()]

    col_k1, col_k2, col_role = st.columns(3)
    with col_k1:
        cand_k = st.slider("Chroma Candidates (Initial K)", 5, 25, 13, key="slider_cand_k")
    with col_k2:
        final_k = st.slider("Reranked Output (Final K)", 1, 10, 4, key="slider_final_k")
    with col_role:
        role = st.selectbox("User Role Scope", ["Employee (Public)", "Project Lead (Scoped 121)"], key="select_role_scope")

    if st.button("🚀 Run Retrieval & Assert Chunk ID", type="primary", use_container_width=True, key="btn_run_funnel_retrieval"):
        store = get_chroma_store()
        reranker = get_cached_reranker()

        t0 = time.time()
        # 1. Bi-Encoder candidate search
        candidates = store.query(query_text=query, top_k=cand_k)
        retrieval_time = (time.time() - t0) * 1000

        # 2. Cross-Encoder Reranking
        t1 = time.time()
        reranked = reranker.rerank(query=query, candidates=candidates, top_k=final_k)
        rerank_time = (time.time() - t1) * 1000

        top_retrieved_text = reranked[0].get("text", "") if reranked else ""
        top_retrieved_id = reranked[0].get("id", "none") if reranked else "none"

        # Persist bundle in session state so buttons don't reset view
        st.session_state["funnel_bundle"] = {
            "query": query,
            "expected_target_ids": expected_target_ids,
            "candidates": candidates,
            "reranked": reranked,
            "retrieval_time": retrieval_time,
            "rerank_time": rerank_time,
            "cand_k": cand_k,
            "final_k": final_k,
            "top_id": top_retrieved_id,
            "top_text": top_retrieved_text,
        }
        # Initialize candidate response with first factual sentence and clear old audit
        st.session_state.pop("ragas_audit_result", None)
        st.session_state.pop("geval_audit_result", None)
        first_sentence = top_retrieved_text.split(".")[0].strip() + "." if "." in top_retrieved_text else top_retrieved_text[:120]
        st.session_state["eval_rag_resp_text"] = first_sentence

    # Render Active Funnel Results (Persists across button clicks)
    bundle = st.session_state.get("funnel_bundle")
    if bundle:
        b_query = bundle["query"]
        b_target_ids = bundle["expected_target_ids"]
        b_candidates = bundle["candidates"]
        b_reranked = bundle["reranked"]
        b_ret_time = bundle["retrieval_time"]
        b_rerank_time = bundle["rerank_time"]
        b_cand_k = bundle["cand_k"]
        b_final_k = bundle["final_k"]
        top_fetched_id = bundle["top_id"]
        top_retrieved_text = bundle["top_text"]

        # Needle Verification Diagnostics
        if b_target_ids:
            st.markdown("---")
            st.markdown("### 🎯 Needle Chunk Verification & Assertion")

            evaluations = {}
            for cid in b_target_ids:
                s1_rank = next((i for i, c in enumerate(b_candidates, 1) if c.get("id") == cid), None)
                s2_rank = next((i for i, r in enumerate(b_reranked, 1) if r.get("id") == cid), None)
                s1_dist = b_candidates[s1_rank - 1].get("distance") if s1_rank else None
                s2_score = b_reranked[s2_rank - 1].get("_rerank_score") if s2_rank else None

                if s2_rank == 1:
                    verdict_label = "🎯 BULLSEYE HIT (Rank #1)"
                    verdict_type = "success"
                elif s2_rank is not None:
                    verdict_label = f"✅ TOP-{b_final_k} HIT (Rank #{s2_rank})"
                    verdict_type = "info"
                elif s1_rank is not None:
                    verdict_label = f"⚠️ RERANKER DEMOTION (S1: #{s1_rank})"
                    verdict_type = "warning"
                else:
                    verdict_label = "❌ BI-ENCODER MISS"
                    verdict_type = "error"

                evaluations[cid] = {
                    "s1_rank": s1_rank,
                    "s1_dist": s1_dist,
                    "s2_rank": s2_rank,
                    "s2_score": s2_score,
                    "verdict_label": verdict_label,
                    "verdict_type": verdict_type,
                }

            # Top Summary Banner
            primary_target = b_target_ids[0]
            pe = evaluations[primary_target]

            if pe["s2_rank"] == 1:
                st.success(f"🎯 **BULLSEYE HIT!** Target Chunk `{primary_target}` was retrieved as **Rank #1** by the Cross-Encoder (Score: `{pe['s2_score']:.4f}`).")
            elif pe["s2_rank"] is not None:
                st.info(f"✅ **NEEDLE RETRIEVED!** Target Chunk `{primary_target}` was fetched in the final top-{b_final_k} at **Rank #{pe['s2_rank']}** (Score: `{pe['s2_score']:.4f}`).")
            elif pe["s1_rank"] is not None:
                st.warning(f"⚠️ **RERANKER DEMOTION:** Target Chunk `{primary_target}` was found in Stage 1 Bi-Encoder (Rank #{pe['s1_rank']}, dist=`{pe['s1_dist']:.4f}`), but Cross-Encoder demoted it outside Top-{b_final_k}.")
            else:
                st.error(f"❌ **BI-ENCODER MISS:** Target Chunk `{primary_target}` was NOT found in the Top-{b_cand_k} Chroma candidates. The embedding search missed this chunk.")

            # Metrics row
            v_col1, v_col2, v_col3, v_col4 = st.columns(4)
            v_col1.metric("Target Chunk ID", primary_target)
            v_col2.metric("Stage 1 Bi-Encoder", f"Rank #{pe['s1_rank']} / {b_cand_k}" if pe['s1_rank'] else "MISS", delta="In Candidates" if pe['s1_rank'] else "Missed", delta_color="normal" if pe['s1_rank'] else "inverse")
            v_col3.metric("Stage 2 Cross-Encoder", f"Rank #{pe['s2_rank']} / {b_final_k}" if pe['s2_rank'] else "DROPPED", delta="Retrieved in Top-K" if pe['s2_rank'] else "Demoted", delta_color="normal" if pe['s2_rank'] else "inverse")
            v_col4.metric("Top-1 Fetched Chunk ID", top_fetched_id, delta="Bullseye Match" if top_fetched_id in b_target_ids else "Different Top-1", delta_color="normal" if top_fetched_id in b_target_ids else "off")

            # Side-by-side snippet comparison
            with st.expander("🔍 Side-by-Side Comparison: Expected Target Chunk vs. Actual Top-1 Retrieved Chunk", expanded=True):
                cmp_left, cmp_right = st.columns(2)

                target_text = "Content not found in local memory"
                target_meta = {}
                if not df_chunks.empty:
                    match_row = df_chunks[df_chunks["chunk_id"] == primary_target]
                    if not match_row.empty:
                        target_text = match_row.iloc[0]["text"]
                        target_meta = match_row.iloc[0].to_dict()
                if target_text == "Content not found in local memory":
                    cand_match = next((c for c in b_candidates if c.get("id") == primary_target), None)
                    if cand_match:
                        target_text = cand_match.get("text", "")
                        target_meta = cand_match.get("metadata", {})

                with cmp_left:
                    st.markdown(f"#### 🎯 Expected Target: `{primary_target}`")
                    st.caption(f"Document: `{target_meta.get('source', 'N/A')}` | Tokens: `{len(target_text.split())}`")
                    st.text_area(label="Expected Chunk Content", value=target_text, height=180, disabled=True, label_visibility="collapsed", key="funnel_expected_chunk_content")

                with cmp_right:
                    top_obj = b_reranked[0] if b_reranked else {}
                    top_text = top_obj.get("text", "")
                    top_meta = top_obj.get("metadata", {})
                    top_score = top_obj.get("_rerank_score", 0.0)
                    st.markdown(f"#### 🥇 Actual Top-1: `{top_fetched_id}`")
                    st.caption(f"Document: `{top_meta.get('source', 'N/A')}` | Score: `{top_score:.4f}` | Tokens: `{len(top_text.split())}`")
                    st.text_area(label="Actual Top-1 Content", value=top_text, height=180, disabled=True, label_visibility="collapsed", key="funnel_top1_content")

                if top_fetched_id and top_fetched_id != "NONE" and top_fetched_id not in b_target_ids:
                    target_key = "custom_funnel_target" if funnel_mode == "✏️ Custom Query & Target Needle" else "preset_funnel_target"
                    def _adopt_top1(top_id: str, t_key: str):
                        st.session_state[t_key] = top_id
                    st.button(f"🎯 Adopt Actual Top-1 (`{top_fetched_id}`) as Expected Target Needle", key="btn_adopt_top1", on_click=_adopt_top1, args=(top_fetched_id, target_key))
        else:
            st.markdown("---")
            st.info("ℹ️ **Pure Retrieval Probe Mode:** No expected target chunk ID was specified. Inspecting top candidates below.")

        # Stage 1 Candidates Table
        st.markdown(f"#### Stage 1: ChromaDB Candidate Retrieval (`{b_ret_time:.1f}ms`, Top-{b_cand_k})")
        cand_records = []
        for rank, cand in enumerate(b_candidates, start=1):
            cid = cand.get("id", "unknown")
            meta = cand.get("metadata", {})
            is_new_doc = (meta.get("document_id") == active_res.get("doc_id") or meta.get("source") == active_res.get("source")) if active_res else False
            src_str = f"🌟 {meta.get('source', 'unknown')} [NEW]" if is_new_doc else meta.get("source", "unknown")
            is_target = "🎯 TARGET NEEDLE" if cid in b_target_ids else ""
            cand_records.append({
                "Rank": rank,
                "Target Match": is_target,
                "Chunk ID": cid,
                "Source": src_str,
                "Distance": round(cand.get("distance", 4), 4) if cand.get("distance") is not None else None,
                "Snippet": cand.get("text", "")[:80] + "...",
            })
        st.dataframe(pd.DataFrame(cand_records), use_container_width=True)

        # Stage 2 Reranked Table
        st.markdown(f"#### Stage 2: BGE Cross-Encoder Top-{b_final_k} Reranking (`{b_rerank_time:.1f}ms`)")
        rerank_rows = []
        for i, item in enumerate(b_reranked, start=1):
            cid = item.get("id", "unknown")
            meta = item.get("metadata", {})
            score = item.get("_rerank_score", 0.0)
            is_new_doc = (meta.get("document_id") == active_res.get("doc_id") or meta.get("source") == active_res.get("source")) if active_res else False
            src_str = f"🌟 {meta.get('source', 'unknown')} [NEW]" if is_new_doc else meta.get("source", "unknown")
            is_target = "🎯 TARGET NEEDLE" if cid in b_target_ids else ""
            rerank_rows.append({
                "Final Rank": i,
                "Target Match": is_target,
                "Chunk ID": cid,
                "Source": src_str,
                "Rerank Score": round(score, 4),
                "Snippet": item.get("text", "")[:80] + "...",
            })
        st.dataframe(pd.DataFrame(rerank_rows), use_container_width=True)

        for i, item in enumerate(b_reranked, start=1):
            meta = item.get("metadata", {})
            score = item.get("_rerank_score", 0.0)
            chunk_id = item.get("id", "unknown")
            is_target = chunk_id in b_target_ids
            target_badge = " 🎯 [TARGET NEEDLE HIT]" if is_target else ""
            is_new_doc = (meta.get("document_id") == active_res.get("doc_id") or meta.get("source") == active_res.get("source")) if active_res else False
            new_tag = " 🌟 [NEWLY ADDED DOC]" if is_new_doc else ""
            with st.expander(f"**Rank {i}: `{chunk_id}`**{target_badge} — {meta.get('source', 'Unknown')}{new_tag} (Score: `{score:.4f}`)", expanded=(i == 1 or is_target)):
                st.markdown(f"🧩 **Chunk ID:** `{chunk_id}` &nbsp;|&nbsp; **Scope:** `{meta.get('project_id', 'unassigned')}` &nbsp;|&nbsp; **Rerank Score:** `{score:.4f}`")
                st.code(chunk_id, language="text")
                st.info(item.get("text", ""))

        # Stage 3: Ragas Response Quality & Grounding Auditor
        st.markdown("---")
        st.subheader("📊 Layer 3 & 4: Ragas Response Quality & Grounding Auditor")
        st.caption("Evaluate whether an LLM-generated response is faithfully grounded in the retrieved chunk without hallucinating.")

        if top_retrieved_text:
            if "eval_rag_resp_text" not in st.session_state:
                first_sentence = top_retrieved_text.split(".")[0].strip() + "." if "." in top_retrieved_text else top_retrieved_text[:120]
                st.session_state["eval_rag_resp_text"] = first_sentence

            def _set_funnel_resp(text: str):
                st.session_state["eval_rag_resp_text"] = text
                st.session_state.pop("ragas_audit_result", None)

            col_ge_actions, col_ge_box = st.columns([1.3, 2.7])
            with col_ge_actions:
                st.markdown("**Option B Helpers:**")
                if st.button("🤖 Generate Live LLM Response", key="btn_gen_live_llm", use_container_width=True, type="secondary", help="Calls live LLM via OpenRouter using retrieved chunks. Text appears in box for inspection & tweaking."):
                    with st.spinner("Generating live response from LLM using top retrieved chunks..."):
                        from app.use_cases.chat.rag_context_builder import RAGContextBuilder
                        from app.infrastructure.llm.openrouter_client import OpenRouterClient
                        builder = RAGContextBuilder()
                        sys_p = builder.build_system_prompt()
                        user_p = builder.build_user_prompt(question=b_query, context_chunks=b_reranked)
                        llm_client = OpenRouterClient()
                        live_resp = llm_client.generate(messages=[
                            {"role": "system", "content": sys_p},
                            {"role": "user", "content": user_p},
                        ]).strip()
                        st.session_state["eval_rag_resp_text"] = live_resp
                        st.session_state.pop("ragas_audit_result", None)
                        st.rerun()

                first_sentence = top_retrieved_text.split(".")[0].strip() + "." if "." in top_retrieved_text else top_retrieved_text[:120]
                st.button(
                    "🟢 Grounded Sample",
                    key="btn_load_grounded",
                    use_container_width=True,
                    on_click=_set_funnel_resp,
                    args=(first_sentence,),
                )

                st.button(
                    "🔴 Hallucinated Sample",
                    key="btn_load_hallucinated",
                    use_container_width=True,
                    on_click=_set_funnel_resp,
                    args=("Employees receive 45 days of annual leave and a free company car.",),
                )

            with col_ge_box:
                st.text_area(
                    "Candidate RAG Response to Audit (Inspect & tweak freely before auditing)",
                    height=125,
                    key="eval_rag_resp_text",
                    help="Edit, tweak, or inject custom assertions to test Ragas metrics.",
                )

            st.markdown("##### Evaluator Model Selection")
            funnel_eval_model = st.selectbox(
                "Evaluator LLM (OpenRouter):",
                ["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet", "meta-llama/llama-3.1-70b-instruct"],
                index=0,
                key="funnel_eval_model_sel",
            )

            col_btn1, col_btn2 = st.columns([1, 1])
            with col_btn1:
                if st.button("🚀 Audit Current Response (Ragas Metrics)", type="primary", use_container_width=True, key="btn_run_ragas"):
                    curr_resp = st.session_state.get("eval_rag_resp_text", "").strip()
                    if not curr_resp:
                        st.warning("Candidate response cannot be empty.")
                    else:
                        with st.spinner("Computing Ragas Faithfulness, Factual Correctness & Relevancy via OpenRouter..."):
                            tc = TestCase(
                                id="FUNNEL-AUDIT",
                                title="Funnel Audit",
                                category="FACTUAL_POLICY_LOOKUP",
                                input=TestInput(question=b_query),
                                gold_evidence=GoldEvidence(),
                                expected_behavior=ExpectedBehavior(answer=top_retrieved_text[:200])
                            )
                            eval_res = execute_ragas_evaluation(
                                test_case=tc,
                                response_text=curr_resp,
                                context_chunks=[{"text": top_retrieved_text, "id": "top-chunk"}],
                                execution_mode="remote_provider_allowed",
                                llm_provider="openrouter",
                                evaluator_model=funnel_eval_model
                            )
                            st.session_state["ragas_audit_result"] = eval_res

            with col_btn2:
                if st.button("⚡ 1-Click: Generate Live LLM Response & Audit", type="secondary", use_container_width=True, key="btn_gen_and_audit"):
                    with st.spinner("Step 1: Generating live LLM response... Step 2: Running Ragas audit..."):
                        from app.use_cases.chat.rag_context_builder import RAGContextBuilder
                        from app.infrastructure.llm.openrouter_client import OpenRouterClient

                        builder = RAGContextBuilder()
                        sys_p = builder.build_system_prompt()
                        user_p = builder.build_user_prompt(question=b_query, context_chunks=b_reranked)
                        llm_client = OpenRouterClient()
                        live_resp = llm_client.generate(messages=[
                            {"role": "system", "content": sys_p},
                            {"role": "user", "content": user_p},
                        ]).strip()

                        st.session_state["eval_rag_resp_text"] = live_resp

                        tc = TestCase(
                            id="FUNNEL-AUDIT",
                            title="Funnel Audit",
                            category="FACTUAL_POLICY_LOOKUP",
                            input=TestInput(question=b_query),
                            gold_evidence=GoldEvidence(),
                            expected_behavior=ExpectedBehavior(answer=top_retrieved_text[:200])
                        )
                        eval_res = execute_ragas_evaluation(
                            test_case=tc,
                            response_text=live_resp,
                            context_chunks=[{"text": top_retrieved_text, "id": "top-chunk"}],
                            execution_mode="remote_provider_allowed",
                            llm_provider="openrouter",
                            evaluator_model=funnel_eval_model
                        )
                        st.session_state["ragas_audit_result"] = eval_res

            # Render Ragas Evaluation Card in UI if available
            eval_res = st.session_state.get("ragas_audit_result")
            if eval_res:
                st.markdown("---")
                funnel_llm_resp = st.session_state.get("eval_rag_resp_text", "")
                render_ragas_evaluation_card(eval_res, llm_response=funnel_llm_resp)


def render_benchmark_suite(df_chunks: pd.DataFrame):
    st.subheader("🧪 Ground-Truth RAG Benchmark Suite")
    st.caption("Execute 15+ benchmark test cases validating Recall@k with explicit required Chunk IDs.")

    benchmark_path = _REPO_ROOT / "test_data" / "rag_benchmark_questions.json"
    if not benchmark_path.exists():
        st.error(f"Benchmark file not found at {benchmark_path}")
        return

    with open(benchmark_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    active_res = st.session_state.get("active_chunk_results")
    prefill = st.session_state.get("benchmark_prefill", {})

    # Category Filter & Search
    categories = ["All Categories"] + sorted(list({c.get("category", "") for c in cases}))
    col_c1, col_c2 = st.columns([1, 2])
    with col_c1:
        selected_cat = st.selectbox("Filter Category", categories)
    with col_c2:
        search_q = st.text_input("Filter Questions", placeholder="Search questions...")

    filtered_cases = cases
    if selected_cat != "All Categories":
        filtered_cases = [c for c in filtered_cases if c.get("category") == selected_cat]
    if search_q:
        filtered_cases = [c for c in filtered_cases if search_q.lower() in c.get("question", "").lower()]

    st.markdown(f"**Loaded {len(filtered_cases)} of {len(cases)} benchmark test cases.**")

    df_cases_view = pd.DataFrame(filtered_cases)
    if "required_chunk_ids" not in df_cases_view.columns:
        df_cases_view["required_chunk_ids"] = [[] for _ in range(len(df_cases_view))]
    df_cases_view["required_chunk_ids"] = df_cases_view["required_chunk_ids"].apply(
        lambda ids: ", ".join(ids) if isinstance(ids, list) else str(ids)
    )

    df_cases_display = df_cases_view.rename(columns={
        "id": "Test ID",
        "category": "Category",
        "question": "Question",
        "required_chunk_ids": "Required Chunk IDs",
        "expected_document": "Expected Document",
    })
    st.dataframe(
        df_cases_display[["Test ID", "Category", "Question", "Required Chunk IDs", "Expected Document"]],
        use_container_width=True,
        height=240,
    )

    # Add New Question Form with Dynamic Needle Chunk ID Selector
    form_expanded = bool(prefill)
    with st.expander("➕ Add New Benchmark Test Question to Dataset", expanded=form_expanded):
        if prefill:
            st.info(f"✨ **Pre-filling test case for:** `{prefill.get('expected_document')}` &nbsp;|&nbsp; **Suggested Needle Chunks:** `{', '.join(prefill.get('chunk_ids', []))}`")

        col_q1, col_q2 = st.columns([2, 1])
        with col_q1:
            new_q = st.text_input(
                "Test Question",
                value=prefill.get("question", ""),
                placeholder="e.g. Can an employee encash unused privilege leaves?",
            )
            new_notes = st.text_input(
                "Notes / Test Purpose",
                value=f"Validates policy lookup for {prefill.get('expected_document', '')}" if prefill else "",
                placeholder="Validates leave encashment policy lookup",
            )
        with col_q2:
            new_cat = st.selectbox("Category", [
                "FACTOID_POLICY",
                "PROCEDURAL_WORKFLOW",
                "NUMERICAL_CALCULATION",
                "INTENT_PERSONAL_BALANCE",
                "NEGATIVE_HALLUCINATION_GUARD",
                "MULTI_SECTION_SYNTHESIS",
                "RBAC_CONFIDENTIAL_ISOLATION",
                "SYNONYM_ROBUSTNESS",
            ])
            new_id = st.text_input("Test ID", value=f"RAG-VAL-{len(cases)+1:02d}")

        col_q3, col_q4, col_q5 = st.columns(3)
        with col_q3:
            # Build all known documents including newly added ones
            all_known_docs = set()
            for c in cases:
                if c.get("expected_document"):
                    all_known_docs.add(c.get("expected_document"))
            if not df_chunks.empty:
                for s in df_chunks["source"].unique():
                    if s and s != "unknown":
                        all_known_docs.add(s)
            if active_res and active_res.get("source"):
                all_known_docs.add(active_res["source"])

            doc_options = ["(None / Out of Domain)"] + sorted(list(all_known_docs))
            def_idx = 0
            target_doc_name = prefill.get("expected_document")
            if target_doc_name and target_doc_name in doc_options:
                def_idx = doc_options.index(target_doc_name)

            selected_exp_doc = st.selectbox("Expected Document", doc_options, index=def_idx)
            exp_doc_val = None if selected_exp_doc.startswith("(None") else selected_exp_doc
        with col_q4:
            new_kws = st.text_input("Expected Keywords (comma-separated)", placeholder="encash, privilege leave, approval")
        with col_q5:
            new_intent = st.selectbox("Expected Intent", ["policy_lookup", "personal_status", "general_inquiry", "out_of_domain"])

        # Dynamic Chunk ID Selection for the Selected Document
        doc_available_chunk_ids = []
        if exp_doc_val and not df_chunks.empty:
            doc_available_chunk_ids = df_chunks[df_chunks["source"] == exp_doc_val]["chunk_id"].tolist()
        if not doc_available_chunk_ids and active_res and active_res.get("source") == exp_doc_val:
            doc_available_chunk_ids = [r["id"] for r in active_res["records"]]

        col_q6, col_q7 = st.columns([1.6, 0.8])
        with col_q6:
            preselected_chunk_ids = []
            if prefill and prefill.get("chunk_ids"):
                preselected_chunk_ids = [cid for cid in prefill["chunk_ids"] if cid in doc_available_chunk_ids]

            if doc_available_chunk_ids:
                chosen_chunk_ids = st.multiselect(
                    f"Select Required Chunk IDs for '{exp_doc_val}' ({len(doc_available_chunk_ids)} available)",
                    options=doc_available_chunk_ids,
                    default=preselected_chunk_ids,
                    help="Pick the exact chunk IDs that must be retrieved in top-k for this test case to PASS.",
                )
            else:
                chosen_chunk_ids = []

            extra_chunk_ids = st.text_input(
                "Additional / Manual Chunk IDs (comma-separated)",
                value="" if doc_available_chunk_ids else (", ".join(prefill.get("chunk_ids", []))),
                placeholder="e.g. DOC-002-0, TEST-001-0",
            )
        with col_q7:
            def_scope = prefill.get("project_id", "unassigned")
            new_scope = st.text_input("Project Scope (if RBAC)", value=def_scope)

        new_refusal = st.checkbox("Expected Refusal (Negative Guardrail)")

        if st.button("💾 Save Benchmark Question to Dataset"):
            if not new_q.strip():
                st.error("Please enter a question.")
            else:
                combined_cids = list(dict.fromkeys(
                    chosen_chunk_ids + [cid.strip() for cid in extra_chunk_ids.split(",") if cid.strip()]
                ))
                new_case = {
                    "id": new_id,
                    "category": new_cat,
                    "question": new_q.strip(),
                    "expected_intent": new_intent,
                    "should_succeed": True,
                }
                if exp_doc_val:
                    new_case["expected_document"] = exp_doc_val
                else:
                    new_case["expected_document"] = None
                if new_kws.strip():
                    new_case["expected_answer_keywords"] = [k.strip() for k in new_kws.split(",") if k.strip()]
                new_case["required_chunk_ids"] = combined_cids
                if new_scope.strip() and new_scope.strip() != "unassigned":
                    new_case["project_id"] = new_scope.strip()
                if new_refusal:
                    new_case["expected_refusal"] = True
                    new_case["expected_refusal_substring"] = "could not find that information"
                if new_notes.strip():
                    new_case["notes"] = new_notes.strip()

                cases.append(new_case)
                with open(benchmark_path, "w", encoding="utf-8") as f:
                    json.dump(cases, f, indent=2)

                if "benchmark_prefill" in st.session_state:
                    del st.session_state["benchmark_prefill"]

                st.success(f"Added test case {new_id} targeting chunks [{', '.join(combined_cids)}] to test_data/rag_benchmark_questions.json!")
                st.rerun()

    # Runner with explicit Chunk ID evaluation
    if st.button("🚀 Run Live Benchmark Validation", type="primary"):
        classifier = get_query_intent_classifier()
        store = get_chroma_store()
        reranker = get_cached_reranker()

        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, tc in enumerate(filtered_cases):
            status_text.text(f"Running test {idx+1}/{len(filtered_cases)}: {tc['id']}...")
            q_id = tc["id"]
            question = tc["question"]
            cat = tc["category"]
            should_succeed = tc.get("should_succeed", True)
            expected_intent = tc.get("expected_intent")

            t0 = time.time()
            intent_result = classifier.classify(question)
            detected_intent = intent_result.intent.value

            intent_pass = (detected_intent == expected_intent) if expected_intent else True

            candidates = store.query(query_text=question, top_k=13)
            reranked = reranker.rerank(query=question, candidates=candidates, top_k=4)
            duration = time.time() - t0

            top_chunk_id = reranked[0].get("id", "none") if reranked else "none"
            retrieved_chunk_ids = [r.get("id", "") for r in reranked]
            req_chunk_ids = tc.get("required_chunk_ids", [])

            expected_doc = (tc.get("expected_document") or "").lower()
            if expected_doc:
                hit = any(expected_doc in str(r.get("metadata", {}).get("source", "")).lower() for r in reranked)
                hit_str = "YES" if hit else "NO"
            else:
                hit = True
                hit_str = "N/A"

            # Check if required chunk IDs were retrieved
            if req_chunk_ids:
                chunk_hit = any(cid in retrieved_chunk_ids for cid in req_chunk_ids)
                chunk_hit_str = "YES" if chunk_hit else "NO"
            else:
                chunk_hit = True
                chunk_hit_str = "N/A"

            is_pass = intent_pass and (hit if should_succeed else True) and chunk_hit

            results.append({
                "ID": q_id,
                "Category": cat,
                "Status": "PASS" if is_pass else "FAIL",
                "Top Chunk ID": top_chunk_id,
                "Required Chunk IDs": ", ".join(req_chunk_ids) if req_chunk_ids else "None",
                "Chunk Hit": chunk_hit_str,
                "Intent Match": "YES" if intent_pass else "NO",
                "Doc Hit @ 4": hit_str,
                "Duration": f"{duration:.2f}s",
                "Question": question,
                "Retrieved Chunk IDs": ", ".join(retrieved_chunk_ids),
                "Top Snippet": reranked[0].get("text", "")[:120] if reranked else "No chunks",
            })
            progress_bar.progress((idx + 1) / len(filtered_cases))

        status_text.empty()
        res_df = pd.DataFrame(results)

        pass_count = (res_df["Status"] == "PASS").sum()
        total_count = len(res_df)
        pct = (pass_count / total_count) * 100

        st.markdown(f"### Benchmark Result: **{pass_count} / {total_count} Passed ({pct:.1f}%)**")
        st.dataframe(
            res_df[["ID", "Category", "Status", "Top Chunk ID", "Required Chunk IDs", "Retrieved Chunk IDs", "Chunk Hit", "Intent Match", "Doc Hit @ 4", "Duration", "Question"]],
            use_container_width=True,
        )

        with st.expander("🔎 Detailed Candidate Traces per Test Case", expanded=False):
            for r in results:
                st.markdown(f"**[{r['Status']}] {r['ID']}** — `{r['Question']}`")
                st.markdown(f"🧩 **Top Chunk ID:** `{r['Top Chunk ID']}` &nbsp;|&nbsp; **Required:** `{r['Required Chunk IDs']}` &nbsp;|&nbsp; **Retrieved (@ 4):** `{r['Retrieved Chunk IDs']}`")
                st.caption(f"Top Snippet: {r['Top Snippet']}...")


def main():
    st.markdown("""
    <div class="workbench-header">
        <div class="brand-row">
            <span class="brand-badge">KNOWLAYER</span>
            <span class="brand-title">Developer Sandbox & Observability Studio</span>
            <span class="brand-version">v3.4 • Enterprise RAG</span>
        </div>
        <div class="brand-subline">Interactive evaluation workbench for ChromaDB chunk validation, 6-dimension quality auditing, 2-stage retrieval funnel, and RAGAS benchmarks.</div>
    </div>
    """, unsafe_allow_html=True)

    df_chunks = load_all_chunks()

    with st.sidebar:
        st.markdown("""
        <div class="sidebar-brand">
            <div class="sidebar-logo">KL</div>
            <div>
                <div class="sidebar-title">KnowLayer Studio</div>
                <div class="sidebar-sub">Observability Suite</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("### ⚙️ System Status")
        st.metric("Total Chunks", f"{len(df_chunks):,}")
        st.metric("Embedder Context", "256 tokens")
        st.metric("Reranker Model", "BAAI/bge-reranker-base")
        st.markdown("---")
        st.markdown("### 🔎 Quick Chunk ID Lookup")
        lookup_chunk_id = st.text_input("Find Chunk by ID", placeholder="e.g. TEST-001-0")
        if lookup_chunk_id.strip():
            cid_query = lookup_chunk_id.strip()
            matched = df_chunks[df_chunks["chunk_id"] == cid_query] if not df_chunks.empty else pd.DataFrame()
            if not matched.empty:
                m_row = matched.iloc[0]
                st.success(f"Found in `{m_row['source']}` ({m_row['token_count']} tok)")
                st.caption(m_row["text"][:140] + "...")
            else:
                active_res = st.session_state.get("active_chunk_results")
                found_in_active = None
                if active_res:
                    for r in active_res.get("records", []):
                        if r["id"] == cid_query:
                            found_in_active = r
                            break
                if found_in_active:
                    st.info(f"🌟 Found in active session document `{active_res['source']}` ({len(found_in_active['text'].split())} tok)")
                    st.caption(found_in_active["text"][:140] + "...")
                else:
                    st.warning("Chunk ID not found in active collection.")
        st.markdown("---")
        st.markdown("### 📁 Dataset Scope")
        if not df_chunks.empty:
            for src, count in df_chunks["source"].value_counts().items():
                st.caption(f"• **{src}**: {count} chunks (`{Path(src).stem}-*`)")
        st.markdown("---")
        st.caption("KnowLayer • Enterprise RAG Architecture v3")

    tab_home, tab_s1, tab_s2, tab_s3, tab_s4, tab_s5 = st.tabs([
        "🏠 Home Overview & Guided Pipeline",
        "📁 Step 1: Ingestion & Chunking",
        "📊 Step 2: Chunk Quality (CQI)",
        "🔍 Step 3: Chunk Explorer",
        "🎯 Step 4: 2-Stage Retrieval & Funnel",
        "🧪 Step 5: Test Studio & Benchmarks",
    ])

    with tab_home:
        render_home_dashboard(df_chunks)
    with tab_s1:
        render_golden_data_and_ingestion(df_chunks)
    with tab_s2:
        render_quality_diagnostics(df_chunks)
    with tab_s3:
        render_chunk_explorer(df_chunks)
    with tab_s4:
        render_retrieval_funnel(df_chunks)
    with tab_s5:
        render_test_studio_tab(df_chunks)



if __name__ == "__main__":
    main()
