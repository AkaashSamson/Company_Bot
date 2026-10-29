"""
Unit tests for Adaptive Hierarchical Bridge Chunking (AHBC)
===========================================================
Tests the 4 pillars of AHBC:
1. Adaptive Modality Router
2. Hierarchical Core Chunks (Child chunks linked to Parent section)
3. Selective Bridge Graph (Validated vs Candidate states)
4. Three-Tier Query-Aware Dynamic Context Assembly
"""

import pytest

from app.infrastructure.document.bridge_linked_chunking import (
    BridgeStatus,
    BridgeType,
    DocumentModality,
    assemble_query_aware_context,
    route_document_modality,
)
from app.infrastructure.document.chunking_strategies import (
    CHUNK_STRATEGIES_META,
    apply_chunking_strategy,
    chunk_adaptive_hierarchical_bridge,
)


SAMPLE_TABLE_DOC = """
| Department | Carry Forward Cap | Approval Required |
|---|---|---|
| Engineering | 5 Days | Manager |
| Operations | 5 Days | Director |
| Finance | 3 Days | VP Finance |
| Human Resources | 7 Days | Head of HR |
"""

SAMPLE_CODE_DOC = """
def calculate_leave_balance(employee_id: str, requested_days: int) -> bool:
    # Check carry-forward policy rules
    balance = get_employee_balance(employee_id)
    return balance >= requested_days
"""

SAMPLE_POLICY_DOC = """
# Annual Leave Carry-Forward Policy

## 1. General Entitlement and Rules
Employees in full-time employment may carry forward up to five days of unused annual leave into the subsequent calendar year.

## 2. Managerial Approval Conditions
This is permitted only with manager approval before 31 December. Failing which, unused leave days are forfeited.

## 3. Operational HR Recording Procedure
The approved carry-forward must be recorded in the HR system within 14 calendar days of approval.
"""


def test_adaptive_router_table_detection():
    modality, strat, rationale = route_document_modality(SAMPLE_TABLE_DOC)
    assert modality == DocumentModality.TABLE_DENSE
    assert strat == "document_section_broad"
    assert "Table-dense" in rationale


def test_adaptive_router_code_detection():
    modality, strat, rationale = route_document_modality(SAMPLE_CODE_DOC)
    assert modality == DocumentModality.CODE_OR_API
    assert strat == "sentence_window_small_to_big"


def test_adaptive_router_narrative_policy_detection():
    modality, strat, rationale = route_document_modality(SAMPLE_POLICY_DOC)
    assert modality == DocumentModality.HIERARCHICAL or modality == DocumentModality.NARRATIVE_PROSE


def test_ahbc_generates_hierarchical_parent_child_chunks():
    """Verify AHBC creates child chunks linked to parent section IDs and parent texts."""
    chunks = apply_chunking_strategy(
        strategy_key="adaptive_hierarchical_bridge",
        text=SAMPLE_POLICY_DOC,
        target_tokens=40,
        doc_prefix="AHBC-TEST",
        enable_bridge_links=True,
    )

    assert len(chunks) >= 3
    for idx, c in enumerate(chunks):
        assert c.strategy == "adaptive_hierarchical_bridge"
        assert c.parent_id is not None
        assert "AHBC-TEST-SEC" in c.parent_id
        assert c.parent_text is not None
        assert len(c.parent_text) >= len(c.text)

        # Doubly Linked List continuity
        assert c.sequence_index == idx
        if idx > 0:
            assert c.previous_chunk_id == chunks[idx - 1].id
        if idx < len(chunks) - 1:
            assert c.next_chunk_id == chunks[idx + 1].id
            assert c.bridge_to_next is not None
            assert c.bridge_to_next["status"] in {BridgeStatus.VALIDATED.value, BridgeStatus.CANDIDATE.value}


def test_three_tier_query_aware_context_assembly():
    """Verify 3-tier dynamic expansion:
    Tier 1 (Core Chunk) for normal questions.
    Tier 2 (Validated Bridge Expansion) when query asks for conditions/qualifications.
    Tier 3 (Parent Section Fallback) when needle is tiny and needs parent grounding.
    """
    chunk_a = {
        "id": "chunk-001",
        "text": "Employees may carry forward up to five days of unused annual leave.",
        "metadata": {
            "chunk_id": "chunk-001",
            "next_chunk_id": "chunk-002",
            "bridge_type": BridgeType.QUALIFIES.value,
            "bridge_status": BridgeStatus.VALIDATED.value,
            "parent_id": "SEC-01",
            "parent_text": "Section 1 Full Policy: Employees may carry forward up to five days of unused annual leave subject to standard guidelines.",
        },
    }
    chunk_b = {
        "id": "chunk-002",
        "text": "This is permitted only with manager approval before 31 December.",
        "metadata": {
            "chunk_id": "chunk-002",
            "previous_chunk_id": "chunk-001",
            "bridge_type": BridgeType.PROCEDURE_DEPENDENCY.value,
            "bridge_status": BridgeStatus.VALIDATED.value,
        },
    }

    lookup = {"chunk-001": chunk_a, "chunk-002": chunk_b}

    # Test Tier 2: Query asking about conditions triggers bridge expansion!
    res_tier2 = assemble_query_aware_context(
        retrieved_chunk=chunk_a,
        query="Under what condition is leave carry-forward permitted?",
        chunk_lookup=lookup,
    )
    assert res_tier2["tier"] == "tier_2_validated_bridge"
    assert "manager approval" in res_tier2["assembled_text"]
    assert "chunk-002" in res_tier2["provenance_chunks"]

    # Test Tier 1: General self-contained query without condition cues returns core
    chunk_standalone = {
        "id": "chunk-003",
        "text": "The company observes ten standard public holidays each calendar year across all corporate office locations.",
        "metadata": {
            "chunk_id": "chunk-003",
            "bridge_type": BridgeType.SEQUENTIAL.value,
            "bridge_status": BridgeStatus.CANDIDATE.value,
        },
    }
    res_tier1 = assemble_query_aware_context(
        retrieved_chunk=chunk_standalone,
        query="How many public holidays does the company observe?",
        chunk_lookup=lookup,
    )
    assert res_tier1["tier"] == "tier_1_core"
    assert res_tier1["assembled_text"] == chunk_standalone["text"]

    # Test Tier 3: Micro-needle fallback to parent section
    chunk_micro = {
        "id": "chunk-004",
        "text": "Standard rate: $45/hour.",
        "metadata": {
            "chunk_id": "chunk-004",
            "parent_id": "SEC-BILLING",
            "parent_text": "Billing Schedule: Standard contractor rate is $45/hour. Overtime after 40 hours is billed at 1.5x regular rate.",
        },
    }
    res_tier3 = assemble_query_aware_context(
        retrieved_chunk=chunk_micro,
        query="Tell me about the contractor billing terms.",
        chunk_lookup=lookup,
    )
    assert res_tier3["tier"] == "tier_3_parent_fallback"
    assert "Overtime after 40 hours" in res_tier3["assembled_text"]
