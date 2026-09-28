from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence, runtime_checkable


# Values permitted in neutral parse metadata. Restricted to scalars so a parse
# result can be flattened into any vector store's metadata schema without the
# store's own nesting rules leaking into the domain layer.
MetadataValue = str | int | float | bool | None


def _validate_metadata(owner: str, metadata: Mapping[str, MetadataValue]) -> None:
    """Reject metadata a vector store could not accept, at the port boundary.

    Nested containers (dicts, lists, sets) are a common shape in parser
    document trees. Surfacing them as a contract error here keeps the failure
    attributable to the adapter rather than surfacing later as an opaque
    store-level error.
    """
    for key, value in metadata.items():
        if not isinstance(key, str):
            raise TypeError(f"{owner} metadata keys must be str, got {type(key).__name__}")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise TypeError(
                f"{owner} metadata value for {key!r} must be a scalar "
                f"(str, int, float, bool, or None), got {type(value).__name__}"
            )


@dataclass(frozen=True, slots=True)
class SectionHeading:
    """One node of a document's structural outline.

    Neutral by construction: any parser able to report a heading hierarchy
    maps onto this pair without exposing its own document-tree types.
    """

    level: int
    title: str


@dataclass(frozen=True, slots=True)
class ProcessedChunk:
    """One structurally delimited unit of document text, ready to be embedded.

    Carries only what a parser can legitimately know about the content. The
    document's identity and authorization scope (``document_id``,
    ``project_id``, ``source``, ``version``) are supplied by the application
    layer at metadata-construction time and are deliberately absent here, so
    that access-control scope is never sourced from parsed content.
    """

    text: str
    index: int
    page_number: int | None = None
    section_path: tuple[SectionHeading, ...] = ()
    content_type: str = "text"
    metadata: Mapping[str, MetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_metadata("ProcessedChunk", self.metadata)

    @property
    def hierarchy_titles(self) -> tuple[str, ...]:
        """Applicable headings, outermost first.

        This is the ordered hierarchy the canonical metadata records. Empty when
        the document exposes no heading structure.
        """
        return tuple(heading.title for heading in self.section_path)

    @property
    def section_heading(self) -> str | None:
        """The most specific applicable heading, e.g. ``"14.4 Performance Review Process"``.

        ``None`` when the chunk precedes the document's first heading.
        """
        return self.section_path[-1].title if self.section_path else None

    @property
    def section(self) -> str | None:
        """Flattened heading path, e.g. ``"Leave Policy > Eligibility"``.

        The single-line form retained for the pre-canonical ``section`` metadata
        key. New code should prefer :attr:`section_heading` and
        :attr:`hierarchy_titles`. Returns ``None`` when the document exposes no
        heading hierarchy, so the metadata builder omits the key and the
        existing citation fallbacks apply instead of persisting a null.
        """
        return " > ".join(self.hierarchy_titles) or None


@dataclass(frozen=True, slots=True)
class ProcessedDocument:
    """Neutral result of parsing and structurally chunking one source file.

    Returned by :class:`DocumentProcessingPort` implementations. Holds only
    content-derived facts; the caller supplies document identity and scope.
    """

    chunks: tuple[ProcessedChunk, ...]
    file_type: str | None = None
    page_count: int | None = None
    outline: tuple[SectionHeading, ...] = ()
    metadata: Mapping[str, MetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_metadata("ProcessedDocument", self.metadata)


@runtime_checkable
class DocumentProcessingPort(Protocol):
    """Port for turning raw document bytes into neutral, structurally chunked text.

    This is the only seam through which a document parser or chunker reaches
    the application layer. Implementations live in the infrastructure layer
    and may wrap any conversion technology; the application layer depends on
    this protocol and on :class:`ProcessedDocument` alone, so swapping one
    converter for another requires no change above the adapter.

    Implementations must:

    * return only the neutral result types declared in this module, never a
      vendor document, chunker, or converter object;
    * leave ``project_id`` and other authorization scope to the caller;
    * expose metadata values as scalars (see :data:`MetadataValue`).
    """

    def supported_extensions(self) -> Sequence[str]:
        """Lower-case file extensions this implementation can process, dot included."""
        ...

    def supports(self, file_name: str) -> bool:
        """Whether this implementation can process the given file name."""
        ...

    def process(self, content: bytes, file_name: str) -> ProcessedDocument:
        """Parse and structurally chunk raw file bytes into a neutral result.

        Returns an empty ``chunks`` tuple for content that yields no text.
        """
        ...
