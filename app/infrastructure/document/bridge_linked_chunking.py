"""
Adaptive Hierarchical Bridge Chunking (AHBC)
============================================
Combines:
1. Adaptive Chunking Router (modality classification: tables, code, hierarchy, prose)
2. Hierarchical Core Chunks (granular child chunks linked to larger parent sections)
3. Selective Bridge Graph (ordered sequence + validated, typed semantic relationships)
4. Three-Tier Query-Aware Context Assembly (Core Chunk -> Validated Bridge -> Parent Fallback)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class BridgeType(str, Enum):
    """Semantic relationship types connecting adjacent chunks across boundaries."""
    CONTINUES = "continues"                     # Broken sentence, trailing punctuation, or lowercase continuation
    QUALIFIES = "qualifies"                     # Condition, caveat, or exception modifying prior rule
    DEFINES = "defines"                         # Term defined or elaborated across boundary
    PROCEDURE_DEPENDENCY = "procedure_dependency" # Step N depends on prior step or action recording
    TABLE_STRUCTURE = "table_structure"         # Table headers/rows split across chunks
    HEADING_CONTEXT = "heading_context"         # Heading provides the semantic context for adjacent body
    SEQUENTIAL = "sequential"                   # Standard narrative sequence


class BridgeStatus(str, Enum):
    """Validation lifecycle states for boundary bridges."""
    CANDIDATE = "candidate"     # Detected by heuristics but not yet validated
    VALIDATED = "validated"     # High-confidence, source-grounded link safe for retrieval expansion
    REJECTED = "rejected"       # Stale, ambiguous, or failed threshold


class DocumentModality(str, Enum):
    """Detected structural modality of the document."""
    TABLE_DENSE = "table_dense"
    CODE_OR_API = "code_or_api"
    HIERARCHICAL = "hierarchical"
    NARRATIVE_PROSE = "narrative_prose"


@dataclass
class BridgeLink:
    """Represents a directional relationship between two adjacent chunks."""
    bridge_id: str
    source_chunk_id: str
    target_chunk_id: str
    relationship: str
    confidence: float
    boundary_span: str
    rationale: str
    status: BridgeStatus = BridgeStatus.VALIDATED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bridge_id": self.bridge_id,
            "source_chunk_id": self.source_chunk_id,
            "target_chunk_id": self.target_chunk_id,
            "relationship": self.relationship,
            "confidence": round(self.confidence, 3),
            "boundary_span": self.boundary_span,
            "rationale": self.rationale,
            "status": self.status.value,
        }


# Regex patterns for deterministic boundary relationship classification
_QUALIFYING_PATTERNS = re.compile(
    r"^(this is permitted only|provided that|subject to|notwithstanding|"
    r"unless|except (where|as|when|for)|however|on the condition that|"
    r"only if|in the event that|with manager approval|under the condition|"
    r"this exception applies|conditional upon|failing which)",
    re.IGNORECASE,
)

_DEFINING_PATTERNS = re.compile(
    r"^(for the purpose[s]? of|defined as|means any|in this (section|policy|clause)|"
    r"the term [\"\'].*?[\"\'] refers to|refer[s]? to|specifically,|namely,)",
    re.IGNORECASE,
)

_PROCEDURAL_PATTERNS = re.compile(
    r"^(the approved|to record|this must be recorded|step \d+|then|afterwards|"
    r"subsequently|once approved|upon completion|the procedure for|following this|"
    r"in order to finalize|all records must be)",
    re.IGNORECASE,
)

_DANGLING_TAIL_PUNCTUATION = re.compile(r"[,;:\-—\(\[\"\']\s*$")
_DANGLING_CONJUNCTION = re.compile(
    r"\b(and|or|but|with|that|which|because|including|such as|for|to|of)\s*$",
    re.IGNORECASE,
)
_TABLE_ROW_PATTERN = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)


def route_document_modality(text: str) -> Tuple[DocumentModality, str, str]:
    """Inspects text layout and returns (DocumentModality, recommended_strategy, rationale)."""
    if not text or not text.strip():
        return DocumentModality.NARRATIVE_PROSE, "recursive_sliding_window", "Empty or minimal text."

    lines = text.strip().split("\n")
    total_lines = len(lines)

    # 1. Check for table density
    table_lines = sum(1 for line in lines if line.strip().startswith("|") and line.strip().endswith("|"))
    if total_lines > 4 and (table_lines / total_lines) >= 0.18:
        return (
            DocumentModality.TABLE_DENSE,
            "document_section_broad",
            f"Table-dense content detected ({table_lines}/{total_lines} rows). Requires preserving column headers.",
        )

    # 2. Check for code or API specifications
    code_indicators = sum(
        1 for line in lines if re.search(r"^\s*(def\s+|class\s+|curl\s+|import\s+|from\s+|{\s*$|public\s+|private\s+|return\s+|/\*|//)", line) or "->" in line
    )
    if "```" in text or code_indicators >= 2:
        return (
            DocumentModality.CODE_OR_API,
            "sentence_window_small_to_big",
            "Code/API signatures detected. Needs tight needle precision with surrounding context window.",
        )

    # 3. Check for Markdown / numbered hierarchy
    heading_count = sum(1 for line in lines if re.match(r"^(#{1,6}\s+|[0-9]+\.[0-9]+|\bArticle\b|\bSection\b)", line.strip()))
    if heading_count >= 2:
        return (
            DocumentModality.HIERARCHICAL,
            "structural_hierarchical",
            f"Structured outline detected ({heading_count} headings/articles). Preserves section breadcrumbs.",
        )

    # 4. Standard narrative prose
    return (
        DocumentModality.NARRATIVE_PROSE,
        "adaptive_hierarchical_bridge",
        "Narrative policy document. Best suited for Adaptive Hierarchical Bridge Chunking (AHBC).",
    )


def detect_boundary_bridge(
    chunk_a_text: str,
    chunk_b_text: str,
    doc_id: str = "DOC",
    id_a: str = "A",
    id_b: str = "B",
    hierarchy_a: str = "",
    hierarchy_b: str = "",
) -> BridgeLink:
    """Analyze the boundary between chunk A and chunk B to detect the bridge relationship and validation status."""
    text_a = (chunk_a_text or "").strip()
    text_b = (chunk_b_text or "").strip()

    tail_a = text_a[-120:] if len(text_a) > 120 else text_a
    head_b = text_b[:120] if len(text_b) > 120 else text_b
    boundary_span = f"...{tail_a[-60:].strip()} [⮂] {head_b[:60].strip()}..."

    bridge_id = f"brg_{doc_id}_{id_a}_{id_b}"

    # 1. Check for table split across boundary
    if ("|" in tail_a and "|" in head_b) and (
        _TABLE_ROW_PATTERN.search(tail_a) or _TABLE_ROW_PATTERN.search(head_b)
    ):
        return BridgeLink(
            bridge_id=bridge_id,
            source_chunk_id=id_a,
            target_chunk_id=id_b,
            relationship=BridgeType.TABLE_STRUCTURE.value,
            confidence=0.92,
            boundary_span=boundary_span,
            rationale="Table rows or column headers span across the boundary.",
            status=BridgeStatus.VALIDATED,
        )

    # 2. Check for syntax continuation (broken sentence, trailing punctuation, dangling conjunction, lowercase start)
    if (
        _DANGLING_TAIL_PUNCTUATION.search(text_a)
        or _DANGLING_CONJUNCTION.search(text_a)
        or (head_b and head_b[0].islower())
    ):
        return BridgeLink(
            bridge_id=bridge_id,
            source_chunk_id=id_a,
            target_chunk_id=id_b,
            relationship=BridgeType.CONTINUES.value,
            confidence=0.96,
            boundary_span=boundary_span,
            rationale="Sentence or clause severed at boundary; begins with lowercase or follows trailing punctuation/conjunction.",
            status=BridgeStatus.VALIDATED,
        )

    # 3. Check for qualifying conditions modifying prior rule
    if _QUALIFYING_PATTERNS.search(head_b):
        return BridgeLink(
            bridge_id=bridge_id,
            source_chunk_id=id_a,
            target_chunk_id=id_b,
            relationship=BridgeType.QUALIFIES.value,
            confidence=0.94,
            boundary_span=boundary_span,
            rationale="Chunk B provides a conditional approval, exception, or qualification for Chunk A.",
            status=BridgeStatus.VALIDATED,
        )

    # 4. Check for procedural dependencies / workflow steps
    if _PROCEDURAL_PATTERNS.search(head_b):
        return BridgeLink(
            bridge_id=bridge_id,
            source_chunk_id=id_a,
            target_chunk_id=id_b,
            relationship=BridgeType.PROCEDURE_DEPENDENCY.value,
            confidence=0.88,
            boundary_span=boundary_span,
            rationale="Chunk B describes subsequent procedural or recording steps dependent on Chunk A.",
            status=BridgeStatus.VALIDATED,
        )

    # 5. Check for definitions
    if _DEFINING_PATTERNS.search(head_b):
        return BridgeLink(
            bridge_id=bridge_id,
            source_chunk_id=id_a,
            target_chunk_id=id_b,
            relationship=BridgeType.DEFINES.value,
            confidence=0.90,
            boundary_span=boundary_span,
            rationale="Chunk B defines or clarifies terminology introduced in Chunk A.",
            status=BridgeStatus.VALIDATED,
        )

    # 6. Check for heading context
    if (hierarchy_a != hierarchy_b) or text_a.startswith("#") or text_a.isupper():
        return BridgeLink(
            bridge_id=bridge_id,
            source_chunk_id=id_a,
            target_chunk_id=id_b,
            relationship=BridgeType.HEADING_CONTEXT.value,
            confidence=0.85,
            boundary_span=boundary_span,
            rationale="Heading hierarchy or title context connects this boundary.",
            status=BridgeStatus.VALIDATED,
        )

    # 7. Default sequential narrative continuity
    return BridgeLink(
        bridge_id=bridge_id,
        source_chunk_id=id_a,
        target_chunk_id=id_b,
        relationship=BridgeType.SEQUENTIAL.value,
        confidence=0.75,
        boundary_span=boundary_span,
        rationale="Standard narrative sequential progression within the document.",
        status=BridgeStatus.CANDIDATE,  # Un-bridged sequential link remains candidate, avoiding false bridge retrieval
    )


def link_chunk_records_into_linked_list(
    chunks: List[Any],
    doc_id: str = "DOC",
) -> List[Any]:
    """Connect a list of ChunkRecord objects into a Doubly Linked List with typed bridges."""
    total = len(chunks)
    if total == 0:
        return chunks

    for idx, chunk in enumerate(chunks):
        chunk.sequence_index = idx
        chunk.previous_chunk_id = chunks[idx - 1].id if idx > 0 else None
        chunk.next_chunk_id = chunks[idx + 1].id if idx < total - 1 else None

        # Build bridge to next chunk
        if idx < total - 1:
            next_chunk = chunks[idx + 1]
            bridge = detect_boundary_bridge(
                chunk_a_text=chunk.text,
                chunk_b_text=next_chunk.text,
                doc_id=doc_id,
                id_a=chunk.id,
                id_b=next_chunk.id,
                hierarchy_a=getattr(chunk, "heading_hierarchy", ""),
                hierarchy_b=getattr(next_chunk, "heading_hierarchy", ""),
            )
            chunk.bridge_to_next = bridge.to_dict()
            next_chunk.bridge_from_prev = bridge.to_dict()

        # Update metadata dictionary on the ChunkRecord
        if hasattr(chunk, "metadata") and isinstance(chunk.metadata, dict):
            chunk.metadata["sequence_index"] = idx
            chunk.metadata["previous_chunk_id"] = chunk.previous_chunk_id
            chunk.metadata["next_chunk_id"] = chunk.next_chunk_id
            if chunk.bridge_to_next:
                chunk.metadata["bridge_type"] = chunk.bridge_to_next["relationship"]
                chunk.metadata["bridge_confidence"] = chunk.bridge_to_next["confidence"]
                chunk.metadata["bridge_to_next_id"] = chunk.bridge_to_next["bridge_id"]
                chunk.metadata["bridge_rationale"] = chunk.bridge_to_next["rationale"]
                chunk.metadata["bridge_status"] = chunk.bridge_to_next["status"]

    return chunks


def link_store_records_with_bridges(
    records: List[Dict[str, Any]],
    doc_id: str = "DOC",
) -> List[Dict[str, Any]]:
    """Connect a list of store-ready record dictionaries into a Doubly Linked List with bridges."""
    total = len(records)
    if total == 0:
        return records

    for idx in range(total):
        rec = records[idx]
        meta = rec.setdefault("metadata", {})
        rec_id = rec.get("id", f"{doc_id}-{idx}")

        prev_id = records[idx - 1].get("id") if idx > 0 else None
        next_id = records[idx + 1].get("id") if idx < total - 1 else None

        meta["sequence_index"] = idx
        meta["previous_chunk_id"] = prev_id
        meta["next_chunk_id"] = next_id

        if idx < total - 1:
            next_rec = records[idx + 1]
            next_rec_id = next_rec.get("id", f"{doc_id}-{idx+1}")
            next_meta = next_rec.setdefault("metadata", {})

            bridge = detect_boundary_bridge(
                chunk_a_text=rec.get("text", ""),
                chunk_b_text=next_rec.get("text", ""),
                doc_id=doc_id,
                id_a=rec_id,
                id_b=next_rec_id,
                hierarchy_a=meta.get("hierarchy_path", "") or meta.get("heading_hierarchy", ""),
                hierarchy_b=next_meta.get("hierarchy_path", "") or next_meta.get("heading_hierarchy", ""),
            )
            b_dict = bridge.to_dict()
            meta["bridge_type"] = b_dict["relationship"]
            meta["bridge_confidence"] = b_dict["confidence"]
            meta["bridge_to_next_id"] = b_dict["bridge_id"]
            meta["bridge_rationale"] = b_dict["rationale"]
            meta["bridge_span"] = b_dict["boundary_span"]
            meta["bridge_status"] = b_dict["status"]

            next_meta["bridge_from_prev_id"] = b_dict["bridge_id"]
            next_meta["bridge_from_prev_type"] = b_dict["relationship"]

    return records


# Query Intent Cues for Three-Tier Retrieval Expansion
_CONDITION_QUERY_CUES = re.compile(
    r"\b(condition|permit|allowed|approval|exception|qualif|unless|subject to|if|when|who can|eligib)\b",
    re.IGNORECASE,
)
_PROCEDURE_QUERY_CUES = re.compile(
    r"\b(how to|steps|procedure|record|submit|apply|process|after|follow|action)\b",
    re.IGNORECASE,
)
_DEFINITION_QUERY_CUES = re.compile(
    r"\b(what is|meaning|defined|term|refer|clarif)\b",
    re.IGNORECASE,
)


def assemble_query_aware_context(
    retrieved_chunk: Dict[str, Any],
    query: str = "",
    chunk_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
    max_tokens: int = 800,
) -> Dict[str, Any]:
    """Three-Tier Query-Aware Dynamic Context Assembly:
    
    Tier 1 (Core): High-precision needle chunk (exact match).
    Tier 2 (Validated Bridge): If query asks for conditions/procedures/definitions and a validated bridge exists,
           expand the linked neighbor chunk.
    Tier 3 (Parent Section Fallback): If broader grounding is required or no bridge applies, expand to parent section.
    """
    chunk_text = retrieved_chunk.get("text", "")
    metadata = retrieved_chunk.get("metadata", {})
    chunk_id = retrieved_chunk.get("id", metadata.get("chunk_id", "core"))

    bridge_type = metadata.get("bridge_type")
    bridge_status = metadata.get("bridge_status")
    next_chunk_id = metadata.get("next_chunk_id")
    parent_text = metadata.get("parent_text")

    # Tier 2 Check: Query asks for a condition/qualification/procedure and validated bridge exists
    should_expand_bridge = False
    expansion_reason = ""

    if bridge_status == BridgeStatus.VALIDATED.value and next_chunk_id and chunk_lookup:
        if bridge_type == BridgeType.QUALIFIES.value and _CONDITION_QUERY_CUES.search(query):
            should_expand_bridge = True
            expansion_reason = "Query inquires about conditions/exceptions; expanding 'qualifies' bridge."
        elif bridge_type == BridgeType.PROCEDURE_DEPENDENCY.value and _PROCEDURE_QUERY_CUES.search(query):
            should_expand_bridge = True
            expansion_reason = "Query inquires about workflow/procedure; expanding 'procedure_dependency' bridge."
        elif bridge_type == BridgeType.DEFINES.value and _DEFINITION_QUERY_CUES.search(query):
            should_expand_bridge = True
            expansion_reason = "Query inquires about terminology; expanding 'defines' bridge."
        elif bridge_type == BridgeType.CONTINUES.value:
            should_expand_bridge = True
            expansion_reason = "Boundary severs sentence or clause; expanding 'continues' bridge."

    if should_expand_bridge and next_chunk_id in chunk_lookup:
        neighbor_chunk = chunk_lookup[next_chunk_id]
        neighbor_text = neighbor_chunk.get("text", "")
        assembled_text = (
            f"{chunk_text}\n\n"
            f"[🔗 Bridge Expansion ({bridge_type}) -> {next_chunk_id}]:\n"
            f"{neighbor_text}"
        )
        return {
            "tier": "tier_2_validated_bridge",
            "assembled_text": assembled_text,
            "core_chunk_id": chunk_id,
            "expanded_chunk_id": next_chunk_id,
            "bridge_type": bridge_type,
            "expansion_reason": expansion_reason,
            "provenance_chunks": [chunk_id, next_chunk_id],
        }

    # Tier 3 Check: Parent Section Fallback if chunk is too brief or broad query
    if parent_text and len(chunk_text) < 300 and len(parent_text) > len(chunk_text):
        return {
            "tier": "tier_3_parent_fallback",
            "assembled_text": f"[📂 Section Context]:\n{parent_text}",
            "core_chunk_id": chunk_id,
            "parent_id": metadata.get("parent_id"),
            "expansion_reason": "Core chunk is a concise micro-needle; expanded to parent section.",
            "provenance_chunks": [chunk_id],
        }

    # Tier 1: Core Chunk
    return {
        "tier": "tier_1_core",
        "assembled_text": chunk_text,
        "core_chunk_id": chunk_id,
        "expansion_reason": "Core chunk provides self-contained, high-precision answer context.",
        "provenance_chunks": [chunk_id],
    }
