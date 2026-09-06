import re
from typing import Dict, List

from app.domain.services.session_memory_service import SessionMemoryService


class ConversationQueryResolver:
    """Resolve dependent follow-ups into standalone retrieval queries."""

    _DEPENDENCY_PATTERN = re.compile(
        r"\b(it|this|that|these|those|they|them|their|its|such)\b|"
        r"^\s*(and|also|what about|how about)\b",
        re.IGNORECASE,
    )

    def __init__(self, llm, memory: SessionMemoryService | None = None):
        self.llm = llm
        self.memory = memory or SessionMemoryService()

    def resolve(self, question: str, history: List[Dict[str, str]] | None = None) -> str:
        recent_history = self.memory.get_recent_messages(history or [])
        if not recent_history or not self._is_dependent(question):
            return question

        history_text = "\n".join(
            f"{message['role']}: {message['content']}"
            for message in recent_history
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "Rewrite a dependent follow-up as one standalone search query. "
                    "Use only context in the conversation. Do not answer, add facts, "
                    "or change an independent question. Return only the query."
                ),
            },
            {
                "role": "user",
                "content": f"Conversation:\n{history_text}\nCurrent question: {question}",
            },
        ]
        try:
            rewritten = self.llm.generate(messages).strip()
        except Exception:
            return question
        return rewritten or question

    @classmethod
    def _is_dependent(cls, question: str) -> bool:
        return bool(cls._DEPENDENCY_PATTERN.search(question))