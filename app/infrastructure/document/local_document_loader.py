from pathlib import Path
from typing import List

from app.domain.ports.document_processing import DocumentProcessingPort
from app.infrastructure.document.plaintext_processor import SUPPORTED_EXTENSIONS


class LocalDocumentLoader:
    def __init__(self, documents_dir: str, processor: DocumentProcessingPort | None = None):
        self.documents_dir = Path(documents_dir)
        self.processor = processor

    def list_documents(self) -> List[str]:
        if not self.documents_dir.exists():
            return []
        return [
            str(path)
            for path in sorted(self.documents_dir.iterdir())
            if path.is_file() and self._supports(path)
        ]

    def _supports(self, path: Path) -> bool:
        if self.processor is not None:
            return self.processor.supports(path.name)
        return path.suffix.lower() in SUPPORTED_EXTENSIONS

    def get_document(self, file_name: str) -> str:
        file_path = self.documents_dir / file_name
        if not file_path.exists():
            raise FileNotFoundError(file_name)
        return str(file_path)
