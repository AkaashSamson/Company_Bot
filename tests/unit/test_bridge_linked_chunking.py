"""
Unit tests for Bridge-Linked Chunk Architecture (BLCA)
======================================================
Tests that all chunk strategies and the ingestion step link chunks into
a Doubly Linked List with typed boundary bridges.
"""

import base64
import pytest

from app.domain.entities.organization_models import Document
from app.infrastructure.document.bridge_linked_chunking import (
    BridgeType,
    detect_boundary_bridge,
    link_chunk_records_into_linked_list,
    link_store_records_with_bridges,
)
from app.infrastructure.document.chunking_strategies import (
    CHUNK_STRATEGIES_META,
    apply_chunking_strategy,
)
from app.infrastructure.ingestion.provisioner import provision_document


SAMPLE_POLICY_DOC = """
# Annual Leave Carry-Forward Policy

## 1. General Entitlement and Rules
Employees in full-time employment may carry forward up to five days of unused annual leave into the subsequent calendar year.

## 2. Managerial Approval Conditions
This is permitted only with manager approval before 31 December. Failing which, unused leave days are forfeited.

## 3. Operational HR Recording Procedure
The approved carry-forward must be recorded in the HR system within 14 calendar days of approval.
"""


def test_detect_boundary_bridge_qualifies():
    """Chunk B begins with conditional exception modifying rule in Chunk A."""
    rule_chunk = "Employees may carry forward up to five days of unused annual leave."
    condition_chunk = "This is permitted only with manager approval before 31 December."

    bridge = detect_boundary_bridge(rule_chunk, condition_chunk, doc_id="LEAVE", id_a="A", id_b="B")
    assert bridge.relationship == BridgeType.QUALIFIES.value
    assert bridge.confidence >= 0.90
    assert "manager approval" in bridge.boundary_span or "permitted" in bridge.rationale.lower()


def test_detect_boundary_bridge_procedure():
    """Chunk B begins with procedural recording step dependent on prior chunk."""
    condition_chunk = "Carry forward requires manager approval before 31 December."
    procedure_chunk = "The approved carry-forward must be recorded in the HR system within 14 days."

    bridge = detect_boundary_bridge(condition_chunk, procedure_chunk, doc_id="LEAVE", id_a="B", id_b="C")
    assert bridge.relationship == BridgeType.PROCEDURE_DEPENDENCY.value
    assert bridge.confidence >= 0.85


def test_detect_boundary_bridge_continues():
    """Chunk A ends with dangling punctuation/comma and Chunk B continues."""
    chunk_a = "The eligible departments include Engineering, Human Resources, and"
    chunk_b = "Finance operations across all regional offices."

    bridge = detect_boundary_bridge(chunk_a, chunk_b, doc_id="DEP", id_a="C1", id_b="C2")
    assert bridge.relationship == BridgeType.CONTINUES.value
    assert bridge.confidence >= 0.95


def test_all_chunking_strategies_generate_linked_list_with_bridges():
    """Verify that every single strategy in CHUNK_STRATEGIES_META generates linked-list pointers and bridges."""
    for strategy_key, meta in CHUNK_STRATEGIES_META.items():
        chunks = apply_chunking_strategy(
            strategy_key=strategy_key,
            text=SAMPLE_POLICY_DOC,
            target_tokens=35,  # Small target to ensure multiple chunks are created
            overlap_pct=0,
            doc_prefix="TEST",
            enable_bridge_links=True,
        )

        assert len(chunks) >= 2, f"Strategy {strategy_key} should have produced at least 2 chunks"

        # Check Doubly Linked List continuity
        for idx, chunk in enumerate(chunks):
            assert chunk.sequence_index == idx
            if idx == 0:
                assert chunk.previous_chunk_id is None
            else:
                assert chunk.previous_chunk_id == chunks[idx - 1].id

            if idx == len(chunks) - 1:
                assert chunk.next_chunk_id is None
            else:
                assert chunk.next_chunk_id == chunks[idx + 1].id
                assert chunk.bridge_to_next is not None
                assert "relationship" in chunk.bridge_to_next
                assert "confidence" in chunk.bridge_to_next
                assert chunk.bridge_to_next["source_chunk_id"] == chunk.id
                assert chunk.bridge_to_next["target_chunk_id"] == chunks[idx + 1].id

            # Verify metadata contract
            assert chunk.metadata["sequence_index"] == idx
            assert chunk.metadata["previous_chunk_id"] == chunk.previous_chunk_id
            assert chunk.metadata["next_chunk_id"] == chunk.next_chunk_id


def test_link_store_records_with_bridges():
    """Verify link_store_records_with_bridges on store dictionaries."""
    records = [
        {"id": "doc-0", "text": "Employees may carry forward up to 5 days of leave.", "metadata": {}},
        {"id": "doc-1", "text": "This is permitted only with manager approval before 31 December.", "metadata": {}},
        {"id": "doc-2", "text": "The approved carry-forward must be recorded in the HR system.", "metadata": {}},
    ]
    linked = link_store_records_with_bridges(records, doc_id="doc")

    assert len(linked) == 3
    # Check node 0
    assert linked[0]["metadata"]["sequence_index"] == 0
    assert linked[0]["metadata"]["previous_chunk_id"] is None
    assert linked[0]["metadata"]["next_chunk_id"] == "doc-1"
    assert linked[0]["metadata"]["bridge_type"] == BridgeType.QUALIFIES.value

    # Check node 1
    assert linked[1]["metadata"]["sequence_index"] == 1
    assert linked[1]["metadata"]["previous_chunk_id"] == "doc-0"
    assert linked[1]["metadata"]["next_chunk_id"] == "doc-2"
    assert linked[1]["metadata"]["bridge_type"] == BridgeType.PROCEDURE_DEPENDENCY.value

    # Check node 2
    assert linked[2]["metadata"]["sequence_index"] == 2
    assert linked[2]["metadata"]["previous_chunk_id"] == "doc-1"
    assert linked[2]["metadata"]["next_chunk_id"] is None


class MockVectorStore:
    def __init__(self):
        self.records = []

    def add_documents(self, records):
        self.records.extend(records)


def test_provision_document_with_strategy_and_bridges(tmp_path, monkeypatch):
    """Test ingestion step: provision_document with a strategy applies bridge linking."""
    import app.infrastructure.ingestion.provisioner as provisioner_mod
    monkeypatch.setattr(provisioner_mod, "DOCUMENTS_DIR", str(tmp_path))

    store = MockVectorStore()
    doc = Document("doc-strat-test", "Policy.txt", project_id="proj-123")
    content = base64.b64encode(SAMPLE_POLICY_DOC.encode("utf-8")).decode("utf-8")

    # Ingest using semantic_paragraph strategy
    chunk_count = provision_document(
        source_path=None,
        document=doc,
        content=content,
        store=store,
        chunking_strategy="semantic_paragraph",
        target_tokens=40,
        enable_bridge_linking=True,
    )

    assert chunk_count >= 2
    assert len(store.records) == chunk_count

    # Check that stored records have linked list and bridge metadata
    first_rec = store.records[0]
    assert first_rec["metadata"]["previous_chunk_id"] is None
    assert first_rec["metadata"]["next_chunk_id"] is not None
    assert "bridge_type" in first_rec["metadata"]
    assert first_rec["metadata"]["sequence_index"] == 0

    second_rec = store.records[1]
    assert second_rec["metadata"]["previous_chunk_id"] == first_rec["id"]
    assert second_rec["metadata"]["sequence_index"] == 1
