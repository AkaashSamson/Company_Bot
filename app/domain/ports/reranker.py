from typing import Protocol, Sequence

class RerankerPort(Protocol):
    def rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        """
        Rerank a list of candidates given a query.
        Must preserve all original metadata and return the top_k candidates.
        """
        ...
