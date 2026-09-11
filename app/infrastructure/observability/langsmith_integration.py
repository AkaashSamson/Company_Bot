"""
LangSmith integration for token tracking.

Properly adds token counts to LangSmith traces using the official API.
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def add_tokens_to_current_run(
    prompt_tokens: int,
    completion_tokens: int,
    model: str = "unknown",
) -> None:
    """
    Add token usage to the current LangSmith run.

    This should be called immediately after an LLM API call to ensure
    tokens are captured in the active trace.

    Parameters
    ----------
    prompt_tokens : int
        Number of tokens in the prompt
    completion_tokens : int
        Number of tokens in the completion
    model : str
        Model name (e.g., "claude-3.5-sonnet")
    """
    try:
        from langsmith import get_run_tree
        
        # Get the current run in the trace
        run = get_run_tree()
        
        if not run:
            logger.debug("No active LangSmith run to update")
            return

        # Add outputs with token information
        outputs = {
            "completion": "Generated",  # Minimal output
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "model": model,
        }

        # Update the run with outputs containing token info
        run.end(outputs=outputs)
        
        logger.debug(
            f"Updated LangSmith run {run.id} with tokens: "
            f"prompt={prompt_tokens}, completion={completion_tokens}, "
            f"total={prompt_tokens + completion_tokens}"
        )

    except ImportError:
        logger.debug("LangSmith not installed")
    except Exception as e:
        logger.debug(f"Could not add tokens to LangSmith run: {e}")


def add_token_metadata(metadata: Dict[str, Any]) -> None:
    """
    Add metadata to the current LangSmith run.

    Parameters
    ----------
    metadata : dict
        Key-value pairs to add to run metadata
    """
    try:
        from langsmith import get_run_tree
        
        run = get_run_tree()
        if not run:
            return

        # LangSmith runs can have metadata attached
        if hasattr(run, 'metadata'):
            if run.metadata is None:
                run.metadata = {}
            run.metadata.update(metadata)
            logger.debug(f"Added metadata to LangSmith run: {metadata}")

    except Exception as e:
        logger.debug(f"Could not add metadata to LangSmith: {e}")


def add_tokens_via_extra(
    prompt_tokens: int,
    completion_tokens: int,
    model: str = "unknown",
) -> Dict[str, Any]:
    """
    Create a metadata dict that can be passed to LangSmith run.

    This is useful when you want to attach token info to a traced function.

    Parameters
    ----------
    prompt_tokens : int
        Number of tokens in the prompt
    completion_tokens : int
        Number of tokens in the completion
    model : str
        Model name

    Returns
    -------
    dict
        Metadata dict with token information
    """
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "model": model,
    }


def format_tokens_for_display(
    prompt_tokens: int,
    completion_tokens: int,
) -> str:
    """Format token counts for display in logs."""
    total = prompt_tokens + completion_tokens
    return f"{prompt_tokens}P + {completion_tokens}C = {total}T"
