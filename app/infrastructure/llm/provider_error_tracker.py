"""
Provider Error Tracker & Structured Error Diagnostics

Tracks and categorizes LLM provider errors for debugging and monitoring:
- Error type classification (timeout, rate limit, auth, etc.)
- Error frequency tracking per provider
- Recent error history with timestamps
- Error pattern detection
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Categorized error types from LLM providers."""
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION = "authentication"
    QUOTA_EXCEEDED = "quota_exceeded"
    SERVER_ERROR = "server_error"
    NETWORK_ERROR = "network_error"
    INVALID_REQUEST = "invalid_request"
    MODEL_UNAVAILABLE = "model_unavailable"
    CONTEXT_LENGTH = "context_length"
    UNKNOWN = "unknown"


@dataclass
class TrackedError:
    """Represents a single tracked error event."""
    timestamp: float
    category: ErrorCategory
    provider: str
    message: str
    status_code: Optional[int] = None
    recovery_action: Optional[str] = None


@dataclass 
class ErrorStats:
    """Aggregated error statistics for a provider."""
    total_errors: int = 0
    timeout_count: int = 0
    rate_limit_count: int = 0
    auth_count: int = 0
    quota_count: int = 0
    server_error_count: int = 0
    network_error_count: int = 0
    invalid_request_count: int = 0
    model_unavailable_count: int = 0
    context_length_count: int = 0
    unknown_count: int = 0
    
    last_error_time: Optional[float] = None
    first_error_time: Optional[float] = None
    
    @property
    def error_rate(self) -> float:
        """Errors per minute since first error."""
        if self.total_errors == 0 or self.first_error_time is None:
            return 0.0
        elapsed_minutes = (time.time() - self.first_error_time) / 60
        if elapsed_minutes == 0:
            return float(self.total_errors)
        return self.total_errors / elapsed_minutes


class RetryPolicy:
    """
    Intelligent retry policy for LLM providers.
    
    Categorizes errors into retryable vs non-retryable:
    - Retryable: 429 (Rate Limit), 5xx (Server Errors), TIMEOUT, NETWORK_ERROR
    - Fail-Fast / Non-retryable: 401/403 (Authentication), 400 (Invalid Request), 
      QUOTA_EXCEEDED, MODEL_UNAVAILABLE, CONTEXT_LENGTH
    
    Provides exponential backoff calculation.
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
        max_delay: float = 10.0,
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay

    @staticmethod
    def is_retryable_status(status_code: Optional[int]) -> bool:
        """
        Check if an HTTP status code is retryable.
        
        - 429: Rate limit (retry with backoff)
        - 500, 502, 503, 504: Server errors (retry)
        - 401, 403: Authentication errors (fail fast)
        - 400, 404, 422: Client/model errors (fail fast)
        """
        if status_code is None:
            return False
        if status_code in (401, 403, 400, 404, 422):
            return False
        if status_code == 429 or 500 <= status_code < 600:
            return True
        return False

    @staticmethod
    def is_retryable_category(category: ErrorCategory) -> bool:
        """
        Check if an ErrorCategory is retryable.
        
        Retryable:
        - RATE_LIMIT
        - SERVER_ERROR
        - TIMEOUT
        - NETWORK_ERROR
        
        Fail-Fast:
        - AUTHENTICATION (401/403)
        - QUOTA_EXCEEDED
        - INVALID_REQUEST (400)
        - MODEL_UNAVAILABLE (404)
        - CONTEXT_LENGTH
        - UNKNOWN
        """
        retryable_categories = {
            ErrorCategory.RATE_LIMIT,
            ErrorCategory.SERVER_ERROR,
            ErrorCategory.TIMEOUT,
            ErrorCategory.NETWORK_ERROR,
        }
        return category in retryable_categories

    def should_retry(
        self,
        category: ErrorCategory,
        status_code: Optional[int] = None,
        attempt: int = 1,
    ) -> bool:
        """
        Determine if an error should be retried based on attempt and error type.
        
        Args:
            category: Classified error category
            status_code: HTTP status code if available
            attempt: Current attempt count (1-indexed)
            
        Returns:
            True if request should be retried, False to fail fast
        """
        if attempt > self.max_retries:
            return False
            
        # Fail-fast immediately on authentication errors
        if status_code in (401, 403) or category == ErrorCategory.AUTHENTICATION:
            return False
            
        # If status code is available, evaluate it first
        if status_code is not None:
            return self.is_retryable_status(status_code)
            
        # Fall back to category evaluation
        return self.is_retryable_category(category)

    def get_backoff_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay in seconds."""
        delay = self.initial_delay * (self.backoff_factor ** max(0, attempt - 1))
        return min(delay, self.max_delay)


