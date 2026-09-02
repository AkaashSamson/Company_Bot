from pathlib import Path
from typing import List


SUPPORTED_EXTENSIONS = {".docx", ".txt", ".md", ".rst"}


class LocalDocumentLoader:
    def __init__(self, documents_dir: str):
        self.documents_dir = Path(documents_dir)

    def list_documents(self) -> List[str]:
        if not self.documents_dir.exists():
            return []
        return [
            str(path)
            for path in sorted(self.documents_dir.iterdir())
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ]

    def get_document(self, file_name: str) -> str:
        file_path = self.documents_dir / file_name
        if not file_path.exists():
            raise FileNotFoundError(file_name)
        return str(file_path)
