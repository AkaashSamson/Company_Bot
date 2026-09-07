from typing import Any, Dict


def format_response(result: Dict[str, Any]) -> str:
    """Format the shared chat result as a Teams message."""
    lines = [result.get("answer", "I could not generate an answer.")]

    for citation in result.get("citations", []):
        source = citation.get("source", "Policy")
        section = citation.get("section", "Policy")
        text = citation.get("text", "")
        lines.append(f"\nSource: {source} | Section: {section}\n{text}")

    return "\n".join(lines)