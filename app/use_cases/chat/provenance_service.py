import re


def _clean_section(section: str) -> str:
    """Strip leading numbering/section label from section name if descriptive text follows."""
    if not section:
        return ""
    cleaned = re.sub(
        r"^\s*(?:(?:Section|Article|Clause)\s+)?\d+(?:\.\d+)*[:\s-]*",
        "",
        section,
        flags=re.IGNORECASE,
    ).strip()
    return cleaned if cleaned else section


def _strip_numbering(text: str) -> str:
    """Remove leading list/section numbers from citation text.

    Handles patterns like:
      • "1. text"  "1) text"  "(1) text"  "1 - text"
      • "- 1. text"  "• 1. text"
      • "a. text"  "i. text"  "ii) text"  "(a) text"
      • "1.2 text"  "Section 3:" prefixes
    Repeated across multiple lines so every paragraph in the chunk is cleaned.
    """
    if not text:
        return text
    # Patterns to strip from the START of each line
    _NUM_PREFIX = re.compile(
        r"^\s*(?:"
        r"[-*•]\s*"                                         # Optional bullet prefix like "- 1."
        r")?(?:"
        r"\(?\d+(?:\.\d+)*\)?[.):]?\s*(?:[-–—]\s*)?"       # 1.  1)  (1)  1.2  1.2.3  1 -
        r"|\(?[a-zA-Z]{1,4}\)?[.):]\s*(?:[-–—]\s*)?"        # a.  b)  (a)  iv.  A.
        r"|(?:Section|Article|Clause)\s+\d[\d.]*[:\s-]*"   # Section 3:  Section 3.1 -
        r"|[-*•–—]\s+"                                     # Standalone bullet
        r")",
        re.IGNORECASE,
    )
    cleaned_lines = []
    for line in text.splitlines():
        cleaned_lines.append(_NUM_PREFIX.sub("", line).strip())
    return "\n".join(cleaned_lines).strip()


class ProvenanceService:
    def build_citations(self, results):
        citations = []
        for result in results:
            metadata = result.get("metadata", {})
            raw_text = result.get("text", "")
            raw_section = metadata.get("section", "Policy")
            citations.append({
                "source": metadata.get("source", "NEXORA TECHNOLOGIES PVT.docx"),
                "section": _clean_section(raw_section),
                "text": _strip_numbering(raw_text),
            })
        return citations
