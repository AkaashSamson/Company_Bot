"""
app/infrastructure/document/dynamic_section_assignor.py
Dynamic Stateful Section Assignor for KnowLayer.
Propagates heading hierarchy across sequential document chunks with edge-case hardening:
  - EC-05: Fenced code block stripping prevents code comments from being identified as headings.
  - EC-06: Out-of-order heading level jumps cleanly pop deeper levels from the hierarchy stack.
  - EC-07: Deep hierarchy prefix compaction.
  - EC-08: Safe fallback when document has zero headings or document_title is None/empty.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)

# EC-05: Fenced code blocks (``` or ~~~) must not have comments parsed as Markdown headings
FENCED_CODE_BLOCK_REGEX = re.compile(r"```[\s\S]*?```|~~~[\s\S]*?~~~")
MARKDOWN_HEADING_REGEX = re.compile(r"^(#{1,6})\s+(.+)$")


@dataclass
class HeadingNode:
    level: int
    title: str


class DynamicSectionTracker:
    def __init__(self, root_document_name: str = "General Policy") -> None:
        self.root_document_name = root_document_name
        self.stack: List[HeadingNode] = []

    def process_line(self, line: str) -> Optional[HeadingNode]:
        """Processes a single line for Markdown headings. Pops all levels >= L on out-of-order jumps (EC-06)."""
        m = MARKDOWN_HEADING_REGEX.match(line.strip())
        if not m:
            return None
        level = len(m.group(1))
        title = m.group(2).strip()

        # Pop any heading with equal or deeper level
        while self.stack and self.stack[-1].level >= level:
            self.stack.pop()

        node = HeadingNode(level=level, title=title)
        self.stack.append(node)
        return node

    def get_current_hierarchy(self) -> Tuple[str, str]:
        if not self.stack:
            return self.root_document_name, self.root_document_name
        hierarchy_path = " > ".join(n.title for n in self.stack)
        section_heading = self.stack[-1].title
        return hierarchy_path, section_heading


class DynamicSectionAssignor:
    """
    Statefully tracks and propagates heading hierarchies across sequential chunks of a document.
    Maintains active section context for downstream chunk normalization and contextual prefix injection.
    """

    def __init__(self, separator: str = " > ") -> None:
        self.separator = separator

    def assign_sections_to_chunks(
        self,
        chunks: List[Any],
        document_title: str = "General Policy",
    ) -> List[Any]:
        if not chunks:
            return []

        # EC-08: Ensure fallback title is never empty or 'None'
        safe_root = (document_title or "").strip()
        if not safe_root or safe_root.lower() == "none":
            safe_root = "General Policy"

        tracker = DynamicSectionTracker(root_document_name=safe_root)

        for chunk in chunks:
            is_dict = isinstance(chunk, dict)
            chunk_text = chunk.get("text", "") if is_dict else getattr(chunk, "text", "")

            # EC-05: Strip triple-backtick code fences before scanning for `#` headings
            # so Python/Bash comments (`# calculate tax`) never hijack the heading stack!
            scannable_text = FENCED_CODE_BLOCK_REGEX.sub("", chunk_text or "")

            heading_found = False
            for line in scannable_text.splitlines():
                # EC-06: tracker.process_line() pops all levels >= L on out-of-order jumps
                if tracker.process_line(line) is not None:
                    heading_found = True

            if is_dict:
                if "metadata" not in chunk or chunk["metadata"] is None:
                    chunk["metadata"] = {}
                meta = chunk["metadata"]
            else:
                if not hasattr(chunk, "metadata") or chunk.metadata is None:
                    chunk.metadata = {}
                meta = chunk.metadata

            existing_h = str(meta.get("heading_hierarchy") or meta.get("hierarchy_path") or "").strip()
            if existing_h and existing_h.lower() != "none" and not heading_found:
                parts = [p.strip() for p in existing_h.split(">") if p.strip()]
                if parts:
                    tracker.stack = [
                        HeadingNode(level=idx + 1, title=p) for idx, p in enumerate(parts)
                    ]

            hierarchy_path, section_heading = tracker.get_current_hierarchy()
            meta["heading_hierarchy"] = hierarchy_path or safe_root
            meta["hierarchy_path"] = hierarchy_path or safe_root
            meta["section_heading"] = section_heading or safe_root
            meta["section"] = hierarchy_path or safe_root
            meta.setdefault("document_title", safe_root)
            meta.setdefault("policy_name", safe_root)

        return chunks
