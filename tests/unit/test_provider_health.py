"""
Tests for Provider Health Monitoring & Circuit Breaker (AB-1.1)

Validates:
- CircuitBreaker state transitions (HEALTHY -> DEGRADED -> OPEN -> RECOVERING -> HEALTHY)
- Automatic timeout-based half-open recovery
- ProviderHealthMonitor metrics tracking and failover selection
- ProviderErrorTracker error classification and diagnostics
- RetryPolicy intelligent retry categorization (retry 429/5xx, fail-fast 401/403)
"""

import time
import pytest

from app.infrastructure.llm.provider_health import (
    CircuitBreaker,
    HealthStatus,
    ProviderHealthMetrics,
    ProviderHealthMonitor,
    get_provider_health_monitor,
)
from app.infrastructure.llm.provider_error_tracker import (
    ErrorCategory,
    ErrorStats,
    ProviderErrorTracker,
    RetryPolicy,
    TrackedError,
    get_error_tracker,
)


class TestCircuitBreaker:
    """Test suite for CircuitBreaker state transitions."""

    def test_initial_state_healthy(self):
        cb = CircuitBreaker(provider_name="test_provider", failure_threshold=3, timeout_seconds=1.0)
        assert cb.state == HealthStatus.HEALTHY
        assert cb.can_execute() is True

    def test_transition_to_degraded(self):
        cb = CircuitBreaker(provider_name="test_provider", failure_threshold=3, timeout_seconds=1.0)
        
        # 3 failures -> DEGRADED
        for _ in range(3):
            cb.record_failure()
            
        assert cb.state == HealthStatus.DEGRADED
        assert cb.can_execute() is True  # Still allowed to execute in degraded state

    def test_transition_to_open_or_unhealthy(self):
        cb = CircuitBreaker(provider_name="test_provider", failure_threshold=3, timeout_seconds=1.0)
        
        # 6 failures (2x threshold) -> UNHEALTHY / OPEN
        for _ in range(6):
            cb.record_failure()
            
        assert cb.state in (HealthStatus.OPEN, HealthStatus.UNHEALTHY)
        assert cb.can_execute() is False

    def test_recovery_after_timeout(self):
        cb = CircuitBreaker(
            provider_name="test_provider",
            failure_threshold=2,
            success_threshold=2,
            timeout_seconds=0.05,  # 50ms timeout for test
        )
        for _ in range(4):
            cb.record_failure()
            
        assert cb.can_execute() is False
        
        # Wait for timeout to elapse
        time.sleep(0.06)
        
        # Accessing state should transition to RECOVERING
        assert cb.state == HealthStatus.RECOVERING
        assert cb.can_execute() is True

    def test_successful_recovery_transitions_to_healthy(self):
        cb = CircuitBreaker(
            provider_name="test_provider",
            failure_threshold=2,
            success_threshold=2,
            timeout_seconds=0.05,
        )
        for _ in range(4):
            cb.record_failure()
            
        time.sleep(0.06)
        assert cb.state == HealthStatus.RECOVERING
        
        # 2 successful trial requests -> HEALTHY
        cb.record_success()
        assert cb.state == HealthStatus.RECOVERING
        cb.record_success()
        assert cb.state == HealthStatus.HEALTHY
        assert cb.can_execute() is True

    def test_failed_recovery_trips_to_open_immediately(self):
        cb = CircuitBreaker(
            provider_name="test_provider",
            failure_threshold=2,
            success_threshold=2,
            timeout_seconds=0.05,
        )
        for _ in range(4):
            cb.record_failure()
            
        time.sleep(0.06)
        assert cb.state == HealthStatus.RECOVERING
        
        # Failure during recovery immediately trips to OPEN
        cb.record_failure()
        assert cb.state == HealthStatus.OPEN
        assert cb.can_execute() is False

    def test_manual_reset(self):
        cb = CircuitBreaker(provider_name="test_provider", failure_threshold=2)
        for _ in range(4):
            cb.record_failure()
        assert cb.can_execute() is False
        
        cb.reset()
        assert cb.state == HealthStatus.HEALTHY
        assert cb.can_execute() is True


