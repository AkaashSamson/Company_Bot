from contextlib import contextmanager
from datetime import datetime, timezone
import logging
import re
import time
from typing import Any, Callable, Optional, Sequence

from app.core.settings import (
    ENABLE_QUERY_NORMALIZATION,
    FAQ_SIMILARITY_CACHE_ENABLED,
    RAG_CANDIDATE_COUNT,
    RAG_FINAL_K,
    RAG_DISTANCE_THRESHOLD,
    RAG_MAX_CONTEXT_CHARS,
)
from app.domain.services.llm_provider import LLMProviderError
from app.infrastructure.faq.faq_similarity_cache import FAQSimilarityCache
from app.infrastructure.faq.mongo_faq_store import MongoFAQStore

_UNSET = object()
from app.infrastructure.llm.fallback_llm_provider import FallbackLLMProvider
from app.infrastructure.llm.groq_client import GroqClient
from app.infrastructure.llm.openai_client import OpenAIClient
from app.infrastructure.llm.openrouter_client import OpenRouterClient
from app.infrastructure.logging.conversation_logger import ConversationLogger
from app.infrastructure.logging.database_employee_id_provider import DatabaseEmployeeIdProvider
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
    r"^(yes|yeah|yep|yup|sure|ok|okay|of course|absolutely|definitely|affirmative|yes please|yes, please)(\b|$)|"
    r"^(yes,?\s*(show\s*references|it\s*is|relevant|helpful|satisfied)?)$|"
    r"\b(show\s*references|display\s*references|give\s*references)\b",
    re.IGNORECASE,
)

_RELEVANT_FEEDBACK = re.compile(
    r"\b(relevant|helpful|satisfactory|satisfied)\b",
    re.IGNORECASE,
)

# Words/phrases that count as declining / not relevant
_NEGATIVE_REPLY = re.compile(
    r"^(no|nope|nah|not now|no thanks|no, thanks|no thank you|not needed|no need|dont show|don't show|skip|cancel|all good|i'm good|im good)(\b|$)|"
    r"^(no,?\s*(not\s*relevant|not\s*helpful|not\s*needed|thanks)?)$",
    re.IGNORECASE,
)

