from app.use_cases.access.authorization_service import AuthorizationError
from app.use_cases.chat.query_orchestrator import (
    NO_ACCESS_MESSAGE,
    NO_RELEVANT_MESSAGE,
    QueryOrchestrator,
)


class StubAuthorization:
    def __init__(self, document_ids=None, error=None):
        self.document_ids = document_ids or []
        self.error = error

    def get_accessible_document_ids(self, employee_id):
        if self.error:
            raise self.error
        return self.document_ids


class StubRetrieval:
    def __init__(self, evidence=None):
        self.evidence = evidence or []
        self.called_with = None

    def retrieve(self, query_text, top_k=None, document_ids=None):
        self.called_with = {"query": query_text, "top_k": top_k, "document_ids": document_ids}
        return [dict(item) for item in self.evidence]


class StubQueryResolver:
    def resolve(self, question, conversation_history=None):
        return question


class StubLLM:
    def __init__(self):
        self.messages = None

    def generate(self, messages):
        self.messages = messages
        return "Synthesized answer."


class StubProvenance:
    def build_citations(self, evidence):
        return evidence


def _evidence(text, document_id):
    return {
        "text": text,
        "metadata": {"document_id": document_id},
        "distance": 0.1,
    }


def _orchestrator(retrieval, authorization, **kwargs):
    return QueryOrchestrator(
        retrieval=retrieval,
        provenance=StubProvenance(),
        llm=StubLLM(),
        query_resolver=StubQueryResolver(),
        authorization=authorization,
    )


def test_answer_with_no_employee_id_returns_no_access_message():
    orch = _orchestrator(StubRetrieval(), StubAuthorization())
    result = orch.answer("question", employee_id=None)
    assert result["answer"] == NO_ACCESS_MESSAGE
    assert result["citations"] == []


def test_answer_raises_authorization_error_as_no_access():
    orch = _orchestrator(
        StubRetrieval(),
        StubAuthorization(error=AuthorizationError("missing")),
    )
    result = orch.answer("question", employee_id="MSS999")
    assert result["answer"] == NO_ACCESS_MESSAGE


def test_answer_with_no_accessible_documents_returns_no_access():
    retrieval = StubRetrieval()
    orch = _orchestrator(retrieval, StubAuthorization(document_ids=[]))
    result = orch.answer("question", employee_id="MSS001")
    assert result["answer"] == NO_ACCESS_MESSAGE
    assert retrieval.called_with is None


def test_answer_without_evidence_returns_no_relevant_message():
    retrieval = StubRetrieval(evidence=[])
    orch = _orchestrator(
        retrieval,
        StubAuthorization(document_ids=["DOC001"]),
    )
    result = orch.answer("question", employee_id="MSS001")
    assert result["answer"] == NO_RELEVANT_MESSAGE
    assert retrieval.called_with["document_ids"] == ["DOC001"]


def test_retrieval_is_restricted_to_authorized_documents():
    retrieval = StubRetrieval(evidence=[_evidence("hello", "DOC001")])
    orch = _orchestrator(
        retrieval,
        StubAuthorization(document_ids=["DOC001", "DOC002"]),
    )
    orch.answer("question", employee_id="MSS001")
    assert retrieval.called_with["document_ids"] == ["DOC001", "DOC002"]


def test_unauthorized_chunk_is_never_sent_to_llm():
    retrieval = StubRetrieval(
        evidence=[
            _evidence("authorized content", "DOC001"),
            _evidence("leaked secret", "DOC099"),
        ]
    )
    orch = _orchestrator(
        retrieval,
        StubAuthorization(document_ids=["DOC001"]),
    )
    result = orch.answer("question", employee_id="MSS001")
    # The leaked chunk must be filtered before the LLM context is assembled.
    assert "leaked secret" not in result["context"]
    assert "authorized content" in result["context"]
    assert orch.llm.messages[1]["content"] == (
        "Document context:\n\n"
        "authorized content\n\n"
        "Question: question"
    )


def test_all_evidence_filtered_returns_no_relevant_message():
    retrieval = StubRetrieval(
        evidence=[_evidence("leaked secret", "DOC099")]
    )
    orch = _orchestrator(
        retrieval,
        StubAuthorization(document_ids=["DOC001"]),
    )
    result = orch.answer("question", employee_id="MSS001")
    assert result["answer"] == NO_RELEVANT_MESSAGE
    assert orch.llm.messages is None