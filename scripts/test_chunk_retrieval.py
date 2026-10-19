"""
Chunk Retrieval & Needle-in-a-Haystack Tester
=============================================
Quick CLI utility to test whether the 2-stage RAG retrieval pipeline (ChromaDB + BGE Reranker)
fetches the correct chunk based on a query, asserting accuracy directly by Chunk ID.

Usage Examples:
  # 1. Test a specific query against an expected Chunk ID
  python scripts/test_chunk_retrieval.py --query "What is the probation period?" --expected "NEXORA TECHNOLOGIES PVT-12"

  # 2. Test using a benchmark question ID from rag_benchmark_questions.json
  python scripts/test_chunk_retrieval.py --bench-id RAG-VAL-02

  # 3. Run chunk accuracy evaluation across all benchmark questions
  python scripts/test_chunk_retrieval.py --all-benchmarks

  # 4. Interactive mode (prompts for query and chunk ID)
  python scripts/test_chunk_retrieval.py
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# Add project root to sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.infrastructure.vector.chroma_client import ChromaVectorStore
from app.infrastructure.vector.reranker_factory import get_reranker


BENCHMARK_PATH = _REPO_ROOT / "test_data" / "rag_benchmark_questions.json"


def load_benchmark_cases():
    if not BENCHMARK_PATH.exists():
        return []
    with open(BENCHMARK_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_single_retrieval(
    query: str,
    expected_chunk_ids: list[str],
    cand_k: int = 13,
    final_k: int = 4,
    verbose: bool = True,
):
    """
    Executes 2-stage retrieval for a single query and evaluates whether expected chunk IDs are fetched.
    Returns a dict with ranks, hits, and verdict.
    """
    store = ChromaVectorStore()
    reranker = get_reranker()

    t0 = time.time()
    candidates = store.query(query_text=query, top_k=cand_k)
    s1_time = (time.time() - t0) * 1000

    t1 = time.time()
    reranked = reranker.rerank(query=query, candidates=candidates, top_k=final_k)
    s2_time = (time.time() - t1) * 1000

    # Evaluate each expected chunk ID
    evaluations = {}
    for cid in expected_chunk_ids:
        cid_clean = cid.strip()
        s1_rank = next((i for i, c in enumerate(candidates, 1) if c.get("id") == cid_clean), None)
        s2_rank = next((i for i, r in enumerate(reranked, 1) if r.get("id") == cid_clean), None)

        s1_dist = candidates[s1_rank - 1].get("distance") if s1_rank else None
        s2_score = reranked[s2_rank - 1].get("_rerank_score") if s2_rank else None

        if s2_rank == 1:
            verdict = "BULLSEYE_RANK_1"
        elif s2_rank is not None:
            verdict = f"HIT_TOP_{final_k}"
        elif s1_rank is not None:
            verdict = "DEMOTED_BY_RERANKER"
        else:
            verdict = "BI_ENCODER_MISS"

        evaluations[cid_clean] = {
            "s1_rank": s1_rank,
            "s1_distance": s1_dist,
            "s2_rank": s2_rank,
            "s2_score": s2_score,
            "verdict": verdict,
        }

    overall_pass = any(
        e["verdict"] in ("BULLSEYE_RANK_1", f"HIT_TOP_{final_k}")
        for e in evaluations.values()
    ) if expected_chunk_ids else True

    if verbose:
        print("\n" + "=" * 80)
        print(f"🎯 QUERY: \"{query}\"")
        if expected_chunk_ids:
            print(f"📌 EXPECTED TARGET CHUNK ID(S): {', '.join(expected_chunk_ids)}")
        print("=" * 80)

        # Stage 1 Candidates Table
        print(f"\n[Stage 1: ChromaDB Bi-Encoder Candidates ({s1_time:.1f}ms, Top-{cand_k})]")
        print("-" * 80)
        print(f"{'Rank':<5} | {'Target':<8} | {'Chunk ID':<30} | {'Dist':<7} | {'Snippet Preview'}")
        print("-" * 80)
        for i, c in enumerate(candidates, 1):
            cid = c.get("id", "N/A")
            is_target = "🎯 YES" if cid in expected_chunk_ids else "  -"
            dist_str = f"{c.get('distance', 0):.4f}" if c.get('distance') is not None else "N/A"
            text_snip = (c.get("text") or "").replace("\n", " ")[:40]
            print(f"{i:<5} | {is_target:<8} | {cid:<30} | {dist_str:<7} | {text_snip}...")

        # Stage 2 Reranked Table
        print(f"\n[Stage 2: BGE Cross-Encoder Reranked Output ({s2_time:.1f}ms, Top-{final_k})]")
        print("-" * 80)
        print(f"{'Rank':<5} | {'Target':<8} | {'Chunk ID':<30} | {'Score':<7} | {'Snippet Preview'}")
        print("-" * 80)
        for i, r in enumerate(reranked, 1):
            cid = r.get("id", "N/A")
            is_target = "🎯 YES" if cid in expected_chunk_ids else "  -"
            score_str = f"{r.get('_rerank_score', 0):.4f}"
            text_snip = (r.get("text") or "").replace("\n", " ")[:40]
            print(f"{i:<5} | {is_target:<8} | {cid:<30} | {score_str:<7} | {text_snip}...")

        # Needle Verification Summary
        if expected_chunk_ids:
            print("\n" + "-" * 80)
            print("📋 NEEDLE VERIFICATION VERDICT:")
            for cid, ev in evaluations.items():
                s1_info = f"Rank #{ev['s1_rank']}" if ev['s1_rank'] else "MISS"
                s2_info = f"Rank #{ev['s2_rank']}" if ev['s2_rank'] else "DROPPED"
                
                if ev['verdict'] == "BULLSEYE_RANK_1":
                    tag = "✅ [PASS - 🎯 BULLSEYE RANK #1]"
                elif "HIT_TOP" in ev['verdict']:
                    tag = f"✅ [PASS - RETRIEVED AT RANK #{ev['s2_rank']}]"
                elif ev['verdict'] == "DEMOTED_BY_RERANKER":
                    tag = f"⚠️ [FAIL - CANDIDATE FOUND AT #{ev['s1_rank']} BUT EXCLUDED BY RERANKER]"
                else:
                    tag = "❌ [FAIL - NOT FOUND IN BI-ENCODER CANDIDATES]"

                print(f"  • Chunk ID '{cid}': {tag}")
                print(f"    └─ Stage 1 (Chroma Bi-Encoder): {s1_info} | Stage 2 (BGE Cross-Encoder): {s2_info}")
            print("-" * 80)

            # Top Retrieved vs Expected Content Comparison
            top_retrieved = reranked[0] if reranked else None
            top_id = top_retrieved.get("id") if top_retrieved else "NONE"
            matched_expected = top_id in expected_chunk_ids

            if matched_expected:
                print(f"\n🎉 SUCCESS: The Top-1 fetched chunk ID '{top_id}' matches your expected target!")
            else:
                print(f"\n⚠️ NOTE: Top-1 fetched chunk is '{top_id}'.")
                # Look up text of expected chunk if available in candidates
                target_cand = next((c for c in candidates if c.get("id") in expected_chunk_ids), None)
                if target_cand:
                    print(f"   Expected chunk was present in candidates (Rank #{evaluations[target_cand.get('id')]['s1_rank']}):")
                    print(f"   \"{target_cand.get('text', '')[:120]}...\"")

    return {
        "query": query,
        "expected_chunk_ids": expected_chunk_ids,
        "evaluations": evaluations,
        "overall_pass": overall_pass,
        "top_retrieved_id": reranked[0].get("id") if reranked else None,
        "candidates": candidates,
        "reranked": reranked,
    }


def run_benchmark_validation(cand_k: int = 13, final_k: int = 4):
    cases = load_benchmark_cases()
    if not cases:
        print(f"No benchmark questions found at {BENCHMARK_PATH}")
        return

    cases_with_chunks = [c for c in cases if c.get("required_chunk_ids")]
    print(f"\nEvaluating Chunk Retrieval for {len(cases_with_chunks)} benchmark questions with required_chunk_ids...")
    print("=" * 90)
    print(f"{'ID':<12} | {'Status':<10} | {'Expected Chunk ID':<25} | {'Fetched Top Chunk ID':<25} | {'S2 Rank'}")
    print("=" * 90)

    passed = 0
    total = len(cases_with_chunks)

    for c in cases_with_chunks:
        qid = c["id"]
        q = c["question"]
        req_ids = c["required_chunk_ids"]
        res = test_single_retrieval(
            query=q,
            expected_chunk_ids=req_ids,
            cand_k=cand_k,
            final_k=final_k,
            verbose=False,
        )

        top_id = res["top_retrieved_id"] or "NONE"
        is_hit = res["overall_pass"]
        status_str = "PASS" if is_hit else "FAIL"
        if is_hit:
            passed += 1

        primary_id = req_ids[0]
        ev = res["evaluations"].get(primary_id, {})
        s2_rank = f"#{ev.get('s2_rank')}" if ev.get('s2_rank') else "MISS"

        print(f"{qid:<12} | {status_str:<10} | {primary_id:<25} | {top_id:<25} | {s2_rank}")

    pct = (passed / total) * 100 if total > 0 else 0
    print("=" * 90)
    print(f"TOTAL CHUNK RETRIEVAL ACCURACY: {passed}/{total} Passed ({pct:.1f}% Recall@{final_k})\n")


def main():
    parser = argparse.ArgumentParser(description="Test RAG chunk retrieval accuracy based on Chunk ID.")
    parser.add_argument("-q", "--query", type=str, help="The user query to test.")
    parser.add_argument("-e", "--expected", type=str, help="Comma-separated expected Chunk IDs (e.g. 'NEXORA TECHNOLOGIES PVT-12').")
    parser.add_argument("-b", "--bench-id", type=str, help="Benchmark question ID to run (e.g. 'RAG-VAL-02').")
    parser.add_argument("--all-benchmarks", action="store_true", help="Run chunk accuracy on all benchmark test cases.")
    parser.add_argument("--cand-k", type=int, default=13, help="Stage 1 Bi-Encoder candidate count (default: 13).")
    parser.add_argument("--final-k", type=int, default=4, help="Stage 2 Cross-Encoder output count (default: 4).")

    args = parser.parse_args()

    if args.all_benchmarks:
        run_benchmark_validation(cand_k=args.cand_k, final_k=args.final_k)
        return

    if args.bench_id:
        cases = load_benchmark_cases()
        matched = next((c for c in cases if c.get("id") == args.bench_id), None)
        if not matched:
            print(f"Error: Benchmark question '{args.bench_id}' not found.")
            return
        query = matched["question"]
        expected = matched.get("required_chunk_ids", [])
        test_single_retrieval(query, expected, cand_k=args.cand_k, final_k=args.final_k, verbose=True)
        return

    if args.query:
        expected = [e.strip() for e in args.expected.split(",") if e.strip()] if args.expected else []
        test_single_retrieval(args.query, expected, cand_k=args.cand_k, final_k=args.final_k, verbose=True)
        return

    # Interactive Demo Mode if no args
    print("\n" + "=" * 70)
    print("🧪 KnowLayer Chunk ID Retrieval Tester (Interactive)")
    print("=" * 70)
    print("No arguments provided. Running default verification query:")
    sample_query = "What is the standard probation period duration for new employees?"
    sample_expected = ["NEXORA TECHNOLOGIES PVT-12"]
    test_single_retrieval(sample_query, sample_expected, cand_k=args.cand_k, final_k=args.final_k, verbose=True)
    print("\nTip: Pass your own query and expected chunk ID:")
    print("  python scripts/test_chunk_retrieval.py -q \"How many annual leaves?\" -e \"NEXORA TECHNOLOGIES PVT-57\"")


if __name__ == "__main__":
    main()