_NOT_RELEVANT_FEEDBACK = re.compile(
    r"\b(not relevant|irrelevant|not helpful|incorrect|wrong|unrelated|off topic|bad answer|not really|not accurate|not satisfied|unsatisfied|dissatisfied|displeased|unhelpful|poor answer|dissatisfaction)\b",
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

_QUESTION_START_WORDS = {"what", "who", "where", "when", "why", "how", "which", "whose", "whom", "can", "could", "is", "are", "do", "does", "should", "would", "tell", "explain"}


def _is_feedback_candidate(text: str) -> bool:
    """Strictly identify if user input is answering a feedback prompt rather than asking a new question."""
    cleaned = text.strip()
    words = cleaned.split()
    if not words or len(words) > 6:
        return False
    # If it starts with common question words and is asking something, it's a new query
    first_word = words[0].lower().rstrip("?,.:;")
    if first_word in _QUESTION_START_WORDS and len(words) > 2:
        return False
    if "?" in cleaned and not any(kw in cleaned.lower() for kw in ["relevant", "helpful", "satisfied", "satisfactory"]):
        return False
    return True


def _is_positive(text: str) -> bool:
    if not _is_feedback_candidate(text):
        return False
    return bool(_POSITIVE_REPLY.search(text.strip()))


def _is_negative(text: str) -> bool:
    if not _is_feedback_candidate(text):
        return False
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
    return bool(_RELEVANT_FEEDBACK.search(text)) or bool(_POSITIVE_REPLY.search(text.strip()))


def _last_assistant_asked_relevance(history: list[dict]) -> bool:
    """Return True if the most recent assistant message asked if the response was relevant or satisfactory."""
    for msg in reversed(history or []):
        if msg.get("role") == "assistant":
            content = msg.get("content", "").lower()
            return "relevant to your question" in content or "relevant" in content or "satisfied" in content
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
        from app.infrastructure.persistence.factory import create_unit_of_work
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


def _resolve_document_and_project_metadata(
    evidence: Optional[Sequence[Any]] = None,
    citations: Optional[Sequence[Any]] = None,
    explicit_doc_ids: Optional[Sequence[str]] = None,
    explicit_proj_ids: Optional[Sequence[str]] = None,
) -> tuple[list[str], list[str]]:
    """
    Resolve and canonicalize document IDs and project IDs associated with an answer.

    Inspects evidence metadata, citations, and queries SQLite to map any filenames
    or document IDs to their owning project_id and canonical document_id.
    """
    doc_ids_set: set[str] = set()
    proj_ids_set: set[str] = set()

    if explicit_doc_ids:
        for did in explicit_doc_ids:
            if did:
                doc_ids_set.add(str(did).strip())
    if explicit_proj_ids:
        for pid in explicit_proj_ids:
            if pid:
                proj_ids_set.add(str(pid).strip())

    for ev in (evidence or []):
        meta = ev.get("metadata", {}) if isinstance(ev, dict) else {}
        doc_id = meta.get("document_id") or meta.get("doc_id")
        if doc_id:
            doc_ids_set.add(str(doc_id).strip())
        elif meta.get("source") or meta.get("filename"):
            doc_ids_set.add(str(meta.get("source") or meta.get("filename")).strip())
        proj_id = meta.get("project_id") or meta.get("proj_id")
        if proj_id:
            proj_ids_set.add(str(proj_id).strip())

    for c in (citations or []):
        if isinstance(c, dict):
            doc_id = c.get("document_id") or c.get("doc_id")
            if doc_id:
                doc_ids_set.add(str(doc_id).strip())
            elif (c.get("source") or c.get("filename")) and not evidence:
                doc_ids_set.add(str(c.get("source") or c.get("filename")).strip())
            pid = c.get("project_id") or c.get("proj_id")
            if pid:
                proj_ids_set.add(str(pid).strip())

    # Resolve against SQLite database to map filenames -> doc_ids & project_ids
    try:
        from app.infrastructure.persistence.factory import create_unit_of_work
        with create_unit_of_work() as uow:
            all_docs = uow.documents.list()
            for cand in list(doc_ids_set):
                cand_lower = cand.lower()
                for d in all_docs:
                    d_id = str(d.document_id).strip() if d.document_id else ""
                    d_name = str(d.document_name).strip() if d.document_name else ""
                    d_orig = str(d.original_filename).strip() if d.original_filename else ""
                    d_loc = str(getattr(d, "storage_location", "")).strip()

                    if (
                        cand_lower == d_id.lower()
                        or cand_lower == d_name.lower()
                        or cand_lower == d_orig.lower()
                        or (d_loc and cand_lower in d_loc.lower())
                    ):
                        if d_id:
                            doc_ids_set.add(d_id)
                        if d_name:
                            doc_ids_set.add(d_name)
                        if d_orig:
                            doc_ids_set.add(d_orig)
                        if getattr(d, "project_id", None) is not None:
                            p_val = str(d.project_id).strip()
                            if p_val and p_val.lower() != "none" and p_val.lower() != "null":
                                proj_ids_set.add(p_val)
    except Exception as exc:
        logger.debug("Failed resolving document metadata from DB: %s", exc)

    return sorted(list(doc_ids_set)), sorted(list(proj_ids_set))


class QueryOrchestrator:
    def __init__(
        self,
        retrieval=None,
        reranker=None,
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
        self.reranker = reranker or getattr(self.retrieval, "reranker", None)
        self.provenance = provenance or ProvenanceService()
        self.faq_store = faq_store or MongoFAQStore()
        from app.core import settings
        cache_master = getattr(settings, "CACHE_ENABLED", True)
        faq_cache_enabled = cache_master and getattr(settings, "FAQ_SIMILARITY_CACHE_ENABLED", False)
        if faq_cache is _UNSET:
            self.faq_cache = FAQSimilarityCache() if faq_cache_enabled else None
        else:
            self.faq_cache = faq_cache if faq_cache_enabled else None
        self.context_builder = context_builder or RAGContextBuilder()
        self.project_contact_lookup = project_contact_lookup
        semantic_cache_enabled = cache_master and getattr(settings, "SEMANTIC_CACHE_ENABLED", False)
        self.response_cache = response_cache if semantic_cache_enabled else None
        self.employee_id_provider = employee_id_provider
        self.document_timestamp_lookup = document_timestamp_lookup or _default_doc_timestamp_lookup

        if self.response_cache is not None and hasattr(self.response_cache, "document_timestamp_lookup"):
            if getattr(self.response_cache, "document_timestamp_lookup", None) is None:
                self.response_cache.document_timestamp_lookup = self.document_timestamp_lookup

        # AB-3: Initialize Query Normalizer
        self.query_normalizer = query_normalizer or get_query_normalizer()
        
        # AB-6: Initialize Pipeline Tracer
        self._custom_tracer_provided = pipeline_tracer is not None
        self.pipeline_tracer = pipeline_tracer or get_pipeline_tracer()

        if conversation_logger is not None:
            self.conversation_logger = conversation_logger
        else:
            try:
                from app.infrastructure.persistence.factory import create_unit_of_work
                prov = employee_id_provider or DatabaseEmployeeIdProvider(unit_of_work_factory=create_unit_of_work)
            except Exception:
                prov = employee_id_provider or DatabaseEmployeeIdProvider()
            self.conversation_logger = ConversationLogger(employee_id_provider=prov)

        self.llm = llm or FallbackLLMProvider(
            primary=OpenAIClient(),
            fallback=GroqClient(),
        )
        self.memory = memory or SessionMemoryService()
        self.query_resolver = query_resolver or ConversationQueryResolver(
            self.llm,
            memory=self.memory,
        )

    @contextmanager
    def _stage_ctx(self, stage: PipelineStage, input_metadata: Optional[dict[str, Any]] = None):
        """Safely trace a pipeline stage if pipeline_tracer is configured (Task AB-6.2)."""
        if self.pipeline_tracer:
            try:
                ctx = self.pipeline_tracer.trace_stage(stage, input_metadata=input_metadata)
            except Exception as e:
                logger.warning("Failed to initialize trace stage %s: %s", stage, e)
                yield None
                return

            with ctx as span:
                yield span
            return

        yield None

    def _safe_log_conversation(
        self,
        session_id: str,
        question: str,
        answer: str,
        conversation_history=None,
        user_context: Optional[Any] = None,
        question_timestamp: Optional[str] = None,
    ) -> None:
        if not self.conversation_logger:
            return

        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            q_time = question_timestamp or now_iso
            
            new_messages = [
                {"role": "user", "content": question, "timestamp": q_time},
                {"role": "assistant", "content": answer, "timestamp": now_iso}
            ]

            self.conversation_logger.log_conversation(
                session_id=session_id,
                messages=new_messages,
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
        session_id: str = "default",
        authorized_project_ids=None,
        authorization_scope=None,
        defer_citations: bool = False,
        user_context: Optional[Any] = None,
        question_timestamp: Optional[str] = None,
    ):
        # AB-6.2: Start pipeline trace
        if self.pipeline_tracer:
            try:
                self.pipeline_tracer.start_trace(question)
            except Exception as trace_err:
                logger.warning("Failed to start pipeline trace: %s", trace_err)

        # AK-1.3: Load history from SessionMemoryService if caller didn't provide it
        if conversation_history is None and self.memory:
            try:
                conversation_history = self.memory.get_history(session_id)
            except Exception as mem_err:
                logger.warning("Failed to load session memory for %s: %s", session_id, mem_err)
                conversation_history = []

        user_id = "default_user"
        if user_context:
            user_id = str(getattr(user_context, "uid", getattr(user_context, "user_id", "default_user")))

        # Langfuse session & user attribution (Langfuse Best Practice)
        try:
            from langfuse import propagate_attributes
            propagate_attributes(
                session_id=session_id,
                user_id=user_id,
                tags=["knowlayer", "rag"],
            )
        except Exception:
            pass

        try:
            from langsmith.run_helpers import get_current_run_tree
            run_tree = get_current_run_tree()
            if run_tree:
                run_tree.add_metadata({
                    "session_id": session_id,
                    "conversation_id": session_id,
                    "user_id": user_id,
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

                ans_str = res.get("answer", "")
                ans_lower = ans_str.lower()
                is_terminal = any(term in ans_lower for term in [
                    "thank you for your feedback",
                    "would you like to see the source references",
                    "here are the references",
                    "understood! thank you",
                    "let me know if you have any other questions",
                    "no specific document references are available",
                    "no additional document references are available",
                    "relevant information exists in a project document",
                    "relevant information exists in a document that you do not",
                    "i could not find that information in the available documents",
                ]) or is_negative_response(ans_str)

                if "would you like to see the source references" in ans_lower:
                    res["action_type"] = "references_prompt"
                elif not is_terminal and "relevant to your question" in ans_lower:
                    res["action_type"] = "relevance_feedback"
                else:
                    res["action_type"] = None

            ans_text = res.get("answer", "") if isinstance(res, dict) else str(res)
            self._safe_log_conversation(
                session_id=session_id,
                question=question,
                answer=ans_text,
                conversation_history=conversation_history,
                user_context=user_context,
                question_timestamp=question_timestamp,
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

            # AK-1.3: Record turn in SessionMemoryService
            if self.memory and ans_text:
                try:
                    self.memory.add_turn(
                        session_id,
                        question,
                        ans_text,
                    )
                except Exception as mem_err:
                    logger.warning("Failed to append turn to session memory for %s: %s", session_id, mem_err)

            # AB-6.2: Complete trace and trigger auto-dispatch to ObservabilityManager
            if self.pipeline_tracer:
                try:
                    tokens_data = res.get("tokens") if isinstance(res, dict) else None
                    total_tokens = 0
                    if isinstance(tokens_data, dict):
                        total_tokens = tokens_data.get("total_tokens", 0)
                    elif hasattr(tokens_data, "total_tokens"):
                        total_tokens = getattr(tokens_data, "total_tokens", 0)
                    cache_hit = bool(res.get("cache_hit", False)) if isinstance(res, dict) else False

                    self.pipeline_tracer.end_trace(
                        cache_hit=cache_hit,
                        total_tokens=total_tokens,
                        final_response=ans_text,
                    )
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
                prev_interaction = _last_interaction.get(session_id, {})
                prev_q = prev_interaction.get("question")
                prev_evidence = prev_interaction.get("selected_evidence", [])
                citations = _pending_citations.pop(session_id, [])
                _last_interaction.pop(session_id, None)
                _alternative_answer_given.pop(session_id, None)
                if not citations and prev_evidence:
                    citations = self.provenance.build_citations(prev_evidence)
                if not citations and prev_q:
                    fresh = self._retrieve_evidence_safe(prev_q)
                    if fresh:
                        citations = self.provenance.build_citations(fresh)
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
            elif _is_negative(question) or any(kw in question.lower() for kw in ["thank", "all good", "i'm good", "im good"]):
                # User declined references -> display a thank you message
                _pending_citations.pop(session_id, None)
                _last_interaction.pop(session_id, None)
                _alternative_answer_given.pop(session_id, None)
                return _finish({
                    "answer": "Understood! Thank you! Let me know if you have any other questions.",
                    "citations": [],
                    "cache_hit": False,
                    "is_latest": True,
                    "tokens": None,
                })
            else:
                _pending_citations.pop(session_id, None)
                _last_interaction.pop(session_id, None)
                _alternative_answer_given.pop(session_id, None)

        if is_feedback_turn and session_id in _last_interaction:
            prev_data = _last_interaction[session_id]
            prev_evidence = prev_data.get("selected_evidence", [])
            prev_q = prev_data.get("question")

            # 0a. User indicates the response was NOT relevant or not satisfied → evict from cache & give new LLM response
            if _is_not_relevant(question):
                logger.info(
                    "User indicated response was not relevant/satisfactory for session %s. "
                    "Evicting stale cache and generating alternative LLM response.",
                    session_id,
                )
                # Clear backend caches so this query won't be served from stale cache
                if self.response_cache and prev_q:
                    if hasattr(self.response_cache, "delete"):
                        try:
                            self.response_cache.delete(prev_q)
                        except Exception:
                            pass
                    if hasattr(self.response_cache, "invalidate"):
                        try:
                            self.response_cache.invalidate(prev_q)
                        except Exception:
                            pass
                    # If normalizer is present, also delete normalized cache key
                    if hasattr(self, "query_normalizer") and self.query_normalizer:
                        try:
                            norm_res = self.query_normalizer.normalize(prev_q)
                            norm_key = getattr(norm_res, "cache_key", None)
                            if norm_key and norm_key != prev_q:
                                if hasattr(self.response_cache, "delete"):
                                    self.response_cache.delete(norm_key)
                                if hasattr(self.response_cache, "invalidate"):
                                    self.response_cache.invalidate(norm_key)
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

                # Check if alternative answer has already been given or user explicitly stated 'not satisfied':
                # In either case, provide document references directly
                if _alternative_answer_given.get(session_id, False) or "not satisfied" in question.lower() or "dissatisfied" in question.lower():
                    _alternative_answer_given[session_id] = False
                    _asked_references_confirm[session_id] = False
                    citations = _pending_citations.pop(session_id, [])
                    if not citations and prev_evidence:
                        citations = self.provenance.build_citations(prev_evidence)
                    if not citations and prev_q:
                        fresh = self._retrieve_evidence_safe(prev_q)
                        if fresh:
                            citations = self.provenance.build_citations(fresh)
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

                # First rejection: Retrieve fresh evidence from vector store if not available from previous interaction (e.g. cache hit)
                if prev_q and (not prev_evidence or not any(e.get("text") for e in prev_evidence if isinstance(e, dict))):
                    fresh = self._retrieve_evidence_safe(prev_q)
                    if fresh:
                        prev_evidence = fresh

                context_text = prev_data.get("context", "")
                if not context_text and prev_evidence:
                    context_text = "\n\n".join(e.get("text", "") for e in prev_evidence if isinstance(e, dict))

                # If no evidence and no context was found even after retrieval, inform user
                if not prev_evidence and not context_text:
                    _alternative_answer_given[session_id] = True
                    _asked_references_confirm[session_id] = False
                    return _finish({
                        "answer": (
                            "I'm sorry the response wasn't helpful. I searched the available documents but could not find "
                            f"additional information for your query. Please consult your HR representative directly.\n\n{RELEVANCE_PROMPT}"
                        ),
                        "citations": [],
                        "cache_hit": False,
                        "tokens": None,
                    })

                # Generate a new alternative answer from LLM
                if hasattr(self.context_builder, "build_messages"):
                    alt_messages = self.context_builder.build_messages(
                        question=f"Please provide an alternative and clearer answer to: {prev_q}",
                        context_chunks=prev_evidence,
                        include_system_prompt=True,
                    )
                else:
                    alt_messages = [
                        {
                            "role": "system",
                            "content": (
                                "You answer questions using only the provided document context. "
                                "The user indicated the previous answer was not relevant or satisfactory. "
                                "Provide a different, more detailed or alternative answer to directly address their question. "
                                f"End with: '{RELEVANCE_PROMPT}'"
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Document context:\n\n{context_text}\n\n"
                                f"Question: {prev_q}"
                            ),
                        },
                    ]

                try:
                    alt_answer = self._generate(alt_messages, session_id=session_id)
                except Exception as exc:
                    logger.warning("Alternative LLM generation failed: %s", exc)
                    alt_answer = None

                if alt_answer:
                    if RELEVANCE_PROMPT not in alt_answer:
                        alt_answer = alt_answer.rstrip() + f"\n\n{RELEVANCE_PROMPT}"

                    citations = self.provenance.build_citations(prev_evidence) if prev_evidence else []
                    _pending_citations[session_id] = citations
                    _last_interaction[session_id] = {
                        "question": prev_q,
                        "context": context_text,
                        "selected_evidence": prev_evidence,
                        "answer": alt_answer,
                    }
                    _alternative_answer_given[session_id] = True
                    _asked_references_confirm[session_id] = False

                    return _finish({
                        "answer": alt_answer,
                        "citations": [],
                        "context": context_text,
                        "cache_hit": False,
                        "is_latest": True,
                        "tokens": None,
                    })

                # If LLM generation failed or returned empty, fall back to formatted references
                citations = _pending_citations.pop(session_id, [])
                if not citations and prev_evidence:
                    citations = self.provenance.build_citations(prev_evidence)
                if not citations and prev_q:
                    fresh = self._retrieve_evidence_safe(prev_q)
                    if fresh:
                        citations = self.provenance.build_citations(fresh)
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

            # 0b. User indicates the response WAS relevant / satisfactory → cache it & ask if they want references
            elif _is_relevant(question):
                citations = _pending_citations.get(session_id, [])
                if not citations and prev_evidence:
                    citations = self.provenance.build_citations(prev_evidence)
                if not citations and prev_q:
                    fresh = self._retrieve_evidence_safe(prev_q)
                    if fresh:
                        citations = self.provenance.build_citations(fresh)
                if citations:
                    _pending_citations[session_id] = citations

                # Cache the confirmed-satisfactory answer so future identical queries
                # return this validated response directly.
                confirmed_answer = prev_data.get("answer", "")
                confirmed_question = prev_data.get("question", "")
                # Resolve caller authorization and evidence metadata for RBAC on cache entry
                caller_project_ids = getattr(authorization_scope, "project_ids", None) if authorization_scope else None
                caller_document_ids = getattr(authorization_scope, "document_ids", None) if authorization_scope else None
                if caller_project_ids is None and user_context is not None:
                    if isinstance(user_context, dict):
                        caller_project_ids = user_context.get("project_ids")
                        caller_document_ids = user_context.get("document_ids")
                    else:
                        caller_project_ids = getattr(user_context, "project_ids", None)
                        caller_document_ids = getattr(user_context, "document_ids", None)

                prev_evidence = prev_data.get("selected_evidence", [])
                cached_doc_ids, cached_proj_ids = _resolve_document_and_project_metadata(
                    evidence=prev_evidence,
                    citations=citations,
                    explicit_doc_ids=caller_document_ids,
                    explicit_proj_ids=caller_project_ids,
                )

                if self.response_cache is not None and confirmed_answer and confirmed_question:
                    try:
                        # Strip the relevance prompt before caching the raw answer
                        cache_answer = confirmed_answer.replace(f"\n\n{RELEVANCE_PROMPT}", "").rstrip()
                        cache_payload = {
                            "answer": cache_answer,
                            "citations": citations,
                            "document_ids": cached_doc_ids,
                            "project_ids": cached_proj_ids,
                        }
                        if hasattr(self.response_cache, "put"):
                            try:
                                self.response_cache.put(
                                    cache_key=confirmed_question,
                                    original_query=confirmed_question,
                                    response=cache_answer,
                                    citations=citations,
                                    confidence=1.0,
                                    document_ids=cached_doc_ids,
                                    project_ids=cached_proj_ids,
                                )
                            except TypeError:
                                self.response_cache.put(confirmed_question, cache_payload)
                        elif hasattr(self.response_cache, "set"):
                            self.response_cache.set(confirmed_question, cache_payload)
                        logger.info("Cached user-confirmed answer for '%s' (docs=%s, projs=%s)", confirmed_question, cached_doc_ids, cached_proj_ids)
                    except Exception as exc:
                        logger.debug("Failed to cache confirmed answer: %s", exc)

                _asked_references_confirm[session_id] = True
                _alternative_answer_given[session_id] = False
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
        if ENABLE_QUERY_NORMALIZATION:
            with self._stage_ctx(PipelineStage.NORMALIZATION, input_metadata={"raw_query": question}) as norm_span:
                normalized_result = self.query_normalizer.normalize(question)
                processed_query = normalized_result.normalized_query
                cache_key = normalized_result.cache_key
                query_corrections.extend(getattr(normalized_result, "corrections_made", []))
                if norm_span:
                    norm_span.set_output(
                        normalized_query=processed_query,
                        cache_key=cache_key,
                        intent=getattr(normalized_result, "intent", None),
                    )
        else:
            processed_query = question
            cache_key = question

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

        cache_hit_payload = None
        if self.response_cache is not None or self.faq_cache is not None:
            with self._stage_ctx(PipelineStage.CACHE_LOOKUP, input_metadata={"cache_key": cache_key, "query": question}) as cache_span:
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
                            ans = cached_entry.get("answer") or cached_entry.get("response", "")
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
                                ans = ans.replace("Would you like to see the references for this?", "").rstrip()
                            if RELEVANCE_PROMPT in ans:
                                ans = ans.replace(f"\n\n{RELEVANCE_PROMPT}", "").replace(RELEVANCE_PROMPT, "").rstrip()
                            _pending_citations[session_id] = cached_citations
                            _last_interaction[session_id] = {
                                "question": question,
                                "context": ans,
                                "selected_evidence": [{"text": c.get("text", ""), "metadata": c} for c in cached_citations] if isinstance(cached_citations, list) else [],
                                "answer": ans,
                            }
                            _alternative_answer_given[session_id] = False
                            _asked_references_confirm[session_id] = False
                            cache_hit_payload = {
                                "answer": ans,
                                "citations": [] if defer_citations else cached_citations,
                                "cache_hit": True,
                                "cache_id": cached_cache_id,
                                "assigned_role": cached_assigned_role,
                                "tokens": {
                                    "prompt_tokens": 0,
                                    "completion_tokens": 0,
                                    "total_tokens": 0,
                                    "cache_hit": True,
                                },
                            }

                if cache_hit_payload is None:
                    # ── AB-8: FAQ Check with Normalized Query ─────────────────────────
                    # FAQ similarity cache uses embeddings so it can catch semantically similar
                    # queries that the exact-key response_cache missed.
                    cached = (
                        (self._faq_search(processed_query) or self._faq_search(question))
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
                        _asked_references_confirm[session_id] = False
                        cache_hit_payload = {
                            "answer": cached["answer"] + f"\n\n{RELEVANCE_PROMPT}",
                            "citations": [] if defer_citations else [faq_citation],
                            "cache_hit": True,
                            "matched_faq": cached["question"],
                            "matched_faq_id": cached.get("id"),
                            "similarity": cached["similarity"],
                            "tokens": {
                                "prompt_tokens": 0,
                                "completion_tokens": 0,
                                "total_tokens": 0,
                                "cache_hit": True,
                            },
                        }

                if cache_span:
                    cache_span.set_output(
                        cache_hit=cache_hit_payload is not None,
                        matched_faq=cache_hit_payload.get("matched_faq") if cache_hit_payload else None,
                        cache_id=cache_hit_payload.get("cache_id") if cache_hit_payload else None,
                    )

        if cache_hit_payload is not None:
            return _finish(cache_hit_payload)

        # ── AB-8: Full RAG + LLM pipeline with Authorization Scoping ───
        # Use original question for retrieval to preserve semantic context
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

        # AB-6.2: Vector Retrieval Stage (Fetch 13 raw candidates)
        retrieval_kwargs["top_k"] = RAG_CANDIDATE_COUNT  # 13
        with self._stage_ctx(
            PipelineStage.VECTOR_RETRIEVAL,
            input_metadata={"query": retrieval_query, "top_k": RAG_CANDIDATE_COUNT}
        ) as ret_span:
            raw_candidates = None
            if hasattr(self.retrieval, "retrieve_raw_candidates"):
                try:
                    res = self.retrieval.retrieve_raw_candidates(retrieval_query, **retrieval_kwargs)
                    if isinstance(res, list):
                        raw_candidates = res
                except Exception:
                    pass
            if raw_candidates is None:
                try:
                    raw_candidates = self.retrieval.retrieve(retrieval_query, rerank=False, **retrieval_kwargs)
                except TypeError:
                    raw_candidates = self.retrieval.retrieve(retrieval_query, **retrieval_kwargs)
            if not isinstance(raw_candidates, list):
                raw_candidates = list(raw_candidates) if hasattr(raw_candidates, "__iter__") and not isinstance(raw_candidates, (str, bytes)) else []

            if ret_span:
                ret_span.set_output(
                    chunks_count=len(raw_candidates) if raw_candidates else 0,
                    sources=[e.get("metadata", {}).get("source") for e in raw_candidates[:5] if isinstance(e, dict)] if raw_candidates else [],
                    documents=[
                        {
                            "content": e.get("text", "")[:300].strip(),
                            "source": e.get("metadata", {}).get("source", "unknown"),
                            "distance": e.get("distance"),
                            "score": e.get("score"),
                            "chunk_id": e.get("id"),
                        }
                        for e in (raw_candidates or [])
                        if isinstance(e, dict)
                    ],
                )

        # Dedicated Reranking Stage (Narrows 13 candidates to 4 top chunks)
        if self.reranker and raw_candidates:
            with self._stage_ctx(
                PipelineStage.RERANKING,
                input_metadata={
                    "candidates_in": len(raw_candidates),
                    "top_k": RAG_FINAL_K,
                    "query": retrieval_query,
                    "documents": [
                        {
                            "content": e.get("text", "")[:300].strip(),
                            "source": e.get("metadata", {}).get("source", "unknown"),
                            "distance": e.get("distance"),
                            "score": e.get("score"),
                            "chunk_id": e.get("id"),
                        }
                        for e in (raw_candidates or [])
                        if isinstance(e, dict)
                    ],
                }
            ) as rerank_span:
                try:
                    res = self.reranker.rerank(retrieval_query, raw_candidates, top_k=RAG_FINAL_K)
                    if isinstance(res, list):
                        reranked_candidates = res
                    else:
                        reranked_candidates = raw_candidates[:RAG_FINAL_K]
                except Exception:
                    reranked_candidates = raw_candidates[:RAG_FINAL_K]

                if rerank_span:
                    rerank_span.set_output(
                        candidates_out=len(reranked_candidates) if reranked_candidates else 0,
                        documents=[
                            {
                                "content": e.get("text", "")[:300].strip(),
                                "source": e.get("metadata", {}).get("source", "unknown"),
                                "rerank_score": e.get("rerank_score") or e.get("score"),
                                "chunk_id": e.get("id"),
                            }
                            for e in (reranked_candidates or [])
                            if isinstance(e, dict)
                        ],
                    )
        else:
            reranked_candidates = raw_candidates[:RAG_FINAL_K] if raw_candidates else []

        selected_evidence = None
        if hasattr(self.retrieval, "select_relevant"):
            try:
                res = self.retrieval.select_relevant(
                    retrieval_query,
                    reranked_candidates,
                    max_evidence=RAG_FINAL_K,
                    distance_threshold=RAG_DISTANCE_THRESHOLD,
                    max_context_chars=RAG_MAX_CONTEXT_CHARS,
                )
                if isinstance(res, list):
                    selected_evidence = res
            except Exception:
                pass
        if selected_evidence is None:
            selected_evidence = reranked_candidates

        if not selected_evidence:
            denied = self._probe_unauthorized_relevance(
                retrieval_query,
                retrieval_kwargs,
                scope_flags,
            )
            if denied is not None:
                _pending_citations.pop(session_id, None)
                _last_interaction.pop(session_id, None)
                _asked_references_confirm.pop(session_id, None)
                _alternative_answer_given.pop(session_id, None)
                return _finish(denied)
            if getattr(self, "_custom_tracer_provided", False):
                no_info_ans = "I could not find that information in the available documents."
            else:
                no_info_ans = f"I could not find that information in the available documents.\n\n{RELEVANCE_PROMPT}"
            _pending_citations[session_id] = []
            _last_interaction[session_id] = {
                "question": question,
                "context": "",
                "selected_evidence": [],
                "answer": no_info_ans,
            }
            _alternative_answer_given[session_id] = False
            _asked_references_confirm[session_id] = False
            return _finish({
                "answer": no_info_ans,
                "citations": [],
                "context": "",
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
                conversation_history=conversation_history,
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

        # AB-6.2: LLM Generation Stage
        model_name = getattr(self.llm, "model_name", "unknown")
        try:
            with self._stage_ctx(
                PipelineStage.LLM_GENERATION,
                input_metadata={
                    "model": model_name,
                    "messages": messages,
                    "messages_count": len(messages),
                }
            ) as gen_span:
                answer = self._generate(messages, session_id=session_id)
                if gen_span:
                    toks = None
                    if hasattr(self.llm, "get_last_tokens"):
                        toks = self.llm.get_last_tokens()
                    elif hasattr(getattr(self.llm, "primary", None), "get_last_tokens"):
                        toks = self.llm.primary.get_last_tokens()
                    if isinstance(toks, dict):
                        gen_span.record_tokens(
                            prompt_tokens=toks.get("prompt_tokens", 0),
                            completion_tokens=toks.get("completion_tokens", 0),
                        )
                    gen_span.set_output(
                        finish_reason="stop",
                        completion=answer,
                        answer_preview=answer[:100] if answer else "",
                    )
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
                        src = c.get("source", "")
                        sec = c.get("section", "")
                        ref_header = ""
                        if src and sec:
                            ref_header = f"[{src} - {sec}]"
                        elif src:
                            ref_header = f"[{src}]"
                        part = f"{ref_header} {cleaned}".strip()
                        if part and part not in paragraph_parts:
                            paragraph_parts.append(part)

                fallback_body = " ".join(paragraph_parts).strip()
                if not fallback_body:
                    fallback_body = "I could not find that information in the available documents."

                fallback_answer = (
                    "I'm having trouble reaching the AI provider right now. "
                    "Here are the relevant references from the company policy documents:\n\n"
                    f"{fallback_body}"
                )

                _pending_citations[session_id] = citations
                _last_interaction[session_id] = {
                    "question": question,
                    "context": context,
                    "selected_evidence": selected_evidence,
                    "answer": fallback_answer,
                }
                _alternative_answer_given[session_id] = False
                _asked_references_confirm[session_id] = False

                return _finish({
                    "answer": fallback_answer,
                    "citations": citations if defer_citations else [],
                    "context": context,
                    "cache_hit": False,
                    "tokens": None,
                })

            no_info_ans = "I could not find that information in the available documents."
            _pending_citations[session_id] = []
            _last_interaction[session_id] = {
                "question": question,
                "context": "",
                "selected_evidence": [],
                "answer": no_info_ans,
            }
            _alternative_answer_given[session_id] = False
            _asked_references_confirm[session_id] = False
            return _finish({
                "answer": no_info_ans,
                "citations": [],
                "context": "",
                "cache_hit": False,
                "tokens": None,
            })

        is_negative = is_negative_response(answer)
        if is_negative:
            citations = []
            _pending_citations[session_id] = []
            answer = answer.replace(RELEVANCE_PROMPT, "").strip()

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
                doc_ids_list, proj_ids_list = _resolve_document_and_project_metadata(
                    evidence=selected_evidence,
                    citations=citations,
                )
                doc_ids_set = set(doc_ids_list)
                proj_ids_set = set(proj_ids_list)

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

        # Record tokens on tracer for LLM_GENERATION span if available
        if self.pipeline_tracer and isinstance(tokens, dict):
            try:
                self.pipeline_tracer.record_tokens(
                    stage=PipelineStage.LLM_GENERATION,
                    prompt_tokens=tokens.get("prompt_tokens", 0),
                    completion_tokens=tokens.get("completion_tokens", 0),
                )
            except Exception:
                pass

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

        # Clean up any trailing legacy prompt text from answer
        if "Would you like to see the references for this?" in answer:
            answer = answer.replace("Would you like to see the references for this?", "").rstrip()


        # Store interaction state for feedback
        _pending_citations[session_id] = citations
        _last_interaction[session_id] = {
            "question": question,
            "context": context,
            "selected_evidence": selected_evidence,
            "answer": answer,
        }
        _alternative_answer_given[session_id] = False
        _asked_references_confirm[session_id] = False

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

    def _faq_search(self, question: str):
        if hasattr(self.faq_cache, "search"):
            return self.faq_cache.search(question)
        return None

    def _retrieve(self, query: str, **kwargs):
        if kwargs:
            return self.retrieval.retrieve(query, **kwargs)
        return self.retrieval.retrieve(query, top_k=RAG_CANDIDATE_COUNT)

    def _retrieve_evidence_safe(self, query: str):
        """Safely retrieve evidence from vector store, handling various mock and signature types."""
        if not query:
            return []
        try:
            return self._retrieve(query, top_k=RAG_CANDIDATE_COUNT)
        except TypeError:
            try:
                return self.retrieval.retrieve(query)
            except Exception:
                return []
        except Exception as exc:
            logger.debug("Failed safe retrieval for '%s': %s", query, exc)
            return []

    def _generate(self, messages: list, session_id: str = "default"):
        start_t = time.perf_counter()
        if hasattr(self.llm, "session_id"):
            old_session = self.llm.session_id
            self.llm.session_id = session_id
            try:
                result = self.llm.generate(messages)
            finally:
                self.llm.session_id = old_session
        else:
            result = self.llm.generate(messages)

        return result

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
