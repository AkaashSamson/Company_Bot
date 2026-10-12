"""
Comprehensive Pipeline Tracing Infrastructure

Implements 8-stage execution tracking for the RAG pipeline:
1. NORMALIZATION: Query normalization and preprocessing
2. CACHE_CHECK: Semantic cache lookup
3. FAQ_CHECK: FAQ similarity cache lookup
4. QUERY_EXPANSION: Query expansion with synonyms
5. RETRIEVAL: Vector database retrieval
6. QUALITY_ASSESSMENT: Evidence quality gate assessment
7. LLM_GENERATION: LLM response generation
8. CACHE_WRITE: Writing to semantic cache

Features:
- Context manager spans for automatic timing
- Per-stage metrics (latency, token counts)
- Integration with ObservabilityManager (Akaash's design)
- Thread-safe operation
"""

import functools
import inspect
import logging
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Generator, Optional

from app.core import settings
from app.core.settings import (
    LANGCHAIN_API_KEY,
    LANGCHAIN_ENDPOINT,
    LANGCHAIN_PROJECT,
    LANGCHAIN_TRACING_V2,
)

logger = logging.getLogger(__name__)

# Activate LangSmith if enabled
if LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY
    os.environ["LANGCHAIN_ENDPOINT"] = LANGCHAIN_ENDPOINT
    os.environ["LANGCHAIN_PROJECT"] = LANGCHAIN_PROJECT
    logger.info("LangSmith tracing enabled → project '%s'", LANGCHAIN_PROJECT)
else:
    os.environ["LANGCHAIN_TRACING_V2"] = "false"



class PipelineStage(Enum):
    """
    8 stages of the RAG pipeline (Task AB-6.1 specification):
    1. CONTEXT_REWRITE: Multi-turn contextual query rewriting
    2. NORMALIZATION: Query normalization and preprocessing
    3. CACHE_LOOKUP: Semantic and FAQ cache lookup
    4. VECTOR_RETRIEVAL: Vector database retrieval
    5. RERANKING: Cross-encoder and semantic reranking
    6. QUALITY_GATE: Evidence quality gate assessment
    7. LLM_GENERATION: LLM response generation
    8. POST_GUARDRAILS: Post-generation guardrails and cache write
    """
    # 8 Canonical Stages:
    CONTEXT_REWRITE = "context_rewrite"
    NORMALIZATION = "normalization"
    CACHE_LOOKUP = "cache_lookup"
    VECTOR_RETRIEVAL = "vector_retrieval"
    RERANKING = "reranking"
    QUALITY_GATE = "quality_gate"
    LLM_GENERATION = "llm_generation"
    POST_GUARDRAILS = "post_guardrails"

    # Compatibility / Alternative Aliases
    CACHE_CHECK = "cache_check"
    FAQ_CHECK = "faq_check"
    QUERY_EXPANSION = "query_expansion"
    RETRIEVAL = "retrieval"
    QUALITY_ASSESSMENT = "quality_assessment"
    CACHE_WRITE = "cache_write"


@dataclass
class StageSpan:
    """
    Represents a single stage span in the pipeline.
    
    Tracks:
    - Stage name and timing
    - Input/output metadata
    - Token usage (for LLM stages)
    - Error information
    """
    stage: PipelineStage
    start_time: float
    start_perf: float = field(default_factory=time.perf_counter)
    end_time: Optional[float] = None
    duration_ms: float = 0.0
    input_metadata: dict[str, Any] = field(default_factory=dict)
    output_metadata: dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: Optional[str] = None
    
    def finish(self, output_metadata: Optional[dict[str, Any]] = None) -> None:
        """Mark span as finished and calculate duration."""
        self.end_time = time.time()
        self.duration_ms = (time.perf_counter() - self.start_perf) * 1000.0
        if output_metadata:
            self.output_metadata = output_metadata

    def set_output(self, **kwargs) -> None:
        """Set output metadata fields for this stage."""
        self.output_metadata.update(kwargs)

    def record_tokens(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        tokens_used: Optional[int] = None,
    ) -> None:
        """Record token usage for this stage span."""
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.tokens_used = tokens_used if tokens_used is not None else (prompt_tokens + completion_tokens)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "stage": self.stage.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "input_metadata": self.input_metadata,
            "output_metadata": self.output_metadata,
            "tokens_used": self.tokens_used,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "error": self.error,
        }


