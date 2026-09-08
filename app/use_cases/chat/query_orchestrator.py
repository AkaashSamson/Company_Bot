from typing import List, Optional

from app.core.settings import RAG_CANDIDATE_COUNT
from app.infrastructure.llm.fallback_llm_provider import FallbackLLMProvider
from app.infrastructure.llm.groq_client import GroqClient
from app.infrastructure.llm.openrouter_client import OpenRouterClient
from app.use_cases.access.authorization_service import (
    AuthorizationError,
    AuthorizationService,
)
from app.use_cases.chat.provenance_service import ProvenanceService
from app.use_cases.chat.conversation_query_resolver import ConversationQueryResolver
from app.use_cases.chat.retrieval_service import RetrievalService
from app.domain.services.session_memory_service import SessionMemoryService

NO_ACCESS_MESSAGE = "You currently do not have access to any documents in the system."
NO_RELEVANT_MESSAGE = (
    "I could not find relevant information in the documents available to you."
)


class QueryOrchestrator:
    def __init__(
        self,
        retrieval=None,
        provenance=None,
        llm=None,
        query_resolver=None,
        memory=None,
        authorization: Optional[AuthorizationService] = None,
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
        self.authorization = authorization or AuthorizationService()

    def answer(
        self,
        question: str,
        conversation_history=None,
        employee_id: Optional[str] = None,
        role_code: Optional[str] = None,
    ):
        if not employee_id:
            return self._empty(NO_ACCESS_MESSAGE)

        try:
            accessible_ids: List[str] = self.authorization.get_accessible_document_ids(
                employee_id
            )
        except AuthorizationError:
            return self._empty(NO_ACCESS_MESSAGE)

        if not accessible_ids:
            return self._empty(NO_ACCESS_MESSAGE)

        retrieval_query = self.query_resolver.resolve(question, conversation_history)
        selected_evidence = self.retrieval.retrieve(
            retrieval_query,
            top_k=RAG_CANDIDATE_COUNT,
            document_ids=accessible_ids,
        )

        if not selected_evidence:
            return self._empty(NO_RELEVANT_MESSAGE)

        # Defense in depth: never let an unauthorized chunk into the LLM context.
        allowed_ids = set(accessible_ids)
        selected_evidence = [
            evidence
            for evidence in selected_evidence
            if evidence.get("metadata", {}).get("document_id") in allowed_ids
        ]
        if not selected_evidence:
            return self._empty(NO_RELEVANT_MESSAGE)

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

        return {
            "answer": answer,
            "citations": self.provenance.build_citations(selected_evidence),
            "context": context,
        }

    @staticmethod
    def _empty(message: str) -> dict:
        return {
            "answer": message,
            "citations": [],
            "context": "",
        }