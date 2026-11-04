"""Visual output contract for document visual understanding.

Defines the structured schema for visual extraction results (diagrams,
flowcharts, charts, screenshots, and visual assets) with validation,
search-friendly serialization for RAG embedding, and metadata dictionary export.
"""

from __future__ import annotations

from typing import Any, Sequence
from pydantic import BaseModel, Field


class VisualOutputContract(BaseModel):
    """Structured contract for visual intelligence analysis."""

    visual_type: str = Field(
        default="other",
        description="Categorization: architecture_diagram, flowchart, chart, screenshot, table, decorative, other",
    )
    summary: str = Field(
        default="",
        description="Factual, concise summary of the visual element.",
    )
    entities: list[str] = Field(
        default_factory=list,
        description="Identified components, services, nodes, actors, or labeled boxes.",
    )
    relationships: list[str] = Field(
        default_factory=list,
        description="Explicit connections, flows, arrows, or relationships observed.",
    )
    visible_text: list[str] = Field(
        default_factory=list,
        description="Key visible text, labels, legend values, or axis titles.",
    )
    uncertain_items: list[str] = Field(
        default_factory=list,
        description="Elements that are blurry, illegible, ambiguous, or partially visible.",
    )
    source_reference: str = Field(
        default="",
        description="Reference identifier of the source image or picture item (e.g. #/pictures/0).",
    )

    def to_search_text(self) -> str:
        """Render a concise, high-signal text representation for vector embedding and retrieval.

        Preserves 100% compatibility with text-based RAG indexing while avoiding
        unnecessary narrative filler.
        """
        sections: list[str] = []
        if self.visual_type and self.visual_type not in {"other", "unclassified"}:
            sections.append(f"Visual type: {self.visual_type}")
        if self.summary:
            sections.append(f"Summary: {self.summary}")
        if self.entities:
            sections.append(f"Components: {', '.join(self.entities)}")
        if self.relationships:
            sections.append(f"Flows: {'; '.join(self.relationships)}")
        if self.visible_text:
            sections.append(f"Labels: {', '.join(self.visible_text)}")
        if self.uncertain_items:
            sections.append(f"Uncertain: {', '.join(self.uncertain_items)}")

        return "\n".join(sections) if sections else self.summary

    def __str__(self) -> str:
        return self.to_search_text()

    def to_metadata(self) -> dict[str, Any]:
        """Convert structured fields to ChromaDB-safe metadata dictionary."""
        return {
            "visual_type": self.visual_type,
            "summary": self.summary,
            "entities": ", ".join(self.entities) if self.entities else "",
            "relationships": "; ".join(self.relationships) if self.relationships else "",
            "visible_text": ", ".join(self.visible_text) if self.visible_text else "",
            "uncertain_items": ", ".join(self.uncertain_items) if self.uncertain_items else "",
            "source_reference": self.source_reference,
            "entity_count": len(self.entities),
            "relationship_count": len(self.relationships),
        }
