import pytest
from app.use_cases.ingestion.document_processing import (
    DocumentBlock, chunk_text, build_chunk_records, extract_text_from_bytes
)

def test_paragraph_and_table_extraction():
    # We simulate what extract_blocks_from_docx returns since we can't easily mock docx python objects deeply
    blocks = [
        DocumentBlock(block_type='heading', content='1. Introduction', order=0, heading_level=1, section='1. Introduction'),
        DocumentBlock(block_type='paragraph', content='Welcome to the company.', order=1, section='1. Introduction'),
        DocumentBlock(block_type='table', content='[Table]', order=2, section='1. Introduction', table_rows=['Leave | Days', 'Annual | 10']),
        DocumentBlock(block_type='paragraph', content='Enjoy your stay.', order=3, section='1. Introduction')
    ]
    
    chunks = chunk_text(blocks, chunk_size=500, overlap=10)
    
    # Assert ordering and extraction
    assert len(chunks) == 3
    assert chunks[0]['content_type'] == 'text'
    assert 'Welcome to the company.' in chunks[0]['text']
    assert chunks[1]['content_type'] == 'table'
    assert 'Leave | Days' in chunks[1]['text']
    assert chunks[2]['content_type'] == 'text'
    assert 'Enjoy your stay.' in chunks[2]['text']

def test_heading_detection_and_metadata():
    blocks = [
        DocumentBlock(block_type='heading', content='1. Policies', order=0, heading_level=1, section='1. Policies'),
        DocumentBlock(block_type='heading', content='1.1 PTO', order=1, heading_level=2, section='1. Policies', subsection='1.1 PTO'),
        DocumentBlock(block_type='paragraph', content='PTO is nice.', order=2, section='1. Policies', subsection='1.1 PTO')
    ]
    
    chunks = chunk_text(blocks)
    assert len(chunks) == 1
    assert chunks[0]['section'] == '1. Policies'
    assert chunks[0]['subsection'] == '1.1 PTO'
    
    records = build_chunk_records(blocks, "doc-1")
    assert records[0]['metadata']['section'] == '1. Policies'
    assert records[0]['metadata']['subsection'] == '1.1 PTO'
    assert records[0]['metadata']['content_type'] == 'text'

def test_structural_headers():
    blocks = [
        DocumentBlock(block_type='paragraph', content='PTO is nice.', order=0, section='Policies', subsection='PTO')
    ]
    chunks = chunk_text(blocks)
    assert 'Section: Policies' in chunks[0]['text']
    assert 'Subsection: PTO' in chunks[0]['text']

def test_chunk_boundaries_and_overlap():
    blocks = [
        DocumentBlock(block_type='paragraph', content='This is the first sentence. This is the second sentence. And a third.', order=0, section='S1')
    ]
    # Small chunk size to force split
    chunks = chunk_text(blocks, chunk_size=40, overlap=15)
    
    assert len(chunks) > 1
    # Check overlap (should pull the last part of previous chunk)
    assert 'sentence.' in chunks[1]['text']

def test_table_splitting():
    blocks = [
        DocumentBlock(block_type='table', content='[Table]', order=0, section='S1', table_rows=[
            "R1", "R2", "R3", "R4"
        ])
    ]
    # "R1" is 2 chars. "R2" is 2 chars. 
    # With a small chunk size of 10, the rows will group until length > 10.
    chunks = chunk_text(blocks, chunk_size=10, overlap=0)
    assert len(chunks) == 2
    assert 'R1' in chunks[0]['text']
    assert 'R4' in chunks[1]['text']

def test_deterministic_ordering():
    blocks = [
        DocumentBlock(block_type='paragraph', content='A', order=0),
        DocumentBlock(block_type='paragraph', content='B', order=1),
        DocumentBlock(block_type='paragraph', content='C', order=2)
    ]
    chunks = chunk_text(blocks, chunk_size=2, overlap=0)
    assert chunks[0]['text'].strip() == 'A'
    assert chunks[1]['text'].strip() == 'B'
    assert chunks[2]['text'].strip() == 'C'
    assert chunks[0]['block_order'] == 0
    assert chunks[1]['block_order'] == 1
    assert chunks[2]['block_order'] == 2
