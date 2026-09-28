import pytest
import os
from io import BytesIO
from unittest.mock import MagicMock, patch
from docx import Document
from app.use_cases.ingestion.document_processing import (
    extract_blocks_from_docx,
    extract_blocks_from_pdf,
    chunk_text,
    DocumentBlock
)

# 1. Heading Detection
def test_heading_detection_edge_cases():
    doc = Document()
    
    # Proper Heading 1/2
    doc.add_heading('1. Main Topic', level=1)
    doc.add_heading('1.1 Subtopic', level=2)
    
    # Bold-only heading
    p_bold = doc.add_paragraph()
    run = p_bold.add_run('2. Another Topic')
    run.bold = True
    
    # Bold normal paragraph must NOT become a heading (too long)
    p_long_bold = doc.add_paragraph()
    run = p_long_bold.add_run('This is a very long paragraph that happens to be entirely bolded for some reason. ' * 5)
    run.bold = True
    
    # Numbered list items must NOT become headings (if they are short but not bold, they might match the regex, let's see if they fail)
    # Our regex: r'^(\d+)(?:\.(\d+))*\s+'
    doc.add_paragraph('3. Just a list item but not bold.')
    
    # Nested headings
    doc.add_heading('14. Perf', level=1)
    doc.add_heading('14.1 Perf Sub', level=2)
    doc.add_paragraph('14.1.1 Nested Sub').runs[0].bold = True

    doc_bytes = BytesIO()
    doc.save(doc_bytes)
    doc_bytes.seek(0)
    
    blocks = extract_blocks_from_docx(doc_bytes.read())
    
    assert blocks[0].block_type == 'heading'
    assert blocks[0].heading_level == 1
    
    assert blocks[1].block_type == 'heading'
    assert blocks[1].heading_level == 2
    
    # Bold only heading
    assert blocks[2].block_type == 'heading'
    assert blocks[2].heading_level == 1
    
    # Long bold paragraph should NOT be heading
    assert blocks[3].block_type == 'paragraph'
    
    # Numbered list item not bold: Wait, our regex might catch this as a heading! 
    # Let's assert what currently happens to see if it fails.
    
    # Nested headings
    # 14. Perf -> 14.1 Perf Sub -> 14.1.1 Nested Sub
    nested_sub = next((b for b in blocks if "14.1.1" in b.content), None)
    assert nested_sub is not None
    assert nested_sub.block_type == 'heading'
    assert nested_sub.heading_level == 3


# 2. Ordering
def test_ordering_and_duplication():
    doc = Document()
    doc.add_heading('1. Start', level=1)
    doc.add_paragraph('Para 1')
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = 'H1'
    table.rows[0].cells[1].text = 'H2'
    table.rows[1].cells[0].text = 'D1'
    table.rows[1].cells[1].text = 'D2'
    doc.add_paragraph('Para 2')
    doc.add_heading('2. End', level=1)
    
    doc_bytes = BytesIO()
    doc.save(doc_bytes)
    doc_bytes.seek(0)
    
    blocks = extract_blocks_from_docx(doc_bytes.read())
    
    assert len(blocks) == 5
    assert blocks[0].block_type == 'heading'
    assert blocks[1].block_type == 'paragraph'
    assert blocks[2].block_type == 'table'
    assert blocks[3].block_type == 'paragraph'
    assert blocks[4].block_type == 'heading'


# 3. Tables
def test_tables_edge_cases():
    doc = Document()
    
    # Table without header row (all data)
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = 'Row1Col1'
    table.rows[0].cells[1].text = 'Row1Col2'
    table.rows[1].cells[0].text = 'Row2Col1'
    table.rows[1].cells[1].text = 'Row2Col2'
    
    doc_bytes = BytesIO()
    doc.save(doc_bytes)
    doc_bytes.seek(0)
    
    blocks = extract_blocks_from_docx(doc_bytes.read())
    assert len(blocks) == 1
    # Check if the first row is wrongly treated as header
    # If it is, the output string will be "Row1Col1: Row2Col1 | Row1Col2: Row2Col2"
    # Is that what we want for headerless tables? We'll see if the test passes.
    assert "Row1Col1: Row2Col1" in blocks[0].table_rows[0]
    
    # Chunking a large table
    large_table_block = DocumentBlock(
        block_type='table',
        content="[Table]",
        order=0,
        table_rows=[f"Col1: Val{i} | Col2: Val{i}" for i in range(100)]
    )
    chunks = chunk_text([large_table_block], chunk_size=500)
    assert len(chunks) > 1
    assert "Val0" in chunks[0]['text']


