import os
import sys
from pathlib import Path

# Add the project root to sys.path so we can import from app
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.infrastructure.document.processor_factory import build_document_processor
from app.use_cases.ingestion.document_processing import build_chunk_records_from_processed

def main():
    doc_path = project_root / "input" / "NEXORA TECHNOLOGIES PVT.docx"
    
    # FORCE DOCLING PROCESSOR
    processor = build_document_processor(structural=True)
    
    print("Processing with Docling...")
    processed = processor.process(doc_path.read_bytes(), doc_path.name)
    
    print(f"Total outline items: {len(processed.outline)}")
    for heading in processed.outline[:10]:
        print(f"Heading level {heading.level}: {heading.title}")
    
    records = build_chunk_records_from_processed(
        processed,
        document_id=doc_path.stem,
        project_id="test_project",
        source=doc_path.name,
    )
    
    print(f"Total chunks: {len(records)}")
    
    for i, record in enumerate(records):
        metadata = record["metadata"]
        text = record["text"]
        
        # 1. Beginning of the document
        if i == 0:
            print(f"\n[Beginning] Chunk {i}:")
            print(f"Metadata: {metadata}")
            print(f"Text Preview: {text[:200]}...")
            
        # 2. Middle of the document
        if i == len(records) // 2:
            print(f"\n[Middle] Chunk {i}:")
            print(f"Metadata: {metadata}")
            print(f"Text Preview: {text[:200]}...")
            
        # 3. specific match
        if "14.4" in text or "Performance Review Process" in text:
            print(f"\n[Found 14.4 Match] Chunk {i}:")
            print(f"Metadata: {metadata}")
            print(f"Text Preview: {text[:200]}...")

if __name__ == "__main__":
    main()
