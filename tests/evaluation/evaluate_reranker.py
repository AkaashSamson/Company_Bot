import json
import os
import sys

# Ensure the root directory is in the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app.infrastructure.vector.chroma_client import ChromaVectorStore
from app.infrastructure.vector.bge_reranker import BgeReranker
from tests.evaluation.metrics import recall_at_k, mrr

def evaluate():
    store = ChromaVectorStore(collection_name="hr_policy_docs")
    reranker = BgeReranker()
    
    dataset_path = os.path.join(os.path.dirname(__file__), "dataset.json")
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
        
    retrieval_top_k = 15
    k_values = [1, 2, 3, 4, 5]
    
    results = []
    
    for item in dataset:
        query = item["query"]
        relevant_ids = item["relevant_chunks"]
        
        # 1. Retrieve candidates from vector store
        raw_candidates = store.query(query, top_k=retrieval_top_k)
        raw_ids = [c["id"] for c in raw_candidates]
        
        # 2. Rerank the candidate pool
        reranked_candidates = reranker.rerank(query, raw_candidates, top_k=retrieval_top_k)
        reranked_ids = [c["id"] for c in reranked_candidates]
        
        query_result = {
            "query": query,
            "relevant_ids": relevant_ids,
            "before_ids": raw_ids,
            "after_ids": reranked_ids,
            "before_candidates": raw_candidates,
            "after_candidates": reranked_candidates,
            "metrics": {
                "before": {},
                "after": {}
            }
        }
        
        # Calculate metrics for K=1..5
        for k in k_values:
            query_result["metrics"]["before"][f"recall@{k}"] = recall_at_k(raw_ids, relevant_ids, k)
            query_result["metrics"]["after"][f"recall@{k}"] = recall_at_k(reranked_ids, relevant_ids, k)
            
        query_result["metrics"]["before"]["mrr"] = mrr(raw_ids, relevant_ids)
        query_result["metrics"]["after"]["mrr"] = mrr(reranked_ids, relevant_ids)
        
        results.append(query_result)
        
    # Aggregate Metrics
    agg = {
        "before": {f"recall@{k}": 0.0 for k in k_values},
        "after": {f"recall@{k}": 0.0 for k in k_values}
    }
    agg["before"]["mrr"] = 0.0
    agg["after"]["mrr"] = 0.0
    
    valid_queries = [r for r in results if r["relevant_ids"]]
    num_queries = len(valid_queries)
    
    if num_queries > 0:
        for r in valid_queries:
            for k in k_values:
                agg["before"][f"recall@{k}"] += r["metrics"]["before"][f"recall@{k}"]
                agg["after"][f"recall@{k}"] += r["metrics"]["after"][f"recall@{k}"]
            agg["before"]["mrr"] += r["metrics"]["before"]["mrr"]
            agg["after"]["mrr"] += r["metrics"]["after"]["mrr"]
            
        for k in k_values:
            agg["before"][f"recall@{k}"] /= num_queries
            agg["after"][f"recall@{k}"] /= num_queries
        agg["before"]["mrr"] /= num_queries
        agg["after"]["mrr"] /= num_queries

    # Output Terminal Report
    print("========================================================")
    print("RERANKER EVALUATION")
    print("========================================================")
    print(f"\nQueries evaluated: {num_queries}")
    print(f"Retriever candidate pool: {retrieval_top_k}")
    print("Reranker: BAAI/bge-reranker-base\n")
    
    print(f"{'':<20} {'WITHOUT BGE':<15} {'WITH BGE':<15}")
    print("-" * 50)
    for k in k_values:
        print(f"Recall@{k:<12} {agg['before'][f'recall@{k}']:.2f}{'':<11} {agg['after'][f'recall@{k}']:.2f}")
    print()
    print(f"MRR{'':<17} {agg['before']['mrr']:.2f}{'':<11} {agg['after']['mrr']:.2f}")
    print("\n========================================================")
    
    # Detailed examples (show 4 to cover improvements and potential regressions)
    for i, r in enumerate(valid_queries[:4]):
        print(f"\nQuery: {r['query']}")
        
        print("\nBEFORE RERANKING")
        for rank, c in enumerate(r['before_candidates'][:5], 1):
            is_rel = "relevant" if c["id"] in r["relevant_ids"] else "irrelevant"
            print(f"{rank}. {c['id']:<30} {is_rel}")
            
        print("\nAFTER RERANKING")
        for rank, c in enumerate(r['after_candidates'][:5], 1):
            is_rel = "relevant" if c["id"] in r["relevant_ids"] else "irrelevant"
            score = c.get("_rerank_score", 0.0)
            orig_rank = c.get("_original_rank", -1)
            print(f"{rank}. {c['id']:<30} {is_rel:<15} score={score:.4f} (was #{orig_rank})")
            
        print(f"\nRecall@4:")
        print(f"Before = {r['metrics']['before']['recall@4']:.2f}")
        print(f"After  = {r['metrics']['after']['recall@4']:.2f}")
        
        print(f"\nMRR:")
        print(f"Before = {r['metrics']['before']['mrr']:.2f}")
        print(f"After  = {r['metrics']['after']['mrr']:.2f}")
        
        print("-" * 50)

if __name__ == "__main__":
    evaluate()
