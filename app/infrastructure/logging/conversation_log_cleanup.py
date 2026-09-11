from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import os
from pathlib import Path
from typing import Optional, Union

from app.core.settings import CONVERSATION_LOG_DIR, CONVERSATION_LOG_RETENTION_DAYS

logger = logging.getLogger(__name__)


@dataclass
class CleanupResult:
    """Summary of conversation log cleanup operations."""

    deleted: int = 0
    failed: int = 0
    preserved: int = 0


class ConversationLogCleanup:
    """
    Scans the conversation log directory and removes expired log files
    based on filesystem modification time (mtime) and configured retention days.
    """

    def __init__(
        self,
        log_dir: Optional[Union[str, Path]] = None,
        retention_days: Optional[int] = None,
    ) -> None:
        self.log_dir = Path(log_dir) if log_dir else CONVERSATION_LOG_DIR
        self.retention_days = (
            retention_days
            if retention_days is not None
            else CONVERSATION_LOG_RETENTION_DAYS
        )

    def is_eligible_file(self, path: Path) -> bool:
        """
        Check if a file is an eligible conversation log candidate.
        Excludes directories, hidden files, temporary files, and non-JSON files.
        """
        if not path.is_file():
            return False
        if path.name.startswith((".", "_tmp")):
            return False
        if path.suffix.lower() != ".json":
            return False
        return True

    def cleanup_expired_logs(
        self,
        now: Optional[datetime] = None,
    ) -> CleanupResult:
        """
        Delete conversation logs older than retention_days based on modification time (mtime).
        Preserves non-expired and unrelated files.
        Continues safely across per-file deletion failures.
        Repeat-safe and idempotent.
        """
        result = CleanupResult()

        if not self.log_dir.exists():
            logger.info("Log directory does not exist: %s. Skipping cleanup.", self.log_dir)
            return result

        current_time = now or datetime.now(timezone.utc)
        cutoff_timestamp = (current_time - timedelta(days=self.retention_days)).timestamp()

        try:
            entries = list(self.log_dir.iterdir())
        except Exception as exc:
            logger.error("Failed to list log directory %s: %s", self.log_dir, exc)
            return result

        for entry in entries:
            try:
                if not self.is_eligible_file(entry):
                    continue

                mtime = entry.stat().st_mtime
                if mtime < cutoff_timestamp:
                    try:
                        entry.unlink()
                        result.deleted += 1
                        logger.info("Deleted expired conversation log: %s", entry.name)
                    except Exception as del_exc:
                        result.failed += 1
                        logger.error(
                            "Failed to delete expired log %s: %s",
                            entry.name,
                            del_exc,
                        )
                else:
                    result.preserved += 1
            except Exception as entry_exc:
                logger.error(
                    "Error inspecting log entry %s: %s",
                    entry.name,
                    entry_exc,
                )

        return result