class TraceContext:
    """
    Context manager for measuring stage durations and token metrics (Task AB-6.1).
    
    Provides fine-grained stage tracking with duration timing, token recording,
    output metadata setting, and error capture.
    
    Usage:
        with TraceContext(stage=PipelineStage.VECTOR_RETRIEVAL) as ctx:
            results = retrieve(query)
            ctx.record_tokens(prompt_tokens=10, completion_tokens=5)
            ctx.set_output(result_count=len(results))
    """
    def __init__(
        self,
        stage: PipelineStage,
        tracer: Optional['PipelineTracer'] = None,
        trace_id: Optional[str] = None,
        input_metadata: Optional[dict[str, Any]] = None,
    ):
        self.stage = stage
        self.tracer = tracer
        self.trace_id = trace_id
        self.input_metadata = input_metadata or {}
        self.output_metadata: dict[str, Any] = {}
        self.span: Optional[StageSpan] = None
        self.start_time: float = 0.0
        self.end_time: Optional[float] = None
        self.duration_ms: float = 0.0
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.tokens_used: int = 0
        self.error: Optional[str] = None

    def __enter__(self) -> 'TraceContext':
        self.start_time = time.time()
        self.start_perf = time.perf_counter()
        tracer = self.tracer
        if tracer is None:
            try:
                tracer = get_pipeline_tracer()
                self.tracer = tracer
            except Exception:
                tracer = None

        if tracer and getattr(tracer, "enable_tracing", True):
            self.span = StageSpan(
                stage=self.stage,
                start_time=self.start_time,
            start_perf=self.start_perf,
                input_metadata=dict(self.input_metadata),
            )
            with tracer._lock:
                trace = tracer._traces.get(self.trace_id) if self.trace_id else tracer._current_trace
                if trace:
                    trace.add_span(self.span)
                    tracer._current_span = self.span
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.end_time = time.time()
        self.duration_ms = (time.perf_counter() - self.start_perf) * 1000.0

        if exc_val is not None:
            self.error = str(exc_val)
            if self.span:
                self.span.error = self.error
            stage_str = self.stage.value if hasattr(self.stage, "value") else str(self.stage)
            logger.warning("pipeline_stage_error stage=%s error=%s", stage_str, exc_val)

        if self.span:
            if self.prompt_tokens or self.completion_tokens or self.tokens_used:
                self.span.prompt_tokens = self.prompt_tokens
                self.span.completion_tokens = self.completion_tokens
                self.span.tokens_used = self.tokens_used or (self.prompt_tokens + self.completion_tokens)
            else:
                self.prompt_tokens = self.span.prompt_tokens
                self.completion_tokens = self.span.completion_tokens
                self.tokens_used = self.span.tokens_used
            self.span.finish(output_metadata=self.output_metadata)

        return False  # Propagate exceptions

    def record_tokens(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        tokens_used: Optional[int] = None,
    ) -> None:
        """Record token metrics for this stage."""
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.tokens_used = tokens_used if tokens_used is not None else (prompt_tokens + completion_tokens)
        if self.span:
            self.span.prompt_tokens = self.prompt_tokens
            self.span.completion_tokens = self.completion_tokens
            self.span.tokens_used = self.tokens_used
        if self.tracer and hasattr(self.tracer, "record_tokens"):
            self.tracer.record_tokens(self.stage, prompt_tokens, completion_tokens)

    def set_output(self, **kwargs) -> None:
        """Set output metadata for this stage."""
        self.output_metadata.update(kwargs)
        if self.span:
            self.span.output_metadata.update(kwargs)

    def to_dict(self) -> dict:
        """Convert context state to dictionary."""
        return {
            "stage": self.stage.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "input_metadata": self.input_metadata,
            "output_metadata": self.output_metadata,
            "tokens_used": self.tokens_used,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "error": self.error,
        }


