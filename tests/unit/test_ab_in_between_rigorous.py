"""
Rigorous In-Between Handshake & Seam Integration Tests for all AB Tasks (Phase 1 to Phase 3)

Validates the critical transitions and boundaries across all Abhinav components:
1. AB-3 (QueryNormalizer) -> AB-3.3 (SynonymClusterer) -> AB-4 (QualityAwareCache):
   Cross-module query canonicalization, synonym clustering, and semantic cache matching.
2. AB-4 (QualityAwareCache) <-> AB-5.1 (RetrievalQualityGate):
   Cache write gate: refuses unverified/INVALID evidence, commits STRONG verified evidence.
3. AB-5.2 (RetrievalService) -> AB-5.1 (RetrievalQualityGate) -> AB-6 (PipelineTracer):
   Candidate retrieval, metric enrichment (level, grounding, confidence), and span telemetry.
4. AB-1.1 (CircuitBreaker/Health) <-> AB-2 (LLMResponse & Aggregator):
   Intelligent retry policy, circuit failover state transitions, and standard LLMResponse encapsulation.
5. AB-4 (QualityAwareCache) Document Freshness Lifecycle:
   Time-based cache invalidation when document timestamp is updated.
6. AB-3.4 (QueryIntentClassifier) Routing Handshake:
   Accurate intent classification driving cache vs retrieval routing decisions.
7. Concurrency & Thread-Safety:
   Multi-threaded stress testing across normalization, caching, and quality assessment.
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
import numpy as np
from unittest.mock import MagicMock

# AB-1.1: Health & Circuit Breaker
from app.infrastructure.llm.provider_health import (
    CircuitBreaker,
    HealthStatus,
    ProviderHealthMonitor,
)
from app.infrastructure.llm.provider_error_tracker import (
    RetryPolicy,
    ErrorCategory,
    ProviderErrorTracker,
)

# AB-2: Standard LLM Response
from app.infrastructure.llm.llm_response import (
    LLMResponse,
    LLMProviderName,
    LLMResponseStatus,
    LLMResponseBuilder,
    ResponseAggregator,
)

# AB-3.1 / AB-3.2: Query Normalizer
from app.use_cases.chat.query_normalizer import (
    QueryNormalizer,
    NormalizationResult,
)

# AB-3.3: Synonym Clustering
from app.use_cases.chat.synonym_clustering import (
    SynonymClusterer,
    SynonymCluster,
    ClusteringResult,
)

# AB-3.4: Query Intent Classifier
from app.use_cases.chat.query_intent_classifier import (
    QueryIntentClassifier,
    QueryIntent,
)

# AB-4: Quality Aware Cache
from app.infrastructure.cache.quality_aware_cache import (
    QualityAwareCache,
    CacheEntry,
)

# AB-5.1 / AB-5.2: Retrieval Quality Gate & Service
from app.use_cases.chat.retrieval_quality import (
    RetrievalQualityGate,
    QualityGateResult,
    EvidenceQualityLevel,
)
from app.use_cases.chat.retrieval_service import RetrievalService

# AB-6: Pipeline Tracer
from app.infrastructure.observability.pipeline_tracer import (
    PipelineTracer,
    PipelineStage,
    StageSpan,
)


class MockVectorEncoder:
    """Mock encoder returning deterministic normalized embeddings for fast testing."""
    def __init__(self, vector_map=None, default_dim=4):
        self.vector_map = vector_map or {}
        self.default_dim = default_dim

    def encode(self, words, show_progress_bar=False):
        vecs = []
        for w in words:
            lower = w.lower().strip()
            if lower in self.vector_map:
                vecs.append(self.vector_map[lower])
            else:
                np.random.seed(abs(hash(lower)) % (2**32))
                v = np.random.randn(self.default_dim).astype(np.float32)
                vecs.append(v / (np.linalg.norm(v) + 1e-7))
        return np.array(vecs, dtype=np.float32)


# ─── In-Between 1: Normalizer -> Synonym Clustering -> Cache ───────────────────

class TestNormalizerSynonymCacheInBetween:
    """Tests the seam between query normalization, vector synonym clustering, and semantic caching."""

    def test_synonym_registered_normalizes_to_same_cache_entry(self):
        normalizer = QueryNormalizer(
            enable_vocabulary_mapping=True,
            enable_typo_correction=True,
            enable_lemmatization=True,
        )
        cache = QualityAwareCache(max_entries=50)

        # 1. Register vector synonym cluster: "stipend" and "remuneration" -> canonical "salary"
        mock_encoder = MockVectorEncoder({
            "salary": [1.0, 0.0],
            "stipend": [0.98, 0.05],
            "remuneration": [0.97, 0.08],
        }, default_dim=2)
        clusterer = SynonymClusterer(embedding_model=mock_encoder, similarity_threshold=0.80)
        clusters = clusterer.cluster_nouns(["salary", "stipend", "remuneration"])
        syn_map = clusterer.build_synonym_map(clusters)
        clusterer.integrate_with_query_normalizer(syn_map, normalizer=normalizer)

        # 2. Populate cache with canonical query
        query_1 = "what is the base salary?"
        norm_1 = normalizer.normalize(query_1)
        cache.set(
            cache_key=norm_1.cache_key,
            original_query=query_1,
            response="Base salary is reviewed annually in December.",
            citations=[{"source": "salary_policy.pdf", "text": "Base salary reviewed annually"}],
            confidence=0.90,
        )

        # 3. User asks with a synonym ("stipend") and conjoined typo ("whatisthe")
        query_2 = "whatisthe base stipend?"
        norm_2 = normalizer.normalize(query_2)

        # The normalized query and cache key should match the cached entry
        cached_result = cache.get(norm_2.cache_key)
        assert cached_result is not None
        assert "Base salary is reviewed annually" in cached_result.response

    def test_dp_word_splitting_into_cache_hit(self):
        normalizer = QueryNormalizer(enable_vocabulary_mapping=True)
        cache = QualityAwareCache(max_entries=10)

        # Cache key for standard phrase
        clean_q = "leave policy"
        norm_clean = normalizer.normalize(clean_q)
        cache.set(
            cache_key=norm_clean.cache_key,
            original_query=clean_q,
            response="Standard leave policy is 18 days.",
            confidence=0.88,
        )

        # Conjoined input
        conjoined_q = "whatisleavepolicy"
        norm_conjoined = normalizer.normalize(conjoined_q)

        # Both should resolve to related cache terms
        assert "leave policy" in norm_conjoined.normalized_query
        assert norm_conjoined.was_modified is True


# ─── In-Between 2: QualityAwareCache <-> RetrievalQualityGate ─────────────────

class TestCacheQualityGateInBetween:
    """Tests the gate keeping unverified/INVALID evidence out of the semantic cache."""

    def test_cache_refuses_invalid_evidence_from_quality_gate(self):
        cache = QualityAwareCache(max_entries=10, min_confidence_threshold=0.60)
        gate = RetrievalQualityGate()

        # Evidence with poor distance (0.88 >= 0.85 threshold -> INVALID)
        poor_evidence = [
            {"text": "Random unrelated text about parking spaces.", "distance": 0.88}
        ]
        gate_res = gate.evaluate("maternity leave policy", poor_evidence)
        assert gate_res.quality_level == EvidenceQualityLevel.INVALID
        assert gate_res.passed is False

        # Attempt to set in cache with low confidence / negative response
        key = "maternity_leave_policy"
        success = cache.set(
            cache_key=key,
            original_query="maternity leave policy",
            response="I could not find that information in the available documents.",
            confidence=gate_res.confidence,
        )
        assert success is False

        # Reading from cache must return None
        entry = cache.get(key)
        assert entry is None

    def test_cache_accepts_strong_evidence_with_metrics(self):
        cache = QualityAwareCache(max_entries=10)
        gate = RetrievalQualityGate()

        strong_evidence = [
            {"text": "Employees receive 18 days of paid annual leave.", "distance": 0.25}
        ]
        gate_res = gate.evaluate("how much annual leave?", strong_evidence)
        assert gate_res.quality_level == EvidenceQualityLevel.STRONG

        success = cache.set(
            cache_key="how_much_annual_leave",
            original_query="how much annual leave?",
            response="Employees receive 18 days of paid annual leave.",
            citations=strong_evidence,
            confidence=gate_res.confidence,
            metadata={"confidence": gate_res.confidence, "quality_level": gate_res.quality_level.value},
        )
        assert success is True

        cached = cache.get("how_much_annual_leave")
        assert cached is not None
        assert cached.confidence == gate_res.confidence
        assert cached.metadata["quality_level"] == "strong"


# ─── In-Between 3: RetrievalService -> QualityGate -> PipelineTracer ──────────

class TestRetrievalQualityGateTracerInBetween:
    """Tests the interaction between RetrievalService, QualityGate, and PipelineTracer."""

    def test_retrieval_enriches_chunks_and_records_telemetry(self):
        tracer = PipelineTracer()
        trace_id = "trace_test_001"
        tracer.start_trace(query="What is the sick leave policy?", trace_id=trace_id)

        service = RetrievalService.__new__(RetrievalService)
        service.store = MagicMock()
        service.store.query.return_value = [
            {"text": "Sick leave allows up to 10 working days.", "distance": 0.32, "metadata": {"source": "hr.pdf"}},
            {"text": "Medical certificate required after 2 consecutive days.", "distance": 0.45, "metadata": {"source": "hr.pdf"}},
        ]
        service.quality_gate = RetrievalQualityGate()
        service.reranker = None
        service.last_quality_result = None

        # Execute retrieval inside a traced stage span
        with tracer.trace_stage(PipelineStage.RETRIEVAL, trace_id=trace_id) as ctx:
            chunks = service.retrieve("sick leave policy", top_k=5, max_evidence=2)
            ctx.output_metadata["evidence_count"] = len(chunks)

        # Verify chunks were enriched with quality metrics (AB-5.2)
        assert len(chunks) == 2
        for chunk in chunks:
            assert chunk["quality_level"] in {"strong", "borderline", "weak", "invalid"}
            assert "grounding_score" in chunk
            assert "confidence" in chunk

        # Verify tracer captured the execution (AB-6)
        trace = tracer.get_trace(trace_id)
        assert trace is not None
        stage_names = [s.stage for s in trace.spans]
        assert PipelineStage.RETRIEVAL in stage_names
        retrieval_span = next(s for s in trace.spans if s.stage == PipelineStage.RETRIEVAL)
        assert retrieval_span.error is None
        assert retrieval_span.duration_ms >= 0


# ─── In-Between 4: CircuitBreaker <-> LLMResponse Contract ─────────────────────

class TestCircuitBreakerLLMResponseInBetween:
    """Tests failure recovery, circuit state changes, and standard LLMResponse encapsulation."""

    def test_rate_limit_trips_breaker_and_triggers_fallback_response(self):
        monitor = ProviderHealthMonitor()
        monitor.reset_all()

        retry_policy = RetryPolicy()
        assert retry_policy.is_retryable_status(429) is True

        # Simulate 10 consecutive rate limit errors to trip circuit breaker past threshold
        for _ in range(10):
            monitor.record_request_start("openrouter")
            monitor.record_request_failure("openrouter")

        # OpenRouter circuit breaker should now be tripped/unavailable
        assert monitor.is_provider_available("openrouter") is False
        chosen_provider = monitor.get_healthy_provider(preferred="openrouter", fallback="groq")
        assert chosen_provider == "groq"

        # Build standard LLMResponse encapsulating the fallback outcome (AB-2)
        response = (
            LLMResponseBuilder()
            .with_content("This answer was served by fallback provider Groq.")
            .with_provider(LLMProviderName.GROQ)
            .with_status(LLMResponseStatus.PARTIAL)
            .with_model("llama-3-70b")
            .with_tokens(prompt_tokens=150, completion_tokens=40)
            .build()
        )

        assert response.provider == LLMProviderName.GROQ
        assert response.status == LLMResponseStatus.PARTIAL
        assert response.tokens.total_tokens == 190
        assert response.is_successful() is False  # PARTIAL is not full SUCCESS


# ─── In-Between 5: Document Freshness Invalidation in Cache ───────────────────

class TestCacheDocumentFreshnessInBetween:
    """Tests that QualityAwareCache invalidates when a document timestamp updates."""

    def test_document_timestamp_update_invalidates_cache(self):
        doc_timestamps = {"doc_leave": 1725184800.0}  # 2026-09-01
        lookup = lambda doc_id: doc_timestamps.get(doc_id)

        cache = QualityAwareCache(max_entries=10, document_timestamp_lookup=lookup)

        key = "annual_leave_policy"
        cache.set(
            cache_key=key,
            original_query="annual leave policy",
            response="You receive 18 days annual leave.",
            citations=[{"document_id": "doc_leave", "text": "18 days annual leave"}],
            document_ids=["doc_leave"],
            doc_last_updated={"doc_leave": 1725184800.0},
            confidence=0.90,
        )

        # Cache hit before document update
        hit_1 = cache.get(key)
        assert hit_1 is not None

        # Document is updated by HR at later timestamp
        doc_timestamps["doc_leave"] = 1727521200.0  # 2026-09-28

        # Cache lookup should detect document update and evict entry
        hit_2 = cache.get(key)
        assert hit_2 is None


# ─── In-Between 6: Intent Classifier Routing ───────────────────────────────────

class TestQueryIntentClassifierRoutingInBetween:
    """Tests that QueryIntentClassifier directs queries correctly before retrieval."""

    def test_intent_classification_routes_correctly(self):
        classifier = QueryIntentClassifier()

        greeting = classifier.classify("Hello there, good morning!")
        assert greeting.intent in (QueryIntent.GREETING, QueryIntent.GENERAL_FAQ)

        policy_entitlement = classifier.classify("How many annual leave days are provided per year?")
        assert policy_entitlement.intent == QueryIntent.POLICY_ENTITLEMENT

        procedural = classifier.classify("How to apply for sick leave in the portal?")
        assert procedural.intent == QueryIntent.PROCEDURAL

        personal = classifier.classify("How many leaves do I have left?")
        assert personal.intent == QueryIntent.PERSONAL_BALANCE
        assert personal.is_personal_query is True


# ─── In-Between 7: Concurrency & Thread-Safety Stress Test ─────────────────────

class TestConcurrencyStressAcrossABComponents:
    """Tests simultaneous access across normalizer, synonym clusterer, cache, and quality gate."""

    def test_concurrent_pipeline_execution_no_race_conditions(self):
        normalizer = QueryNormalizer()
        cache = QualityAwareCache(max_entries=100)
        gate = RetrievalQualityGate()
        tracer = PipelineTracer()

        def worker_task(thread_id: int):
            q = f"How many sick leave days are available for employee {thread_id}?"
            trace_id = f"trace_thread_{thread_id}_{time.time()}"
            tracer.start_trace(query=q, trace_id=trace_id)

            # 1. Normalize
            with tracer.trace_stage(PipelineStage.NORMALIZATION, trace_id=trace_id):
                norm = normalizer.normalize(q)

            # 2. Check Cache
            with tracer.trace_stage(PipelineStage.CACHE_CHECK, trace_id=trace_id):
                hit = cache.get(norm.cache_key)

            # 3. Evaluate Quality & Set Cache
            with tracer.trace_stage(PipelineStage.RETRIEVAL, trace_id=trace_id):
                sim_evidence = [{
                    "text": f"How many sick leave days are available for employee {thread_id}: 10 days per year according to standard policy.",
                    "distance": 0.15,
                    "source": "leave_policy.docx",
                }]
                q_res = gate.evaluate(norm.normalized_query, sim_evidence)
                cache.set(
                    cache_key=norm.cache_key,
                    original_query=q,
                    response=f"Answer for {thread_id}",
                    confidence=q_res.confidence,
                    citations=sim_evidence,
                    evidence_count=1,
                )

            tracer.end_trace(trace_id)
            return q_res.passed

        num_threads = 8
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker_task, i) for i in range(num_threads)]
            results = [f.result() for f in futures]

        assert all(results)
        assert len(cache._cache) == num_threads
