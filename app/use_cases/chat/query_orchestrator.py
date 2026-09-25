from datetime import datetime, timezone
import logging
import re
from typing import Any, Callable, Optional

from app.core.settings import FAQ_SIMILARITY_CACHE_ENABLED, RAG_CANDIDATE_COUNT
from app.domain.services.llm_provider import LLMProviderError
from app.infrastructure.faq.faq_similarity_cache import FAQSimilarityCache
from app.infrastructure.faq.mongo_faq_store import MongoFAQStore

_UNSET = object()
from app.infrastructure.llm.fallback_llm_provider import FallbackLLMProvider
from app.infrastructure.llm.groq_client import GroqClient
from app.infrastructure.llm.openrouter_client import OpenRouterClient
from app.infrastructure.logging.conversation_logger import ConversationLogger
from app.infrastructure.logging.database_employee_id_provider import DatabaseEmployeeIdProvider
from app.infrastructure.observability.tracer import traceable
from app.use_cases.chat.conversation_query_resolver import ConversationQueryResolver
from app.use_cases.chat.provenance_service import ProvenanceService
from app.use_cases.chat.retrieval_service import RetrievalService
from app.use_cases.chat.rag_context_builder import RAGContextBuilder
from app.domain.services.session_memory_service import SessionMemoryService
from app.infrastructure.observability.langsmith_integration import add_tokens_to_current_run

# AB-3: Import Query Normalizer
from app.use_cases.chat.query_normalizer import QueryNormalizer, get_query_normalizer

# AB-6: Import Pipeline Tracer
from app.infrastructure.observability.pipeline_tracer import (
    PipelineTracer,
    PipelineStage,
    get_pipeline_tracer,
)

logger = logging.getLogger(__name__)

RELEVANCE_PROMPT = "Was this response relevant to your question?"
REFERENCES_CONFIRM_PROMPT = "Would you like to see the source references?"

# Words/phrases that count as a positive response / relevant
_POSITIVE_REPLY = re.compile(
    r"\b(yes|yeah|yep|yup|sure|please|show|go ahead|ok|okay|of course|"
    r"absolutely|definitely|affirmative|why not|do it|send|display|give)\b",
    re.IGNORECASE,
)

_RELEVANT_FEEDBACK = re.compile(
    r"\b(relevant|helpful|correct|accurate|good|satisfactory)\b",
    re.IGNORECASE,
)

# Words/phrases that count as declining / not relevant
_NEGATIVE_REPLY = re.compile(
    r"\b(no|nope|nah|not now|no thanks|not needed|no need|dont show|don't show|skip|cancel)\b",
    re.IGNORECASE,
)

_NOT_RELEVANT_FEEDBACK = re.compile(
    r"\b(not relevant|irrelevant|not helpful|incorrect|wrong|unrelated|off topic|bad answer|not really|not accurate|not satisfied|unsatisfied|dissatisfied|displeased|unhelpful|poor answer|not good|dissatisfaction)\b",
    re.IGNORECASE,
)

from app.core.cache_quality import is_negative_response, _NO_INFO_PATTERN

# Keeps the last pending citations per session_id so they can be returned
# when the user asks for references or confirms relevance.
_pending_citations: dict[str, list] = {}
# Keeps the last interaction per session_id to enable generating alternative answers
_last_interaction: dict[str, dict] = {}
# Tracks whether an alternative answer has already been given for the current question
_alternative_answer_given: dict[str, bool] = {}
# Tracks sessions where the bot asked "Would you like to see the source references?"
_asked_references_confirm: dict[str, bool] = {}


def _is_feedback_candidate(text: str) -> bool:
    cleaned = text.strip()
    words = cleaned.split()
    if len(words) > 12:
        return False
    if "?" in cleaned and not any(kw in cleaned.lower() for kw in ["relevant", "helpful", "accurate"]):
        return False
    return True


def _is_positive(text: str) -> bool:
    return bool(_POSITIVE_REPLY.search(text))


def _is_negative(text: str) -> bool:
    return bool(_NEGATIVE_REPLY.search(text.strip()))


def _is_not_relevant(text: str) -> bool:
    if not _is_feedback_candidate(text):
        return False
    return bool(_NOT_RELEVANT_FEEDBACK.search(text)) or bool(_NEGATIVE_REPLY.search(text.strip()))