@dataclass 
class PipelineTrace:
    """
    Complete trace of a single request through the pipeline.
    
    Contains all stage spans and aggregate metrics.
    """
    trace_id: str
    query: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    total_duration_ms: float = 0.0
    spans: list[StageSpan] = field(default_factory=list)
    cache_hit: bool = False
    early_exit: bool = False
    exit_stage: Optional[PipelineStage] = None
    exit_reason: Optional[str] = None
    final_response: Optional[str] = None
    total_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def add_span(self, span: StageSpan) -> None:
        """Add a stage span to the trace."""
        self.spans.append(span)
    
    def finish(
        self,
        cache_hit: bool = False,
        early_exit: bool = False,
        exit_stage: Optional[PipelineStage] = None,
        exit_reason: Optional[str] = None,
        total_tokens: int = 0,
        final_response: Optional[str] = None,
    ) -> None:
        """Mark trace as finished and calculate totals."""
        self.end_time = time.time()
        self.total_duration_ms = (self.end_time - self.start_time) * 1000
        self.cache_hit = cache_hit
        self.early_exit = early_exit
        self.exit_stage = exit_stage
        self.exit_reason = exit_reason
        self.total_tokens = total_tokens
        if final_response is not None:
            self.final_response = final_response
        
        # Sum tokens from all spans, falling back to passed total_tokens
        span_tokens = sum(s.tokens_used for s in self.spans)
        self.total_tokens = span_tokens if span_tokens > 0 else total_tokens
    
    def get_stage_duration(self, stage: PipelineStage) -> float:
        """Get duration of a specific stage."""
        for span in self.spans:
            if span.stage == stage:
                return span.duration_ms
        return 0.0
    
    def get_stage_metrics(self) -> dict[str, dict]:
        """Get metrics for all stages."""
        metrics = {}
        for span in self.spans:
            metrics[span.stage.value] = {
                "duration_ms": span.duration_ms,
                "tokens": span.tokens_used,
                "error": span.error,
            }
        return metrics
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "trace_id": self.trace_id,
            "query": self.query,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_duration_ms": self.total_duration_ms,
            "spans": [s.to_dict() for s in self.spans],
            "cache_hit": self.cache_hit,
            "early_exit": self.early_exit,
            "exit_stage": self.exit_stage.value if self.exit_stage else None,
            "exit_reason": self.exit_reason,
            "total_tokens": self.total_tokens,
            "metadata": self.metadata,
        }


