from app.use_cases.chat.provenance_service import (
    ProvenanceService,
    _clean_section,
    _strip_numbering,
)


def test_provenance_service_extracts_explicit_source():
    service = ProvenanceService()
    results = [
        {
            "text": "1. Standard annual leave is 18 days.",
            "metadata": {
                "source": "HR_Policy.pdf",
                "section": "Section 2.1 Leave Policy",
                "document_id": "doc_hr_1",
                "project_id": "proj_internal",
            },
        }
    ]
    citations = service.build_citations(results)
    assert len(citations) == 1
    citation = citations[0]
    assert citation["source"] == "HR_Policy.pdf"
    assert citation["section"] == "Leave Policy"
    assert citation["text"] == "Standard annual leave is 18 days."
    assert citation["document_id"] == "doc_hr_1"
    assert citation["project_id"] == "proj_internal"


def test_provenance_service_fallback_to_file_name():
    service = ProvenanceService()
    results = [
        {
            "text": "Benefits information.",
            "metadata": {
                "source": "",
                "file_name": "Benefits_Overview.docx",
            },
        }
    ]
    citations = service.build_citations(results)
    assert len(citations) == 1
    assert citations[0]["source"] == "Benefits_Overview.docx"


def test_provenance_service_fallback_to_unknown_document():
    service = ProvenanceService()
    results = [
        {
            "text": "No source metadata provided.",
            "metadata": {},
        },
        {
            "text": "None source provided.",
            "metadata": {"source": None, "file_name": None},
        },
    ]
    citations = service.build_citations(results)
    assert len(citations) == 2
    assert citations[0]["source"] == "Unknown Document"
    assert citations[1]["source"] == "Unknown Document"


def test_strip_numbering_patterns():
    assert _strip_numbering("1. First rule") == "First rule"
    assert _strip_numbering("• 2) Second rule") == "Second rule"
    assert _strip_numbering("- 1.2 Sub-clause") == "Sub-clause"
    assert _strip_numbering("(a) Item text") == "Item text"
    assert _strip_numbering("Section 3: Important") == "Important"


def test_clean_section():
    assert _clean_section("Section 4.2 Vacation Policy") == "Vacation Policy"
    assert _clean_section("Clause 10 Non-disclosure") == "Non-disclosure"
    assert _clean_section("3.1 Core Working Hours") == "Core Working Hours"
    assert _clean_section("") == ""
