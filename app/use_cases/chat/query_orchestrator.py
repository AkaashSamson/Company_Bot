import json

from app.core.settings import FAQ_CACHE_FILE, RAG_CANDIDATE_COUNT, RESPONSE_CACHE_FILE
from app.infrastructure.llm.fallback_llm_provider import FallbackLLMProvider
from app.infrastructure.llm.groq_client import GroqClient
from app.infrastructure.llm.openrouter_client import OpenRouterClient
from app.use_cases.chat.provenance_service import ProvenanceService
from app.use_cases.chat.conversation_query_resolver import ConversationQueryResolver
from app.use_cases.chat.retrieval_service import RetrievalService
from app.domain.services.session_memory_service import SessionMemoryService
from app.infrastructure.faq.mongo_faq_store import MongoFAQStore
from app.infrastructure.faq.json_faq_cache import JsonFAQCache
from app.infrastructure.llm.prompt_cache import PromptLRUCache
from app.infrastructure.llm.json_semantic_cache import JsonSemanticResponseCache


class QueryOrchestrator:
    def __init__(
        self,
        retrieval=None,
        provenance=None,
        llm=None,
        query_resolver=None,
        memory=None,
        faq_store=None,
        response_cache=None,
        faq_cache=None,
    ):
        self.retrieval = retrieval or RetrievalService()
        self.provenance = provenance or ProvenanceService()
        self.faq_store = faq_store or MongoFAQStore()
        self.response_cache = response_cache or JsonSemanticResponseCache(RESPONSE_CACHE_FILE)
        self.faq_cache = faq_cache or JsonFAQCache(FAQ_CACHE_FILE)

        self.llm = llm or FallbackLLMProvider(
            primary=OpenRouterClient(),
            fallback=GroqClient(),
        )
        self.query_resolver = query_resolver or ConversationQueryResolver(
            self.llm,
            memory=memory or SessionMemoryService(),
        )

    def answer(self, question: str, conversation_history=None):
        cache_messages = [{"role": "user", "content": question}]
        cached_result = self.response_cache.get(cache_messages)
        if cached_result is not None:
            return json.loads(cached_result)

        retrieval_query = self.query_resolver.resolve(question, conversation_history)
        selected_evidence = self.retrieval.retrieve(
            retrieval_query,
            top_k=RAG_CANDIDATE_COUNT,
        )

        if not selected_evidence:
            result = {
                "answer": (
                    "I could not find the requested information in the "
                    "available documents."
                ),
                "citations": [],
            }
            self.response_cache.put(cache_messages, json.dumps(result, sort_keys=True))
            return result

        context = "\n\n".join(
            result.get("text", "")
            for result in selected_evidence
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an HR assistant answering employee questions using ONLY the provided document context below. "
                    "The context is from the official company employee handbook. "
                    "IMPORTANT: The user may use everyday terms (e.g. 'payment', 'pay', 'perks') that correspond to "
                    "formal document sections (e.g. 'Compensation and Payroll', 'Employee Benefits'). "
                    "Always treat the provided context as covering the user's question if it is relevant. "
                    "Do NOT say the information is unavailable if the context contains relevant content. "
                    "Give a clear, direct answer in 2-4 sentences based on the context. "
                    "For multi-part questions, address each part that is supported by the context. "
                    "Only say information is unavailable if the context is genuinely unrelated to the question."
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
        self.faq_store.save(question, answer, citations)

        result = {
            "answer": answer,
            "citations": citations,
            "context": context,
        }
        self.response_cache.put(cache_messages, json.dumps(result, sort_keys=True))
        return result

    def generate_faqs(self):
        cached_faqs = self.faq_cache.load()
        if cached_faqs is not None:
            return cached_faqs

        selected_evidence = self.retrieval.retrieve(
            "what are the main questions in the FAQs and handbook policies",
            top_k=RAG_CANDIDATE_COUNT,
            max_evidence=12,
        )
        if not selected_evidence:
            result = {"faqs": "No FAQs could be found in the available documents.", "citations": []}
            self.faq_cache.save(result)
            return result

        context = "\n\n".join(result.get("text", "") for result in selected_evidence)
        messages = [
            {
                "role": "system",
                "content": (
                    "Create exactly 20 distinct FAQ questions using only the provided employee "
                    "handbook context. Cover different policy areas and write one question per "
                    "numbered line. Do not provide answers or invent topics. Return only the "
                    "numbered questions."
                ),
            },
            {
                "role": "user",
                "content": f"Employee handbook context:\n\n{context}",
            },
        ]
        faqs = self.llm.generate(messages)
        result = {
            "faqs": faqs,
            "citations": self.provenance.build_citations(selected_evidence),
        }
        self.faq_cache.save(result)
        return result