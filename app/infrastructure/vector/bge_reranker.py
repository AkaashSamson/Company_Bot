import logging
import re
from typing import Optional

# pyrefly: ignore[missing-import]
from sentence_transformers import CrossEncoder

from app.domain.ports.reranker import RerankerPort

logger = logging.getLogger(__name__)

CUTOFF_TAG_REGEX = re.compile(r"<!--\s*CUTOFF(?:_START|_END)?\s*-->", re.IGNORECASE)
TABLE_SEP_REGEX = re.compile(r"^\s*\|?(?:\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?\s*$", re.MULTILINE)


def clean_text_for_reranker(text: str) -> str:
    """Strip structural noise, stitch tags, and table separator bars before cross-encoder scoring.

    Cross-encoders expend attention heads and token budget on HTML comments and table separator pipes.
    Stripping them for scoring keeps the semantic content clean and avoids relevance logit penalty,
    while leaving the original formatted text intact on the candidate for prompt generation.
    """
    if not text:
        return ""
    # 1. Strip <!-- CUTOFF_START --> and <!-- CUTOFF_END --> tags
    cleaned = CUTOFF_TAG_REGEX.sub("", text)
    # 2. Collapse table separator rows (| :--- | :--- |) to single spaces
    cleaned = TABLE_SEP_REGEX.sub(" ", cleaned)
    # 3. Collapse redundant whitespace and empty lines
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n", cleaned)
    return cleaned.strip()


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
            # Strip structural noise and tags only for scoring pairs fed to CrossEncoder.predict
            clean_texts = [clean_text_for_reranker(c.get("text", "") or "") for c in candidates]
            pairs = [[query, text] for text in clean_texts]
            
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
