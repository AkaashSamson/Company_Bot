import logging
import re

from app.core.settings import RAG_CANDIDATE_COUNT
from app.infrastructure.faq.faq_similarity_cache import FAQSimilarityCache
from app.infrastructure.faq.mongo_faq_store import MongoFAQStore
from app.infrastructure.llm.fallback_llm_provider import FallbackLLMProvider
from app.infrastructure.llm.groq_client import GroqClient
from app.infrastructure.llm.openrouter_client import OpenRouterClient
from app.infrastructure.observability.tracer import traceable
from app.use_cases.chat.conversation_query_resolver import ConversationQueryResolver
from app.use_cases.chat.provenance_service import ProvenanceService
from app.use_cases.chat.retrieval_service import RetrievalService
from app.use_cases.chat.rag_context_builder import RAGContextBuilder
from app.domain.services.session_memory_service import SessionMemoryService
from app.infrastructure.observability.langsmith_integration import add_tokens_to_current_run

logger = logging.getLogger(__name__)

# Words/phrases that count as a positive response to "Would you like references?"
_POSITIVE_REPLY = re.compile(
    r"\b(yes|yeah|yep|yup|sure|please|show|go ahead|ok|okay|of course|"
    r"absolutely|definitely|affirmative|why not|do it|send|display|give)\b",
    re.IGNORECASE,
)

# Keeps the last pending citations per session_id so they can be returned
# when the user asks for references.
_pending_citations: dict[str, list] = {}


def _is_positive(text: str) -> bool:
    return bool(_POSITIVE_REPLY.search(text))


def _last_assistant_offered_references(history: list[dict]) -> bool:
    """Return True if the most recent assistant message asked about references."""
    for msg in reversed(history or []):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            return "reference" in content.lower() or "source" in content.lower()
    return False


class QueryOrchestrator:
    def __init__(
        self,
        retrieval=None,
        provenance=None,
        llm=None,
        query_resolver=None,
        memory=None,
        faq_store=None,
        faq_cache=None,
        context_builder=None,
    ):
        self.retrieval = retrieval or RetrievalService()
        self.provenance = provenance or ProvenanceService()
        self.faq_store = faq_store or MongoFAQStore()
        self.faq_cache = faq_cache or FAQSimilarityCache()
        self.context_builder = context_builder or RAGContextBuilder()

        self.llm = llm or FallbackLLMProvider(
            primary=OpenRouterClient(),
            fallback=GroqClient(),
        )
        self.query_resolver = query_resolver or ConversationQueryResolver(
            self.llm,
            memory=memory or SessionMemoryService(),
        )

    @traceable(name="QueryOrchestrator.answer", run_type="chain")
    def answer(self, question: str, conversation_history=None, session_id: str = "default"):
        # ── 0. References follow-up — user said yes to "show references?" ──
        if (
            _is_positive(question)
            and _last_assistant_offered_references(conversation_history)
            and session_id in _pending_citations
        ):
            citations = _pending_citations.pop(session_id)
            if citations:
                return {
                    "answer": "Here are the references for my previous answer:",
                    "citations": citations,
                    "cache_hit": False,
                    "show_citations": True,
                    "tokens": None,
                }
            return {
                "answer": "No specific document references are available for that answer.",
                "citations": [],
                "cache_hit": False,
                "tokens": None,
            }

        # ── 1. FAQ similarity cache — always checked first ───────────────
        cached = self._faq_search(question)
        if cached is not None:
            logger.info(
                "FAQ cache hit (similarity=%.4f): '%s' → '%s'",
                cached["similarity"],
                question,
                cached["question"],
            )
            faq_citation = {
                "source": cached.get("source", "HR Policy Handbook"),
                "section": cached.get("section", cached["question"]),
                "text": cached["answer"],
            }
            _pending_citations[session_id] = [faq_citation]
            return {
                "answer": cached["answer"] + "\n\nWould you like to see the references for this?",
                "citations": [],
                "cache_hit": True,
                "matched_faq": cached["question"],
                "similarity": cached["similarity"],
                "tokens": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cache_hit": True,
                },
            }

        # ── 2. Full RAG + LLM pipeline ────────────────────────────────
        retrieval_query = self.query_resolver.resolve(question, conversation_history)
        selected_evidence = self._retrieve(retrieval_query)

        if not selected_evidence:
            return {
                "answer": "I could not find that information in the available documents.",
                "citations": [],
                "cache_hit": False,
                "tokens": None,
            }

        # Build optimized prompt from ChromaDB retrieved context
        messages = self.context_builder.build_messages(
            question=question,
            context_chunks=selected_evidence,
            include_system_prompt=True,
        )

        answer = self._generate(messages, session_id=session_id)
        citations = self.provenance.build_citations(selected_evidence)
        self.faq_store.save(question, answer, citations)
        _pending_citations[session_id] = citations

        # Extract token usage from LLM provider
        tokens = None
        if hasattr(self.llm, 'get_last_tokens'):
            tokens = self.llm.get_last_tokens()
        elif hasattr(self.llm, 'primary') and hasattr(self.llm.primary, 'get_last_tokens'):
            # If using FallbackLLMProvider, get from primary
            tokens = self.llm.primary.get_last_tokens()

        # Add tokens to LangSmith if available
        if tokens and tokens.get("total_tokens", 0) > 0:
            add_tokens_to_current_run(
                prompt_tokens=tokens.get("prompt_tokens", 0),
                completion_tokens=tokens.get("completion_tokens", 0),
                model=tokens.get("model", "unknown"),
            )

        return {
            "answer": answer,
            "citations": [],
            "cache_hit": False,
            "tokens": tokens,
        }

    @traceable(name="FAQSimilarityCache.search", run_type="retriever")
    def _faq_search(self, question: str):
        return self.faq_cache.search(question)

    @traceable(name="RAGRetrieval", run_type="retriever")
    def _retrieve(self, query: str):
        return self.retrieval.retrieve(query, top_k=RAG_CANDIDATE_COUNT)

    @traceable(name="LLMGenerate", run_type="llm")
    def _generate(self, messages: list, session_id: str = "default"):
        # Pass session_id to LLM provider for token tracking
        if hasattr(self.llm, 'session_id'):
            old_session = self.llm.session_id
            self.llm.session_id = session_id
            try:
                return self.llm.generate(messages)
            finally:
                self.llm.session_id = old_session
        else:
            return self.llm.generate(messages)
