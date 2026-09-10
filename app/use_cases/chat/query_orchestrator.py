import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.settings import RAG_CANDIDATE_COUNT
from app.domain.services.session_memory_service import SessionMemoryService
from app.infrastructure.llm.fallback_llm_provider import FallbackLLMProvider
from app.infrastructure.llm.groq_client import GroqClient
from app.infrastructure.llm.openrouter_client import OpenRouterClient
from app.infrastructure.logging.conversation_logger import ConversationLogger
from app.infrastructure.logging.mock_employee_id_provider import MockEmployeeIdProvider
from app.use_cases.chat.conversation_query_resolver import ConversationQueryResolver
from app.use_cases.chat.provenance_service import ProvenanceService
from app.use_cases.chat.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)


class QueryOrchestrator:
    def __init__(
        self,
        retrieval=None,
        provenance=None,
        llm=None,
        query_resolver=None,
        memory=None,
        conversation_logger=None,
        employee_id_provider=None,
    ):
        self.retrieval = retrieval or RetrievalService()
        self.provenance = provenance or ProvenanceService()

        self.llm = llm or FallbackLLMProvider(
            primary=OpenRouterClient(),
            fallback=GroqClient(),
        )
        self.query_resolver = query_resolver or ConversationQueryResolver(
            self.llm,
            memory=memory or SessionMemoryService(),
        )
        self.conversation_logger = conversation_logger or ConversationLogger(
            employee_id_provider=employee_id_provider or MockEmployeeIdProvider(),
        )

    def _safe_log_conversation(
        self,
        session_id: str,
        question: str,
        answer: str,
        conversation_history=None,
        user_context: Optional[Any] = None,
    ) -> None:
        if not self.conversation_logger:
            return

        try:
            full_messages = []
            if conversation_history:
                for msg in conversation_history:
                    if isinstance(msg, dict):
                        full_messages.append(
                            {
                                "role": msg.get("role", "user"),
                                "content": msg.get("content", ""),
                                "timestamp": msg.get(
                                    "timestamp",
                                    datetime.now(timezone.utc).isoformat(),
                                ),
                            }
                        )
                    elif hasattr(msg, "role") and hasattr(msg, "content"):
                        full_messages.append(
                            {
                                "role": getattr(msg, "role"),
                                "content": getattr(msg, "content"),
                                "timestamp": getattr(
                                    msg,
                                    "timestamp",
                                    datetime.now(timezone.utc).isoformat(),
                                ),
                            }
                        )

            now_iso = datetime.now(timezone.utc).isoformat()
            trailing_is_current_question = (
                full_messages
                and full_messages[-1].get("role") == "user"
                and full_messages[-1].get("content", "").strip() == question.strip()
            )
            if not trailing_is_current_question:
                full_messages.append(
                    {"role": "user", "content": question, "timestamp": now_iso}
                )

            full_messages.append(
                {"role": "assistant", "content": answer, "timestamp": now_iso}
            )

            self.conversation_logger.log_conversation(
                session_id=session_id,
                messages=full_messages,
                user_context=user_context,
            )
        except Exception as exc:
            logger.error(
                "Unexpected failure during conversation logging for session %s: %s",
                session_id,
                exc,
            )

    def answer(
        self,
        question: str,
        conversation_history=None,
        session_id: str = "default-session",
        user_context: Optional[Any] = None,
    ):
        retrieval_query = self.query_resolver.resolve(question, conversation_history)
        selected_evidence = self.retrieval.retrieve(
            retrieval_query,
            top_k=RAG_CANDIDATE_COUNT,
        )

        if not selected_evidence:
            response = {
                "answer": (
                    "I could not find the requested information in the "
                    "available documents."
                ),
                "citations": [],
            }
            self._safe_log_conversation(
                session_id=session_id,
                question=question,
                answer=response["answer"],
                conversation_history=conversation_history,
                user_context=user_context,
            )
            return response

        context = "\n\n".join(
            result.get("text", "")
            for result in selected_evidence
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You answer questions using only the provided document context. "
                    "Do not invent or assume information. "
                    "For multi-part questions, answer each supported part "
                    "and explicitly state which part is not present in the documents. "
                    "If no part is supported, say the requested information "
                    "could not be found in the available documents. "
                    "Keep the answer concise and directly answer "
                    "the user's question."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Document context:\n\n"
                    f"{context}\n\n"
                    f"Question: {question}"
                ),
            },
        ]

        answer = self.llm.generate(messages)
        citations = self.provenance.build_citations(selected_evidence)

        response = {
            "answer": answer,
            "citations": citations,
            "context": context,
        }

        self._safe_log_conversation(
            session_id=session_id,
            question=question,
            answer=answer,
            conversation_history=conversation_history,
            user_context=user_context,
        )

        return response