def _is_relevant(text: str) -> bool:
    if not _is_feedback_candidate(text):
        return False
    if _is_not_relevant(text):
        return False
    return bool(_RELEVANT_FEEDBACK.search(text)) or bool(_POSITIVE_REPLY.search(text))


def _last_assistant_asked_relevance(history: list[dict]) -> bool:
    """Return True if the most recent assistant message asked if the response was relevant."""
    for msg in reversed(history or []):
        if msg.get("role") == "assistant":
            content = msg.get("content", "").lower()
            return "relevant to your question" in content or "relevant" in content
    return False


def _last_assistant_offered_references(history: list[dict]) -> bool:
    """Return True if the most recent assistant message asked about references."""
    for msg in reversed(history or []):
        if msg.get("role") == "assistant":
            content = msg.get("content", "").lower()
            return "reference" in content or "source" in content
    return False


def _last_assistant_asked_references_confirm(history: list[dict]) -> bool:
    """Return True if the most recent assistant message asked whether the user wants to see references."""
    for msg in reversed(history or []):
        if msg.get("role") == "assistant":
            content = msg.get("content", "").lower()
            return "would you like to see the source references" in content
    return False



def _default_doc_timestamp_lookup(doc_id_or_name: str) -> Optional[float]:
    """Lookup updated_at timestamp for a document by ID, name, or filename from SQLite."""
    try:
        from app.infrastructure.persistence.sqlalchemy.session import create_unit_of_work
        with create_unit_of_work() as uow:
            doc = uow.documents.get(doc_id_or_name)
            if doc is None:
                for d in uow.documents.list():
                    if d.document_name == doc_id_or_name or d.original_filename == doc_id_or_name:
                        doc = d
                        break
            if doc is not None and getattr(doc, "updated_at", None):
                ts = doc.updated_at
                if hasattr(ts, "timestamp"):
                    return float(ts.timestamp())
                return float(ts)
    except Exception:
        pass
    return None


