import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.append(str(project_root))

from app.use_cases.ingestion.document_processing import extract_text_from_document, build_chunk_records

def debug_chunking(file_path: str):
    """Developer tool to see exactly how a document is chunked."""
    print(f"--- Debugging Chunking for: {file_path} ---")
    
    try:
        text = extract_text_from_document(file_path)
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    records = build_chunk_records(
        text=text,
        document_id=Path(file_path).stem,
        source=Path(file_path).name,
        file_type=Path(file_path).suffix
    )
    
    print(f"Total Chunks Generated: {len(records)}\n")
    
    for record in records:
        print(f"[{record['id']}] (Length: {len(record['text'])} chars)")
        print(f"Text: {record['text']}")
        print(f"Metadata: {record['metadata']}")
        print("-" * 50)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        debug_chunking(sys.argv[1])
    else:
        print("Usage: python debug_chunking.py <path_to_document>")
        print("Example: python debug_chunking.py ./input/Handbook.docx")
