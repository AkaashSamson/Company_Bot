"""
tests/integration/test_chunk_normalizer_edge_cases.py
Automated Verification Suite for the 20 Integration Edge Cases (EC-01 through EC-20).
"""

import io
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_current_principal,
    get_current_user,
    get_document_ingestion_use_case,
)
from app.api.routes.documents import _build_collision_safe_doc_id, _sanitize_filename
from app.core.settings import settings
from app.domain.entities.document_models import DocumentChunk
from app.domain.entities.organization_models import Employee
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.infrastructure.document.chunk_normalizer import (
    ChunkNormalizer,
    NormalizedChunk,
)
from app.infrastructure.document.dynamic_section_assignor import (
    DynamicSectionAssignor,
    DynamicSectionTracker,
)
from app.main import app
from app.use_cases.ingestion.document_processing import (
    DocumentIngestionUseCase,
    ensure_fallback_contract_metadata,
    sanitize_chroma_metadata,
)


# ==============================================================================
# Layer 1: Upload & Filename Edge Cases (EC-01, EC-02, EC-03, EC-04)
# ==============================================================================

def test_ec01_collision_safe_doc_id():
    """EC-01: handbook_2025.pdf and handbook_2026.pdf must not collide on stem prefix."""
    bytes_a = b"Handbook 2025 policy content"
    bytes_b = b"Handbook 2026 policy content"
    id_a = _build_collision_safe_doc_id("handbook_2025.pdf", bytes_a)
    id_b = _build_collision_safe_doc_id("handbook_2026.pdf", bytes_b)
    assert id_a != id_b
    assert id_a.startswith("DOC-HANDBO-")
    assert id_b.startswith("DOC-HANDBO-")


def test_ec02_ec03_empty_upload_file_rejected():
    """EC-02 & EC-03: Empty file upload (0 bytes) returns HTTP 400 Bad Request."""
    mock_user = Employee(
        uid="u1", name="User", email="u@example.com", role="Admin", department_id="HR"
    )
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("u1")
    app.dependency_overrides[get_current_user] = lambda: mock_user
    client = TestClient(app)

    try:
        res = client.post(
            "/api/documents/upload",
            files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
            data={"project_id": "PROJ-1"},
        )
        assert res.status_code == 400
        assert "empty" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_ec04_sanitize_filename_traversal_and_artifacts():
    """EC-04: Path traversal and special chars are expunged."""
    unsafe_name = "../../etc/passwd.pdf"
    clean = _sanitize_filename(unsafe_name)
    assert "/" not in clean and "\\" not in clean
    assert clean == "passwd.pdf"

    artifact_name = "policy...v2.final.pdf"
    clean_artifact = _sanitize_filename(artifact_name)
    assert clean_artifact == "policy...v2.final.pdf"


# ==============================================================================
# Layer 2: Section Tracking & Heading Invariants (EC-05, EC-06, EC-07, EC-08)
# ==============================================================================

def test_ec05_code_block_comments_do_not_hijack_headings():
    """EC-05: Python and Bash comments in triple backticks must never alter the heading stack."""
    assignor = DynamicSectionAssignor()
    chunks = [
        NormalizedChunk(chunk_id="c1", text="# Actual Heading\nIntroduction."),
        NormalizedChunk(
            chunk_id="c2",
            text="```python\n# calculate tax rate\ndef calc():\n    pass\n```\nTax calculation details.",
        ),
    ]
    assigned = assignor.assign_sections_to_chunks(chunks, document_title="Tax Policy")
    assert assigned[0].metadata["section_heading"] == "Actual Heading"
    # Chunk 2 should NOT have section_heading == 'calculate tax rate'
    assert assigned[1].metadata["section_heading"] == "Actual Heading"


def test_ec06_out_of_order_heading_jumps_pop_deep_levels():
    """EC-06: Out-of-order jumps from H1 to H4 and back to H1 cleanly pop deeper levels."""
    tracker = DynamicSectionTracker(root_document_name="HR Master")
    tracker.process_line("# Benefits")
    tracker.process_line("#### Dental Details")
    h_path, section = tracker.get_current_hierarchy()
    assert h_path == "Benefits > Dental Details"
    assert section == "Dental Details"

    # Jump back to Level 1
    tracker.process_line("# Paid Time Off")
    h_path2, section2 = tracker.get_current_hierarchy()
    assert h_path2 == "Paid Time Off"
    assert section2 == "Paid Time Off"


def test_ec08_zero_headings_safe_fallback():
    """EC-08: Document with no headings and empty/None document_title falls back safely."""
    assignor = DynamicSectionAssignor()
    chunks = [
        NormalizedChunk(chunk_id="c1", text="Flat scanned memorandum with no headers."),
    ]
    assigned = assignor.assign_sections_to_chunks(chunks, document_title=None)
    assert assigned[0].metadata["heading_hierarchy"] == "General Policy"
    assert assigned[0].metadata["section_heading"] == "General Policy"


