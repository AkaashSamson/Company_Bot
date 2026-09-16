from app.use_cases.chat.retrieval_service import RetrievalService


class RecordingStore:
    def __init__(self):
        self.project_filters = []

    def query(self, query_text, top_k=3, project_ids=None, where=None):
        self.project_filters.append(project_ids)
        return []


def test_retrieval_receives_authorized_project_ids_with_org_wide_scope():
    store = RecordingStore()
    retrieval = RetrievalService.__new__(RetrievalService)
    retrieval.store = store

    assert retrieval.retrieve("question", authorized_project_ids=["p1"]) == []
    assert store.project_filters == [["p1", "unassigned"]]


def test_empty_authorized_set_still_retrieves_organization_wide_documents():
    store = RecordingStore()
    retrieval = RetrievalService.__new__(RetrievalService)
    retrieval.store = store

    assert retrieval.retrieve("question", authorized_project_ids=[]) == []
    assert store.project_filters == [["unassigned"]]
