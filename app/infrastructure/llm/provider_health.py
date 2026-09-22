"""
Provider Health Monitoring & Circuit Breaker Pattern

Implements circuit breaker pattern for LLM provider reliability:
- Tracks provider health status (HEALTHY, DEGRADED, UNHEALTHY)
- Consecutive failure counting with automatic recovery
- Thread-safe state management
- Integration with FallbackLLMProvider for automatic failover
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Provider health states for circuit breaker."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    OPEN = "open"
    RECOVERING = "recovering"


class ProviderType(Enum):
    """LLM provider types."""
    OPENROUTER = "openrouter"
    GROQ = "groq"
    UNKNOWN = "unknown"


@dataclass
class ProviderHealthMetrics:
    """Metrics tracked per provider."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_success_time: Optional[float] = None
    last_failure_time: Optional[float] = None
    average_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100
    
    @property
    def failure_rate(self) -> float:
        """Calculate failure rate as percentage."""
        return 100.0 - self.success_rate


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for LLM providers.
    
    States:
    - CLOSED: Normal operation, requests flow through
    - OPEN: Provider is unhealthy, requests fail fast
    - HALF_OPEN: Testing if provider recovered
    
    Configuration:
    - failure_threshold: Number of consecutive failures to open circuit
    - success_threshold: Number of successes to close circuit
    - timeout_seconds: Time before attempting recovery
    """
    
    def __init__(
        self,
        provider_name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout_seconds: float = 30.0,
    ):
        self.provider_name = provider_name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds
        
        self._state = HealthStatus.HEALTHY
        self._lock = threading.RLock()
        self._last_state_change = time.time()
        self._failure_count = 0
        self._success_count = 0
        
    @property
    def state(self) -> HealthStatus:
        """Get current circuit breaker state with automatic recovery check."""
        with self._lock:
            if self._state in (HealthStatus.OPEN, HealthStatus.UNHEALTHY):
                # Check if timeout has passed to transition to HALF_OPEN / RECOVERING
                if time.time() - self._last_state_change >= self.timeout_seconds:
                    self._state = HealthStatus.RECOVERING
                    self._success_count = 0
                    logger.info(
                        "circuit_breaker provider=%s state=RECOVERING timeout_elapsed",
                        self.provider_name
                    )
            return self._state
    
    def record_success(self) -> None:
        """Record a successful request."""
        with self._lock:
            self._failure_count = 0
            
            if self._state == HealthStatus.RECOVERING:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = HealthStatus.HEALTHY
                    self._last_state_change = time.time()
                    logger.info(
                        "circuit_breaker provider=%s state=HEALTHY recovery_success",
                        self.provider_name
                    )
            elif self._state == HealthStatus.DEGRADED:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = HealthStatus.HEALTHY
                    self._last_state_change = time.time()
                    
    def record_failure(self) -> None:
        """Record a failed request."""
        with self._lock:
            self._failure_count += 1
            self._success_count = 0
            
            if self._state == HealthStatus.HEALTHY:
                if self._failure_count >= self.failure_threshold:
                    self._state = HealthStatus.DEGRADED
                    self._last_state_change = time.time()
                    logger.warning(
                        "circuit_breaker provider=%s state=DEGRADED failures=%d",
                        self.provider_name, self._failure_count
                    )
            elif self._state == HealthStatus.DEGRADED:
                if self._failure_count >= self.failure_threshold * 2:
                    self._state = HealthStatus.UNHEALTHY
                    self._last_state_change = time.time()
                    logger.warning(
                        "circuit_breaker provider=%s state=UNHEALTHY failures=%d",
                        self.provider_name, self._failure_count
                    )
            elif self._state == HealthStatus.RECOVERING:
                self._state = HealthStatus.OPEN
                self._last_state_change = time.time()
                logger.warning(
                    "circuit_breaker provider=%s state=OPEN recovery_failed",
                    self.provider_name
                )
    
    def can_execute(self) -> bool:
        """Check if requests can be executed through this provider."""
        state = self.state
        return state in (HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.RECOVERING)
    
    def reset(self) -> None:
        """Reset circuit breaker to healthy state."""
        with self._lock:
            self._state = HealthStatus.HEALTHY
            self._failure_count = 0
            self._success_count = 0
            self._last_state_change = time.time()
            logger.info("circuit_breaker provider=%s state=RESET", self.provider_name)


class ProviderHealthMonitor:
    """
    Centralized health monitoring for all LLM providers.
    
    Provides:
    - Per-provider health status tracking
    - Circuit breaker management
    - Metrics collection and reporting
    - Thread-safe operations
    """
    
    _instance: Optional['ProviderHealthMonitor'] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'ProviderHealthMonitor':
        """Singleton pattern for global health monitoring."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._metrics: dict[str, ProviderHealthMetrics] = {}
        self._lock = threading.RLock()
        self._initialized = True
        
        # Default circuit breaker settings
        self._default_failure_threshold = 5
        self._default_success_threshold = 2
        self._default_timeout_seconds = 30.0
        
        # Register default providers
        self.register_provider(ProviderType.OPENROUTER.value)
        self.register_provider(ProviderType.GROQ.value)
        
        logger.info("provider_health_monitor initialized")
    
    def register_provider(
        self,
        provider_name: str,
        failure_threshold: Optional[int] = None,
        success_threshold: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        """Register a new provider with health monitoring."""
        with self._lock:
            if provider_name not in self._circuit_breakers:
                self._circuit_breakers[provider_name] = CircuitBreaker(
                    provider_name=provider_name,
                    failure_threshold=failure_threshold or self._default_failure_threshold,
                    success_threshold=success_threshold or self._default_success_threshold,
                    timeout_seconds=timeout_seconds or self._default_timeout_seconds,
                )
                self._metrics[provider_name] = ProviderHealthMetrics()
                logger.info("provider_registered provider=%s", provider_name)
    
    def get_circuit_breaker(self, provider_name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker for a provider."""
        with self._lock:
            return self._circuit_breakers.get(provider_name)
    
    def is_provider_available(self, provider_name: str) -> bool:
        """Check if a provider can handle requests."""
        breaker = self.get_circuit_breaker(provider_name)
        if breaker is None:
            return True  # Unknown providers are allowed
        return breaker.can_execute()
    
    def record_request_start(self, provider_name: str) -> float:
        """Record the start of a request and return start time."""
        with self._lock:
            if provider_name not in self._metrics:
                self._metrics[provider_name] = ProviderHealthMetrics()
            self._metrics[provider_name].total_requests += 1
            return time.time()
    
    def record_request_success(
        self,
        provider_name: str,
        latency_ms: float,
    ) -> None:
        """Record a successful request with latency."""
        with self._lock:
            # Update circuit breaker
            breaker = self._circuit_breakers.get(provider_name)
            if breaker:
                breaker.record_success()
            
            # Update metrics
            if provider_name not in self._metrics:
                self._metrics[provider_name] = ProviderHealthMetrics()
            
            metrics = self._metrics[provider_name]
            metrics.successful_requests += 1
            metrics.consecutive_failures = 0
            metrics.consecutive_successes += 1
            metrics.last_success_time = time.time()
            
            # Update average latency (exponential moving average)
            if metrics.total_requests == 1:
                metrics.average_latency_ms = latency_ms
            else:
                alpha = 0.1  # Smoothing factor
                metrics.average_latency_ms = (
                    alpha * latency_ms + 
                    (1 - alpha) * metrics.average_latency_ms
                )
            metrics.total_latency_ms += latency_ms
            
            logger.debug(
                "provider_success provider=%s latency_ms=%.2f success_rate=%.1f%%",
                provider_name, latency_ms, metrics.success_rate
            )
    
    def record_request_failure(self, provider_name: str) -> None:
        """Record a failed request."""
        with self._lock:
            # Update circuit breaker
            breaker = self._circuit_breakers.get(provider_name)
            if breaker:
                breaker.record_failure()
            
            # Update metrics
            if provider_name not in self._metrics:
                self._metrics[provider_name] = ProviderHealthMetrics()
            
            metrics = self._metrics[provider_name]
            metrics.failed_requests += 1
            metrics.consecutive_failures += 1
            metrics.consecutive_successes = 0
            metrics.last_failure_time = time.time()
            
            logger.warning(
                "provider_failure provider=%s consecutive=%d failure_rate=%.1f%%",
                provider_name, metrics.consecutive_failures, metrics.failure_rate
            )
    
    def get_health_status(self, provider_name: str) -> Optional[HealthStatus]:
        """Get current health status of a provider."""
        breaker = self.get_circuit_breaker(provider_name)
        if breaker is None:
            return None
        return breaker.state
    
    def get_metrics(self, provider_name: str) -> Optional[ProviderHealthMetrics]:
        """Get metrics for a provider."""
        with self._lock:
            return self._metrics.get(provider_name)
    
    def get_all_metrics(self) -> dict[str, ProviderHealthMetrics]:
        """Get metrics for all providers."""
        with self._lock:
            return dict(self._metrics)
    
    def get_healthy_provider(self, preferred: str, fallback: str) -> Optional[str]:
        """
        Get the best available provider based on health status.
        
        Returns the preferred provider if healthy, otherwise returns fallback
        if healthy, otherwise returns None.
        """
        if self.is_provider_available(preferred):
            return preferred
        if self.is_provider_available(fallback):
            logger.info(
                "provider_fallback preferred=%s unavailable, using=%s",
                preferred, fallback
            )
            return fallback
        return None
    
    def reset_provider(self, provider_name: str) -> None:
        """Manually reset a provider's circuit breaker."""
        breaker = self.get_circuit_breaker(provider_name)
        if breaker:
            breaker.reset()
            logger.info("provider_reset provider=%s", provider_name)
    
    def reset_all(self) -> None:
        """Reset all providers to healthy state."""
        with self._lock:
            for breaker in self._circuit_breakers.values():
                breaker.reset()
            logger.info("all_providers_reset")


# Global singleton instance
_provider_health_monitor: Optional[ProviderHealthMonitor] = None


def get_provider_health_monitor() -> ProviderHealthMonitor:
    """Get the global provider health monitor instance."""
    global _provider_health_monitor
    if _provider_health_monitor is None:
        _provider_health_monitor = ProviderHealthMonitor()
    return _provider_health_monitor