class QueryOrchestrator:
    def __init__(
        self,
        retrieval=None,
        provenance=None,
        llm=None,
        query_resolver=None,
        memory=None,
        faq_store=None,
        faq_cache=_UNSET,
        context_builder=None,
        project_contact_lookup=None,
        response_cache=None,
        conversation_logger=None,
        employee_id_provider=None,
        query_normalizer=None,
        pipeline_tracer=None,
        document_timestamp_lookup: Optional[Callable[[str], Optional[float]]] = None,
    ):
        self.retrieval = retrieval or RetrievalService()
        self.provenance = provenance or ProvenanceService()
        self.faq_store = faq_store or MongoFAQStore()
        if faq_cache is _UNSET:
            self.faq_cache = FAQSimilarityCache() if FAQ_SIMILARITY_CACHE_ENABLED else None
        else:
            self.faq_cache = faq_cache
        self.context_builder = context_builder or RAGContextBuilder()
        self.project_contact_lookup = project_contact_lookup
        self.response_cache = response_cache
        self.employee_id_provider = employee_id_provider
        self.document_timestamp_lookup = document_timestamp_lookup or _default_doc_timestamp_lookup

        if self.response_cache is not None and hasattr(self.response_cache, "document_timestamp_lookup"):
            if getattr(self.response_cache, "document_timestamp_lookup", None) is None:
                self.response_cache.document_timestamp_lookup = self.document_timestamp_lookup

        # AB-3: Initialize Query Normalizer
        self.query_normalizer = query_normalizer or get_query_normalizer()
        
        # AB-6: Initialize Pipeline Tracer
        self.pipeline_tracer = pipeline_tracer or get_pipeline_tracer()

        if conversation_logger is not None:
            self.conversation_logger = conversation_logger
        else:
            try:
                from app.infrastructure.persistence.sqlalchemy.session import create_unit_of_work
                prov = employee_id_provider or DatabaseEmployeeIdProvider(unit_of_work_factory=create_unit_of_work)
            except Exception:
                prov = employee_id_provider or DatabaseEmployeeIdProvider()
            self.conversation_logger = ConversationLogger(employee_id_provider=prov)

        self.llm = llm or FallbackLLMProvider(
            primary=OpenRouterClient(),
            fallback=GroqClient(),
        )
        self.query_resolver = query_resolver or ConversationQueryResolver(
            self.llm,
            memory=memory or SessionMemoryService(),
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

    @traceable(name="QueryOrchestrator.answer", run_type="chain")
    def answer(
        self,
        question: str,
        conversation_history=None,
        session_id: str = "default",
        authorized_project_ids=None,
        authorization_scope=None,
        defer_citations: bool = False,
        user_context: Optional[Any] = None,
    ):
        try:
            from langsmith.run_helpers import get_current_run_tree
            run_tree = get_current_run_tree()
            if run_tree:
                run_tree.add_metadata({
                    "session_id": session_id,
                    "conversation_id": session_id,
                    "user_id": getattr(user_context, "user_id", "default_user") if user_context else "default_user",
                })
                run_tree.add_tags(["company_bot", "v3", "rag"])
        except Exception:
            pass

        query_corrections = []

        def _finish(res):
            if isinstance(res, dict):
                res.setdefault("is_latest", True)
                if "corrections" not in res:
                    res["corrections"] = list(query_corrections)
            ans_text = res.get("answer", "") if isinstance(res, dict) else str(res)
            self._safe_log_conversation(
                session_id=session_id,
                question=question,
                answer=ans_text,
                conversation_history=conversation_history,
                user_context=user_context,
            )
            try:
                from langsmith.run_helpers import get_current_run_tree
                run_tree = get_current_run_tree()
                if run_tree and isinstance(res, dict):
                    run_tree.add_metadata({
                        "cache_hit": bool(res.get("cache_hit", False)),
                        "has_citations": bool(res.get("citations")),
                    })
            except Exception:
                pass
            return res

        # ── 0. Relevance / References follow-up ─────────────────────────
        asked_relevance = (
            _last_assistant_asked_relevance(conversation_history)
            or (
                session_id in _last_interaction
                and "relevant to your question" in _last_interaction[session_id].get("answer", "").lower()
            )
        )
        asked_references = _last_assistant_offered_references(conversation_history)

        # Allow user dissatisfaction feedback even if the relevance prompt was omitted/truncated
        is_feedback_turn = (
            asked_relevance
            or (
                session_id in _last_interaction
                and (_is_not_relevant(question) or _is_relevant(question))
            )
        )

        # ── 0-pre. Did the bot ask "Would you like to see the source references?" ──
        asked_refs_confirm = (
            _asked_references_confirm.get(session_id, False)
            or _last_assistant_asked_references_confirm(conversation_history)
        )
        if asked_refs_confirm:
            _asked_references_confirm.pop(session_id, None)
            if _is_positive(question):
                # User confirmed they want to see references
                prev_evidence = _last_interaction.get(session_id, {}).get("selected_evidence", [])
                citations = _pending_citations.pop(session_id, [])
                if not citations and prev_evidence:
                    citations = self.provenance.build_citations(prev_evidence)
                if citations:
                    return _finish({
                        "answer": "Here are the references from the documents:",
                        "citations": citations,
                        "cache_hit": False,
                        "show_citations": True,
                        "is_latest": True,
                        "tokens": None,
                    })
                return _finish({
                    "answer": "No specific document references are available for that answer.",
                    "citations": [],
                    "cache_hit": False,
                    "is_latest": True,
                    "tokens": None,
                })
            elif _is_negative(question):
                # User declined references
                _pending_citations.pop(session_id, None)
                return _finish({
                    "answer": "No problem! Let me know if you have any other questions.",
                    "citations": [],
                    "cache_hit": False,
                    "is_latest": True,
                    "tokens": None,
                })

        if is_feedback_turn and session_id in _last_interaction:
            prev_data = _last_interaction[session_id]
            prev_evidence = prev_data.get("selected_evidence", [])

            # 0a. User indicates the response was NOT relevant or not satisfied → evict from cache & show references
            if _is_not_relevant(question):
                logger.info(
                    "User indicated response was not relevant/satisfactory for session %s. "
                    "Evicting stale cache and showing formatted references directly.",
                    session_id,
                )
                # Clear backend caches so this query won't be served from stale cache
                prev_q = prev_data.get("question")
                if self.response_cache and prev_q and hasattr(self.response_cache, "delete"):
                    try:
                        self.response_cache.delete(prev_q)
                    except Exception:
                        pass
                if self.response_cache and hasattr(self.response_cache, "clear"):
                    try:
                        self.response_cache.clear()
                    except Exception as exc:
                        logger.warning("Failed to clear response_cache: %s", exc)
                if hasattr(self.llm, "cache") and self.llm.cache and hasattr(self.llm.cache, "clear"):
                    try:
                        self.llm.cache.clear()
                    except Exception as exc:
                        logger.warning("Failed to clear llm cache: %s", exc)

                # Evict from FAQ similarity cache if the rejected answer came from FAQ cache
                matched_faq = prev_data.get("matched_faq")
                matched_faq_id = prev_data.get("matched_faq_id")
                if (matched_faq or matched_faq_id) and hasattr(self.faq_cache, "delete_entry"):
                    target = matched_faq_id or matched_faq
                    try:
                        self.faq_cache.delete_entry(target)
                        logger.info("Evicted rejected FAQ '%s' from FAQ cache.", target)
                    except Exception as exc:
                        logger.warning("Failed to evict FAQ entry from cache: %s", exc)

                citations = _pending_citations.pop(session_id, [])
                if not citations and prev_evidence:
                    citations = self.provenance.build_citations(prev_evidence)

                if citations:
                    return _finish({
                        "answer": "Here are the references from the documents for your review:",
                        "citations": citations,
                        "cache_hit": False,
                        "show_citations": True,
                        "tokens": None,
                    })
                return _finish({
                    "answer": (
                        "I'm sorry the response wasn't helpful. No additional document references are "
                        "available for that query. Please consult your HR representative directly."
                    ),
                    "citations": [],
                    "cache_hit": False,
                    "tokens": None,
                })

            # 0b. User indicates the response WAS relevant → ask if they want references
            elif _is_relevant(question):
                _asked_references_confirm[session_id] = True
                return _finish({
                    "answer": f"I'm glad the answer was helpful! {REFERENCES_CONFIRM_PROMPT}",
                    "citations": [],
                    "cache_hit": False,
                    "tokens": None,
                })

        # ── 0c. Legacy References follow-up (when asked about references, not relevance) ──
        if (
            _is_positive(question)
            and asked_references
            and session_id in _pending_citations
        ):
            citations = _pending_citations.pop(session_id)
            if citations:
                return _finish({
                    "answer": "Here are the references for my previous answer:",
                    "citations": citations,
                    "cache_hit": False,
                    "show_citations": True,
                    "tokens": None,
                })
            return _finish({
                "answer": "No specific document references are available for that answer.",
                "citations": [],
                "cache_hit": False,
                "tokens": None,
            })

        if (
            _is_negative(question)
            and asked_references
            and session_id in _pending_citations
        ):
            _pending_citations.pop(session_id, None)
            return _finish({
                "answer": "Understood! Let me know if there is anything else I can help you with.",
                "citations": [],
                "cache_hit": False,
                "tokens": None,
            })


        # ── AB-3: Query Normalization Stage ─────────────────────────────
        # Start pipeline trace with normalized query
        normalized_result = self.query_normalizer.normalize(question)
        processed_query = normalized_result.normalized_query
        query_corrections.extend(normalized_result.corrections_made)
        
        # Use normalized query for cache lookup and retrieval
        cache_key = normalized_result.cache_key

        # ── AB-9: Semantic Cache Check with RBAC Isolation & Cache ID ───
        # Resolve caller authorization & role for RBAC cache checking
        caller_role = None
        caller_roles = []
        is_admin_flag = False
        caller_project_ids = None
        caller_document_ids = None

        if authorization_scope is not None:
            is_admin_flag = getattr(authorization_scope, "is_admin", False)
            caller_project_ids = getattr(authorization_scope, "project_ids", None)
            caller_document_ids = getattr(authorization_scope, "document_ids", None)
        elif authorized_project_ids is not None:
            caller_project_ids = list(authorized_project_ids)

        if user_context is not None:
            if isinstance(user_context, dict):
                caller_role = user_context.get("role")
                if "roles" in user_context:
                    caller_roles = list(user_context["roles"])
                if user_context.get("is_admin"):
                    is_admin_flag = True
            else:
                caller_role = getattr(user_context, "role", None)
                if hasattr(user_context, "roles"):
                    caller_roles = list(getattr(user_context, "roles"))
                if getattr(user_context, "is_admin", False):
                    is_admin_flag = True

        if is_admin_flag and not caller_role:
            caller_role = "admin"

        if self.response_cache is not None:
            # Check normalized cache_key first, fall back to raw question with RBAC scoping and doc freshness
            cache_get_kwargs = {
                "role": caller_role,
                "roles": caller_roles,
                "project_ids": caller_project_ids,
                "document_ids": caller_document_ids,
                "is_admin": is_admin_flag,
                "document_timestamp_lookup": self.document_timestamp_lookup,
            }
            try:
                cached_entry = self.response_cache.get(cache_key, **cache_get_kwargs)
                if cached_entry is None and cache_key != question:
                    cached_entry = self.response_cache.get(question, **cache_get_kwargs)
            except TypeError:
                cached_entry = self.response_cache.get(cache_key)
                if cached_entry is None and cache_key != question:
                    cached_entry = self.response_cache.get(question)

            if cached_entry is not None:
                if isinstance(cached_entry, dict):
                    ans = cached_entry.get("answer", "")
                    cached_citations = cached_entry.get("citations", [])
                    cached_cache_id = cached_entry.get("cache_id")
                    cached_assigned_role = cached_entry.get("assigned_role")
                elif hasattr(cached_entry, "response") and isinstance(cached_entry.response, str):
                    ans = cached_entry.response
                    cached_citations = getattr(cached_entry, "citations", [])
                    cached_cache_id = getattr(cached_entry, "cache_id", None)
                    cached_assigned_role = getattr(cached_entry, "assigned_role", None)
                elif isinstance(cached_entry, str):
                    ans = cached_entry
                    cached_citations = []
                    cached_cache_id = None
                    cached_assigned_role = None
                else:
                    ans = str(getattr(cached_entry, "response", cached_entry))
                    cached_citations = []
                    cached_cache_id = getattr(cached_entry, "cache_id", None)
                    cached_assigned_role = getattr(cached_entry, "assigned_role", None)

                # Cache Read Quality Gate: Never return a cached negative response
                if is_negative_response(ans):
                    logger.info("Evicting/ignoring cached negative response for key '%s'", cache_key)
                    if hasattr(self.response_cache, "delete"):
                        try:
                            self.response_cache.delete(cache_key)
                            if cache_key != question:
                                self.response_cache.delete(question)
                        except Exception:
                            pass
                    cached_entry = None
                else:
                    if "Would you like to see the references for this?" in ans:
                        ans = ans.replace("Would you like to see the references for this?", RELEVANCE_PROMPT)
                    # Ensure every cached answer ends with the relevance prompt so feedback buttons appear
                    if defer_citations and RELEVANCE_PROMPT not in ans and REFERENCES_CONFIRM_PROMPT not in ans:
                        ans = ans.rstrip() + f"\n\n{RELEVANCE_PROMPT}"
                    _pending_citations[session_id] = cached_citations
                    _last_interaction[session_id] = {
                        "question": question,
                        "context": ans,
                        "selected_evidence": [{"text": c.get("text", ""), "metadata": c} for c in cached_citations] if isinstance(cached_citations, list) else [],
                        "answer": ans,
                    }
                    _alternative_answer_given[session_id] = False
                    if defer_citations:
                        return _finish({
                            "answer": ans,
                            "citations": [],
                            "cache_hit": True,
                            "cache_id": cached_cache_id,
                            "assigned_role": cached_assigned_role,
                            "tokens": {
                                "prompt_tokens": 0,
                                "completion_tokens": 0,
                                "total_tokens": 0,
                                "cache_hit": True,
                            },
                        })
                    return _finish({
                        "answer": ans,
                        "citations": cached_citations,
                        "cache_hit": True,
                        "cache_id": cached_cache_id,
                        "assigned_role": cached_assigned_role,
                        "tokens": {
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0,
                            "cache_hit": True,
                        },
                    })

        # ── AB-8: FAQ Check with Normalized Query ─────────────────────────
        # FAQ similarity cache uses embeddings so it can catch semantically similar
        # queries that the exact-key response_cache missed.
        cached = (
            self._faq_search(question)
            if authorized_project_ids is None
            else None
        )
        if cached is not None and is_negative_response(cached.get("answer", "")):
            logger.info("Ignoring negative response in FAQ match for '%s'", question)
            cached = None

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
            _last_interaction[session_id] = {
                "question": question,
                "context": cached["answer"],
                "selected_evidence": [{"text": cached["answer"], "metadata": {"source": cached.get("source", "HR Policy Handbook"), "section": cached.get("section", cached["question"])}}],
                "answer": cached["answer"],
                "matched_faq": cached.get("question", question),
                "matched_faq_id": cached.get("id"),
            }
            _alternative_answer_given[session_id] = False
            if defer_citations:
                return _finish({
                    "answer": cached["answer"] + f"\n\n{RELEVANCE_PROMPT}",
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
                })
            else:
                return _finish({
                    "answer": cached["answer"] + f"\n\n{RELEVANCE_PROMPT}",
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
                })

        # ── AB-8: Full RAG + LLM pipeline with Authorization Scoping ───
        # Use normalized/expanded query for retrieval (AB-8)
        retrieval_query = self.query_resolver.resolve(processed_query, conversation_history)
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
                return _finish(denied)
            no_info_ans = f"I could not find that information in the available documents.\n\n{RELEVANCE_PROMPT}"
            _pending_citations[session_id] = []
            _last_interaction[session_id] = {
                "question": question,
                "context": "",
                "selected_evidence": [],
                "answer": no_info_ans,
            }
            _alternative_answer_given[session_id] = False
            return _finish({
                "answer": no_info_ans,
                "citations": [],
                "cache_hit": False,
                "tokens": None,
            })

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
                        f"End with: '{RELEVANCE_PROMPT}'"
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

        citations = self.provenance.build_citations(selected_evidence)

        try:
            answer = self._generate(messages, session_id=session_id)
        except (LLMProviderError, Exception) as llm_error:
            logger.warning(
                "LLM generation failed: %s. Providing document references as a single paragraph response.",
                llm_error,
            )
            if selected_evidence:
                paragraph_parts = []
                for c in citations[:3]:
                    text = c.get("text", "").strip()
                    if text:
                        cleaned = re.sub(r"\s+", " ", text).strip()
                        if cleaned and cleaned not in paragraph_parts:
                            paragraph_parts.append(cleaned)

                fallback_answer = " ".join(paragraph_parts).strip()
                if not fallback_answer:
                    fallback_answer = "I could not find that information in the available documents."

                _pending_citations[session_id] = citations
                _last_interaction[session_id] = {
                    "question": question,
                    "context": context,
                    "selected_evidence": selected_evidence,
                    "answer": fallback_answer,
                }
                _alternative_answer_given[session_id] = False

                return _finish({
                    "answer": fallback_answer,
                    "citations": [],  # Response was created from references; skip showing references again
                    "context": context,
                    "cache_hit": False,
                    "tokens": None,
                })

            no_info_ans = f"I could not find that information in the available documents.\n\n{RELEVANCE_PROMPT}"
            _pending_citations[session_id] = []
            _last_interaction[session_id] = {
                "question": question,
                "context": "",
                "selected_evidence": [],
                "answer": no_info_ans,
            }
            _alternative_answer_given[session_id] = False
            return _finish({
                "answer": no_info_ans,
                "citations": [],
                "context": "",
                "cache_hit": False,
                "tokens": None,
            })

        is_negative = is_negative_response(answer)

        if hasattr(self.faq_store, "save") and not is_negative:
            try:
                self.faq_store.save(question, answer, citations)
            except Exception:
                pass

        # Generate Cache ID and extract documents for RBAC cache storage
        cache_id = None
        assigned_role_to_cache = caller_role
        if self.response_cache is not None and not is_negative:
            try:
                # Extract referenced documents and projects from selected_evidence and citations
                doc_ids_set = set()
                proj_ids_set = set()
                for ev in (selected_evidence or []):
                    meta = ev.get("metadata", {}) if isinstance(ev, dict) else {}
                    doc_id = meta.get("document_id")
                    if doc_id:
                        doc_ids_set.add(str(doc_id))
                    elif meta.get("source"):
                        doc_ids_set.add(str(meta.get("source")))
                    proj_id = meta.get("project_id")
                    if proj_id:
                        proj_ids_set.add(str(proj_id))
                if not doc_ids_set:
                    for c in (citations or []):
                        src = c.get("document_id") or c.get("source")
                        if src:
                            doc_ids_set.add(str(src))

                import uuid
                cache_id = f"cch_{uuid.uuid4().hex[:12]}"

                # Resolve current updated_at timestamps for all cited documents
                doc_last_updated = {}
                if self.document_timestamp_lookup:
                    for did in doc_ids_set:
                        try:
                            ts = self.document_timestamp_lookup(did)
                            if ts is not None:
                                if hasattr(ts, "timestamp"):
                                    doc_last_updated[did] = float(ts.timestamp())
                                else:
                                    doc_last_updated[did] = float(ts)
                        except Exception as exc:
                            logger.debug("Failed resolving timestamp for document %s: %s", did, exc)

                payload = {
                    "answer": answer,
                    "citations": citations,
                    "cache_id": cache_id,
                    "assigned_role": assigned_role_to_cache,
                    "document_ids": list(doc_ids_set),
                    "doc_last_updated": doc_last_updated,
                    "project_ids": list(proj_ids_set),
                }
                if hasattr(self.response_cache, "put"):
                    try:
                        self.response_cache.put(
                            cache_key=cache_key,
                            original_query=question,
                            response=answer,
                            citations=citations,
                            confidence=1.0,
                            cache_id=cache_id,
                            assigned_role=assigned_role_to_cache,
                            document_ids=list(doc_ids_set),
                            doc_last_updated=doc_last_updated,
                            project_ids=list(proj_ids_set),
                        )
                        if cache_key != question:
                            self.response_cache.put(
                                cache_key=question,
                                original_query=question,
                                response=answer,
                                citations=citations,
                                confidence=1.0,
                                cache_id=cache_id,
                                assigned_role=assigned_role_to_cache,
                                document_ids=list(doc_ids_set),
                                doc_last_updated=doc_last_updated,
                                project_ids=list(proj_ids_set),
                            )
                    except TypeError:
                        self.response_cache.put(cache_key, payload)
                        if cache_key != question:
                            self.response_cache.put(question, payload)
                elif hasattr(self.response_cache, "set"):
                    self.response_cache.set(cache_key, payload)
                    if cache_key != question:
                        self.response_cache.set(question, payload)
            except Exception as exc:
                logger.debug("Failed to store in response_cache: %s", exc)

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

        # Ensure answer ends with RELEVANCE_PROMPT so feedback buttons always render
        if "Would you like to see the references for this?" in answer:
            answer = answer.replace("Would you like to see the references for this?", RELEVANCE_PROMPT)
        if defer_citations and RELEVANCE_PROMPT not in answer and REFERENCES_CONFIRM_PROMPT not in answer:
            answer = answer.rstrip() + f"\n\n{RELEVANCE_PROMPT}"


        # Store interaction state for feedback
        _pending_citations[session_id] = citations
        _last_interaction[session_id] = {
            "question": question,
            "context": context,
            "selected_evidence": selected_evidence,
            "answer": answer,
        }
        _alternative_answer_given[session_id] = False

        if defer_citations:
            return _finish({
                "answer": answer,
                "citations": [],
                "context": context,
                "cache_hit": False,
                "cache_id": cache_id,
                "assigned_role": assigned_role_to_cache,
                "tokens": tokens,
            })

        return _finish({
            "answer": answer,
            "citations": citations,
            "context": context,
            "cache_hit": False,
            "cache_id": cache_id,
            "assigned_role": assigned_role_to_cache,
            "tokens": tokens,
        })

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
        if probe is None or not callable(probe):
            return None
        try:
            hits = probe(
                retrieval_query,
                authorized_project_ids=scope_flags.get("authorized_project_ids"),
                authorized_document_ids=scope_flags.get("authorized_document_ids"),
                include_unassigned=scope_flags.get("include_unassigned", True),
                top_k=retrieval_kwargs.get("top_k"),
            )
        except Exception:
            return None
        if not hits or not isinstance(hits, list) or not isinstance(hits[0], dict):
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