class PipelineTracer:
    """
    Comprehensive pipeline tracer with 8-stage tracking.
    
    Features:
    - Context manager for automatic span management
    - Thread-safe trace creation
    - Integration point with Akaash's ObservabilityManager
    - Trace storage and retrieval
    """
    
    _instance = None
    _lock = threading.Lock()
    _allow_new_instance = False
    
    def __new__(cls, enable_tracing: bool = True, max_traces: int = 1000) -> 'PipelineTracer':
        """Singleton pattern for global tracing, unless _allow_new_instance is True."""
        if cls._allow_new_instance:
            instance = super().__new__(cls)
            instance._initialized = False
            return instance
        
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    @classmethod
    def create_new(cls, enable_tracing: bool = True, max_traces: int = 1000) -> 'PipelineTracer':
        """Create a new non-singleton instance for testing."""
        cls._allow_new_instance = True
        try:
            return cls(enable_tracing=enable_tracing, max_traces=max_traces)
        finally:
            cls._allow_new_instance = False
    
    def __init__(
        self,
        enable_tracing: bool = True,
        max_traces: int = 1000,
    ):
        """
        Initialize pipeline tracer.
        
        Args:
            enable_tracing: Whether tracing is enabled
            max_traces: Maximum number of traces to keep in memory
        """
        # Handle singleton - don't reinitialize if already initialized
        if getattr(self, '_initialized', False):
            # Update settings if provided
            if enable_tracing is not True or max_traces != 1000:
                self.enable_tracing = enable_tracing
                self.max_traces = max_traces
            return
        
        if getattr(self, '_allow_new_instance', False):
            # Allow fresh initialization for test instances
            pass
        elif PipelineTracer._instance is not None and PipelineTracer._instance is not self:
            # This is the singleton - just update settings
            self.enable_tracing = enable_tracing
            self.max_traces = max_traces
            self._initialized = True
            return
        
        self.enable_tracing = enable_tracing
        self.max_traces = max_traces
        
        self._traces: dict[str, PipelineTrace] = {}
        self._current_trace: Optional[PipelineTrace] = None
        self._current_span: Optional[StageSpan] = None
        self._lock = threading.RLock()
        
        # Callback for observability integration
        self._observability_callback: Optional[Callable[[PipelineTrace], None]] = None
        
        self._initialized = True
        
        logger.info(
            "pipeline_tracer initialized enable=%s max_traces=%d",
            enable_tracing, max_traces
        )
    
    def set_observability_callback(
        self,
        callback: Callable[[PipelineTrace], None],
    ) -> None:
        """
        Set callback for observability integration.
        
        The callback will be called with each completed trace
        for integration with Akaash's ObservabilityManager.
        """
        self._observability_callback = callback
        logger.info("pipeline_tracer observability_callback set")
    
    def start_trace(
        self,
        query: str,
        trace_id: Optional[str] = None,
    ) -> PipelineTrace:
        """
        Start a new pipeline trace.
        
        Args:
            query: User query being traced
            trace_id: Optional trace ID (generated if not provided)
            
        Returns:
            New PipelineTrace object
        """
        if not self.enable_tracing:
            return None
        
        import uuid
        
        trace = PipelineTrace(
            trace_id=trace_id or str(uuid.uuid4()),
            query=query,
        )
        
        with self._lock:
            self._traces[trace.trace_id] = trace
            self._current_trace = trace
            
            # Cleanup old traces if needed
            if len(self._traces) > self.max_traces:
                self._cleanup_old_traces()
        
        logger.debug("pipeline_trace_started trace_id=%s query=%s", trace.trace_id, query)
        
        return trace
    
    def end_trace(
        self,
        trace_id: Optional[str] = None,
        cache_hit: bool = False,
        early_exit: bool = False,
        exit_stage: Optional[PipelineStage] = None,
        exit_reason: Optional[str] = None,
        total_tokens: int = 0,
        final_response: Optional[str] = None,
    ) -> Optional[PipelineTrace]:
        """
        End the current or specified trace.
        
        Args:
            trace_id: Trace to end (current if not specified)
            cache_hit: Whether cache was hit
            early_exit: Whether early exit occurred
            exit_stage: Stage where early exit happened
            exit_reason: Reason for early exit
            total_tokens: Total tokens used
            final_response: Final generated answer text
            
        Returns:
            Completed PipelineTrace
        """
        if not self.enable_tracing:
            return None
        
        with self._lock:
            if trace_id:
                trace = self._traces.get(trace_id)
            else:
                trace = self._current_trace
            
            if trace is None:
                logger.warning("pipeline_trace_not_found trace_id=%s", trace_id)
                return None
            
            trace.finish(
                cache_hit=cache_hit,
                early_exit=early_exit,
                exit_stage=exit_stage,
                exit_reason=exit_reason,
                total_tokens=total_tokens,
                final_response=final_response,
            )
            
            # Call observability callback or auto-dispatch to ObservabilityManager
            if self._observability_callback:
                try:
                    self._observability_callback(trace)
                except Exception as e:
                    logger.error("observability_callback_failed error=%s", e)
            else:
                try:
                    from app.infrastructure.observability.manager import get_observability_manager
                    get_observability_manager().dispatch_trace(trace)
                except Exception as e:
                    logger.warning("observability_autodispatch_failed error=%s", e)
            
            self._current_trace = None
            
            logger.info(
                "pipeline_trace_completed trace_id=%s duration_ms=%.2f cache_hit=%s tokens=%d",
                trace.trace_id, trace.total_duration_ms, cache_hit, total_tokens
            )
            
            return trace
    
    def trace_context(
        self,
        stage: PipelineStage,
        trace_id: Optional[str] = None,
        input_metadata: Optional[dict[str, Any]] = None,
    ) -> TraceContext:
        """Create a TraceContext context manager for the given stage (Task AB-6.1)."""
        return TraceContext(stage=stage, tracer=self, trace_id=trace_id, input_metadata=input_metadata)

    @contextmanager
    def trace_stage(
        self,
        stage: PipelineStage,
        trace_id: Optional[str] = None,
        input_metadata: Optional[dict[str, Any]] = None,
    ) -> Generator[StageSpan, None, None]:
        """
        Context manager for tracing a pipeline stage.
        
        Usage:
            with tracer.trace_stage(PipelineStage.RETRIEVAL, input_metadata={"query": "..."}):
                # Do retrieval
                results = retrieval.retrieve(query)
        
        Args:
            stage: Pipeline stage being traced
            trace_id: Trace to add span to
            input_metadata: Input metadata for the stage
            
        Yields:
            StageSpan that is finished after the stage completes
        """
        if not self.enable_tracing:
            yield None
            return
        
        with TraceContext(stage=stage, tracer=self, trace_id=trace_id, input_metadata=input_metadata) as ctx:
            yield ctx.span
    
    def record_tokens(
        self,
        stage: PipelineStage,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        """Record token usage for current/last span."""
        with self._lock:
            span = self._current_span
            if span and span.stage == stage:
                span.prompt_tokens = prompt_tokens
                span.completion_tokens = completion_tokens
                span.tokens_used = prompt_tokens + completion_tokens

    def record_llm_call(
        self,
        model: str,
        token_usage: Any,
        latency_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
        prompt: Optional[Any] = None,
        completion: Optional[Any] = None,
    ) -> None:
        """Loosely coupled delegate to ObservabilityManager for recording LLM calls."""
        try:
            from app.infrastructure.observability.manager import get_observability_manager
            get_observability_manager().record_llm_call(
                model=model,
                token_usage=token_usage,
                latency_ms=latency_ms,
                metadata=metadata,
                prompt=prompt,
                completion=completion,
            )
        except Exception as exc:
            logger.debug("PipelineTracer record_llm_call error: %s", exc)
    
    def get_trace(self, trace_id: str) -> Optional[PipelineTrace]:
        """Get a specific trace by ID."""
        with self._lock:
            return self._traces.get(trace_id)
    
    def get_recent_traces(self, limit: int = 10) -> list[PipelineTrace]:
        """Get most recent traces."""
        with self._lock:
            traces = sorted(
                self._traces.values(),
                key=lambda t: t.start_time,
                reverse=True
            )
            return traces[:limit]
    
    def _cleanup_old_traces(self) -> None:
        """Remove oldest traces when limit exceeded."""
        if len(self._traces) <= self.max_traces:
            return
        
        # Sort by start time and remove oldest
        sorted_traces = sorted(
            self._traces.items(),
            key=lambda x: x[1].start_time,
        )
        
        to_remove = len(self._traces) - self.max_traces + 100  # Remove extra buffer
        for trace_id, _ in sorted_traces[:to_remove]:
            del self._traces[trace_id]
    
    def get_statistics(self) -> dict:
        """Get tracer statistics."""
        with self._lock:
            if not self._traces:
                return {
                    "total_traces": 0,
                    "cache_hit_rate": 0.0,
                    "early_exit_rate": 0.0,
                    "avg_duration_ms": 0.0,
                }
            
            total = len(self._traces)
            cache_hits = sum(1 for t in self._traces.values() if t.cache_hit)
            early_exits = sum(1 for t in self._traces.values() if t.early_exit)
            total_duration = sum(t.total_duration_ms for t in self._traces.values())
            
            return {
                "total_traces": total,
                "cache_hit_rate": (cache_hits / total * 100) if total > 0 else 0,
                "early_exit_rate": (early_exits / total * 100) if total > 0 else 0,
                "avg_duration_ms": total_duration / total if total > 0 else 0,
            }


# Global singleton instance
_pipeline_tracer: Optional[PipelineTracer] = None


def get_pipeline_tracer() -> PipelineTracer:
    """Get the global pipeline tracer instance."""
    global _pipeline_tracer
    if _pipeline_tracer is None:
        _pipeline_tracer = PipelineTracer()
    return _pipeline_tracer


# Convenience function for context manager
def trace_stage(
    stage: PipelineStage,
    query: str = "",
    **kwargs,
) -> Generator[StageSpan, None, None]:
    """Convenience function for tracing a stage."""
    tracer = get_pipeline_tracer()
    return tracer.trace_stage(stage, **kwargs)


class _NoOpSpan:
    """Returned when tracing is disabled — all methods are safe no-ops."""
    def end(self, outputs: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> None:
        pass

    def update(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


def _is_langfuse_active() -> bool:
    provider = getattr(settings, "OBSERVABILITY_PROVIDER", "").lower()
    return provider == "langfuse"


def _sanitize_inputs(func: Callable, args: tuple, kwargs: dict) -> Dict[str, Any]:
    """Extract clean, user-meaningful inputs without leaking 'self' or sensitive keys."""
    sensitive_keys = {"api_key", "secret", "password", "token", "auth", "authorization", "secret_key"}
    cleaned: Dict[str, Any] = {}

    try:
        sig = inspect.signature(func)
        bound = sig.bind_partial(*args, **kwargs)
        for name, val in bound.arguments.items():
            if name in ("self", "cls"):
                continue
            if any(s in name.lower() for s in sensitive_keys):
                cleaned[name] = "[REDACTED]"
            elif isinstance(val, (str, int, float, bool, list, dict)) or val is None:
                cleaned[name] = val
            else:
                cleaned[name] = str(val)[:200]
    except Exception:
        # Fallback if binding fails
        for k, v in kwargs.items():
            if any(s in k.lower() for s in sensitive_keys):
                cleaned[k] = "[REDACTED]"
            elif isinstance(v, (str, int, float, bool)):
                cleaned[k] = v
        if args and len(args) > 1 and isinstance(args[1], str):
            cleaned["query"] = args[1]
        elif args and len(args) > 0 and isinstance(args[0], str):
            cleaned["query"] = args[0]

    return cleaned


def _sanitize_output(result: Any) -> Any:
    """Sanitize output object for trace display, preserving documents and chunks."""
    if isinstance(result, dict):
        clean = {}
        for k, v in result.items():
            if k in ("answer", "question", "cache_hit", "tokens", "is_latest", "model", "latency_ms", "chunks", "documents", "evidence", "chunks_count", "candidates_out", "matched_faq"):
                clean[k] = v
            elif k == "citations" and isinstance(v, list):
                clean[k] = [
                    {"document": getattr(c, "document_name", str(c)), "page": getattr(c, "page_number", None)}
                    if hasattr(c, "document_name") else str(c)[:100]
                    for c in v[:5]
                ]
            elif isinstance(v, (str, int, float, bool, list, dict)):
                clean[k] = v
        return clean
    elif isinstance(result, list):
        # Format candidate documents / chunks cleanly for trace visibility
        return [
            {
                "content": str(e.get("text", "") or e.get("content", ""))[:300].strip(),
                "source": e.get("metadata", {}).get("source", "unknown") if isinstance(e.get("metadata"), dict) else e.get("source", "unknown"),
                "chunk_id": e.get("id") or e.get("chunk_id"),
                "score": e.get("rerank_score") or e.get("score") or e.get("distance"),
            }
            if isinstance(e, dict) else str(e)[:100]
            for e in result
        ]
    elif isinstance(result, str):
        return result
    return str(result)[:500]


@contextmanager
def trace_step(
    name: str,
    inputs: Optional[Any] = None,
    run_type: str = "chain",
    metadata: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Generator[Any, None, None]:
    """Context manager for tracing an internal pipeline step."""
    # 1. ObservabilityManager Dispatch (Langfuse / Phoenix)
    provider_name = getattr(settings, "OBSERVABILITY_PROVIDER", "").lower()
    if provider_name in ("langfuse", "phoenix") or _is_langfuse_active():
        try:
            from app.infrastructure.observability.manager import get_observability_manager
            mgr = get_observability_manager()
            with mgr.trace_step(
                name=name,
                inputs=inputs,
                run_type=run_type,
                metadata=metadata,
                session_id=session_id,
                user_id=user_id,
            ) as span:
                yield span
            return
        except Exception as exc:
            logger.debug("ObservabilityManager trace_step dispatch error: %s", exc)
            yield _NoOpSpan()
            return

    # 2. LangSmith Dispatch
    if LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY:
        try:
            from langsmith import Client
            client = Client()
            run = client.create_run(
                name=name,
                run_type=run_type,
                inputs=inputs if isinstance(inputs, dict) else {"input": inputs},
                project_name=LANGCHAIN_PROJECT,
            )
            try:
                yield run
            except Exception as exc:
                run.end(error=str(exc))
                client.update_run(run.id, error=str(exc))
                raise
            else:
                client.update_run(run.id)
            return
        except Exception as exc:
            logger.debug("LangSmith trace_step failed: %s", exc)
            yield _NoOpSpan()
            return

    # 3. No-op
    yield _NoOpSpan()


def traceable(name: Optional[str] = None, run_type: str = "chain") -> Callable:
    """Decorator that wraps a function or method in a trace span.
    
    Compatible with Langfuse v4 canonical types and LangSmith.
    """
    def decorator(fn: Callable) -> Callable:
        span_name = name or fn.__name__

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                provider_name = getattr(settings, "OBSERVABILITY_PROVIDER", "").lower()
                is_active = (provider_name in ("langfuse", "phoenix")) or _is_langfuse_active() or (LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY)
                if not is_active:
                    return await fn(*args, **kwargs)

                clean_in = _sanitize_inputs(fn, args, kwargs)
                with trace_step(name=span_name, inputs=clean_in, run_type=run_type) as span:
                    try:
                        res = await fn(*args, **kwargs)
                        if hasattr(span, "update"):
                            span.update(output=_sanitize_output(res))
                        return res
                    except Exception as exc:
                        if hasattr(span, "end"):
                            span.end(error=str(exc))
                        raise
            return async_wrapper
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                provider_name = getattr(settings, "OBSERVABILITY_PROVIDER", "").lower()
                is_active = (provider_name in ("langfuse", "phoenix")) or _is_langfuse_active() or (LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY)
                if not is_active:
                    return fn(*args, **kwargs)

                clean_in = _sanitize_inputs(fn, args, kwargs)
                with trace_step(name=span_name, inputs=clean_in, run_type=run_type) as span:
                    try:
                        res = fn(*args, **kwargs)
                        if hasattr(span, "update"):
                            span.update(output=_sanitize_output(res))
                        return res
                    except Exception as exc:
                        if hasattr(span, "end"):
                            span.end(error=str(exc))
                        raise
            return sync_wrapper

    return decorator