def recall_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
    """Calculate Recall@K: fraction of relevant chunks retrieved within top K."""
    if not relevant_ids:
        return 0.0
    top_k = retrieved_ids[:k]
    hits = sum(1 for rid in relevant_ids if rid in top_k)
    return hits / len(relevant_ids)

def mrr(retrieved_ids: list[str], relevant_ids: list[str]) -> float:
    """Calculate Mean Reciprocal Rank (MRR)."""
    if not relevant_ids:
        return 0.0
    for i, rid in enumerate(retrieved_ids):
        if rid in relevant_ids:
            return 1.0 / (i + 1)
    return 0.0
