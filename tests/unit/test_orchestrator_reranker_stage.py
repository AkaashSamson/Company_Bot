from unittest.mock import MagicMock
from app.use_cases.chat.query_orchestrator import QueryOrchestrator
from app.use_cases.chat.retrieval_service import RetrievalService
from app.infrastructure.observability.pipeline_tracer import PipelineTracer, PipelineStage

def test_orchestrator_emits_reranking_stage_with_13_in_and_4_out():
    tracer = PipelineTracer.create_new(enable_tracing=True)
    
    # 13 mock raw vector candidates
    raw_13 = [
        {"id": f"chunk-{i}", "text": f"Policy chunk text {i}", "metadata": {"source": f"DOC-{i}.docx"}, "distance": 0.1 * i}
        for i in range(13)
    ]
    # 4 top reranked chunks
    reranked_4 = [
        {**raw_13[i], "rerank_score": 0.95 - (0.1 * i)}
        for i in [2, 0, 5, 8]
    ]

    mock_retrieval = MagicMock()
    mock_retrieval.retrieve_raw_candidates.return_value = raw_13
    mock_retrieval.select_relevant.side_effect = lambda q, c, **kw: c

    mock_reranker = MagicMock()
    mock_reranker.rerank.return_value = reranked_4

    mock_llm = MagicMock()
    mock_llm.generate.return_value = "Here is the policy answer."

    orchestrator = QueryOrchestrator(
        retrieval=mock_retrieval,
        reranker=mock_reranker,
        llm=mock_llm,
        pipeline_tracer=tracer,
        provenance=MagicMock(),
        faq_store=None,
        faq_cache=None,
        response_cache=None,
        context_builder=MagicMock(),
        memory=MagicMock(),
        query_resolver=MagicMock(),
        query_normalizer=MagicMock(),
        conversation_logger=MagicMock(),
    )

    res = orchestrator.answer("What is the leave policy?")

    trace = list(tracer._traces.values())[-1]
    stage_names = [s.stage for s in trace.spans]
    assert PipelineStage.VECTOR_RETRIEVAL in stage_names
    assert PipelineStage.RERANKING in stage_names

    # Check vector retrieval metadata: 13 chunks
    ret_span = next(s for s in trace.spans if s.stage == PipelineStage.VECTOR_RETRIEVAL)
    assert ret_span.output_metadata["chunks_count"] == 13
    assert len(ret_span.output_metadata["documents"]) == 13

    # Check reranking metadata: 13 in, 4 out
    rerank_span = next(s for s in trace.spans if s.stage == PipelineStage.RERANKING)
    assert rerank_span.input_metadata["candidates_in"] == 13
    assert rerank_span.output_metadata["candidates_out"] == 4
    assert len(rerank_span.output_metadata["documents"]) == 4
    assert rerank_span.output_metadata["documents"][0]["chunk_id"] == "chunk-2"
