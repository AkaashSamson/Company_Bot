import re
from typing import Dict, List

from app.core.prompt_config import load_prompt
from app.domain.services.session_memory_service import SessionMemoryService


class ConversationQueryResolver:
    """Resolve dependent follow-ups into standalone retrieval queries."""

    _DEPENDENCY_PATTERN = re.compile(
        r"\b(it|this|that|these|those|they|them|their|its|such)\b|"
        r"^\s*(and|also|what about|how about)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        llm,
        memory: SessionMemoryService | None = None,
        system_prompt: str | None = None,
    ):
        self.llm = llm
        self.memory = memory or SessionMemoryService()
        self.system_prompt = system_prompt or load_prompt("conversation_query_rewrite")

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
                "content": self.system_prompt,
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