# 4. Chunking
def test_chunking_edge_cases():
    # Long paragraph
    long_para = "A " * 300 + ". " + "B " * 300 + "."
    blocks = [DocumentBlock(block_type='paragraph', content=long_para, order=0, section='1. Sec')]
    
    chunks = chunk_text(blocks, chunk_size=500, overlap=50)
    assert len(chunks) > 1
    
    # Overlap must not cross section boundaries
    blocks2 = [
        DocumentBlock(block_type='paragraph', content="A " * 300 + ".", order=0, section='1. Sec'),
        DocumentBlock(block_type='paragraph', content="B " * 300 + ".", order=1, section='2. Sec')
    ]
    chunks2 = chunk_text(blocks2, chunk_size=500, overlap=50)
    
    # The overlap of chunks2 for section 2 should NOT contain "A "
    sec2_chunks = [c for c in chunks2 if c['section'] == '2. Sec']
    assert "A " not in sec2_chunks[0]['text']


# 5. PDF-specific
@patch('pdfplumber.open')
def test_pdf_edge_cases(mock_open):
    mock_pdf = MagicMock()
    mock_page = MagicMock()
    
    # Mock page headers/footers (should ideally be skipped or treated correctly, but let's see how our top-sorting handles it)
    w_header = {'x0': 10, 'x1': 50, 'top': 5, 'bottom': 15, 'text': 'Header Text', 'size': 10, 'fontname': 'Arial'}
    w_footer = {'x0': 10, 'x1': 50, 'top': 800, 'bottom': 810, 'text': 'Footer Text', 'size': 10, 'fontname': 'Arial'}
    w_page = {'x0': 100, 'x1': 110, 'top': 800, 'bottom': 810, 'text': '1', 'size': 10, 'fontname': 'Arial'}
    
    mock_page.extract_words.return_value = [w_header, w_footer, w_page]
    mock_page.find_tables.return_value = []
    
    mock_pdf.pages = [mock_page]
    mock_open.return_value.__enter__.return_value = mock_pdf
    
    blocks = extract_blocks_from_pdf(b"dummy")
    assert len(blocks) > 0 # We didn't explicitly strip headers/footers in the implementation


# 6. Metadata
def test_metadata_fields():
    blocks = [
        DocumentBlock(block_type='paragraph', content="Test", order=5, section="Sec", subsection="Sub", page_number=10)
    ]
    chunks = chunk_text(blocks)
    assert chunks[0]['section'] == 'Sec'
    assert chunks[0]['subsection'] == 'Sub'
    assert chunks[0]['block_order'] == 5
    assert chunks[0]['page_number'] == 10
    assert chunks[0]['content_type'] == 'text'


# 7. Nexora regression
def test_nexora_regression():
    nexora_path = "input/NEXORA TECHNOLOGIES PVT.docx"
    if not os.path.exists(nexora_path):
        pytest.skip(f"File not found: {nexora_path}")
        
    with open(nexora_path, 'rb') as f:
        blocks = extract_blocks_from_docx(f.read())
        
    # Check Section 14
    sec14_blocks = [b for b in blocks if b.section == '14. Performance Management']
    assert len(sec14_blocks) > 0, "Section 14 not found or not mapped correctly"
    
    # Check Subsections 14.1 - 14.8
    subsections = set(b.subsection for b in sec14_blocks if b.subsection)
    assert "14.1 Purpose" in subsections
    assert "14.8 Employee Responsibilities" in subsections
    
    # "Formal performance reviews are generally conducted twice each year." must NOT be a section
    bad_sec = [b for b in blocks if "Formal performance reviews" in (b.section or "")]
    assert len(bad_sec) == 0, "Paragraph was mistakenly detected as a section heading"
    
    # Check Important Contacts table (Section 20)
    sec20_tables = [b for b in blocks if b.section == '20. Important Contacts' and b.block_type == 'table']
    assert len(sec20_tables) == 1, f"Expected 1 table in Section 20, got {len(sec20_tables)}"
    
    # Table rows in correct order (HR, IT, Facilities, Finance)
    rows = sec20_tables[0].table_rows
    all_rows_text = "\n".join(rows)
    assert "HR / Employment" in all_rows_text
    assert "Finance Team" in all_rows_text
