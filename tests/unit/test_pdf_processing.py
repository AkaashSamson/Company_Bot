import pytest
from unittest.mock import MagicMock, patch
from app.use_cases.ingestion.document_processing import extract_blocks_from_pdf, DocumentBlock

@pytest.fixture
def mock_pdfplumber():
    with patch('pdfplumber.open') as mock_open:
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        
        # Mock table
        mock_table = MagicMock()
        mock_table.bbox = (10, 100, 200, 150)
        mock_table.extract.return_value = [
            ["Header 1", "Header 2"],
            ["Val 1", "Val 2"]
        ]
        mock_page.find_tables.return_value = [mock_table]
        
        # Mock words (some in table, some out)
        # Word in table
        w_in = {'x0': 20, 'x1': 50, 'top': 110, 'bottom': 120, 'text': 'Val', 'size': 10, 'fontname': 'Arial'}
        # Heading outside table (large bold font)
        w_head1 = {'x0': 10, 'x1': 50, 'top': 10, 'bottom': 25, 'text': '1.', 'size': 16, 'fontname': 'Arial-Bold'}
        w_head2 = {'x0': 55, 'x1': 100, 'top': 10, 'bottom': 25, 'text': 'Introduction', 'size': 16, 'fontname': 'Arial-Bold'}
        # Paragraph outside table
        w_para = {'x0': 10, 'x1': 80, 'top': 50, 'bottom': 60, 'text': 'Some text.', 'size': 10, 'fontname': 'Arial'}
        # Page number at bottom
        w_page = {'x0': 100, 'x1': 110, 'top': 800, 'bottom': 810, 'text': '1', 'size': 10, 'fontname': 'Arial'}
        
        mock_page.extract_words.return_value = [w_in, w_head1, w_head2, w_para, w_page]
        
        mock_pdf.pages = [mock_page]
        mock_open.return_value.__enter__.return_value = mock_pdf
        yield mock_open

def test_pdf_extraction(mock_pdfplumber):
    blocks = extract_blocks_from_pdf(b"dummy_content")
    
    assert len(blocks) == 3
    
    # Check ordering based on top coordinate
    # 1. Heading (top=10)
    assert blocks[0].block_type == 'heading'
    assert blocks[0].content == '1. Introduction'
    assert blocks[0].section == '1. Introduction'
    assert blocks[0].heading_level == 1
    assert blocks[0].page_number == 1
    
    # 2. Paragraph (top=50)
    assert blocks[1].block_type == 'paragraph'
    assert blocks[1].content == 'Some text.'
    assert blocks[1].section == '1. Introduction'
    
    # 3. Table (top=100)
    assert blocks[2].block_type == 'table'
    assert len(blocks[2].table_rows) == 1
    assert blocks[2].table_rows[0] == 'Header 1: Val 1 | Header 2: Val 2'
    assert blocks[2].section == '1. Introduction'

    # Note: Page number (top=800) is automatically skipped because it's just '1'
