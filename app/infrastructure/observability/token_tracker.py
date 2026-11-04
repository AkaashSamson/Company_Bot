"""
Token usage tracking for LLM API calls.

Tracks prompt tokens, completion tokens, and total tokens consumed
across all LLM providers. Supports aggregation by model, session, and time period.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Dict, Optional, List
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Represents token usage for a single LLM call."""

    timestamp: datetime
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    session_id: Optional[str] = None
    cache_hit: bool = False
    provider: str = "unknown"

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "session_id": self.session_id,
            "cache_hit": self.cache_hit,
            "provider": self.provider,
        }


@dataclass
class AggregatedTokens:
    """Aggregated token statistics."""

    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    call_count: int = 0
    cached_calls: int = 0
    avg_tokens_per_call: float = 0.0
    avg_prompt_tokens: float = 0.0
    avg_completion_tokens: float = 0.0

    def update(self, usage: TokenUsage) -> None:
        """Update aggregated stats with new usage data."""
        self.total_tokens += usage.total_tokens
        self.prompt_tokens += usage.prompt_tokens
        self.completion_tokens += usage.completion_tokens
        self.call_count += 1
        if usage.cache_hit:
            self.cached_calls += 1

        # Recalculate averages
        if self.call_count > 0:
            self.avg_tokens_per_call = self.total_tokens / self.call_count
            self.avg_prompt_tokens = self.prompt_tokens / self.call_count
            self.avg_completion_tokens = self.completion_tokens / self.call_count


class TokenTracker:
    """
    Thread-safe token usage tracker for LLM calls.

    Collects, aggregates, and reports token consumption across
    different models, sessions, and time periods.
    """

    def __init__(self, max_history: int = 10000):
        """
        Initialize token tracker.

        Parameters
        ----------
        max_history : int
            Maximum number of token usage records to keep in memory.
        """
        self.max_history = max_history
        self._lock = Lock()
        self._history: List[TokenUsage] = []

    def track(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        session_id: Optional[str] = None,
        cache_hit: bool = False,
        provider: str = "unknown",
    ) -> TokenUsage:
        """
        Record token usage for an LLM call.

        Parameters
        ----------
        model : str
            Model name (e.g., "claude-3.5-sonnet")
        prompt_tokens : int
            Number of tokens in the prompt
        completion_tokens : int
            Number of tokens in the completion
        session_id : str, optional
            Session identifier for grouping
        cache_hit : bool
            Whether this was a cache hit (no API call)
        provider : str
            LLM provider name (e.g., "openrouter", "groq")

        Returns
        -------
        TokenUsage
            The recorded token usage object
        """
        usage = TokenUsage(
            timestamp=datetime.now(),
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            session_id=session_id,
            cache_hit=cache_hit,
            provider=provider,
        )

        with self._lock:
            self._history.append(usage)

            # Keep history within max size
            if len(self._history) > self.max_history:
                self._history = self._history[-self.max_history :]

            logger.debug(
                "Tracked tokens: model=%s, prompt=%d, completion=%d, total=%d, cache=%s",
                model,
                prompt_tokens,
                completion_tokens,
                usage.total_tokens,
                cache_hit,
            )

        return usage

    def get_total(self) -> AggregatedTokens:
        """
        Get aggregated token statistics for all recorded calls.

        Returns
        -------
        AggregatedTokens
            Total aggregated statistics
        """
        aggregated = AggregatedTokens()

        with self._lock:
            for usage in self._history:
                aggregated.update(usage)

        return aggregated

    def get_by_model(self, model: str) -> AggregatedTokens:
        """
        Get aggregated statistics for a specific model.

        Parameters
        ----------
        model : str
            Model name to filter by

        Returns
        -------
        AggregatedTokens
            Aggregated statistics for that model
        """
        aggregated = AggregatedTokens()

        with self._lock:
            for usage in self._history:
                if usage.model == model:
                    aggregated.update(usage)

        return aggregated

    def get_by_session(self, session_id: str) -> AggregatedTokens:
        """
        Get aggregated statistics for a specific session.

        Parameters
        ----------
        session_id : str
            Session ID to filter by

        Returns
        -------
        AggregatedTokens
            Aggregated statistics for that session
        """
        aggregated = AggregatedTokens()

        with self._lock:
            for usage in self._history:
                if usage.session_id == session_id:
                    aggregated.update(usage)

        return aggregated

    def get_by_provider(self, provider: str) -> AggregatedTokens:
        """
        Get aggregated statistics by provider.

        Parameters
        ----------
        provider : str
            Provider name (e.g., "openrouter", "groq")

        Returns
        -------
        AggregatedTokens
            Aggregated statistics for that provider
        """
        aggregated = AggregatedTokens()

        with self._lock:
            for usage in self._history:
                if usage.provider == provider:
                    aggregated.update(usage)

        return aggregated

    def get_all_models(self) -> Dict[str, AggregatedTokens]:
        """
        Get aggregated statistics grouped by model.

        Returns
        -------
        Dict[str, AggregatedTokens]
            Mapping of model names to their token statistics
        """
        stats_by_model: Dict[str, AggregatedTokens] = defaultdict(AggregatedTokens)

        with self._lock:
            for usage in self._history:
                stats_by_model[usage.model].update(usage)

        return dict(stats_by_model)

    def get_all_sessions(self) -> Dict[str, AggregatedTokens]:
        """
        Get aggregated statistics grouped by session.

        Returns
        -------
        Dict[str, AggregatedTokens]
            Mapping of session IDs to their token statistics
        """
        stats_by_session: Dict[str, AggregatedTokens] = defaultdict(AggregatedTokens)

        with self._lock:
            for usage in self._history:
                session = usage.session_id or "unknown"
                stats_by_session[session].update(usage)

        return dict(stats_by_session)

    def get_recent(self, limit: int = 100) -> List[TokenUsage]:
        """
        Get recent token usage records.

        Parameters
        ----------
        limit : int
            Maximum number of recent records to return

        Returns
        -------
        List[TokenUsage]
            Recent token usage records (most recent first)
        """
        with self._lock:
            return list(reversed(self._history[-limit:]))

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get cache hit/miss statistics.

        Returns
        -------
        Dict[str, int]
            Statistics including cache_hits, cache_misses, cache_hit_rate
        """
        with self._lock:
            cache_hits = sum(1 for u in self._history if u.cache_hit)
            cache_misses = len(self._history) - cache_hits
            total = len(self._history)

        hit_rate = (cache_hits / total * 100) if total > 0 else 0

        return {
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "total_calls": total,
            "cache_hit_rate_percent": round(hit_rate, 2),
        }

    def clear_history(self) -> None:
        """Clear all token usage history."""
        with self._lock:
            self._history.clear()
        logger.info("Token usage history cleared.")

    def export_as_list(self) -> List[dict]:
        """
        Export all token usage records as dictionaries.

        Returns
        -------
        List[dict]
            All token usage records in dictionary format
        """
        with self._lock:
            return [usage.to_dict() for usage in self._history]


# Global token tracker instance
_global_tracker: Optional[TokenTracker] = None


def get_token_tracker() -> TokenTracker:
    """Get or create the global token tracker instance."""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = TokenTracker()
    return _global_tracker


def reset_token_tracker() -> None:
    """Reset the global token tracker (useful for testing)."""
    global _global_tracker
    _global_tracker = None
