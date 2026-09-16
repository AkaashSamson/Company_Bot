"""Unit tests for RetrievalService.detect_unauthorized_relevance.

The probe must find relevant content outside the principal's authorized scope
while never returning document text or full metadata.
"""
from app.use_cases.chat.retrieval_service import RetrievalService


def _candidate(
    text,
    distance,
    project_id="p2",
    document_id="docx",
    source="unknown.txt",
    section=None,
):
    metadata = {
        "document_id": document_id,
        "project_id": project_id,
        "source": source,
    }
    if section is not None:
        metadata["section"] = section
    return {"text": text, "distance": distance, "metadata": metadata}


class StubStore:
    def __init__(self, candidates):
        self.candidates = candidates

    def query(self, query_text, top_k=5, **kwargs):
        return list(self.candidates)


def _svc_with(candidates):
    svc = RetrievalService.__new__(RetrievalService)
    svc.store = StubStore(candidates)
    return svc


QUERY = "annual leave policy"


def test_probe_hits_only_redacted_fields_never_text():
    hit = _candidate(
        "annual leave is the confidential caboodle number",
        distance=0.31,
        project_id="p2",
        document_id="docB",
        source="ProjectB_Policy.txt",
    )
    svc = _svc_with([hit])
    hits = svc.detect_unauthorized_relevance(QUERY, authorized_project_ids=["p1"], include_unassigned=False)

    assert hits == [
        {
            "project_id": "p2",
            "document_id": "docB",
            "source": "ProjectB_Policy.txt",
            "section": None,
            "distance": 0.31,
        }
    ]
    assert all("text" not in h and "metadata" not in h for h in hits)


def test_probe_skips_documents_in_authorized_projects():
    hit = _candidate("annual leave is ten days", distance=0.2, project_id="p1", document_id="docA")
    svc = _svc_with([hit])
    hits = svc.detect_unauthorized_relevance(QUERY, authorized_project_ids=["p1"], include_unassigned=False)
    assert hits == []


def test_probe_skips_documents_covered_by_explicit_document_grant():
    hit = _candidate("annual leave is ten days", distance=0.2, project_id="p2", document_id="docB")
    svc = _svc_with([hit])
    hits = svc.detect_unauthorized_relevance(
        QUERY,
        authorized_project_ids=["p1"],
        authorized_document_ids=["docB"],
        include_unassigned=False,
    )
    assert hits == []


def test_probe_respects_include_unassigned_flag():
    unassigned = _candidate("annual leave applies globally", distance=0.25, project_id=None)

    svc = _svc_with([unassigned])
    assert svc.detect_unauthorized_relevance(QUERY, authorized_project_ids=["p1"], include_unassigned=True) == []
    hits = svc.detect_unauthorized_relevance(QUERY, authorized_project_ids=["p1"], include_unassigned=False)
    assert hits and hits[0]["project_id"] is None


def test_probe_rejects_candidates_beyond_distance_threshold():
    weak = _candidate("annual leave blurry text", distance=0.95, project_id="p2", document_id="docB")
    svc = _svc_with([weak])
    hits = svc.detect_unauthorized_relevance(QUERY, authorized_project_ids=["p1"], include_unassigned=False)
    assert hits == []


def test_probe_requires_lexical_grounding():
    unrelated = _candidate("the manticore departs at dawn", distance=0.1, project_id="p2", document_id="docB")
    svc = _svc_with([unrelated])
    hits = svc.detect_unauthorized_relevance(QUERY, authorized_project_ids=["p1"], include_unassigned=False)
    assert hits == []


def test_probe_returns_empty_for_unrestricted_scope():
    hit = _candidate("annual leave is ten days", distance=0.2, project_id="p2", document_id="docB")
    svc = _svc_with([hit])
    assert svc.detect_unauthorized_relevance(QUERY, authorized_project_ids=None) == []


def test_probe_sorts_hits_by_distance_ascending():
    far = _candidate("annual leave paperwork guidelines", distance=0.55, project_id="p2", document_id="docF")
    near = _candidate("annual leave is exactly twenty lunar months", distance=0.2, project_id="p3", document_id="docN")
    svc = _svc_with([far, near])

    hits = svc.detect_unauthorized_relevance(QUERY, authorized_project_ids=["p1"], include_unassigned=False)
    assert [h["document_id"] for h in hits] == ["docN", "docF"]


def test_probe_skips_candidate_missing_distance():
    hit = {"text": "annual leave is ten days", "metadata": {"document_id": "docB", "project_id": "p2"}}
    svc = _svc_with([hit])
    hits = svc.detect_unauthorized_relevance(QUERY, authorized_project_ids=["p1"], include_unassigned=False)
    assert hits == []


def test_probe_accepts_empty_authorized_project_scope_any_hit_is_unauthorized():
    hit = _candidate("annual leave is a confidential caboodle", distance=0.2, project_id="p2", document_id="docB")
    svc = _svc_with([hit])
    hits = svc.detect_unauthorized_relevance(QUERY, authorized_project_ids=[], include_unassigned=False)
    assert len(hits) == 1
    assert hits[0]["project_id"] == "p2"