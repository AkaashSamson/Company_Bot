import logging
import warnings
import pytest

from app.core.settings import (
    CONVERSATION_LOG_DIR,
    CONVERSATION_LOG_RETENTION_DAYS,
    DEFAULT_CONVERSATION_LOG_DIR,
    DEFAULT_CONVERSATION_LOG_RETENTION_DAYS,
    DOCLING_ENABLED,
    parse_retention_days,
)
from app.infrastructure.logging.conversation_log_cleanup import ConversationLogCleanup


def test_default_retention_is_30_days():
    """Verify default retention constant and parser output for None are 30."""
    assert DEFAULT_CONVERSATION_LOG_RETENTION_DAYS == 30
    assert parse_retention_days(None) == 30


def test_empty_or_whitespace_retention_falls_back_safely():
    """Verify empty or whitespace strings return safe default without warnings."""
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        assert parse_retention_days("") == 30
        assert parse_retention_days("   ") == 30
        assert len(recorded_warnings) == 0


def test_valid_positive_integer_retention():
    """Verify valid positive integers are parsed correctly without warnings."""
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        assert parse_retention_days("1") == 1
        assert parse_retention_days("15") == 15
        assert parse_retention_days("60") == 60
        assert parse_retention_days(" 45 ") == 45
        assert len(recorded_warnings) == 0


def test_zero_retention_warns_and_falls_back():
    """Verify zero is rejected with warning and safe fallback to 30."""
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        assert parse_retention_days("0") == 30
        assert len(recorded_warnings) == 1
        warning_msg = str(recorded_warnings[0].message)
        assert "positive integer" in warning_msg
        assert "30" in warning_msg


def test_negative_retention_warns_and_falls_back():
    """Verify negative integers are rejected with warning and safe fallback to 30."""
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        assert parse_retention_days("-1") == 30
        assert parse_retention_days("-30") == 30
        assert len(recorded_warnings) == 2
        for w in recorded_warnings:
            assert "positive integer" in str(w.message)
            assert "30" in str(w.message)


def test_invalid_non_integer_retention_warns_and_falls_back():
    """Verify non-integer strings are rejected with warning and safe fallback to 30."""
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        assert parse_retention_days("not-a-number") == 30
        assert parse_retention_days("30.5") == 30
        assert parse_retention_days("thirty") == 30
        assert len(recorded_warnings) == 3
        for w in recorded_warnings:
            assert "not a valid integer" in str(w.message)
            assert "30" in str(w.message)


def test_conversation_log_dir_setting_defaults():
    """Verify CONVERSATION_LOG_DIR defaults to conversation_logs."""
    assert DEFAULT_CONVERSATION_LOG_DIR == "conversation_logs"
    assert CONVERSATION_LOG_DIR.name == "conversation_logs"


def test_cleanup_consumes_validated_retention_setting():
    """Verify ConversationLogCleanup uses settings.CONVERSATION_LOG_RETENTION_DAYS by default."""
    cleanup = ConversationLogCleanup()
    assert cleanup.retention_days == CONVERSATION_LOG_RETENTION_DAYS
    assert cleanup.log_dir == CONVERSATION_LOG_DIR


def test_docling_flag_is_enabled():
    """Verify the Docling ingestion flag is enabled.

    Docling is now the active parsing adapter for structural document
    ingestion.
    """
    assert DOCLING_ENABLED is True
