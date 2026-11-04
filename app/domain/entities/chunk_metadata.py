"""Canonical metadata contract for chunks persisted to the vector store.

Every chunk KnowLayer stores carries the same set of keys, defined here on the
domain side so the contract does not depend on any parser. A document parser
(``DocumentProcessingPort``) may only contribute the three content-derived
facts it can legitimately observe -- page number, applicable heading, and
heading hierarchy. Document identity and authorization scope are supplied by
the application layer and are never derived from parsed content.

Two representations exist deliberately:

``as_dict``
    The canonical projection. Values the store cannot represent -- a null page
    number, an absent heading, an empty hierarchy -- are *omitted* rather than
    defaulted, so nothing is invented and existing citation fallbacks still
    decide what a user sees.

``as_legacy``
    The pre-canonical key names (``source``, ``section``) that retrieval and
    citation code still read. They are derived from the canonical fields, so
    the old and new names for one fact can never disagree.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence


if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.domain.ports.document_processing import ProcessedDocument


#: Scope for a document that is not bound to a project. Retrieval authorization
#: filters on this exact literal, so it is part of the contract, not a default
#: the store happens to tolerate.
UNASSIGNED_PROJECT_ID = "unassigned"

#: The only content type defined today. The field stays a free-form string so
#: structured kinds can be introduced later without a schema change, but no
#: taxonomy is defined until there is a consumer for one.
CONTENT_TYPE_TEXT = "text"

#: Joins a heading hierarchy into the single-line form used for display and for
#: the legacy ``section`` key.
HIERARCHY_SEPARATOR = " > "

#: Keys of the canonical contract, in a stable order. Useful for asserting that
#: a stored chunk has not silently grown extra fields.
CANONICAL_FIELDS = (
    "document_id",
    "project_id",
    "source_filename",
    "page_number",
    "section_heading",
    "hierarchy_path",
    "chunk_index",
    "content_type",
)


@dataclass(frozen=True, slots=True)
class ChunkMetadata:
    """The canonical metadata for one stored chunk.

    ``page_number`` and ``section_heading`` are ``None`` and ``hierarchy_path``
    is empty when the source document does not provide that structure. Those
    are meaningful "unknown" values here; the store projection omits them.
    """

    document_id: str
    source_filename: str
    chunk_index: int
    project_id: str = UNASSIGNED_PROJECT_ID
    page_number: int | None = None
    section_heading: str | None = None
    hierarchy_path: tuple[str, ...] = ()
    content_type: str = CONTENT_TYPE_TEXT

    def __post_init__(self) -> None:
        if not isinstance(self.document_id, str) or not self.document_id.strip():
            raise ValueError("document_id must be a non-empty identifier")
        if not isinstance(self.source_filename, str) or not self.source_filename.strip():
            raise ValueError("source_filename must be a non-empty file name supplied by the application")
        if not isinstance(self.chunk_index, int) or isinstance(self.chunk_index, bool):
            raise TypeError(f"chunk_index must be int, got {type(self.chunk_index).__name__}")
        if self.chunk_index < 0:
            raise ValueError(f"chunk_index must be zero-based, got {self.chunk_index}")
        if self.page_number is not None:
            if not isinstance(self.page_number, int) or isinstance(self.page_number, bool):
                raise TypeError(f"page_number must be int or None, got {type(self.page_number).__name__}")
            if self.page_number < 1:
                raise ValueError(f"page_number is one-based, got {self.page_number}")
        if self.section_heading is not None and not str(self.section_heading).strip():
            raise ValueError("section_heading must be a non-empty heading or None")
        if not isinstance(self.content_type, str) or not self.content_type.strip():
            raise ValueError("content_type must be a non-empty string")

        # Normalise the two fields whose "absent" representation is ambiguous,
        # so a caller passing ``None`` or ``[]`` still yields the contract's
        # own notion of unknown.
        if not self.project_id:
            object.__setattr__(self, "project_id", UNASSIGNED_PROJECT_ID)
        if not isinstance(self.hierarchy_path, Sequence) or isinstance(self.hierarchy_path, (str, bytes)):
            raise TypeError("hierarchy_path must be a sequence of heading titles")
        titles = tuple(self.hierarchy_path)
        for title in titles:
            if not isinstance(title, str) or not title.strip():
                raise ValueError("hierarchy_path entries must be non-empty heading titles")
        object.__setattr__(self, "hierarchy_path", titles)

    @property
    def hierarchy_text(self) -> str | None:
        """Hierarchy joined for display, or ``None`` when there is no hierarchy."""
        return HIERARCHY_SEPARATOR.join(self.hierarchy_path) or None

    def as_dict(self) -> dict[str, object]:
        """Canonical projection for the vector store.

        Absent structure is omitted rather than written as null or empty, which
        both keeps the store from rejecting the record and lets the existing
        citation fallbacks apply.
        """
        payload: dict[str, object] = {
            "document_id": self.document_id,
            "project_id": self.project_id,
            "source_filename": self.source_filename,
            "chunk_index": self.chunk_index,
            "content_type": self.content_type,
        }
        if self.page_number is not None:
            payload["page_number"] = self.page_number
        if self.section_heading is not None:
            payload["section_heading"] = self.section_heading
        if self.hierarchy_path:
            payload["hierarchy_path"] = list(self.hierarchy_path)
        return payload

    def as_legacy(self) -> dict[str, str]:
        """Pre-canonical key names still read by retrieval and citation code."""
        legacy = {"source": self.source_filename}
        hierarchy_text = self.hierarchy_text
        if hierarchy_text is not None:
            legacy["section"] = hierarchy_text
        return legacy


def build_chunk_metadata(
    processed: "ProcessedDocument",
    *,
    document_id: str,
    source_filename: str,
    project_id: str | None = None,
) -> list[ChunkMetadata]:
    """Build canonical metadata for every chunk of a parsed document.

    ``document_id``, ``project_id`` and ``source_filename`` are required inputs
    from the application: they establish identity and authorization scope, so
    they are never read off the parsed document. ``project_id`` falls back to
    :data:`UNASSIGNED_PROJECT_ID` when the document is not bound to a project.

    ``chunk_index`` is the chunk's position in the document's generated chunk
    sequence, which makes it deterministic regardless of how a particular
    parser numbers its own output.
    """
    scope = project_id or UNASSIGNED_PROJECT_ID
    return [
        ChunkMetadata(
            document_id=document_id,
            project_id=scope,
            source_filename=source_filename,
            chunk_index=position,
            page_number=chunk.page_number,
            section_heading=chunk.section_heading,
            hierarchy_path=chunk.hierarchy_titles,
            content_type=chunk.content_type,
        )
        for position, chunk in enumerate(processed.chunks)
    ]
