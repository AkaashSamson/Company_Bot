import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Sequence, Union

from app.core.settings import (
    CONVERSATION_LOG_DIR,
    GROQ_API_KEY,
    OPENROUTER_API_KEY,
)
from app.domain.entities.conversation_log import (
    ConversationLog,
    ConversationMessage,
)
from app.domain.services.employee_id_provider import EmployeeIdProvider
from app.infrastructure.logging.database_employee_id_provider import DatabaseEmployeeIdProvider

logger = logging.getLogger(__name__)


class ConversationLogger:
    """
    Persists completed conversations as employee-scoped JSON files.
    Redacts sensitive credentials, manages UTC-stamped file naming,
    handles same-second collisions, and performs atomic writes.
    """

    REDACTED_TEXT = "[REDACTED]"

    PATTERNS = [
        # Bearer tokens
        (re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]+)", re.IGNORECASE), r"Bearer [REDACTED]"),
        # Common LLM API keys (sk-..., gsk_...)
        (re.compile(r"\b(sk-[A-Za-z0-9_\-]{16,})\b"), REDACTED_TEXT),
        (re.compile(r"\b(gsk_[A-Za-z0-9_\-]{16,})\b"), REDACTED_TEXT),
        # Generic credentials, e.g. api_key: "secret", password="secret", token='secret'
        (
            re.compile(
                r"(?i)\b(api[_-]?key|secret|password|token|auth[_-]?token)\b\s*[:=]\s*(['\"]?)([^\s'\",;]+)\2"
            ),
            r"\1: [REDACTED]",
        ),
        # Basic auth in URLs
        (
            re.compile(r"(https?://)([^:\s]+):([^@\s]+)@"),
            r"\1[REDACTED]:[REDACTED]@",
        ),
    ]

    def __init__(
        self,
        log_dir: Optional[Union[str, Path]] = None,
        employee_id_provider: Optional[EmployeeIdProvider] = None,
        sensitive_values: Optional[Sequence[str]] = None,
    ) -> None:
        self.log_dir = Path(log_dir) if log_dir else CONVERSATION_LOG_DIR
        
        if employee_id_provider:
            self.employee_id_provider = employee_id_provider
        else:
            self.employee_id_provider = DatabaseEmployeeIdProvider()

        # Collect configured sensitive values to redact
        self._sensitive_values: List[str] = []
        if sensitive_values:
            self._sensitive_values.extend(s for s in sensitive_values if s and len(s) >= 4)
        else:
            for secret in (OPENROUTER_API_KEY, GROQ_API_KEY):
                if secret and len(secret) >= 4:
                    self._sensitive_values.append(secret)
        
        self._active_sessions: dict[str, Path] = {}

    def redact(self, text: str) -> str:
        """
        Redact credentials, tokens, and configured secrets from text.
        """
        if not text:
            return text

        redacted = text

        # 1. Exact matches for configured secrets
        for secret in self._sensitive_values:
            if secret in redacted:
                redacted = redacted.replace(secret, self.REDACTED_TEXT)

        # 2. Regular expression pattern redactions
        for pattern, replacement in self.PATTERNS:
            redacted = pattern.sub(replacement, redacted)

        return redacted

    def _generate_log_path(self, employee_id: str, timestamp: datetime) -> Path:
        """
        Construct destination file path with format: <employee_id>_<timestamp>.json
        Handles same-second collisions with a numerical suffix (_1, _2, etc.).
        """
        base_ts = timestamp.strftime("%Y%m%d_%H%M%S")
        filename = f"{employee_id}_{base_ts}.json"
        target_path = self.log_dir / filename

        if not target_path.exists():
            return target_path

        counter = 1
        while True:
            candidate = self.log_dir / f"{employee_id}_{base_ts}_{counter}.json"
            if not candidate.exists():
                return candidate
            counter += 1

    def _write_atomic(self, target_path: Path, log_data: dict) -> None:
        """
        Write payload to a temporary file in the destination directory and
        atomically rename it to the final target path.
        """
        self.log_dir.mkdir(parents=True, exist_ok=True)
        temp_fd, temp_path_str = tempfile.mkstemp(
            prefix=".tmp_",
            suffix=".json",
            dir=str(self.log_dir),
        )
        temp_path = Path(temp_path_str)
        try:
            with open(temp_fd, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)
            os.replace(temp_path, target_path)
        except Exception:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise

    def log_conversation(
        self,
        session_id: str,
        messages: Sequence[Union[ConversationMessage, dict]],
        user_context: Optional[Any] = None,
        timestamp: Optional[datetime] = None,
    ) -> Optional[Path]:
        """
        Record a completed conversation into a JSON log file.
        Returns the Path to the written file, or None if logging failed.
        Logging failures are isolated and never raise to the caller.
        """
        try:
            now_utc = timestamp or datetime.now(timezone.utc)
            employee_id = self.employee_id_provider.get_employee_id(user_context)

            processed_messages: List[ConversationMessage] = []
            for msg in messages:
                if isinstance(msg, ConversationMessage):
                    role = msg.role
                    content = self.redact(msg.content)
                    msg_ts = msg.timestamp
                elif isinstance(msg, dict):
                    role = msg.get("role", "user")
                    content = self.redact(msg.get("content", ""))
                    msg_ts = msg.get("timestamp") or now_utc.isoformat()
                else:
                    role = getattr(msg, "role", "user")
                    content = self.redact(getattr(msg, "content", ""))
                    msg_ts = getattr(msg, "timestamp", None) or now_utc.isoformat()

                processed_messages.append(
                    ConversationMessage(
                        role=role,
                        content=content,
                        timestamp=msg_ts,
                    )
                )

            if session_id in self._active_sessions and self._active_sessions[session_id].exists():
                target_path = self._active_sessions[session_id]
                try:
                    with open(target_path, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                    existing_log = ConversationLog(**existing_data)
                    existing_log.messages.extend(processed_messages)
                    self._write_atomic(target_path, existing_log.model_dump())
                    logger.info("Successfully appended to conversation log: %s", target_path.name)
                    return target_path
                except Exception as e:
                    logger.warning("Failed to append to %s, falling back to new file: %s", target_path, e)

            conversation_log = ConversationLog(
                employee_id=employee_id,
                session_id=session_id,
                messages=processed_messages,
                recording_status="completed",
            )

            target_path = self._generate_log_path(employee_id, now_utc)
            self._write_atomic(target_path, conversation_log.model_dump())
            self._active_sessions[session_id] = target_path
            logger.info("Successfully recorded new conversation log: %s", target_path.name)
            return target_path

        except Exception as exc:
            logger.error("Failed to record conversation log for session %s: %s", session_id, exc)
            return None
