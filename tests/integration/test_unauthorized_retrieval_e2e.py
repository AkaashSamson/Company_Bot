from app.use_cases.chat.retrieval_service import RetrievalService


class RecordingStore:
    def __init__(self):
        self.project_filters = []

    def query(self, query_text, top_k=3, project_ids=None):
        self.project_filters.append(project_ids)
        return []


def test_retrieval_receives_only_authorized_project_ids():
    store = RecordingStore()
    retrieval = RetrievalService.__new__(RetrievalService)
    retrieval.store = store

    assert retrieval.retrieve("question", authorized_project_ids=["p1"]) == []
    assert store.project_filters == [["p1"]]


def test_empty_authorized_set_does_not_call_vector_store():
    store = RecordingStore()
    retrieval = RetrievalService.__new__(RetrievalService)
    retrieval.store = store

    assert retrieval.retrieve("question", authorized_project_ids=[]) == []
    assert store.project_filters == []
