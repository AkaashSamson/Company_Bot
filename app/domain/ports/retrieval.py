from typing import Protocol, Sequence


class RetrievalPort(Protocol):
    def query(
        self,
        query_text: str,
        top_k: int = 3,
        project_ids: Sequence[str] | None = None,
    ) -> list[dict]: ...
