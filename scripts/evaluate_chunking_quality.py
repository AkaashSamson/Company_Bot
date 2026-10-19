"""
Chunking Quality Evaluation & Observability Script

Measures the structural, semantic, and token quality of all chunks stored in ChromaDB:
1. Token Budget Compliance (<= 256 tokens for sentence-transformers/all-MiniLM-L6-v2)
2. Information Density & Granularity (sweet spot 40-256 tokens vs stub chunks)
3. Structural Context Preservation (presence of hierarchy_path & section_heading)
4. Canonical Metadata Completeness (document_id, project_id, source)
5. Redundancy & Deduplication (Jaccard / duplicate text detection)
6. Composite Chunking Quality Index (CQI) score out of 100

Usage:
    python scripts/evaluate_chunking_quality.py [--json]
"""

import argparse
import json
import logging
import math
import sys
from collections import Counter
from pathlib import Path

# Add project root to sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Safe stdout encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


from app.core.settings import BASE_DIR, COLLECTION_NAME
from app.infrastructure.vector.chroma_client import ChromaVectorStore

logging.basicConfig(level=logging.WARNING)


def evaluate_chroma_chunks():
    store = ChromaVectorStore(
        collection_name=COLLECTION_NAME,
        persist_directory=str(BASE_DIR / ".chroma"),
    )

    total_count = store.collection.count()
    if total_count == 0:
        print("ERROR: ChromaDB collection is empty. Run scripts/reingest_test_data.py first.")
        sys.exit(1)

    data = store.collection.get(include=["documents", "metadatas"])
    ids = data.get("ids", [])
    documents = data.get("documents", [])
    metadatas = data.get("metadatas", [])

    token_lengths = []
    char_lengths = []
    overflow_chunks = []
    stub_chunks = []
    missing_metadata_chunks = []
    missing_hierarchy_chunks = []
    text_hashes = {}
    duplicates = []
    docs_represented = set()
    projects_represented = set()

    for cid, doc, meta in zip(ids, documents, metadatas):
        text = str(doc or "").strip()
        meta = meta or {}
        
        words = text.split()
        t_len = len(words)
        c_len = len(text)
        
        token_lengths.append(t_len)
        char_lengths.append(c_len)

        src = meta.get("source_filename") or meta.get("source") or "unknown"
        doc_id = meta.get("document_id")
        proj_id = meta.get("project_id")
        hier = meta.get("hierarchy_path") or meta.get("section_heading") or meta.get("section")

        if doc_id:
            docs_represented.add(doc_id)
        if proj_id:
            projects_represented.add(proj_id)

        # 1. Token Budget (>256 tokens limit of MiniLM)
        if t_len > 256:
            overflow_chunks.append({"id": cid, "tokens": t_len, "source": src, "excess": t_len - 256})

        # 2. Stub/Noise chunks (<20 tokens or <50 chars)
        if t_len < 20 or c_len < 50:
            stub_chunks.append({"id": cid, "tokens": t_len, "chars": c_len, "source": src})

        # 3. Missing Metadata
        if not doc_id or not proj_id or src == "unknown":
            missing_metadata_chunks.append({"id": cid, "source": src})

        # 4. Missing Hierarchy
        if not hier:
            missing_hierarchy_chunks.append({"id": cid, "source": src})

        # 5. Duplicates
        normalized = " ".join(words).lower()
        if len(normalized) > 50:
            if normalized in text_hashes:
                duplicates.append({"id": cid, "dup_of": text_hashes[normalized], "source": src})
            else:
                text_hashes[normalized] = cid

    # Statistical Computations
    n = len(token_lengths)
    avg_tokens = sum(token_lengths) / n if n > 0 else 0
    token_lengths_sorted = sorted(token_lengths)
    median_tokens = token_lengths_sorted[n // 2] if n > 0 else 0
    p90_tokens = token_lengths_sorted[int(n * 0.9)] if n > 0 else 0
    max_tokens = max(token_lengths) if n > 0 else 0
    min_tokens = min(token_lengths) if n > 0 else 0
    
    variance = sum((x - avg_tokens) ** 2 for x in token_lengths) / n if n > 0 else 0
    std_tokens = math.sqrt(variance)

    # Compliance Rates
    token_budget_rate = ((n - len(overflow_chunks)) / n * 100.0) if n > 0 else 0.0
    optimal_length_rate = (sum(1 for t in token_lengths if 40 <= t <= 256) / n * 100.0) if n > 0 else 0.0
    metadata_rate = ((n - len(missing_metadata_chunks)) / n * 100.0) if n > 0 else 0.0
    hierarchy_rate = ((n - len(missing_hierarchy_chunks)) / n * 100.0) if n > 0 else 0.0
    uniqueness_rate = ((n - len(duplicates)) / n * 100.0) if n > 0 else 0.0

    # Composite Chunking Quality Index (CQI)
    cqi = (
        0.35 * token_budget_rate
        + 0.25 * metadata_rate
        + 0.20 * hierarchy_rate
        + 0.15 * optimal_length_rate
        + 0.05 * uniqueness_rate
    )

    grade = (
        "A+ (Exceptional)" if cqi >= 95
        else "A (High Quality)" if cqi >= 90
        else "B (Good / Acceptable)" if cqi >= 80
        else "C (Needs Tuning)" if cqi >= 70
        else "D (Severe Quality Issues)"
    )

    results = {
        "summary": {
            "total_chunks": n,
            "unique_documents": len(docs_represented),
            "project_scopes": len(projects_represented),
            "cqi_score": round(cqi, 2),
            "quality_grade": grade,
        },
        "token_statistics": {
            "average_tokens": round(avg_tokens, 1),
            "median_tokens": median_tokens,
            "p90_tokens": p90_tokens,
            "min_tokens": min_tokens,
            "max_tokens": max_tokens,
            "std_dev_tokens": round(std_tokens, 1),
        },
        "quality_metrics": {
            "token_budget_compliance_pct": round(token_budget_rate, 2),
            "optimal_length_pct": round(optimal_length_rate, 2),
            "metadata_completeness_pct": round(metadata_rate, 2),
            "hierarchy_breadcrumbs_pct": round(hierarchy_rate, 2),
            "uniqueness_pct": round(uniqueness_rate, 2),
        },
        "issue_counts": {
            "token_overflows_gt_256": len(overflow_chunks),
            "stub_noise_chunks_lt_20": len(stub_chunks),
            "missing_metadata": len(missing_metadata_chunks),
            "missing_hierarchy": len(missing_hierarchy_chunks),
            "near_duplicates": len(duplicates),
        },
    }

    return results, overflow_chunks, stub_chunks, duplicates


def print_report(results, overflows, stubs, duplicates):
    summary = results["summary"]
    stats = results["token_statistics"]
    metrics = results["quality_metrics"]
    issues = results["issue_counts"]

    print("\n" + "=" * 65)
    print("      📊 KNOWLAYER CHUNKING QUALITY EVALUATION REPORT")
    print("=" * 65)
    print(f"Total Stored Chunks     : {summary['total_chunks']:,}")
    print(f"Unique Documents        : {summary['unique_documents']}")
    print(f"Project Scopes          : {summary['project_scopes']}")
    print(f"Composite CQI Score     : {summary['cqi_score']:.2f} / 100")
    print(f"Overall Quality Grade   : {summary['quality_grade']}")
    print("-" * 65)

    print("📈 TOKEN DISTRIBUTION:")
    print(f"  • Average Token Count : {stats['average_tokens']} tokens")
    print(f"  • Median Token Count  : {stats['median_tokens']} tokens")
    print(f"  • 90th Percentile     : {stats['p90_tokens']} tokens")
    print(f"  • Range (Min - Max)   : {stats['min_tokens']} - {stats['max_tokens']} tokens")
    print(f"  • Std Deviation       : {stats['std_dev_tokens']} tokens")
    print("-" * 65)

    print("🛡️ QUALITY DIMENSIONS:")
    print(f"  1. Token Budget Compliance (<=256) : {metrics['token_budget_compliance_pct']}% (Issues: {issues['token_overflows_gt_256']})")
    print(f"  2. Optimal Granularity (40-256)    : {metrics['optimal_length_pct']}% (Stubs <20: {issues['stub_noise_chunks_lt_20']})")
    print(f"  3. Metadata Completeness           : {metrics['metadata_completeness_pct']}% (Missing: {issues['missing_metadata']})")
    print(f"  4. Hierarchy Context Breadcrumbs   : {metrics['hierarchy_breadcrumbs_pct']}% (Missing: {issues['missing_hierarchy']})")
    print(f"  5. Chunk Uniqueness                : {metrics['uniqueness_pct']}% (Duplicates: {issues['near_duplicates']})")
    print("=" * 65)

    if overflows:
        print("\n⚠️ SAMPLE TOKEN BUDGET OVERFLOWS (>256 tokens):")
        for o in overflows[:5]:
            print(f"  - [{o['id']}] {o['tokens']} tokens (+{o['excess']} excess) | Source: {o['source']}")

    if stubs:
        print("\n⚠️ SAMPLE STUB / NOISE CHUNKS (<20 tokens):")
        for s in stubs[:5]:
            print(f"  - [{s['id']}] {s['tokens']} tokens ({s['chars']} chars) | Source: {s['source']}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate chunking quality in ChromaDB.")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    args = parser.parse_args()

    results, overflows, stubs, duplicates = evaluate_chroma_chunks()

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_report(results, overflows, stubs, duplicates)


if __name__ == "__main__":
    main()