class ProviderErrorTracker:
    """
    Tracks and analyzes errors from LLM providers.
    
    Features:
    - Categorizes errors by type
    - Implements intelligent retry policies (retry 429/5xx, fail-fast 401/403)
    - Maintains recent error history (configurable limit)
    - Aggregates statistics per provider
    - Provides error pattern insights
    """
    
    def __init__(
        self,
        max_history: int = 100,
        error_ttl_seconds: float = 3600.0,
        retry_policy: Optional[RetryPolicy] = None,
    ):
        """
        Initialize error tracker.
        
        Args:
            max_history: Maximum number of recent errors to keep per provider
            error_ttl_seconds: Time-to-live for error statistics
            retry_policy: Optional customized RetryPolicy
        """
        self.max_history = max_history
        self.error_ttl_seconds = error_ttl_seconds
        self.retry_policy = retry_policy or RetryPolicy()
        
        self._error_history: dict[str, list[TrackedError]] = {}
        self._error_stats: dict[str, ErrorStats] = {}
        self._lock = threading.RLock()
        
        logger.info("error_tracker initialized max_history=%d ttl=%.0fs", 
                    max_history, error_ttl_seconds)

    def should_retry(
        self,
        error: Exception,
        status_code: Optional[int] = None,
        attempt: int = 1,
    ) -> bool:
        """
        Check if an error should be retried.
        
        Args:
            error: The exception that occurred
            status_code: HTTP status code if available
            attempt: Current attempt number (1-indexed)
            
        Returns:
            True if retryable, False to fail fast
        """
        category = self.classify_error(error, status_code)
        return self.retry_policy.should_retry(category, status_code, attempt)

    def get_backoff_delay(self, attempt: int) -> float:
        """Get recommended retry backoff delay in seconds."""
        return self.retry_policy.get_backoff_delay(attempt)
    
    def classify_error(
        self,
        error: Exception,
        status_code: Optional[int] = None,
    ) -> ErrorCategory:
        """
        Classify an error into a category based on exception type and status code.
        
        Args:
            error: The exception that occurred
            status_code: HTTP status code if available
            
        Returns:
            ErrorCategory representing the type of error
        """
        error_message = str(error).lower()
        
        # Check status code first
        if status_code:
            if status_code == 429:
                return ErrorCategory.RATE_LIMIT
            elif status_code == 401:
                return ErrorCategory.AUTHENTICATION
            elif status_code == 403:
                return ErrorCategory.AUTHENTICATION
            elif status_code == 404:
                return ErrorCategory.MODEL_UNAVAILABLE
            elif status_code == 400:
                return ErrorCategory.INVALID_REQUEST
            elif 500 <= status_code < 600:
                return ErrorCategory.SERVER_ERROR
            
        # Classify by error message
        if any(keyword in error_message for keyword in ["timeout", "timed out", "deadline"]):
            return ErrorCategory.TIMEOUT
        elif any(keyword in error_message for keyword in ["rate limit", "too many requests", "429"]):
            return ErrorCategory.RATE_LIMIT
        elif any(keyword in error_message for keyword in ["auth", "api key", "unauthorized", "401", "403"]):
            return ErrorCategory.AUTHENTICATION
        elif any(keyword in error_message for keyword in ["quota", "insufficient credits", "limit exceeded"]):
            return ErrorCategory.QUOTA_EXCEEDED
        elif any(keyword in error_message for keyword in ["rate limit", "retry after"]):
            return ErrorCategory.RATE_LIMIT
        elif any(keyword in error_message for keyword in ["500", "502", "503", "504", "server error"]):
            return ErrorCategory.SERVER_ERROR
        elif any(keyword in error_message for keyword in ["connection", "network", "dns", "refused"]):
            return ErrorCategory.NETWORK_ERROR
        elif any(keyword in error_message for keyword in ["model", "not found", "unavailable"]):
            return ErrorCategory.MODEL_UNAVAILABLE
        elif any(keyword in error_message for keyword in ["context length", "max tokens", "too long"]):
            return ErrorCategory.CONTEXT_LENGTH
        elif any(keyword in error_message for keyword in ["invalid", "bad request", "400"]):
            return ErrorCategory.INVALID_REQUEST
            
        return ErrorCategory.UNKNOWN
    
    def get_recovery_action(self, category: ErrorCategory) -> str:
        """Get recommended recovery action for an error category."""
        recovery_actions = {
            ErrorCategory.TIMEOUT: "Retry with exponential backoff (1s, 2s, 4s)",
            ErrorCategory.RATE_LIMIT: "Wait for rate limit reset; use fallback provider",
            ErrorCategory.AUTHENTICATION: "Check API key validity; refresh credentials",
            ErrorCategory.QUOTA_EXCEEDED: "Check usage limits; switch to fallback provider",
            ErrorCategory.SERVER_ERROR: "Retry with backoff; fallback if persistent",
            ErrorCategory.NETWORK_ERROR: "Retry request; check network connectivity",
            ErrorCategory.INVALID_REQUEST: "Fix request parameters; validate input",
            ErrorCategory.MODEL_UNAVAILABLE: "Switch to available model; use fallback provider",
            ErrorCategory.CONTEXT_LENGTH: "Reduce context size; truncate input",
            ErrorCategory.UNKNOWN: "Log error details; attempt retry with fallback",
        }
        return recovery_actions.get(category, "Unknown recovery action")
    
    def record_error(
        self,
        error: Exception,
        provider: str,
        status_code: Optional[int] = None,
    ) -> TrackedError:
        """
        Record an error event.
        
        Args:
            error: The exception that occurred
            provider: Name of the provider (e.g., 'openrouter', 'groq')
            status_code: HTTP status code if available
            
        Returns:
            The tracked error that was recorded
        """
        category = self.classify_error(error, status_code)
        recovery_action = self.get_recovery_action(category)
        
        tracked_error = TrackedError(
            timestamp=time.time(),
            category=category,
            provider=provider,
            message=str(error),
            status_code=status_code,
            recovery_action=recovery_action,
        )
        
        with self._lock:
            # Add to history
            if provider not in self._error_history:
                self._error_history[provider] = []
            
            history = self._error_history[provider]
            history.append(tracked_error)
            
            # Trim history if needed
            if len(history) > self.max_history:
                history.pop(0)
            
            # Update stats
            if provider not in self._error_stats:
                self._error_stats[provider] = ErrorStats()
            
            stats = self._error_stats[provider]
            stats.total_errors += 1
            
            # Track first/last error times
            if stats.first_error_time is None:
                stats.first_error_time = tracked_error.timestamp
            stats.last_error_time = tracked_error.timestamp
            
            # Increment category-specific counter
            self._increment_category_counter(stats, category)
        
        logger.warning(
            "llm_error provider=%s category=%s status=%s message=%s",
            provider,
            category.value,
            status_code,
            str(error)[:100],
        )
        
        return tracked_error
    
    def _increment_category_counter(self, stats: ErrorStats, category: ErrorCategory) -> None:
        """Increment the counter for a specific error category."""
        if category == ErrorCategory.TIMEOUT:
            stats.timeout_count += 1
        elif category == ErrorCategory.RATE_LIMIT:
            stats.rate_limit_count += 1
        elif category == ErrorCategory.AUTHENTICATION:
            stats.auth_count += 1
        elif category == ErrorCategory.QUOTA_EXCEEDED:
            stats.quota_count += 1
        elif category == ErrorCategory.SERVER_ERROR:
            stats.server_error_count += 1
        elif category == ErrorCategory.NETWORK_ERROR:
            stats.network_error_count += 1
        elif category == ErrorCategory.INVALID_REQUEST:
            stats.invalid_request_count += 1
        elif category == ErrorCategory.MODEL_UNAVAILABLE:
            stats.model_unavailable_count += 1
        elif category == ErrorCategory.CONTEXT_LENGTH:
            stats.context_length_count += 1
        else:
            stats.unknown_count += 1
    
    def get_recent_errors(
        self,
        provider: str,
        limit: int = 10,
    ) -> list[TrackedError]:
        """Get recent errors for a provider."""
        with self._lock:
            history = self._error_history.get(provider, [])
            return history[-limit:]
    
    def get_error_stats(self, provider: str) -> Optional[ErrorStats]:
        """Get error statistics for a provider."""
        with self._lock:
            return self._error_stats.get(provider)
    
    def get_all_error_stats(self) -> dict[str, ErrorStats]:
        """Get error statistics for all providers."""
        with self._lock:
            return dict(self._error_stats)
    
    def get_dominant_error_category(self, provider: str) -> Optional[ErrorCategory]:
        """Get the most frequent error category for a provider."""
        stats = self.get_error_stats(provider)
        if stats is None:
            return None
        
        category_counts = {
            ErrorCategory.TIMEOUT: stats.timeout_count,
            ErrorCategory.RATE_LIMIT: stats.rate_limit_count,
            ErrorCategory.AUTHENTICATION: stats.auth_count,
            ErrorCategory.QUOTA_EXCEEDED: stats.quota_count,
            ErrorCategory.SERVER_ERROR: stats.server_error_count,
            ErrorCategory.NETWORK_ERROR: stats.network_error_count,
            ErrorCategory.INVALID_REQUEST: stats.invalid_request_count,
            ErrorCategory.MODEL_UNAVAILABLE: stats.model_unavailable_count,
            ErrorCategory.CONTEXT_LENGTH: stats.context_length_count,
            ErrorCategory.UNKNOWN: stats.unknown_count,
        }
        
        max_category = max(category_counts.items(), key=lambda x: x[1])
        if max_category[1] > 0:
            return max_category[0]
        return None
    
    def is_provider_critical(self, provider: str) -> bool:
        """
        Determine if a provider is in a critical error state.
        
        A provider is critical if:
        - Has more than 10 total errors, AND
        - Has a dominant error category (not UNKNOWN), AND
        - Error rate > 5 per minute
        """
        stats = self.get_error_stats(provider)
        if stats is None:
            return False
        
        if stats.total_errors <= 10:
            return False
        
        if self.get_dominant_error_category(provider) == ErrorCategory.UNKNOWN:
            return False
        
        return stats.error_rate > 5.0
    
    def clear_history(self, provider: Optional[str] = None) -> None:
        """Clear error history for a specific provider or all providers."""
        with self._lock:
            if provider:
                self._error_history.pop(provider, None)
                self._error_stats.pop(provider, None)
            else:
                self._error_history.clear()
                self._error_stats.clear()
        
        logger.info("error_history_cleared provider=%s", provider or "all")


# Global singleton instance
_error_tracker: Optional[ProviderErrorTracker] = None


def get_error_tracker() -> ProviderErrorTracker:
    """Get the global error tracker instance."""
    global _error_tracker
    if _error_tracker is None:
        _error_tracker = ProviderErrorTracker()
    return _error_tracker