class TestProviderHealthMonitor:
    """Test suite for ProviderHealthMonitor."""

    @pytest.fixture
    def monitor(self):
        m = ProviderHealthMonitor()
        m.reset_all()
        return m

    def test_default_providers_registered(self, monitor):
        assert monitor.is_provider_available("openrouter") is True
        assert monitor.is_provider_available("groq") is True

    def test_record_success_metrics(self, monitor):
        start = monitor.record_request_start("openrouter")
        time.sleep(0.01)
        monitor.record_request_success("openrouter", latency_ms=120.0)
        
        metrics = monitor.get_metrics("openrouter")
        assert metrics is not None
        assert metrics.total_requests == 1
        assert metrics.successful_requests == 1
        assert metrics.failed_requests == 0
        assert metrics.success_rate == 100.0
        assert metrics.average_latency_ms == 120.0

    def test_record_failure_metrics(self, monitor):
        monitor.record_request_start("groq")
        monitor.record_request_failure("groq")
        
        metrics = monitor.get_metrics("groq")
        assert metrics is not None
        assert metrics.total_requests == 1
        assert metrics.successful_requests == 0
        assert metrics.failed_requests == 1
        assert metrics.success_rate == 0.0
        assert metrics.failure_rate == 100.0
        assert metrics.consecutive_failures == 1

    def test_get_healthy_provider_fallback(self, monitor):
        # When both are healthy, preferred is chosen
        chosen = monitor.get_healthy_provider(preferred="openrouter", fallback="groq")
        assert chosen == "openrouter"
        
        # Fail preferred until circuit breaks
        breaker = monitor.get_circuit_breaker("openrouter")
        assert breaker is not None
        for _ in range(10):
            monitor.record_request_failure("openrouter")
            
        assert monitor.is_provider_available("openrouter") is False
        
        # When preferred is unavailable, fallback is chosen
        chosen = monitor.get_healthy_provider(preferred="openrouter", fallback="groq")
        assert chosen == "groq"


class TestRetryPolicy:
    """Test suite for intelligent retry categorization (AB-1.1)."""

    @pytest.fixture
    def policy(self):
        return RetryPolicy(max_retries=3, initial_delay=1.0, backoff_factor=2.0, max_delay=8.0)

    def test_retryable_status_codes(self, policy):
        # 429 Rate Limit and 5xx Server Errors should be retried
        assert policy.is_retryable_status(429) is True
        assert policy.is_retryable_status(500) is True
        assert policy.is_retryable_status(502) is True
        assert policy.is_retryable_status(503) is True
        assert policy.is_retryable_status(504) is True

    def test_fail_fast_status_codes(self, policy):
        # 401/403 Auth and 400/404 Client errors must fail fast!
        assert policy.is_retryable_status(401) is False
        assert policy.is_retryable_status(403) is False
        assert policy.is_retryable_status(400) is False
        assert policy.is_retryable_status(404) is False
        assert policy.is_retryable_status(422) is False

    def test_retryable_categories(self, policy):
        assert policy.is_retryable_category(ErrorCategory.RATE_LIMIT) is True
        assert policy.is_retryable_category(ErrorCategory.SERVER_ERROR) is True
        assert policy.is_retryable_category(ErrorCategory.TIMEOUT) is True
        assert policy.is_retryable_category(ErrorCategory.NETWORK_ERROR) is True

    def test_fail_fast_categories(self, policy):
        assert policy.is_retryable_category(ErrorCategory.AUTHENTICATION) is False
        assert policy.is_retryable_category(ErrorCategory.INVALID_REQUEST) is False
        assert policy.is_retryable_category(ErrorCategory.QUOTA_EXCEEDED) is False
        assert policy.is_retryable_category(ErrorCategory.MODEL_UNAVAILABLE) is False
        assert policy.is_retryable_category(ErrorCategory.CONTEXT_LENGTH) is False

    def test_should_retry_max_retries_enforced(self, policy):
        assert policy.should_retry(ErrorCategory.RATE_LIMIT, status_code=429, attempt=1) is True
        assert policy.should_retry(ErrorCategory.RATE_LIMIT, status_code=429, attempt=3) is True
        # Exceeded max_retries (3)
        assert policy.should_retry(ErrorCategory.RATE_LIMIT, status_code=429, attempt=4) is False

    def test_should_retry_auth_fail_fast(self, policy):
        # Even on attempt 1, auth errors must NEVER be retried
        assert policy.should_retry(ErrorCategory.AUTHENTICATION, status_code=401, attempt=1) is False
        assert policy.should_retry(ErrorCategory.AUTHENTICATION, status_code=403, attempt=1) is False

    def test_exponential_backoff_calculation(self, policy):
        # attempt 1: 1.0 * (2^0) = 1.0s
        assert policy.get_backoff_delay(1) == 1.0
        # attempt 2: 1.0 * (2^1) = 2.0s
        assert policy.get_backoff_delay(2) == 2.0
        # attempt 3: 1.0 * (2^2) = 4.0s
        assert policy.get_backoff_delay(3) == 4.0
        # attempt 4: 1.0 * (2^3) = 8.0s (capped at max_delay 8.0)
        assert policy.get_backoff_delay(4) == 8.0
        assert policy.get_backoff_delay(5) == 8.0


