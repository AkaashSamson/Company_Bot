import pytest
from unittest.mock import MagicMock
from app.use_cases.chat.query_orchestrator import QueryOrchestrator, RELEVANCE_PROMPT

def test_negative_llm_response_suppresses_citations_and_prompt():
    mock_retrieval = MagicMock()
    mock_retrieval.retrieve_raw_candidates.return_value = [
        {"id": "c1", "text": "Unrelated document text", "metadata": {"source": "DOC-1.docx"}}
    ]
    mock_retrieval.select_relevant.return_value = [
        {"id": "c1", "text": "Unrelated document text", "metadata": {"source": "DOC-1.docx"}}
    ]

    mock_llm = MagicMock()
    mock_llm.generate.return_value = "I am sorry, but the provided documents do not contain information about pet allowances."

    orchestrator = QueryOrchestrator(
        retrieval=mock_retrieval,
        llm=mock_llm,
        query_normalizer=MagicMock(),
        pipeline_tracer=MagicMock(),
        provenance=MagicMock(),
        faq_store=None,
        faq_cache=None,
        response_cache=None,
        context_builder=MagicMock(),
        memory=MagicMock(),
        query_resolver=MagicMock(),
        conversation_logger=MagicMock(),
    )

    res = orchestrator.answer("Can I bring my dog to the office?", session_id="test_sess")

    assert res["citations"] == [], "Negative responses must not return citations"
    assert RELEVANCE_PROMPT not in res["answer"], "Negative responses must not include reference prompt"

def test_empty_retrieval_negative_response_suppresses_prompt():
    mock_retrieval = MagicMock()
    mock_retrieval.retrieve_raw_candidates.return_value = []
    mock_retrieval.select_relevant.return_value = []
    mock_retrieval.detect_unauthorized_relevance.return_value = None

    orchestrator = QueryOrchestrator(
        retrieval=mock_retrieval,
        llm=MagicMock(),
        query_normalizer=MagicMock(),
        pipeline_tracer=MagicMock(),
        provenance=MagicMock(),
        faq_store=None,
        faq_cache=None,
        response_cache=None,
        context_builder=MagicMock(),
        memory=MagicMock(),
        query_resolver=MagicMock(),
        conversation_logger=MagicMock(),
    )
    res = orchestrator.answer("Something completely non-existent", session_id="test_sess")

    assert res["citations"] == []
    assert RELEVANCE_PROMPT not in res["answer"]
