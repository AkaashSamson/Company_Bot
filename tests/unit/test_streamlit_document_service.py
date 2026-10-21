from unittest.mock import MagicMock, patch
import os
from streamlit_app.services.document_service import DocumentService


def test_document_service_create_document_has_no_timeout_by_default():
    service = DocumentService(base_url="http://127.0.0.1:8000", token="test-token")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"document_id": "DOC-1"}

    with patch("requests.post", return_value=mock_resp) as mock_post:
        with patch.dict(os.environ, {}, clear=True):
            res = service.create_document({"document_name": "test.docx"})

    assert res == {"document_id": "DOC-1"}
    mock_post.assert_called_once_with(
        "http://127.0.0.1:8000/api/documents",
        json={"document_name": "test.docx"},
        headers={"Authorization": "Bearer test-token"},
        timeout=None,
    )


def test_document_service_create_document_respects_custom_timeout_env():
    service = DocumentService(base_url="http://127.0.0.1:8000", token="test-token")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"document_id": "DOC-2"}

    with patch("requests.post", return_value=mock_resp) as mock_post:
        with patch.dict(os.environ, {"DOCUMENT_UPLOAD_TIMEOUT": "600"}):
            res = service.create_document({"document_name": "test.docx"})

    assert res == {"document_id": "DOC-2"}
    mock_post.assert_called_once_with(
        "http://127.0.0.1:8000/api/documents",
        json={"document_name": "test.docx"},
        headers={"Authorization": "Bearer test-token"},
        timeout=600.0,
    )
