import pytest
from unittest.mock import MagicMock, patch
from app.use_cases.chat.retrieval_service import RetrievalService


def test_retrieval_service_hybrid_fuses_candidates():
    with patch("app.use_cases.chat.retrieval_service.ChromaVectorStore") as MockStore:
        mock_store_inst = MagicMock()
        MockStore.return_value = mock_store_inst
        
        # Dense query returns general candidate
        mock_store_inst.query.return_value = [
            {"id": "c1", "text": "General HR policy guidelines.", "distance": 0.25, "score": 0.75, "metadata": {}}
        ]
        
        # Collection get has 2 documents
        mock_store_inst.collection.count.return_value = 2
        mock_store_inst.collection.get.return_value = {
            "ids": ["c1", "c2"],
            "documents": [
                "General HR policy guidelines.",
                "Policy Code Form 1095-C specifications and requirements.",
            ],
            "metadatas": [{}, {}],
        }

        service = RetrievalService()
        # Query specifically for exact code
        raw_candidates = service.retrieve_raw_candidates("Form 1095-C", top_k=5)

        cand_ids = [c["id"] for c in raw_candidates]
        assert "c2" in cand_ids
        assert any(c.get("_bm25_rank") == 1 for c in raw_candidates if c["id"] == "c2")

