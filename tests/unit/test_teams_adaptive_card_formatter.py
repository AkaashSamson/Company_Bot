from app.infrastructure.channels.teams.formatter import (
    format_teams_adaptive_card,
    format_teams_text,
)


def test_format_teams_text_with_citations():
    result = {
        "answer": "Company employees receive 20 days annual leave.",
        "citations": [
            {"source": "handbook.docx", "section": "Leave", "text": "Annual leave policy: 20 days."}
        ],
    }
    text = format_teams_text(result)
    assert "Company employees receive 20 days annual leave." in text
    assert "Source: handbook.docx" in text
    assert "Leave" in text


def test_format_teams_adaptive_card_schema():
    result = {
        "answer": "Yes, bereavement leave is 5 days.",
        "citations": [
            {"source": "hr_policy.docx", "section": "Bereavement", "text": "Up to 5 days paid leave."}
        ],
    }
    card = format_teams_adaptive_card(result)
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.4"
    assert "$schema" in card
    body = card["body"]
    assert any("Yes, bereavement leave is 5 days." in item.get("text", "") for item in body)
    assert any(item.get("type") == "FactSet" for item in body)


def test_format_teams_adaptive_card_without_citations():
    result = {"answer": "Hello, how can I help?"}
    card = format_teams_adaptive_card(result)
    assert card["type"] == "AdaptiveCard"
    body = card["body"]
    assert len(body) == 1
    assert body[0]["text"] == "Hello, how can I help?"
