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
        project_contact_lookup=None,
        response_cache=None,
    ):
        self.retrieval = retrieval or RetrievalService()
        self.provenance = provenance or ProvenanceService()
        self.faq_store = faq_store or MongoFAQStore()
        self.faq_cache = faq_cache or FAQSimilarityCache()
        self.context_builder = context_builder or RAGContextBuilder()
        self.project_contact_lookup = project_contact_lookup
        self.response_cache = response_cache

        self.llm = llm or FallbackLLMProvider(
            primary=OpenRouterClient(),
            fallback=GroqClient(),
        )
        self.query_resolver = query_resolver or ConversationQueryResolver(
            self.llm,
            memory=memory or SessionMemoryService(),
        )

    @traceable(name="QueryOrchestrator.answer", run_type="chain")
    def answer(
        self,
        question: str,
        conversation_history=None,
        session_id: str = "default",
        authorized_project_ids=None,
        authorization_scope=None,
        defer_citations: bool = False,
    ):
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

        # ── 1. LRU Response cache check (if configured) ─────────────────
        if self.response_cache is not None:
            cached_entry = self.response_cache.get(question)
            if cached_entry is not None:
                if isinstance(cached_entry, dict):
                    ans = cached_entry.get("answer", "")
                    cached_citations = cached_entry.get("citations", [])
                else:
                    ans = str(cached_entry)
                    cached_citations = []
                if defer_citations:
                    _pending_citations[session_id] = cached_citations
                    return {
                        "answer": ans,
                        "citations": [],
                        "cache_hit": True,
                        "tokens": {
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0,
                            "cache_hit": True,
                        },
                    }
                return {
                    "answer": ans,
                    "citations": cached_citations,
                    "cache_hit": True,
                    "tokens": {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "cache_hit": True,
                    },
                }

        # ── 2. FAQ similarity cache — always checked first (if response_cache not active) ──
        cached = self._faq_search(question) if self.response_cache is None else None
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
            if defer_citations:
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
            else:
                return {
                    "answer": cached["answer"],
                    "citations": [faq_citation],
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

        # ── 3. Full RAG + LLM pipeline with Authorization Scoping ───────
        retrieval_query = self.query_resolver.resolve(question, conversation_history)
        retrieval_kwargs = {"top_k": RAG_CANDIDATE_COUNT}
        scope_flags = {
            "authorized_project_ids": None,
            "authorized_document_ids": None,
            "include_unassigned": True,
        }
        if authorization_scope is not None:
            if not authorization_scope.is_admin:
                scope_flags["authorized_project_ids"] = list(authorization_scope.project_ids or [])
                scope_flags["include_unassigned"] = authorization_scope.include_unassigned
                retrieval_kwargs["authorized_project_ids"] = list(authorization_scope.project_ids or [])
                retrieval_kwargs["include_unassigned"] = authorization_scope.include_unassigned
                if authorization_scope.document_ids:
                    scope_flags["authorized_document_ids"] = list(authorization_scope.document_ids)
                    retrieval_kwargs["authorized_document_ids"] = list(authorization_scope.document_ids)
        elif authorized_project_ids is not None:
            scope_flags["authorized_project_ids"] = list(authorized_project_ids)
            retrieval_kwargs["authorized_project_ids"] = authorized_project_ids

        selected_evidence = self._retrieve(retrieval_query, **retrieval_kwargs)

        if not selected_evidence:
            denied = self._probe_unauthorized_relevance(
                retrieval_query,
                retrieval_kwargs,
                scope_flags,
            )
            if denied is not None:
                return denied
            return {
                "answer": "I could not find that information in the available documents.",
                "citations": [],
                "cache_hit": False,
                "tokens": None,
            }

        context = "\n\n".join(
            result.get("text", "")
            for result in selected_evidence
        )

        # Build optimized prompt from ChromaDB retrieved context
        if hasattr(self.context_builder, "build_messages"):
            messages = self.context_builder.build_messages(
                question=question,
                context_chunks=selected_evidence,
                include_system_prompt=True,
            )
        else:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You answer questions using only the provided document context. "
                        "Do not invent or assume information. "
                        "Keep the answer concise and directly answer the user's question. "
                        "End with: 'Would you like to see the references for this?'"
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

        answer = self._generate(messages, session_id=session_id)
        citations = self.provenance.build_citations(selected_evidence)

        if hasattr(self.faq_store, "save"):
            try:
                self.faq_store.save(question, answer, citations)
            except Exception:
                pass

        if self.response_cache is not None:
            try:
                if hasattr(self.response_cache, "put"):
                    self.response_cache.put(question, {"answer": answer, "citations": citations})
                elif hasattr(self.response_cache, "set"):
                    self.response_cache.set(question, {"answer": answer, "citations": citations})
            except Exception:
                pass

        # Extract token usage from LLM provider
        tokens = None
        if hasattr(self.llm, "get_last_tokens") and callable(self.llm.get_last_tokens):
            raw = self.llm.get_last_tokens()
            if isinstance(raw, dict):
                tokens = raw
        elif hasattr(self.llm, "primary") and hasattr(self.llm.primary, "get_last_tokens") and callable(self.llm.primary.get_last_tokens):
            raw = self.llm.primary.get_last_tokens()
            if isinstance(raw, dict):
                tokens = raw

        # Add tokens to LangSmith if available
        if isinstance(tokens, dict) and isinstance(tokens.get("total_tokens"), (int, float)) and tokens.get("total_tokens", 0) > 0:
            try:
                add_tokens_to_current_run(
                    prompt_tokens=tokens.get("prompt_tokens", 0),
                    completion_tokens=tokens.get("completion_tokens", 0),
                    model=tokens.get("model", "unknown"),
                )
            except Exception:
                pass

        if defer_citations:
            _pending_citations[session_id] = citations
            return {
                "answer": answer,
                "citations": [],
                "context": context,
                "cache_hit": False,
                "tokens": tokens,
            }

        return {
            "answer": answer,
            "citations": citations,
            "context": context,
            "cache_hit": False,
            "tokens": tokens,
        }

    def generate_faqs(self):
        if hasattr(self.faq_cache, "load"):
            cached = self.faq_cache.load()
            if cached:
                return cached
        if hasattr(self.faq_cache, "get"):
            cached = self.faq_cache.get()
            if cached:
                return cached
        if hasattr(self.faq_cache, "read"):
            cached = self.faq_cache.read()
            if cached:
                return cached

        evidence = self.retrieval.retrieve("frequently asked questions HR policies")
        citations = self.provenance.build_citations(evidence) if isinstance(evidence, list) else []
        context = "\n\n".join(e.get("text", "") for e in evidence) if isinstance(evidence, list) else ""
        prompt = (
            "Based on the following HR policy text, generate a concise list of 5 Frequently Asked Questions with answers:\n\n"
            f"{context}"
        )
        faqs_text = self.llm.generate([{"role": "user", "content": prompt}])
        result = {"faqs": faqs_text, "citations": citations}
        if hasattr(self.faq_cache, "save"):
            self.faq_cache.save(result)
        return result

    @traceable(name="FAQSimilarityCache.search", run_type="retriever")
    def _faq_search(self, question: str):
        if hasattr(self.faq_cache, "search"):
            return self.faq_cache.search(question)
        return None

    @traceable(name="RAGRetrieval", run_type="retriever")
    def _retrieve(self, query: str, **kwargs):
        if kwargs:
            return self.retrieval.retrieve(query, **kwargs)
        return self.retrieval.retrieve(query, top_k=RAG_CANDIDATE_COUNT)

    @traceable(name="LLMGenerate", run_type="llm")
    def _generate(self, messages: list, session_id: str = "default"):
        if hasattr(self.llm, "session_id"):
            old_session = self.llm.session_id
            self.llm.session_id = session_id
            try:
                return self.llm.generate(messages)
            finally:
                self.llm.session_id = old_session
        else:
            return self.llm.generate(messages)

    def _probe_unauthorized_relevance(self, retrieval_query, retrieval_kwargs, scope_flags):
        """Detect relevant content that exists only outside the authorized scope."""
        probe = getattr(self.retrieval, "detect_unauthorized_relevance", None)
        if probe is None:
            return None
        hits = probe(
            retrieval_query,
            authorized_project_ids=scope_flags.get("authorized_project_ids"),
            authorized_document_ids=scope_flags.get("authorized_document_ids"),
            include_unassigned=scope_flags.get("include_unassigned", True),
            top_k=retrieval_kwargs.get("top_k"),
        )
        if not hits:
            return None
        return self._access_denied_response(hits[0])

    def _access_denied_response(self, hit):
        """Templated, non-LLM response that never reveals document content."""
        project_id = hit.get("project_id")
        contact = None
        if project_id and project_id != "unassigned" and self.project_contact_lookup:
            try:
                contact = self.project_contact_lookup(project_id)
            except Exception:
                contact = None
        if contact and contact.get("project_name"):
            return {
                "answer": (
                    "Relevant information exists in a project document that you do "
                    "not currently have access to. Please contact "
                    f"{contact.get('manager_name') or 'the project manager'}, "
                    f"the manager of {contact['project_name']}, to request access."
                ),
                "citations": [],
            }
        return {
            "answer": (
                "Relevant information exists in a document that you do not "
                "currently have access to. Please contact the relevant project "
                "manager to request access."
            ),
            "citations": [],
        }
