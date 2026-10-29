import pytest
from app.infrastructure.document.dynamic_section_assignor import DynamicSectionAssignor
from app.infrastructure.document.chunk_normalizer import NormalizedChunk


def test_dynamic_section_assignor_propagation():
    assignor = DynamicSectionAssignor()
    chunks = [
        NormalizedChunk(chunk_id="c1", text="# Code of Conduct\nAll employees must follow ethics rules."),
        NormalizedChunk(chunk_id="c2", text="### Anti-Bribery & Corruption\nBribery of any kind is prohibited."),
        NormalizedChunk(chunk_id="c3", text="Gifts exceeding $50 must be declared to Compliance."),
        NormalizedChunk(chunk_id="c4", text="### Harassment-Free Workplace\nWe maintain zero tolerance for discrimination."),
        NormalizedChunk(chunk_id="c5", text="Reports can be filed anonymously through the whistleblower hotline."),
    ]

    assigned = assignor.assign_sections_to_chunks(chunks, document_title="Corporate Policy")
    assert len(assigned) == 5

    # Chunk 1: Level 1 Header
    assert assigned[0].metadata["heading_hierarchy"] == "Code of Conduct"
    assert assigned[0].metadata["section_heading"] == "Code of Conduct"

    # Chunk 2: Level 3 Header appended
    assert assigned[1].metadata["heading_hierarchy"] == "Code of Conduct > Anti-Bribery & Corruption"
    assert assigned[1].metadata["section_heading"] == "Anti-Bribery & Corruption"

    # Chunk 3: Context propagated forward without header in text
    assert assigned[2].metadata["heading_hierarchy"] == "Code of Conduct > Anti-Bribery & Corruption"
    assert assigned[2].metadata["section_heading"] == "Anti-Bribery & Corruption"

    # Chunk 4: Level 3 Header replaced
    assert assigned[3].metadata["heading_hierarchy"] == "Code of Conduct > Harassment-Free Workplace"
    assert assigned[3].metadata["section_heading"] == "Harassment-Free Workplace"

    # Chunk 5: Context propagated forward
    assert assigned[4].metadata["heading_hierarchy"] == "Code of Conduct > Harassment-Free Workplace"
    assert assigned[4].metadata["section_heading"] == "Harassment-Free Workplace"


def test_dynamic_section_assignor_with_no_markdown_headers():
    assignor = DynamicSectionAssignor()
    chunks = [
        NormalizedChunk(chunk_id="c1", text="First chunk without markdown headers."),
        NormalizedChunk(chunk_id="c2", text="Second chunk also without headers."),
    ]

    assigned = assignor.assign_sections_to_chunks(chunks, document_title="Employee Handbook")
    assert assigned[0].metadata["heading_hierarchy"] == "Employee Handbook"
    assert assigned[1].metadata["heading_hierarchy"] == "Employee Handbook"
    assert assigned[0].metadata["section_heading"] == "Employee Handbook"

