from app.infrastructure.channels.teams.formatter import format_response


def test_format_response_includes_answer_and_citations():
    result = {
        "answer": "Employees receive annual leave.",
        "citations": [
            {
                "source": "handbook.docx",
                "section": "Annual Leave",
                "text": "Employees receive 20 days of annual leave.",
            }
        ],
    }

    formatted = format_response(result)

    assert "Employees receive annual leave." in formatted
    assert "Source: handbook.docx | Section: Annual Leave" in formatted
    assert "Employees receive 20 days of annual leave." in formatted


def test_format_response_supports_multiple_citations():
    result = {
        "answer": "The policy covers leave and remote work.",
        "citations": [
            {"source": "handbook.docx", "section": "Leave", "text": "Leave policy."},
            {"source": "handbook.docx", "section": "Remote Work", "text": "Remote work policy."},
        ],
    }

    formatted = format_response(result)

    assert "Source: handbook.docx | Section: Leave" in formatted
    assert "Source: handbook.docx | Section: Remote Work" in formatted


def test_format_response_without_citations_returns_answer():
    formatted = format_response(
        {"answer": "The requested information was not found.", "citations": []}
    )

    assert formatted == "The requested information was not found."


def test_format_response_uses_defaults_for_missing_fields():
    formatted = format_response({})

    assert formatted == "I could not generate an answer."