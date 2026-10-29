from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class DocumentSource:
    id: str
    title: str
    file_path: str
    content_type: str
    status: str = "active"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DocumentChunk:
    id: Optional[str] = None
    document_id: str = ""
    chunk_index: int = 0
    text: str = ""
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    chunk_id: Optional[str] = None

    def __post_init__(self):
        if self.id is None and self.chunk_id is not None:
            self.id = self.chunk_id
        elif self.chunk_id is None and self.id is not None:
            self.chunk_id = self.id
        if "chunk_index" in self.metadata and self.chunk_index == 0:
            try:
                self.chunk_index = int(self.metadata["chunk_index"])
            except (ValueError, TypeError):
                pass


@dataclass
class VectorRecord:
    id: str
    chunk_id: str
    embedding_model: str
    embedding_version: str
    collection_name: str
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Message:
    id: str
    session_id: str
    role: str
    content: str
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class QuerySession:
    id: str
    user_input: str
    conversation_history: List[Message] = field(default_factory=list)
    session_status: str = "active"
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RetrievedEvidence:
    id: str
    query_session_id: str
    chunk_id: str
    score: float
    citation_text: str
    source_reference: str
    retrieved_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AnswerResponse:
    id: str
    query_session_id: str
    answer_text: str
    citations: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
