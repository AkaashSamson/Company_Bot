"""
Token usage metrics API endpoints.

Provides access to token consumption statistics and analytics.
"""

import logging
from typing import Dict, List

from fastapi import APIRouter

from app.infrastructure.observability.token_tracker import get_token_tracker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tokens", tags=["tokens"])


@router.get("/stats")
def get_token_stats() -> Dict:
    """
    Get overall token usage statistics.

    Returns
    -------
    dict
        Total tokens, calls, cache stats, and averages
    """
    tracker = get_token_tracker()
    total = tracker.get_total()
    cache_stats = tracker.get_cache_stats()

    return {
        "total_tokens": total.total_tokens,
        "prompt_tokens": total.prompt_tokens,
        "completion_tokens": total.completion_tokens,
        "call_count": total.call_count,
        "avg_tokens_per_call": round(total.avg_tokens_per_call, 2),
        "avg_prompt_tokens": round(total.avg_prompt_tokens, 2),
        "avg_completion_tokens": round(total.avg_completion_tokens, 2),
        "cache_hits": cache_stats["cache_hits"],
        "cache_misses": cache_stats["cache_misses"],
        "cache_hit_rate_percent": cache_stats["cache_hit_rate_percent"],
    }


@router.get("/by-model")
def get_tokens_by_model() -> Dict[str, Dict]:
    """
    Get token usage statistics grouped by model.

    Returns
    -------
    dict
        Mapping of model names to token statistics
    """
    tracker = get_token_tracker()
    by_model = tracker.get_all_models()

    result = {}
    for model, stats in by_model.items():
        result[model] = {
            "total_tokens": stats.total_tokens,
            "prompt_tokens": stats.prompt_tokens,
            "completion_tokens": stats.completion_tokens,
            "call_count": stats.call_count,
            "cached_calls": stats.cached_calls,
            "avg_tokens_per_call": round(stats.avg_tokens_per_call, 2),
        }

    return result


@router.get("/by-session")
def get_tokens_by_session() -> Dict[str, Dict]:
    """
    Get token usage statistics grouped by session.

    Returns
    -------
    dict
        Mapping of session IDs to token statistics
    """
    tracker = get_token_tracker()
    by_session = tracker.get_all_sessions()

    result = {}
    for session_id, stats in by_session.items():
        result[session_id] = {
            "total_tokens": stats.total_tokens,
            "prompt_tokens": stats.prompt_tokens,
            "completion_tokens": stats.completion_tokens,
            "call_count": stats.call_count,
            "cached_calls": stats.cached_calls,
            "avg_tokens_per_call": round(stats.avg_tokens_per_call, 2),
        }

    return result


@router.get("/by-provider")
def get_tokens_by_provider() -> Dict[str, Dict]:
    """
    Get token usage statistics grouped by provider.

    Returns
    -------
    dict
        Mapping of provider names to token statistics
    """
    tracker = get_token_tracker()
    by_provider = tracker.get_by_provider("openrouter")
    by_groq = tracker.get_by_provider("groq")

    result = {}

    if by_provider.call_count > 0:
        result["openrouter"] = {
            "total_tokens": by_provider.total_tokens,
            "prompt_tokens": by_provider.prompt_tokens,
            "completion_tokens": by_provider.completion_tokens,
            "call_count": by_provider.call_count,
            "cached_calls": by_provider.cached_calls,
            "avg_tokens_per_call": round(by_provider.avg_tokens_per_call, 2),
        }

    if by_groq.call_count > 0:
        result["groq"] = {
            "total_tokens": by_groq.total_tokens,
            "prompt_tokens": by_groq.prompt_tokens,
            "completion_tokens": by_groq.completion_tokens,
            "call_count": by_groq.call_count,
            "cached_calls": by_groq.cached_calls,
            "avg_tokens_per_call": round(by_groq.avg_tokens_per_call, 2),
        }

    return result


@router.get("/recent")
def get_recent_token_usage(limit: int = 50) -> List[Dict]:
    """
    Get recent token usage records.

    Parameters
    ----------
    limit : int
        Maximum number of records to return (default: 50, max: 1000)

    Returns
    -------
    list
        Recent token usage records in descending order (most recent first)
    """
    limit = min(limit, 1000)  # Cap at 1000 to prevent abuse
    tracker = get_token_tracker()
    recent = tracker.get_recent(limit=limit)

    return [usage.to_dict() for usage in recent]


@router.get("/session/{session_id}")
def get_session_token_usage(session_id: str) -> Dict:
    """
    Get token usage for a specific session.

    Parameters
    ----------
    session_id : str
        Session ID to look up

    Returns
    -------
    dict
        Token statistics for that session
    """
    tracker = get_token_tracker()
    stats = tracker.get_by_session(session_id)

    return {
        "session_id": session_id,
        "total_tokens": stats.total_tokens,
        "prompt_tokens": stats.prompt_tokens,
        "completion_tokens": stats.completion_tokens,
        "call_count": stats.call_count,
        "cached_calls": stats.cached_calls,
        "avg_tokens_per_call": round(stats.avg_tokens_per_call, 2),
        "avg_prompt_tokens": round(stats.avg_prompt_tokens, 2),
        "avg_completion_tokens": round(stats.avg_completion_tokens, 2),
    }


@router.get("/model/{model_name}")
def get_model_token_usage(model_name: str) -> Dict:
    """
    Get token usage for a specific model.

    Parameters
    ----------
    model_name : str
        Model name to look up (e.g., "claude-3.5-sonnet")

    Returns
    -------
    dict
        Token statistics for that model
    """
    tracker = get_token_tracker()
    stats = tracker.get_by_model(model_name)

    return {
        "model": model_name,
        "total_tokens": stats.total_tokens,
        "prompt_tokens": stats.prompt_tokens,
        "completion_tokens": stats.completion_tokens,
        "call_count": stats.call_count,
        "cached_calls": stats.cached_calls,
        "avg_tokens_per_call": round(stats.avg_tokens_per_call, 2),
        "avg_prompt_tokens": round(stats.avg_prompt_tokens, 2),
        "avg_completion_tokens": round(stats.avg_completion_tokens, 2),
    }


@router.post("/clear")
def clear_token_history() -> Dict[str, str]:
    """
    Clear all token usage history (requires authentication in production).

    Returns
    -------
    dict
        Confirmation message
    """
    tracker = get_token_tracker()
    tracker.clear_history()
    logger.info("Token usage history cleared by API request")

    return {"status": "Token history cleared"}
