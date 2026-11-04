from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.infrastructure.logging.conversation_log_cleanup import (
    CleanupResult,
    ConversationLogCleanup,
)
from app.main import app


def set_file_mtime(file_path: Path, mtime_dt: datetime) -> None:
    """Helper to explicitly set file access and modification times."""
    ts = mtime_dt.timestamp()
    os.utime(file_path, (ts, ts))


def test_cleanup_deletes_expired_logs(tmp_path):
    """Verify that files older than retention days are deleted."""
    cleanup = ConversationLogCleanup(log_dir=tmp_path, retention_days=30)
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)

    expired_file = tmp_path / "MSS001_20260701_100000.json"
    expired_file.write_text(json.dumps({"employee_id": "MSS001", "messages": []}))
    set_file_mtime(expired_file, now - timedelta(days=35))

    result = cleanup.cleanup_expired_logs(now=now)

    assert result.deleted == 1
    assert result.failed == 0
    assert not expired_file.exists()


def test_cleanup_preserves_non_expired_logs(tmp_path):
    """Verify that files within retention days are untouched."""
    cleanup = ConversationLogCleanup(log_dir=tmp_path, retention_days=30)
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)

    recent_file = tmp_path / "MSS001_20260905_100000.json"
    recent_file.write_text(json.dumps({"employee_id": "MSS001", "messages": []}))
    set_file_mtime(recent_file, now - timedelta(days=5))

    result = cleanup.cleanup_expired_logs(now=now)

    assert result.deleted == 0
    assert result.preserved == 1
    assert recent_file.exists()


def test_cleanup_retention_boundary(tmp_path):
    """Verify boundary precision: file at 29 days is preserved, file at 31 days is deleted."""
    cleanup = ConversationLogCleanup(log_dir=tmp_path, retention_days=30)
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)

    file_inside = tmp_path / "MSS001_inside.json"
    file_inside.write_text("{}")
    set_file_mtime(file_inside, now - timedelta(days=29))

    file_outside = tmp_path / "MSS001_outside.json"
    file_outside.write_text("{}")
    set_file_mtime(file_outside, now - timedelta(days=31))

    result = cleanup.cleanup_expired_logs(now=now)

    assert result.deleted == 1
    assert result.preserved == 1
    assert file_inside.exists()
    assert not file_outside.exists()


def test_cleanup_ignores_unrelated_and_hidden_files(tmp_path):
    """Verify non-JSON, temporary, and hidden files are ignored even if old."""
    cleanup = ConversationLogCleanup(log_dir=tmp_path, retention_days=30)
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)

    text_file = tmp_path / "notes.txt"
    text_file.write_text("important notes")
    set_file_mtime(text_file, now - timedelta(days=40))

    tmp_file = tmp_path / ".tmp_partial.json"
    tmp_file.write_text("{}")
    set_file_mtime(tmp_file, now - timedelta(days=40))

    result = cleanup.cleanup_expired_logs(now=now)

    assert result.deleted == 0
    assert text_file.exists()
    assert tmp_file.exists()


def test_cleanup_handles_malformed_json_safely(tmp_path):
    """Verify that corrupt JSON files are processed safely by mtime without crashing."""
    cleanup = ConversationLogCleanup(log_dir=tmp_path, retention_days=30)
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)

    corrupt_file = tmp_path / "MSS001_corrupt.json"
    corrupt_file.write_text("{this is invalid json: definitely not valid")
    set_file_mtime(corrupt_file, now - timedelta(days=45))

    result = cleanup.cleanup_expired_logs(now=now)

    assert result.deleted == 1
    assert not corrupt_file.exists()


def test_cleanup_continues_after_individual_deletion_failure(tmp_path, monkeypatch):
    """Verify that if deleting one file fails, cleanup continues for the rest."""
    cleanup = ConversationLogCleanup(log_dir=tmp_path, retention_days=30)
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)

    file_fail = tmp_path / "MSS001_locked.json"
    file_fail.write_text("{}")
    set_file_mtime(file_fail, now - timedelta(days=40))

    file_ok = tmp_path / "MSS001_normal.json"
    file_ok.write_text("{}")
    set_file_mtime(file_ok, now - timedelta(days=40))

    orig_unlink = Path.unlink

    def mock_unlink(self, *args, **kwargs):
        if self.name == "MSS001_locked.json":
            raise PermissionError("File locked by another process")
        return orig_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", mock_unlink)

    result = cleanup.cleanup_expired_logs(now=now)

    assert result.failed == 1
    assert result.deleted == 1
    assert file_fail.exists()
    assert not file_ok.exists()


def test_cleanup_repeat_safe_and_idempotent(tmp_path):
    """Verify that running cleanup repeatedly does not cause errors."""
    cleanup = ConversationLogCleanup(log_dir=tmp_path, retention_days=30)
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)

    expired_file = tmp_path / "MSS001_expired.json"
    expired_file.write_text("{}")
    set_file_mtime(expired_file, now - timedelta(days=50))

    # First run: deletes the file
    res1 = cleanup.cleanup_expired_logs(now=now)
    assert res1.deleted == 1

    # Second run: nothing to delete, safe
    res2 = cleanup.cleanup_expired_logs(now=now)
    assert res2.deleted == 0
    assert res2.failed == 0


def test_cleanup_nonexistent_directory(tmp_path):
    """Verify cleanup on a non-existent directory safely returns empty result."""
    missing_dir = tmp_path / "non_existent_folder"
    cleanup = ConversationLogCleanup(log_dir=missing_dir, retention_days=30)

    result = cleanup.cleanup_expired_logs()
    assert result.deleted == 0
    assert result.failed == 0
    assert result.preserved == 0


def test_startup_cleanup_failure_does_not_prevent_fastapi_startup():
    """Verify that if startup cleanup raises an unexpected error, FastAPI still starts."""
    with patch.object(
        ConversationLogCleanup,
        "cleanup_expired_logs",
        side_effect=RuntimeError("Simulated critical startup cleanup error"),
    ):
        with TestClient(app) as test_client:
            response = test_client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}


def test_cleanup_applies_custom_configured_retention_period(tmp_path):
    """Verify that changing configured retention boundary changes which files expire (US3)."""
    # Create two files: one at 10 days old, one at 5 days old
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)

    file_10d = tmp_path / "MSS001_10d.json"
    file_10d.write_text("{}")
    set_file_mtime(file_10d, now - timedelta(days=10))

    file_5d = tmp_path / "MSS001_5d.json"
    file_5d.write_text("{}")
    set_file_mtime(file_5d, now - timedelta(days=5))

    # Under standard 30-day retention, neither file is expired
    cleanup_30d = ConversationLogCleanup(log_dir=tmp_path, retention_days=30)
    res_30 = cleanup_30d.cleanup_expired_logs(now=now)
    assert res_30.deleted == 0
    assert res_30.preserved == 2
    assert file_10d.exists()
    assert file_5d.exists()

    # Under configured 7-day retention, 10d file expires while 5d file is preserved
    cleanup_7d = ConversationLogCleanup(log_dir=tmp_path, retention_days=7)
    res_7 = cleanup_7d.cleanup_expired_logs(now=now)
    assert res_7.deleted == 1
    assert res_7.preserved == 1
    assert not file_10d.exists()
    assert file_5d.exists()

