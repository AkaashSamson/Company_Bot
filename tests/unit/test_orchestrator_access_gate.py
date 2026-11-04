"""Unit tests: QueryOrchestrator emits a safe access-request response when
relevant content exists only outside the authorized scope, without ever
invoking the LLM with unauthorized evidence.
"""
from app.domain.services.authorization_engine import AuthorizationScope
from app.use_cases.chat.query_orchestrator import QueryOrchestrator


def _result(text, distance=0.2):
    return {"text": text, "distance": distance, "metadata": {}}


class FakeProvenance:
    def build_citations(self, results):
        return [{"text": item["text"]} for item in results]


class FakeLLM:
    def __init__(self):
        self.messages = None

    def generate(self, messages):
        self.messages = messages
        return "10 days per year."


class FixedResolver:
    def resolve(self, question, history):
        return "resolution of the question"


class ProbingRetrieval:
    def __init__(self, evidence=None, probe_hits=None):
        self.evidence = evidence or []
        self.probe_hits = probe_hits or []
        self.probe_calls = []

    def retrieve(self, question, top_k=5, **kwargs):
        return list(self.evidence)

    def detect_unauthorized_relevance(self, query_text, **kwargs):
        self.probe_calls.append((query_text, kwargs))
        return [dict(h) for h in self.probe_hits]


def _orchestrator(retrieval, contact_lookup=None, llm=None):
    return QueryOrchestrator(
        retrieval=retrieval,
        provenance=FakeProvenance(),
        llm=llm or FakeLLM(),
        query_resolver=FixedResolver(),
        project_contact_lookup=contact_lookup,
    )


def test_safe_response_when_unauthorized_project_hit_with_contact():
    llm = FakeLLM()
    retrieval = ProbingRetrieval(
        evidence=[],
        probe_hits=[{
            "project_id": "p2",
            "document_id": "docB",
            "source": "ProjectB_Policy.txt",
            "distance": 0.3,
        }],
    )
    result = _orchestrator(
        retrieval,
        contact_lookup=lambda project_id: {
            "project_id": "p2",
            "project_name": "Project Atlas",
            "manager_name": "Sara Blake",
        },
        llm=llm,
    ).answer(
        "What is the annual leave policy?",
        authorized_project_ids=["p1"],
    )

    assert "do not currently have access to" in result["answer"]
    assert "Project Atlas" in result["answer"]
    assert "Sara Blake" in result["answer"]
    assert result["citations"] == []
    assert llm.messages is None


def test_safe_response_uses_resolved_retrieval_query_for_probe():
    retrieval = ProbingRetrieval(
        evidence=[],
        probe_hits=[{"project_id": "p2", "document_id": "docB", "distance": 0.3}],
    )
    _orchestrator(retrieval).answer("Follow up?", authorized_project_ids=["p1"])

    assert retrieval.probe_calls[0][0] == "resolution of the question"


def test_safe_response_passes_scope_to_probe():
    retrieval = ProbingRetrieval(
        evidence=[],
        probe_hits=[{"project_id": "p2", "document_id": "docB", "distance": 0.3}],
    )
    scope = AuthorizationScope(
        is_admin=False,
        project_ids=["p1"],
        document_ids=["docG"],
        include_unassigned=False,
    )
    _orchestrator(retrieval).answer("What is the annual leave policy?", authorization_scope=scope)

    kwargs = retrieval.probe_calls[0][1]
    assert kwargs["authorized_project_ids"] == ["p1"]
    assert kwargs["authorized_document_ids"] == ["docG"]
    assert kwargs["include_unassigned"] is False


def test_generic_safe_response_when_no_contact_resolution():
    llm = FakeLLM()
    retrieval = ProbingRetrieval(
        evidence=[],
        probe_hits=[{"project_id": None, "document_id": "docU", "distance": 0.3}],
    )
    result = _orchestrator(retrieval, contact_lookup=None, llm=llm).answer(
        "What is the annual leave policy?",
        authorized_project_ids=["p1"],
    )

    assert "do not currently have access to" in result["answer"]
    assert result["citations"] == []
    assert llm.messages is None


def test_not_found_when_probe_has_no_hits():
    llm = FakeLLM()
    retrieval = ProbingRetrieval(evidence=[], probe_hits=[])
    result = _orchestrator(retrieval, llm=llm).answer(
        "Who is the prime minister?",
        authorized_project_ids=["p1"],
    )

    assert "could not find" in result["answer"].lower()
    assert result["citations"] == []
    assert llm.messages is None


def test_not_found_when_retrieval_has_no_probe_capability():
    llm = FakeLLM()

    class BareRetrieval:
        def retrieve(self, question, top_k=5, **kwargs):
            return []

    result = _orchestrator(BareRetrieval(), llm=llm).answer(
        "Who is the prime minister?",
        authorized_project_ids=["p1"],
    )

    assert "could not find" in result["answer"].lower()
    assert result["citations"] == []
    assert llm.messages is None


def test_authorized_evidence_path_passes_through_unaffected():
    llm = FakeLLM()
    retrieval = ProbingRetrieval(
        evidence=[_result("annual leave is ten days")],
        probe_hits=[{"project_id": "p2", "document_id": "docB", "distance": 0.3}],
    )
    result = _orchestrator(retrieval, llm=llm).answer(
        "What is the annual leave policy?",
        authorized_project_ids=["p1"],
    )

    assert ("Sick leave" in result["answer"]) or "10 days per year." in result["answer"]
    assert result["citations"] == [{"text": "annual leave is ten days"}]
    assert llm.messages is not None
    assert retrieval.probe_calls == []


def test_admin_scope_never_triggers_probe_or_safe_response():
    llm = FakeLLM()
    retrieval = ProbingRetrieval(evidence=[_result("annual leave is ten days")])
    scope = AuthorizationScope(is_admin=True)
    result = _orchestrator(retrieval, llm=llm).answer(
        "What is the annual leave policy?",
        authorization_scope=scope,
    )

    assert "do not currently have access to" not in result["answer"]
    assert retrieval.probe_calls == []


def test_safe_response_is_deterministic_without_llm_when_only_unauthorized_content():
    llm = FakeLLM()
    retrieval = ProbingRetrieval(
        evidence=[],
        probe_hits=[{"project_id": "p99", "document_id": "docX", "distance": 0.2}],
    )
    result = _orchestrator(retrieval, llm=llm).answer(
        "What is the confidential plan?",
        authorized_project_ids=[],
    )
    assert llm.messages is None
    assert "confidential plan" not in result["answer"]
    assert result["citations"] == []