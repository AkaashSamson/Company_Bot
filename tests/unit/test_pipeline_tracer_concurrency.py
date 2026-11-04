import time
import threading
import concurrent.futures
from app.infrastructure.observability.pipeline_tracer import PipelineTracer, PipelineStage


def test_concurrent_pipeline_traces_do_not_overwrite_or_drop():
    """
    Test that two concurrent requests running in separate threads/tasks
    do not overwrite each other's trace or spans when trace_id is not explicitly passed.
    """
    tracer = PipelineTracer.create_new(enable_tracing=True)

    barrier_start = threading.Barrier(2)

    def run_query_1():
        # Wait for both threads to be ready
        barrier_start.wait()
        trace1 = tracer.start_trace("Query 1 - casual leaves")
        
        # Stage 1: Normalization
        with tracer.trace_stage(PipelineStage.NORMALIZATION):
            time.sleep(0.04)
        
        # Stage 2: LLM Generation
        with tracer.trace_stage(PipelineStage.LLM_GENERATION):
            time.sleep(0.04)

        completed1 = tracer.end_trace(
            total_tokens=100,
            final_response="Response 1 - Casual leaves info",
        )
        return completed1

    def run_query_2():
        barrier_start.wait()
        # Stagger slightly so Query 1 starts, then Query 2 starts while Query 1 is in-flight
        time.sleep(0.01)
        trace2 = tracer.start_trace("Query 2 - all leaves")

        # Stage 1: Normalization
        with tracer.trace_stage(PipelineStage.NORMALIZATION):
            time.sleep(0.02)

        # Stage 2: LLM Generation
        with tracer.trace_stage(PipelineStage.LLM_GENERATION):
            time.sleep(0.02)

        completed2 = tracer.end_trace(
            total_tokens=200,
            final_response="Response 2 - All leaves info",
        )
        return completed2

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future1 = executor.submit(run_query_1)
        future2 = executor.submit(run_query_2)

        completed1 = future1.result()
        completed2 = future2.result()

    # 1. Neither trace should be dropped / None
    assert completed1 is not None, "Query 1 trace was dropped (pipeline_trace_not_found)"
    assert completed2 is not None, "Query 2 trace was dropped (pipeline_trace_not_found)"

    # 2. Each trace must retain its own query and response
    assert completed1.query == "Query 1 - casual leaves"
    assert completed2.query == "Query 2 - all leaves"
    assert completed1.final_response == "Response 1 - Casual leaves info"
    assert completed2.final_response == "Response 2 - All leaves info"

    # 3. Each trace must have its own 2 spans without span contamination
    assert len(completed1.spans) == 2, f"Query 1 should have 2 spans, got {len(completed1.spans)}"
    assert len(completed2.spans) == 2, f"Query 2 should have 2 spans, got {len(completed2.spans)}"
