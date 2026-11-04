from typing import Any, Dict, List


def format_teams_text(result: Dict[str, Any]) -> str:
    """Format answer and citations as readable markdown text."""
    lines = [result.get("answer", "I could not generate an answer.")]
    citations = result.get("citations") or []

    if citations:
        lines.append("\n**Sources & References:**")
        for cite in citations:
            src = cite.get("source") or "Policy"
            sec = cite.get("section") or ""
            txt = cite.get("text") or ""
            sec_info = f" ({sec})" if sec else ""
            lines.append(f"- **Source: {src}{sec_info}**\n  > {txt}")

    return "\n\n".join(lines)


def format_teams_adaptive_card(result: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a Microsoft Adaptive Card (schema v1.4) JSON payload with collapsible citations."""
    answer = result.get("answer", "I could not generate an answer.")
    citations: List[Dict[str, Any]] = result.get("citations") or []

    body: List[Dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": answer,
            "wrap": True,
            "size": "Medium",
        }
    ]

    if citations:
        facts = []
        for cite in citations:
            src = cite.get("source") or "Document"
            sec = cite.get("section") or ""
            txt = cite.get("text") or ""
            title = f"{src} [{sec}]" if sec else src
            facts.append({"title": title, "value": txt[:250] + ("..." if len(txt) > 250 else "")})

        container_id = "citationsContainer"
        body.append(
            {
                "type": "ActionSet",
                "actions": [
                    {
                        "type": "Action.ToggleVisibility",
                        "title": f"📚 Sources & References ({len(citations)})",
                        "targetElements": [container_id],
                    }
                ],
            }
        )
        body.append(
            {
                "type": "Container",
                "id": container_id,
                "isVisible": False,
                "items": [
                    {
                        "type": "FactSet",
                        "facts": facts,
                    }
                ],
            }
        )

    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body,
    }
