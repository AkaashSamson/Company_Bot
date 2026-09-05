from app.infrastructure.llm.fallback_llm_provider import FallbackLLMProvider
from app.infrastructure.llm.groq_client import GroqClient
from app.infrastructure.llm.openrouter_client import OpenRouterClient
from app.use_cases.chat.provenance_service import ProvenanceService
from app.use_cases.chat.retrieval_service import RetrievalService


class QueryOrchestrator:
    def __init__(
        self,
        retrieval=None,
        provenance=None,
        llm=None,
    ):
        self.retrieval = retrieval or RetrievalService()
        self.provenance = provenance or ProvenanceService()

        self.llm = llm or FallbackLLMProvider(
            primary=OpenRouterClient(),
            fallback=GroqClient(),
        )

    def answer(self, question: str):
        results = self.retrieval.retrieve(
            question,
            top_k=3,
        )

        if not results:
            return {
                "answer": (
                    "I could not find a relevant match in the "
                    "current HR policy document."
                ),
                "citations": [],
            }

        context = "\n\n".join(
            result.get("text", "")
            for result in results
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an HR policy assistant. "
                    "Answer the user's question using only the "
                    "provided handbook context. "
                    "Do not invent or assume information. "
                    "If the answer is not present in the context, "
                    "say that the information could not be found "
                    "in the handbook. "
                    "Keep the answer concise and directly answer "
                    "the user's question."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Handbook context:\n\n"
                    f"{context}\n\n"
                    f"Question: {question}"
                ),
            },
        ]

        answer = self.llm.generate(messages)

        return {
            "answer": answer,
            "citations": self.provenance.build_citations(results),
            "context": context,
        }