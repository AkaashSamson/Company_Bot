#!/usr/bin/env python
"""
Smoke test: Validate ingestion, retrieval, and chat flow end-to-end.
"""

import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.settings import BASE_DIR, COLLECTION_NAME
from app.infrastructure.document.local_document_loader import LocalDocumentLoader
from app.infrastructure.vector.chroma_client import ChromaVectorStore
from app.use_cases.chat.query_orchestrator import QueryOrchestrator


def test_chroma_populated():
    """Test 1: Verify Chroma is populated."""
    print("\n[TEST 1] Checking Chroma collection...")
    store = ChromaVectorStore(collection_name=COLLECTION_NAME, persist_directory=str(BASE_DIR / ".chroma"))
    count = store.collection.count()
    assert count > 0, f"Chroma collection is empty (expected > 0, got {count})"
    print(f"✓ Chroma collection '{COLLECTION_NAME}' has {count} documents")


def test_retrieval():
    """Test 2: Verify retrieval returns results."""
    print("\n[TEST 2] Testing retrieval...")
    store = ChromaVectorStore(collection_name=COLLECTION_NAME, persist_directory=str(BASE_DIR / ".chroma"))
    results = store.query("leave policy", top_k=3)
    assert len(results) > 0, "Retrieval returned no results"
    assert "text" in results[0], "Result missing 'text' field"
    assert "metadata" in results[0], "Result missing 'metadata' field"
    print(f"✓ Retrieval returned {len(results)} results")
    print(f"  First result preview: {results[0]['text'][:80]}...")


def test_orchestrator():
    """Test 3: Verify query orchestrator generates answers with citations."""
    print("\n[TEST 3] Testing query orchestrator...")
    orchestrator = QueryOrchestrator()
    # Authz-aware: only chunks of documents the seeded manager may read feed the LLM.
    result = orchestrator.answer(
        "What is the leave policy?",
        employee_id="MSS001",
        role_code="manager",
    )
    
    assert "answer" in result, "Result missing 'answer' field"
    assert "citations" in result, "Result missing 'citations' field"
    assert len(result["citations"]) > 0, "No citations returned"
    
    citation = result["citations"][0]
    assert "source" in citation, "Citation missing 'source'"
    assert "section" in citation, "Citation missing 'section'"
    assert "text" in citation, "Citation missing 'text'"
    
    print(f"✓ Orchestrator returned answer with {len(result['citations'])} citations")
    print(f"  Answer: {result['answer'][:80]}...")
    print(f"  Citation source: {citation['source']}")


def test_chat_schema():
    """Test 4: Verify chat API schema."""
    print("\n[TEST 4] Testing chat API schema...")
    from app.api.schemas.chat import ChatRequest, ChatResponse, Citation
    
    # Create a request
    req = ChatRequest(
        question="Test question",
        session_id="test-session",
        conversation_history=[]
    )
    assert req.question == "Test question"
    
    # Create a response
    resp = ChatResponse(
        session_id="test-session",
        answer="Test answer",
        citations=[
            Citation(source="Test.docx", section="Policy", text="Some text")
        ]
    )
    assert len(resp.citations) == 1
    print("✓ Chat schema validated")


def main():
    """Run all smoke tests."""
    print("=" * 60)
    print("KnowLayer MVP Smoke Test Suite")
    print("=" * 60)
    
    try:
        test_chroma_populated()
        test_retrieval()
        test_orchestrator()
        test_chat_schema()
        
        print("\n" + "=" * 60)
        print("✓ All smoke tests passed!")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
