import logging
from typing import Optional

from sentence_transformers import CrossEncoder

from app.domain.ports.reranker import RerankerPort

logger = logging.getLogger(__name__)

class BgeReranker(RerankerPort):
    def __init__(self, model_name: str = "BAAI/bge-reranker-base"):
        self.model_name = model_name
        self._model: Optional[CrossEncoder] = None

    @property
    def model(self) -> CrossEncoder:
        if self._model is None:
            logger.info("Loading cross-encoder model: %s", self.model_name)
            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        if not candidates:
            return []
            
        try:
            texts = [c.get("text", "") for c in candidates]
            pairs = [[query, text] for text in texts]
            
            scores = self.model.predict(pairs)
            
            scored_candidates = []
            for i, (candidate, score) in enumerate(zip(candidates, scores)):
                c = candidate.copy()
                c["_rerank_score"] = float(score)
                c["_original_rank"] = i + 1
                scored_candidates.append(c)
                
            scored_candidates.sort(key=lambda x: x["_rerank_score"], reverse=True)
            
            for i, c in enumerate(scored_candidates):
                c["_new_rank"] = i + 1
                
            return scored_candidates[:top_k]
            
        except Exception as e:
            logger.error("Reranking failed with error: %s. Falling back to original order.", e)
            return candidates[:top_k]
