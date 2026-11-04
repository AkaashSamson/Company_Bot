from typing import Any
from app.domain.ports.reranker import RerankerPort

class NullReranker(RerankerPort):
    """
    A pass-through reranker that does not modify scores or order.
    Useful for testing or when reranking needs to be dynamically disabled in production.
    """
    def rerank(self, query: str, candidates: list[dict[str, Any]], top_k: int = 4) -> list[dict[str, Any]]:
        # Take the top_k from the original candidates
        selected = candidates[:top_k]
        
        # Inject standard metadata for consistency with other rerankers
        for index, candidate in enumerate(selected):
            candidate["_new_rank"] = index + 1
            if "_original_rank" not in candidate:
                candidate["_original_rank"] = index + 1
                
        return selected
