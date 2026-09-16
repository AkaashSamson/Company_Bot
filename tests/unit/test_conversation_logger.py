import json
from datetime import datetime, timezone
from pathlib import Path
import pytest

from app.domain.entities.conversation_log import ConversationLog, ConversationMessage
from app.domain.services.employee_id_provider import EmployeeIdProvider
from app.infrastructure.logging.conversation_logger import ConversationLogger
from app.infrastructure.logging.mock_employee_id_provider import MockEmployeeIdProvider


class FixedIdProvider(EmployeeIdProvider):
    def __init__(self, emp_id="MSS001"):
        self.emp_id = emp_id

    def get_employee_id(self, user_context=None) -> str:
        return self.emp_id


def test_conversation_logger_writes_json_file_with_required_fields(tmp_path):
    """Verify JSON structure, schema, session_id, employee_id, and completed status."""
    logger = ConversationLogger(
        log_dir=tmp_path,
        employee_id_provider=FixedIdProvider("MSS001"),
    )

    fixed_time = datetime(2026, 9, 10, 15, 30, 0, tzinfo=timezone.utc)
    messages = [
        {"role": "user", "content": "What is the policy?"},
        {"role": "assistant", "content": "The policy is standard."},
    ]

    log_file = logger.log_conversation(
        session_id="session-xyz-123",
        messages=messages,
        timestamp=fixed_time,
    )

    assert log_file is not None
    assert log_file.exists()
    assert log_file.name == "MSS001_20260910_153000.json"

    with open(log_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Validate against ConversationLog schema
    log_model = ConversationLog(**data)
    assert log_model.employee_id == "MSS001"
    assert log_model.session_id == "session-xyz-123"
    assert log_model.recording_status == "completed"
    assert "conversation_id" not in data  # No separate conversation_id

    # Validate ordered messages
    assert len(log_model.messages) == 2
    assert log_model.messages[0].role == "user"
    assert log_model.messages[0].content == "What is the policy?"
    assert log_model.messages[1].role == "assistant"
    assert log_model.messages[1].content == "The policy is standard."
    assert log_model.messages[0].timestamp is not None
    assert log_model.messages[1].timestamp is not None


def test_conversation_logger_preserves_message_order_and_timestamps(tmp_path):
    """Verify that multiple messages preserve order and have UTC timestamps."""
    logger = ConversationLogger(
        log_dir=tmp_path,
        employee_id_provider=FixedIdProvider("MSS002"),
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    messages = [
        ConversationMessage(role="user", content="Step 1", timestamp=now_iso),
        ConversationMessage(role="assistant", content="Step 2", timestamp=now_iso),
        ConversationMessage(role="user", content="Step 3", timestamp=now_iso),
        ConversationMessage(role="assistant", content="Step 4", timestamp=now_iso),
    ]

    log_file = logger.log_conversation(
        session_id="session-seq-1",
        messages=messages,
    )

    assert log_file is not None
    with open(log_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    loaded_contents = [m["content"] for m in data["messages"]]
    assert loaded_contents == ["Step 1", "Step 2", "Step 3", "Step 4"]


def test_conversation_logger_same_second_collision_handling(tmp_path):
    """Verify that same-second completions create unique files with numerical suffixes."""
    logger = ConversationLogger(
        log_dir=tmp_path,
        employee_id_provider=FixedIdProvider("MSS001"),
    )

    fixed_time = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
    messages = [{"role": "user", "content": "Test"}]

    file1 = logger.log_conversation("s1", messages, timestamp=fixed_time)
    file2 = logger.log_conversation("s2", messages, timestamp=fixed_time)
    file3 = logger.log_conversation("s3", messages, timestamp=fixed_time)

    assert file1.name == "MSS001_20260910_120000.json"
    assert file2.name == "MSS001_20260910_120000_1.json"
    assert file3.name == "MSS001_20260910_120000_2.json"

    # All files exist and contain their respective sessions
    with open(file1) as f:
        assert json.load(f)["session_id"] == "s1"
    with open(file2) as f:
        assert json.load(f)["session_id"] == "s2"
    with open(file3) as f:
        assert json.load(f)["session_id"] == "s3"


def test_conversation_logger_redacts_sensitive_values(tmp_path):
    """Verify redaction of bearer tokens, API keys, passwords, and configured secrets."""
    secret_key = "super-secret-api-key-12345"
    logger = ConversationLogger(
        log_dir=tmp_path,
        employee_id_provider=FixedIdProvider("MSS001"),
        sensitive_values=[secret_key],
    )

    messages = [
        {
            "role": "user",
            "content": (
                f"My key is {secret_key}, and bearer token is Bearer eyJhbGciOiJIUzI1Ni. "
                "Also sk-proj-1234567890abcdef12345 and password: 'my_top_secret_pass'."
            ),
        },
        {
            "role": "assistant",
            "content": "Connecting to https://admin:super_secret@company.internal with gsk_abcdef1234567890abcdef",
        },
    ]

    log_file = logger.log_conversation("session-redact", messages)
    assert log_file is not None

    with open(log_file, "r", encoding="utf-8") as f:
        content_str = f.read()

    # Verify no cleartext secrets or credentials remain
    assert secret_key not in content_str
    assert "Bearer eyJhbGciOiJIUzI1Ni" not in content_str
    assert "Bearer [REDACTED]" in content_str
    assert "sk-proj-1234567890abcdef12345" not in content_str
    assert "gsk_abcdef1234567890abcdef" not in content_str
    assert "my_top_secret_pass" not in content_str
    assert "super_secret" not in content_str
    assert "[REDACTED]" in content_str


def test_conversation_logger_atomic_write_leaves_no_temp_files(tmp_path):
    """Verify atomic write leaves no lingering temporary files."""
    logger = ConversationLogger(
        log_dir=tmp_path,
        employee_id_provider=FixedIdProvider("MSS001"),
    )

    log_file = logger.log_conversation("session-atom", [{"role": "user", "content": "hello"}])
    assert log_file is not None
    assert log_file.exists()

    # Verify no .tmp files remain in log_dir
    temp_files = list(tmp_path.glob(".tmp_*"))
    assert len(temp_files) == 0


def test_conversation_logger_isolates_write_failures(monkeypatch, tmp_path):
    """Verify that write failure does not raise an exception and returns None."""
    logger = ConversationLogger(
        log_dir=tmp_path,
        employee_id_provider=FixedIdProvider("MSS001"),
    )

    def failing_write_atomic(*args, **kwargs):
        raise IOError("Disk full simulation")

    monkeypatch.setattr(logger, "_write_atomic", failing_write_atomic)

    # Should not raise exception
    result = logger.log_conversation("session-fail", [{"role": "user", "content": "hi"}])
    assert result is None
