from unittest.mock import MagicMock
from streamlit_app.services.document_service import DocumentService

def test_document_service_status_and_chunks():
    service = DocumentService(base_url="http://mock", token="test-token")
    service._get = MagicMock(side_effect=[
        {"document_id": "DOC-1", "status": "processing", "progress": None},
        [{"index": 0, "text": "chunk text", "metadata": {"page": 1}}]
    ])

    status = service.get_status("DOC-1")
    assert status["status"] == "processing"

    chunks = service.get_chunks("DOC-1")
    assert len(chunks) == 1
    assert chunks[0]["text"] == "chunk text"

def test_document_service_search_chunks_and_delete_permanent():
    service = DocumentService(base_url="http://mock", token="test-token")
    service._post = MagicMock(return_value=[{"id": "c1", "text": "match", "score": 0.9}])
    service._delete = MagicMock(return_value=True)

    results = service.search_chunks({"query": "test query", "top_k": 3})
    assert len(results) == 1
    assert results[0]["id"] == "c1"

    service.delete_document("DOC-1", permanent=True)
    service._delete.assert_called_once_with("/api/documents/DOC-1", params={"permanent": True})
