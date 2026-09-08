from app.use_cases.chat.retrieval_service import RetrievalService
from app.infrastructure.vector.chroma_client import ChromaVectorStore
from app.use_cases.chat.query_orchestrator import QueryOrchestrator


def result(text, distance):
    return {"text": text, "metadata": {}, "distance": distance}


def test_select_relevant_keeps_only_the_strong_result_after_distance_gap():
    candidates = [
        result("5.8 Sick Leave: Eligible employees receive 10 days per year.", 0.18),
        result("Sick Leave Carry-Forward: unused days may be carried forward.", 0.51),
        result("Medical Documentation: a certificate may be required.", 0.54),
    ]

    selected = RetrievalService.select_relevant("How many sick leaves do I have?", candidates)

    assert [item["text"] for item in selected] == [candidates[0]["text"]]


def test_select_relevant_retains_multiple_chunks_before_distance_gap():
    candidates = [
        result("Annual leave is 20 days per calendar year.", 0.20),
        result("Annual leave requests require manager approval.", 0.23),
        result("The office has a dress code policy.", 0.72),
    ]

    selected = RetrievalService.select_relevant("How much annual leave and how do I request it?", candidates)

    assert [item["text"] for item in selected] == [item["text"] for item in candidates[:2]]


def test_select_relevant_removes_duplicate_text_and_preserves_distance():
    candidates = [
        result("Sick leave is 10 days per year.", 0.2),
        result("Sick leave is 10 days per year.", 0.21),
    ]

    selected = RetrievalService.select_relevant("How many sick leaves?", candidates)

    assert len(selected) == 1
    assert selected[0]["distance"] == 0.2


def test_select_relevant_returns_empty_for_empty_candidates():
    assert RetrievalService.select_relevant("Any policy?", []) == []


def test_select_relevant_rejects_evidence_above_configured_distance_threshold():
    candidates = [result("Unrelated document content.", 0.61)]

    selected = RetrievalService.select_relevant(
        "A question about a different topic.",
        candidates,
        distance_threshold=0.60,
    )

    assert selected == []


def test_select_relevant_accepts_separated_top_result_slightly_above_threshold():
    candidates = [
        result("The requested entitlement is ten days per year.", 0.5267996788),
        result("A related carry-forward rule.", 0.6905689836),
        result("A weaker unrelated policy section.", 0.7123069763),
    ]

    selected = RetrievalService.select_relevant(
        "How many days are available?",
        candidates,
        distance_threshold=0.50,
        distance_relaxation=0.05,
        min_distance_gap=0.10,
    )

    assert [item["text"] for item in selected] == [candidates[0]["text"]]


def test_select_relevant_rejects_weak_top_result_without_a_clear_gap():
    candidates = [
        result("Weak candidate one.", 0.54),
        result("Weak candidate two.", 0.57),
        result("Weak candidate three.", 0.60),
    ]

    selected = RetrievalService.select_relevant(
        "An unrelated question.",
        candidates,
        distance_threshold=0.50,
        distance_relaxation=0.05,
        min_distance_gap=0.10,
    )

    assert selected == []


def test_select_relevant_rejects_irrelevant_separated_top_result():
    candidates = [
        result("An internal attendance passage.", 0.54),
        result("A benefits administration passage.", 0.70),
        result("A workplace conduct passage.", 0.82),
    ]

    selected = RetrievalService.select_relevant(
        "Who is the current Prime Minister of India?",
        candidates,
        distance_threshold=0.50,
        distance_relaxation=0.05,
        min_distance_gap=0.10,
    )

    assert selected == []


def test_relevance_threshold_and_relaxation_are_configurable():
    candidate = result("The policy provides relevant evidence.", 0.62)

    assert RetrievalService.select_relevant(
        "What does the policy provide?",
        [candidate],
        distance_threshold=0.60,
        distance_relaxation=0.01,
    ) == []
    assert RetrievalService.select_relevant(
        "What does the policy provide?",
        [candidate, result("Distant alternative.", 0.80)],
        distance_threshold=0.60,
        distance_relaxation=0.05,
        min_distance_gap=0.10,
    ) == [candidate]


def test_query_parts_preserve_meaningful_conjunction_phrases():
    assert RetrievalService._query_parts("Explain health and safety requirements") == [
        "Explain health and safety requirements",
    ]


def test_query_parts_split_explicit_multi_part_lists():
    assert RetrievalService._query_parts(
        "Explain eligibility, documentation, and approval requirements"
    ) == [
        "Explain eligibility, documentation, and approval requirements",
        "Explain eligibility",
        "documentation",
        "approval requirements",
    ]