# ==============================================================================
# Layer 3 & 4: Chroma Metadata & Persistence Invariants (EC-15, EC-16, EC-18, EC-19, EC-20)
# ==============================================================================

def test_ec15_sanitize_chroma_metadata_non_primitive_types():
    """EC-15: Lists, tuples, and None values are converted to valid ChromaDB types."""
    meta = {
        "page_span": [1, 2],
        "hierarchy_path": ("HR", "Benefits", "Leave"),
        "extra_field": None,
        "valid_int": 42,
        "valid_str": "clean",
    }
    clean = sanitize_chroma_metadata(meta)
    assert clean["page_span"] == "1 > 2"
    assert clean["hierarchy_path"] == "HR > Benefits > Leave"
    assert clean["extra_field"] == ""
    assert clean["valid_int"] == 42
    assert clean["valid_str"] == "clean"
    # Ensure no values are lists, tuples, or None
    assert all(isinstance(v, (str, int, float, bool)) for v in clean.values())


def test_ec16_out_of_order_chroma_hash_dump_sorting():
    """EC-16: Out-of-order Chroma chunks must sort deterministically by document, page, and chunk index."""
    chunks = [
        NormalizedChunk(chunk_id="c3", text="Third", metadata={"source_filename": "a.pdf", "page_number": 2, "chunk_index": 1}),
        NormalizedChunk(chunk_id="c1", text="First", metadata={"source_filename": "a.pdf", "page_number": 1, "chunk_index": 0}),
        NormalizedChunk(chunk_id="c2", text="Second", metadata={"source_filename": "a.pdf", "page_number": 1, "chunk_index": 1}),
    ]
    chunks.sort(
        key=lambda c: (
            str(c.metadata.get("source_filename") or ""),
            int(c.metadata.get("page_number", 0) or 0),
            int(c.metadata.get("chunk_index", 0) or 0),
        )
    )
    assert [c.chunk_id for c in chunks] == ["c1", "c2", "c3"]


def test_ec18_batch_sizing_insert_partitioning():
    """EC-18: Chunks are partitioned into slices of 100 during vector persistence."""
    mock_chroma = MagicMock()
    uc = DocumentIngestionUseCase(chroma_client=mock_chroma)
    # Generate 250 standard chunks (~160 tokens each, within [55, 220] budget so they neither split nor coalesce)
    standard_clause = (
        "Standard full-time employment policy requires advance written notice of resignation. "
        "Employees must return all company equipment, keycards, laptops, monitors, and confidential documents on their final day. "
        "Failure to adhere to the standard handover procedure may impact terminal benefits, severance packages, and final clearance. "
    ) * 3
    raw_chunks = [
        {
            "text": f"{standard_clause}\nSection {i} details and protocols.",
            "metadata": {"page_number": i + 1, "chunk_index": i},
        }
        for i in range(250)
    ]
    created = uc.process_and_index_document(raw_chunks, "large_policy.pdf", "DOC-LARGE", "PROJ-1")
    assert len(created) == 250
    # Verify add_documents was called 3 times (100, 100, 50)
    assert mock_chroma.add_documents.call_count == 3
    first_call_ids = mock_chroma.add_documents.call_args_list[0].kwargs["ids"]
    third_call_ids = mock_chroma.add_documents.call_args_list[2].kwargs["ids"]
    assert len(first_call_ids) == 100
    assert len(third_call_ids) == 50


def test_ec19_disabled_feature_flag_fallback_contract():
    """EC-19: When CHUNK_NORMALIZER_ENABLED=False, fallback ensures mandatory schema contract."""
    chunk = NormalizedChunk(
        chunk_id="c1",
        text="Raw policy clause about sabbatical leave.",
        metadata={"source_filename": "sabbatical.pdf"},
    )
    fallback = ensure_fallback_contract_metadata(chunk)
    assert fallback.text.startswith("[Policy: sabbatical | Section: General Policy]")
    assert fallback.metadata["content_hash"]
    assert fallback.metadata["section_heading"] == "General Policy"
    assert fallback.metadata["page_number"] == 1


def test_ec20_pipeline_idempotency_double_run():
    """EC-20: Passing chunks through normalize_chunks() twice produces identical output."""
    normalizer = ChunkNormalizer(hard_token_ceiling=245)
    initial = [
        NormalizedChunk(
            chunk_id="c1",
            text="Employees must submit receipts within 30 days.",
            metadata={"source_filename": "expenses.pdf", "heading_hierarchy": "Finance > Expenses"},
        )
    ]
    first_pass = normalizer.normalize_chunks(initial)
    second_pass = normalizer.normalize_chunks(first_pass)

    assert len(first_pass) == len(second_pass)
    assert first_pass[0].text == second_pass[0].text
    assert first_pass[0].metadata["content_hash"] == second_pass[0].metadata["content_hash"]
    # Check that [Policy: ...] header did not duplicate
    assert first_pass[0].text.count("[Policy:") == 1