class TestProviderErrorTracker:
    """Test suite for ProviderErrorTracker."""

    @pytest.fixture
    def tracker(self):
        t = ProviderErrorTracker()
        t.clear_history()
        return t

    def test_classify_by_status_code(self, tracker):
        err = Exception("Something went wrong")
        assert tracker.classify_error(err, status_code=429) == ErrorCategory.RATE_LIMIT
        assert tracker.classify_error(err, status_code=401) == ErrorCategory.AUTHENTICATION
        assert tracker.classify_error(err, status_code=403) == ErrorCategory.AUTHENTICATION
        assert tracker.classify_error(err, status_code=503) == ErrorCategory.SERVER_ERROR
        assert tracker.classify_error(err, status_code=400) == ErrorCategory.INVALID_REQUEST

    def test_classify_by_message(self, tracker):
        assert tracker.classify_error(Exception("Connection timed out after 30s")) == ErrorCategory.TIMEOUT
        assert tracker.classify_error(Exception("Rate limit exceeded. Please wait.")) == ErrorCategory.RATE_LIMIT
        assert tracker.classify_error(Exception("Invalid API key provided")) == ErrorCategory.AUTHENTICATION
        assert tracker.classify_error(Exception("Insufficient credits / quota")) == ErrorCategory.QUOTA_EXCEEDED
        assert tracker.classify_error(Exception("Connection refused by peer")) == ErrorCategory.NETWORK_ERROR

    def test_record_error_and_stats(self, tracker):
        err = Exception("Rate limit exceeded")
        tracked = tracker.record_error(err, provider="openrouter", status_code=429)
        
        assert tracked.provider == "openrouter"
        assert tracked.category == ErrorCategory.RATE_LIMIT
        assert tracked.status_code == 429
        
        stats = tracker.get_error_stats("openrouter")
        assert stats is not None
        assert stats.total_errors == 1
        assert stats.rate_limit_count == 1
        assert tracker.get_dominant_error_category("openrouter") == ErrorCategory.RATE_LIMIT

    def test_tracker_should_retry_integration(self, tracker):
        # 429 Rate limit should retry
        assert tracker.should_retry(Exception("Too Many Requests"), status_code=429, attempt=1) is True
        # 401 Auth must fail fast
        assert tracker.should_retry(Exception("Unauthorized"), status_code=401, attempt=1) is False
        # Server error should retry
        assert tracker.should_retry(Exception("Internal Server Error"), status_code=500, attempt=2) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
