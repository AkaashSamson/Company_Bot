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
        project_contact_lookup=None,
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
        self.project_contact_lookup = project_contact_lookup

    def answer(
        self,
        question: str,
        conversation_history=None,
        authorized_project_ids=None,
        authorization_scope=None,
    ):
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
        selected_evidence = self.retrieval.retrieve(retrieval_query, **retrieval_kwargs)

        if not selected_evidence:
            denied = self._probe_unauthorized_relevance(
                retrieval_query,
                retrieval_kwargs,
                scope_flags,
            )
            if denied is not None:
                return denied
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

    def _probe_unauthorized_relevance(self, retrieval_query, retrieval_kwargs, scope_flags):
        """Detect relevant content that exists only outside the authorized scope.

        No document text is ever returned; the hit is used solely to decide
        between the safe access-request response and the "not found" fallback.
        """
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