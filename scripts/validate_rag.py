import os
import sys
from pathlib import Path
import tempfile

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.infrastructure.document.processor_factory import build_document_processor
from app.use_cases.ingestion.document_processing import build_chunk_records_from_processed
from app.infrastructure.vector.chroma_client import ChromaVectorStore
from app.domain.entities.chunk_metadata import UNASSIGNED_PROJECT_ID

def main():
    doc_path = project_root / "input" / "HR_Policy_Manual.docx"
    
    # 1. Parsing
    processor = build_document_processor(structural=True)
    print("1. Parsing document...")
    processed = processor.process(doc_path.read_bytes(), doc_path.name)
    
    # 2. Build metadata
    print("2. Building chunk records...")
    records = build_chunk_records_from_processed(
        processed,
        document_id="HR_POLICY_TEST",
        project_id="PROJ_123",
        source=doc_path.name,
    )
    
    # Add a global unassigned record to test fallback
    records_unassigned = build_chunk_records_from_processed(
        processed,
        document_id="HR_POLICY_GLOBAL",
        project_id=None,
        source=doc_path.name,
    )
    # Modify IDs to avoid clash
    for r in records_unassigned:
        r["id"] = "GLOBAL-" + r["id"]
        
    records.extend(records_unassigned)
    
    # 3. Chroma setup
    print("3. Storing in Chroma...")
    temp_dir = tempfile.mkdtemp()
    store = ChromaVectorStore(collection_name="test_rag_flow", persist_directory=temp_dir)
    store.add_documents(records)
    
    # 4. Retrieval queries
    print("4. Testing Retrieval & Authorization...")
    
    # Test retrieving with project_id PROJ_123
    print("\n--- Querying with PROJ_123 scope ---")
    results_proj = store.query(
        query_text="vacation leave",
        top_k=3,
        project_ids=["PROJ_123"]
    )
    for res in results_proj:
        print(f"ID: {res.get('id', 'N/A')}")
        print(f"Metadata: {res['metadata']}")
        print(f"Distance: {res['distance']}")
        assert res['metadata']['project_id'] == "PROJ_123"
        assert "section_heading" in res['metadata'] or "source_filename" in res['metadata']
    
    # Test retrieving with UNASSIGNED
    print("\n--- Querying with unassigned scope ---")
    results_unassigned = store.query(
        query_text="vacation leave",
        top_k=3,
        project_ids=[UNASSIGNED_PROJECT_ID]
    )
    for res in results_unassigned:
        print(f"ID: {res.get('id', 'N/A')}")
        print(f"Metadata: {res['metadata']}")
        print(f"Distance: {res['distance']}")
        assert res['metadata']['project_id'] == UNASSIGNED_PROJECT_ID
        assert res['metadata']['document_id'] == "HR_POLICY_GLOBAL"
        
    print("\n5. Testing document_id filter...")
    results_doc = store.query(
        query_text="vacation leave",
        top_k=3,
        where={"document_id": "HR_POLICY_TEST"}
    )
    for res in results_doc:
        assert res['metadata']['document_id'] == "HR_POLICY_TEST"
    
    print("\nValidation Complete. All tests passed.")

if __name__ == "__main__":
    main()
