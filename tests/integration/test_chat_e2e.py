"""
Integration test for the chat API end-to-end flow.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_chat_api_end_to_end():
    """Test that the chat API returns real retrieval results with citations."""
    payload = {
        "question": "What is the leave policy?",
        "session_id": "test-session-001",
        "conversation_history": [],
    }
    
    response = client.post("/api/chat", json=payload)
    
    # Validate HTTP response
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    body = response.json()
    
    # Validate response structure
    assert "session_id" in body, "Missing session_id"
    assert body["session_id"] == "test-session-001", "session_id mismatch"
    
    assert "answer" in body, "Missing answer"
    assert len(body["answer"]) > 0, "Answer is empty"
    
    assert "citations" in body, "Missing citations"
    assert len(body["citations"]) > 0, f"Expected citations, got {body['citations']}"
    
    # Validate citation structure
    citation = body["citations"][0]
    assert "source" in citation, "Citation missing source"
    assert "section" in citation, "Citation missing section"
    assert "text" in citation, "Citation missing text"
    assert len(citation["text"]) > 0, "Citation text is empty"


def test_chat_api_with_history():
    """Test that the chat API handles conversation history."""
    payload = {
        "question": "What about remote work?",
        "session_id": "test-session-002",
        "conversation_history": [
            {"role": "user", "content": "Tell me about work policies."},
            {"role": "assistant", "content": "The handbook covers all work policies."},
        ],
    }
    
    response = client.post("/api/chat", json=payload)
    
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "test-session-002"
    assert "answer" in body
    assert len(body["citations"]) > 0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
