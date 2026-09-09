import json
import logging
import re
from pathlib import Path
from typing import Any

from sentence_transformers import SentenceTransformer

from app.core.settings import EMBEDDING_MODEL

logger = logging.getLogger(__name__)


class JsonFAQCache:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                logger.warning("faq_json_cache_invalid path=%s", self.path)
                return None
            if isinstance(data.get("entries"), list):
                data["faqs"] = "\n\n".join(
                    f"{entry['input']}\n{entry['output']}"
                    for entry in data["entries"]
                )
                logger.info("faq_json_cache_hit path=%s entries=%d", self.path, len(data["entries"]))
                return data
            if not isinstance(data.get("faqs"), str):
                logger.warning("faq_json_cache_invalid path=%s", self.path)
                return None
            logger.info("faq_json_cache_hit path=%s", self.path)
            return data
        except (OSError, json.JSONDecodeError) as error:
            logger.warning("faq_json_cache_read_failed path=%s error_type=%s", self.path, type(error).__name__)
            return None

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self.path)
        logger.info("faq_json_cache_store path=%s", self.path)

    def migrate_to_entries(self) -> dict[str, Any] | None:
        data = self.load()
        if data is None or isinstance(data.get("entries"), list):
            return data

        text = data["faqs"]
        matches = list(re.finditer(r"(?m)^(19\.\d+|20\.)\s+(.+?)\n", text))
        entries = []
        model = SentenceTransformer(EMBEDDING_MODEL)
        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            block = text[start:end].strip()
            lines = block.splitlines()
            question = lines[0].strip()
            output = "\n".join(lines[1:]).strip()
            vector = model.encode(question, convert_to_numpy=True).tolist()
            entries.append({
                "input": question,
                "output": output,
                "input_vector": vector,
            })

        migrated = {
            "entries": entries,
            "citations": data.get("citations", []),
        }
        self.save(migrated)
        return migrated
