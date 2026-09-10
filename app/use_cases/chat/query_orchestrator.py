from app.core.settings import RAG_CANDIDATE_COUNT
from app.infrastructure.llm.fallback_llm_provider import FallbackLLMProvider
from app.infrastructure.llm.groq_client import GroqClient
from app.infrastructure.llm.openrouter_client import OpenRouterClient
from app.use_cases.chat.provenance_service import ProvenanceService
from app.use_cases.chat.conversation_query_resolver import ConversationQueryResolver
from app.use_cases.chat.retrieval_service import RetrievalService
from app.domain.services.session_memory_service import SessionMemoryService


class QueryOrchestrator:
    def __init__(
        self,
        retrieval=None,
        provenance=None,
        llm=None,
        query_resolver=None,
        memory=None,
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

    def answer(self, question: str, conversation_history=None, authorized_project_ids=None):
        retrieval_query = self.query_resolver.resolve(question, conversation_history)
        retrieval_kwargs = {"top_k": RAG_CANDIDATE_COUNT}
        if authorized_project_ids is not None:
            retrieval_kwargs["authorized_project_ids"] = authorized_project_ids
        selected_evidence = self.retrieval.retrieve(retrieval_query, **retrieval_kwargs)

        if not selected_evidence:
            return {
                "answer": (
                    "I could not find the requested information in the "
                    "available documents."
                ),
                "citations": [],
            }

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