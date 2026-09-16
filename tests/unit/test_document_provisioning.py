import base64

import pytest

from app.domain.entities.organization_models import Document
from app.infrastructure.ingestion.provisioner import provision_document, _safe_document_id


def test_safe_document_id_sanitizes_dangerous_characters():
    safe = _safe_document_id("My;DROP TABLE\nPolicy..")
    assert ".." not in safe
    assert "/" not in safe
    assert safe.replace("_", "").strip()


def test_safe_document_id_rejects_empty_result():
    with pytest.raises(ValueError):
        _safe_document_id("///...")

def test_provision_document_rejects_unsupported_extension_before_vector_store():
    document = Document("doc-1", "Report.pdf")
    content = base64.b64encode(b"\x89PNG\r\n\x1a\nbinary image payload\x00\xff").decode("utf-8")
    with pytest.raises(ValueError):
        provision_document(None, document, content)


def test_provision_document_rejects_invalid_base64():
    document = Document("doc-1", "Notes.txt")
    with pytest.raises(ValueError):
        provision_document(None, document, "not-base64-!!!")


def test_provision_document_without_source_or_content_is_noop():
    document = Document("doc-legend", "Notes.txt")
    assert provision_document(None, document, None) == 0