def test_retrieve_queries_full_question_and_distinct_parts():
    class Store:
        def __init__(self):
            self.queries = []

        def query(self, query_text, top_k, where=None):
            self.queries.append(query_text)
            return [
                {
                    **result(f"Distinct section {len(self.queries)}", 0.2),
                    "metadata": {"document_id": "DOC001"},
                }
            ]

    service = RetrievalService.__new__(RetrievalService)
    service.store = Store()

    selected = service.retrieve(
        "Explain eligibility, documentation, and approval requirements.",
        top_k=2,
        max_evidence=3,
        document_ids=["DOC001"],
    )

    assert service.store.queries == [
        "Explain eligibility, documentation, and approval requirements.",
        "Explain eligibility",
        "documentation",
        "approval requirements.",
    ]
    assert len(selected) == 3
    assert [item["_query_part_index"] for item in selected] == [0, 1, 2]


def test_retrieve_fails_closed_without_document_ids():
    service = RetrievalService.__new__(RetrievalService)
    service.store = object()  # must never be reached

    assert service.retrieve("Why?", document_ids=None) == []
    assert service.retrieve("Why?", document_ids=[]) == []


def test_chroma_query_preserves_distance():
    class Embedding:
        def tolist(self):
            return [[0.1, 0.2]]

    store = ChromaVectorStore.__new__(ChromaVectorStore)
    store.embedding_model = type(
        "EmbeddingModel",
        (),
        {"encode": lambda self, texts, convert_to_numpy: Embedding()},
    )()
    store.collection = type(
        "Collection",
        (),
        {
            "query": lambda self, **kwargs: {
                "documents": [["Sick leave is 10 days per year."]],
                "metadatas": [[{"section": "Policy"}]],
                "distances": [[0.17]],
            }
        },
    )()

    results = store.query("How many sick leaves?", top_k=1)

    assert results[0]["distance"] == 0.17


class FakeRetrieval:
    def retrieve(self, question, top_k, document_ids=None):
        return [
            {
                **result("Sick leave is 10 days per year.", 0.2),
                "metadata": {"document_id": "DOC001"},
            }
        ]


class FakeProvenance:
    def build_citations(self, results):
        return [{"text": item["text"]} for item in results]


class FakeAuthorization:
    def get_accessible_document_ids(self, employee_id):
        return ["DOC001"]


class FakeLLM:
    def __init__(self):
        self.messages = None

    def generate(self, messages):
        self.messages = messages
        return "10 days per year."


def test_orchestrator_uses_same_selected_evidence_for_context_and_citations():
    llm = FakeLLM()
    result = QueryOrchestrator(
        retrieval=FakeRetrieval(),
        provenance=FakeProvenance(),
        llm=llm,
        authorization=FakeAuthorization(),
    ).answer("How many sick leaves?", employee_id="MSS001")

    assert result["citations"] == [{"text": "Sick leave is 10 days per year."}]
    assert "Sick leave is 10 days per year." in llm.messages[1]["content"]
    assert "Sick leave is 10 days per year." == result["context"]


class RecordingRetrieval:
    def __init__(self):
        self.query = None

    def retrieve(self, question, top_k, document_ids=None):
        self.query = question
        return [
            {
                **result("Carry-forward is described in the policy.", 0.2),
                "metadata": {"document_id": "DOC001"},
            }
        ]


class FixedResolver:
    def resolve(self, question, history):
        return "standalone carry-forward query"


def test_orchestrator_separates_retrieval_query_from_original_question():
    retrieval = RecordingRetrieval()
    llm = FakeLLM()
    QueryOrchestrator(
        retrieval=retrieval,
        provenance=FakeProvenance(),
        llm=llm,
        query_resolver=FixedResolver(),
        authorization=FakeAuthorization(),
    ).answer("What about carrying them forward?", conversation_history=[], employee_id="MSS001")

    assert retrieval.query == "standalone carry-forward query"
    assert "What about carrying them forward?" in llm.messages[1]["content"]


class EmptyRetrieval:
    def retrieve(self, question, top_k, document_ids=None):
        return []


def test_orchestrator_returns_fallback_without_citations_for_empty_retrieval():
    result = QueryOrchestrator(
        retrieval=EmptyRetrieval(),
        provenance=FakeProvenance(),
        llm=FakeLLM(),
        authorization=FakeAuthorization(),
    ).answer("Unknown policy?", employee_id="MSS001")

    assert result["citations"] == []
    assert "could not find" in result["answer"].lower()


class WeakRetrieval:
    def retrieve(self, question, top_k, document_ids=None):
        return RetrievalService.select_relevant(
            question,
            [result("An unrelated policy passage.", 0.9)],
        )


def test_orchestrator_rejects_out_of_domain_evidence_before_llm_context():
    llm = FakeLLM()
    result = QueryOrchestrator(
        retrieval=WeakRetrieval(),
        provenance=FakeProvenance(),
        llm=llm,
        authorization=FakeAuthorization(),
    ).answer("Who is the current Prime Minister of India?", employee_id="MSS001")

    assert result["citations"] == []
    assert "could not find" in result["answer"].lower()
    assert llm.messages is None