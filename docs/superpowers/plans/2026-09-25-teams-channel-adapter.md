# Microsoft Teams Channel Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a production-grade, zero-external-SDK Microsoft Teams Driving Channel Adapter for Company_Bot following Hexagonal Architecture (Ports and Adapters), with identity bridging, session isolation, and Microsoft Adaptive Card formatting.

**Architecture:** A driving domain port (`ChannelAdapterPort`) with an abstract base class (`BaseChannelAdapter`) providing a webhook template method. The Teams implementation parses Bot Framework / Webhook activity payloads, strips bot mentions, validates HMAC signatures, maps sender UPN/email to `AuthenticatedPrincipal` via `ChannelIdentityBridge`, delegates multi-turn queries to `QueryOrchestrator`, and returns rich Microsoft Adaptive Cards (v1.4) with citation `FactSet`s.

**Tech Stack:** Python 3.12 standard library (`hmac`, `hashlib`, `json`, `dataclasses`, `re`), FastAPI / Starlette (`APIRouter`, `Request`, `Response`), Pydantic v2, Pytest.

**Spec:** [Consolidated_Implementation_Plan.md](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/Documentation/Plan/v3/Consolidated_Implementation_Plan.md), [Task_Timeline.md](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/Documentation/Plan/v3/Task_Timeline.md) (Tasks AK-2.1 through AK-2.4).

## Global Constraints
- Zero external SDK dependencies: Avoid `botbuilder-python` or `microsoft-teams-apps`. Standard library `hmac`, `hashlib`, `json` only.
- Strict Hexagonal Architecture: Domain ports in `app/domain/ports/channel_adapter.py`; infrastructure implementations in `app/infrastructure/channels/`.
- Frozen immutable models: Use `@dataclass(frozen=True)` for domain messages and users.
- Fast, non-blocking async execution in FastAPI without separate OS background processes.

## Review Focus
1. Malformed webhook JSON: Returns HTTP 400 with a clean error JSON rather than crashing FastAPI.
2. Bot mention stripping: Cleans XML `<at>CompanyBot</at>` tags and extra whitespace from Teams message text.
3. HMAC verification: Rejects invalid HMAC signatures with HTTP 401 when a secret is configured; allows bypass when `skip_auth=True`.
4. Identity Bridge resolution: Known employee email maps to `AuthenticatedPrincipal(uid=user.uid)`; unknown email gracefully falls back to guest principal without throwing 500.
5. Adaptive card formatting: Returns compliant Adaptive Card schema with answer markdown and citation FactSets; handles empty citations gracefully.

---

### Task 1: Domain Port Contracts (`app/domain/ports/channel_adapter.py`)

**Files:**
- Create: `app/domain/ports/channel_adapter.py`
- Test: `tests/unit/test_channel_adapter_contracts.py`

**Interfaces:**
- Consumes: None (pure domain port).
- Produces: `ChannelUser`, `ChannelMessage`, `ChannelResponse`, `ChannelAdapterPort`.

- [ ] **Step 1: Write the failing contract test**

```python
# tests/unit/test_channel_adapter_contracts.py
from app.domain.ports.channel_adapter import (
    ChannelUser,
    ChannelMessage,
    ChannelResponse,
    ChannelAdapterPort,
)


def test_channel_user_instantiation():
    user = ChannelUser(user_id="29:user123", email="user@company.com", display_name="John Doe")
    assert user.user_id == "29:user123"
    assert user.email == "user@company.com"
    assert user.display_name == "John Doe"


def test_channel_message_session_id_formatting():
    user = ChannelUser(user_id="29:user123", email="user@company.com")
    msg = ChannelMessage(
        channel_name="teams",
        conversation_id="19:thread-abc",
        text="What is the leave policy?",
        sender=user,
    )
    assert msg.session_id == "teams:19:thread-abc"
    assert msg.text == "What is the leave policy?"


def test_channel_response_defaults():
    res = ChannelResponse(status_code=200, text="Hello world")
    assert res.status_code == 200
    assert res.text == "Hello world"
    assert res.card_payload is None
    assert isinstance(res.headers, dict)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_channel_adapter_contracts.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.domain.ports.channel_adapter'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/domain/ports/channel_adapter.py
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional, Protocol, runtime_checkable
from starlette.requests import Request


@dataclass(frozen=True)
class ChannelUser:
    """Normalized sender metadata across all chat channels."""
    user_id: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    tenant_id: Optional[str] = None


@dataclass(frozen=True)
class ChannelMessage:
    """Normalized inbound message from any driving channel."""
    channel_name: str
    conversation_id: str
    text: str
    sender: ChannelUser
    raw_payload: Dict[str, Any] = field(default_factory=dict)
    message_id: Optional[str] = None
    service_url: Optional[str] = None

    @property
    def session_id(self) -> str:
        """Standardized session key format: '{channel_name}:{conversation_id}'."""
        return f"{self.channel_name}:{self.conversation_id}"


@dataclass(frozen=True)
class ChannelResponse:
    """Normalized outbound response delivered back to the channel."""
    status_code: int = 200
    text: str = ""
    card_payload: Optional[Dict[str, Any]] = None
    headers: Dict[str, str] = field(default_factory=dict)


@runtime_checkable
class ChannelAdapterPort(Protocol):
    """Hexagonal driving port for external chat channels (Teams, Slack, etc.)."""
    @property
    def channel_name(self) -> str: ...

    async def parse_and_validate(self, request: Request) -> ChannelMessage: ...

    def format_response(self, message: ChannelMessage, result: Dict[str, Any]) -> ChannelResponse: ...

    async def handle_webhook(
        self,
        request: Request,
        chat_dispatcher: Callable[[ChannelMessage], Awaitable[Dict[str, Any]]],
    ) -> ChannelResponse: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_channel_adapter_contracts.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/domain/ports/channel_adapter.py tests/unit/test_channel_adapter_contracts.py
git commit -m "feat(channels): define channel adapter domain port contracts"
```

---

### Task 2: Infrastructure Template Method Base (`app/infrastructure/channels/base.py`)

**Files:**
- Create: `app/infrastructure/channels/base.py`
- Test: `tests/unit/test_channel_base_adapter.py`

**Interfaces:**
- Consumes: `ChannelAdapterPort`, `ChannelMessage`, `ChannelResponse` from `app.domain.ports.channel_adapter`.
- Produces: `BaseChannelAdapter(ABC)` implementing the webhook template method.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_channel_base_adapter.py
import pytest
from starlette.requests import Request
from starlette.datastructures import Headers
from app.domain.ports.channel_adapter import ChannelUser, ChannelMessage, ChannelResponse
from app.infrastructure.channels.base import BaseChannelAdapter, ChannelAuthenticationError, ChannelValidationError


class DummyAdapter(BaseChannelAdapter):
    @property
    def channel_name(self) -> str:
        return "dummy"

    async def parse_and_validate(self, request: Request) -> ChannelMessage:
        body = await request.json()
        if "auth_fail" in body:
            raise ChannelAuthenticationError("Invalid signature")
        if "bad_data" in body:
            raise ChannelValidationError("Malformed payload")
        return ChannelMessage(
            channel_name="dummy",
            conversation_id="conv-1",
            text=body.get("text", ""),
            sender=ChannelUser(user_id="user-1"),
        )

    def format_response(self, message: ChannelMessage, result: dict) -> ChannelResponse:
        return ChannelResponse(status_code=200, text=f"Echo: {result.get('answer', '')}")


def make_request(payload: dict) -> Request:
    import json
    body_bytes = json.dumps(payload).encode("utf-8")
    async def receive():
        return {"type": "http.request", "body": body_bytes}
    scope = {"type": "http", "method": "POST", "path": "/test", "headers": []}
    return Request(scope, receive)


@pytest.mark.asyncio
async def test_base_adapter_template_method_success():
    adapter = DummyAdapter()
    req = make_request({"text": "Hello"})
    async def fake_dispatcher(msg: ChannelMessage):
        return {"answer": "Hi there"}

    response = await adapter.handle_webhook(req, fake_dispatcher)
    assert response.status_code == 200
    assert response.text == "Echo: Hi there"


@pytest.mark.asyncio
async def test_base_adapter_auth_error():
    adapter = DummyAdapter()
    req = make_request({"auth_fail": True})
    async def fake_dispatcher(msg):
        return {}

    response = await adapter.handle_webhook(req, fake_dispatcher)
    assert response.status_code == 401
    assert "Invalid signature" in response.text


@pytest.mark.asyncio
async def test_base_adapter_validation_error():
    adapter = DummyAdapter()
    req = make_request({"bad_data": True})
    async def fake_dispatcher(msg):
        return {}

    response = await adapter.handle_webhook(req, fake_dispatcher)
    assert response.status_code == 400
    assert "Malformed payload" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_channel_base_adapter.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.infrastructure.channels.base'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/infrastructure/channels/base.py
from abc import ABC, abstractmethod
import logging
from typing import Any, Awaitable, Callable, Dict
from starlette.requests import Request

from app.domain.ports.channel_adapter import (
    ChannelAdapterPort,
    ChannelMessage,
    ChannelResponse,
)

logger = logging.getLogger(__name__)


class ChannelAuthenticationError(Exception):
    """Raised when channel message HMAC or JWT token validation fails."""
    pass


class ChannelValidationError(Exception):
    """Raised when inbound channel payload is malformed or empty."""
    pass


class BaseChannelAdapter(ChannelAdapterPort, ABC):
    """Abstract Base Class providing the Template Method pattern for webhook handling."""

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Name of the driving channel, e.g. 'teams' or 'slack'."""
        pass

    @abstractmethod
    async def parse_and_validate(self, request: Request) -> ChannelMessage:
        """Parse raw request into normalized ChannelMessage, validating signatures/tokens."""
        pass

    @abstractmethod
    def format_response(self, message: ChannelMessage, result: Dict[str, Any]) -> ChannelResponse:
        """Format domain orchestrator result into channel-specific payload."""
        pass

    async def handle_webhook(
        self,
        request: Request,
        chat_dispatcher: Callable[[ChannelMessage], Awaitable[Dict[str, Any]]],
    ) -> ChannelResponse:
        """Template Method: orchestrates validation, query execution, and response formatting."""
        try:
            message = await self.parse_and_validate(request)
        except ChannelAuthenticationError as exc:
            logger.warning("Channel [%s] auth failed: %s", self.channel_name, exc)
            return ChannelResponse(status_code=401, text=str(exc))
        except ChannelValidationError as exc:
            logger.warning("Channel [%s] validation failed: %s", self.channel_name, exc)
            return ChannelResponse(status_code=400, text=str(exc))
        except Exception as exc:
            logger.error("Channel [%s] payload parse exception: %s", self.channel_name, exc, exc_info=True)
            return ChannelResponse(status_code=400, text="Invalid channel payload")

        try:
            result = await chat_dispatcher(message)
            return self.format_response(message, result)
        except Exception as exc:
            logger.error("Channel [%s] dispatcher failed: %s", self.channel_name, exc, exc_info=True)
            return ChannelResponse(
                status_code=500,
                text="An error occurred while processing your request.",
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_channel_base_adapter.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/channels/base.py tests/unit/test_channel_base_adapter.py
git commit -m "feat(channels): add BaseChannelAdapter template method"
```

---

### Task 3: Identity Bridge (`app/infrastructure/channels/identity_bridge.py`)

**Files:**
- Create: `app/infrastructure/channels/identity_bridge.py`
- Test: `tests/unit/test_channel_identity_bridge.py`

**Interfaces:**
- Consumes: `ChannelUser` from `app.domain.ports.channel_adapter`, `UserRepository` from `app.domain.ports.organization_repositories`.
- Produces: `ChannelIdentityBridge.resolve_principal(user: ChannelUser) -> AuthenticatedPrincipal`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_channel_identity_bridge.py
from unittest.mock import MagicMock
from app.domain.ports.channel_adapter import ChannelUser
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.infrastructure.channels.identity_bridge import ChannelIdentityBridge


def test_resolve_principal_known_user():
    user_repo = MagicMock()
    mock_db_user = MagicMock()
    mock_db_user.uid = "usr_real_123"
    user_repo.get_by_email.return_value = mock_db_user

    bridge = ChannelIdentityBridge(user_repo_provider=lambda: user_repo)
    user = ChannelUser(user_id="29:teams_id", email="known@company.com")

    principal = bridge.resolve_principal(user)
    assert principal.uid == "usr_real_123"
    user_repo.get_by_email.assert_called_once_with("known@company.com")


def test_resolve_principal_unknown_user_fallback():
    user_repo = MagicMock()
    user_repo.get_by_email.return_value = None
    user_repo.get_by_username.return_value = None

    bridge = ChannelIdentityBridge(user_repo_provider=lambda: user_repo)
    user = ChannelUser(user_id="29:teams_id", email="stranger@company.com")

    principal = bridge.resolve_principal(user)
    assert principal.uid.startswith("channel_guest:")
    assert "29:teams_id" in principal.uid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_channel_identity_bridge.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.infrastructure.channels.identity_bridge'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/infrastructure/channels/identity_bridge.py
import logging
from typing import Callable, Optional
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.ports.channel_adapter import ChannelUser
from app.domain.ports.organization_repositories import UserRepository

logger = logging.getLogger(__name__)


class ChannelIdentityBridge:
    """Maps channel-specific user identities (UPN/email/ID) to domain AuthenticatedPrincipal."""

    def __init__(self, user_repo_provider: Optional[Callable[[], UserRepository]] = None):
        self._user_repo_provider = user_repo_provider

    def _get_user_repo(self) -> Optional[UserRepository]:
        if self._user_repo_provider:
            return self._user_repo_provider()
        try:
            from app.infrastructure.persistence.factory import get_session_factory
            from app.infrastructure.persistence.sqlalchemy.repositories import SqlAlchemyUserRepository
            session = get_session_factory()()
            return SqlAlchemyUserRepository(session)
        except Exception as exc:
            logger.debug("Failed to acquire DB user repository for channel identity: %s", exc)
            return None

    def resolve_principal(self, sender: ChannelUser) -> AuthenticatedPrincipal:
        """Resolves sender into AuthenticatedPrincipal, checking email then username."""
        repo = self._get_user_repo()
        if repo:
            try:
                # 1. Look up by email (Teams userPrincipalName or email)
                if sender.email:
                    db_user = repo.get_by_email(sender.email.strip().lower())
                    if db_user:
                        return AuthenticatedPrincipal(uid=db_user.uid)

                # 2. Look up by user_id as username
                db_user = repo.get_by_username(sender.user_id)
                if db_user:
                    return AuthenticatedPrincipal(uid=db_user.uid)
            except Exception as exc:
                logger.warning("Identity lookup failed for %s: %s", sender.email or sender.user_id, exc)

        # Fallback to guest principal with channel prefix
        return AuthenticatedPrincipal(uid=f"channel_guest:{sender.user_id}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_channel_identity_bridge.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/channels/identity_bridge.py tests/unit/test_channel_identity_bridge.py
git commit -m "feat(channels): add ChannelIdentityBridge for RBAC mapping"
```

---

### Task 4: Teams Adaptive Card Formatter (`app/infrastructure/channels/teams/formatter.py`)

**Files:**
- Create: `app/infrastructure/channels/teams/formatter.py`
- Test: `tests/unit/test_teams_adaptive_card_formatter.py`

**Interfaces:**
- Consumes: Result dict with `answer`, `citations`.
- Produces: `format_teams_adaptive_card(result: Dict[str, Any]) -> Dict[str, Any]`, `format_teams_text(result: Dict[str, Any]) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_teams_adaptive_card_formatter.py
from app.infrastructure.channels.teams.formatter import (
    format_teams_adaptive_card,
    format_teams_text,
)


def test_format_teams_text_with_citations():
    result = {
        "answer": "Company employees receive 20 days annual leave.",
        "citations": [
            {"source": "handbook.docx", "section": "Leave", "text": "Annual leave policy: 20 days."}
        ],
    }
    text = format_teams_text(result)
    assert "Company employees receive 20 days annual leave." in text
    assert "Source: handbook.docx" in text
    assert "Leave" in text


def test_format_teams_adaptive_card_schema():
    result = {
        "answer": "Yes, bereavement leave is 5 days.",
        "citations": [
            {"source": "hr_policy.docx", "section": "Bereavement", "text": "Up to 5 days paid leave."}
        ],
    }
    card = format_teams_adaptive_card(result)
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.4"
    assert "$schema" in card
    body = card["body"]
    assert any("Yes, bereavement leave is 5 days." in item.get("text", "") for item in body)
    assert any(item.get("type") == "FactSet" for item in body)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_teams_adaptive_card_formatter.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.infrastructure.channels.teams.formatter'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/infrastructure/channels/teams/formatter.py
from typing import Any, Dict, List


def format_teams_text(result: Dict[str, Any]) -> str:
    """Format answer and citations as readable markdown text."""
    lines = [result.get("answer", "I could not generate an answer.")]
    citations = result.get("citations") or []

    if citations:
        lines.append("\n**Sources & References:**")
        for cite in citations:
            src = cite.get("source") or "Policy"
            sec = cite.get("section") or ""
            txt = cite.get("text") or ""
            sec_info = f" ({sec})" if sec else ""
            lines.append(f"- **Source: {src}{sec_info}**\n  > {txt}")

    return "\n\n".join(lines)


def format_teams_adaptive_card(result: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a Microsoft Adaptive Card (schema v1.4) JSON payload."""
    answer = result.get("answer", "I could not generate an answer.")
    citations: List[Dict[str, Any]] = result.get("citations") or []

    body: List[Dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": answer,
            "wrap": True,
            "size": "Medium",
        }
    ]

    if citations:
        body.append(
            {
                "type": "TextBlock",
                "text": "Sources & References",
                "weight": "Bolder",
                "size": "Small",
                "separator": True,
                "spacing": "Medium",
            }
        )

        facts = []
        for cite in citations:
            src = cite.get("source") or "Document"
            sec = cite.get("section") or ""
            txt = cite.get("text") or ""
            title = f"{src} [{sec}]" if sec else src
            facts.append({"title": title, "value": txt[:250] + ("..." if len(txt) > 250 else "")})

        body.append({"type": "FactSet", "facts": facts})

    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_teams_adaptive_card_formatter.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/channels/teams/formatter.py tests/unit/test_teams_adaptive_card_formatter.py
git commit -m "feat(teams): add adaptive card v1.4 and markdown formatter"
```

---

### Task 5: Teams Channel Adapter (`app/infrastructure/channels/teams/adapter.py`)

**Files:**
- Create: `app/infrastructure/channels/teams/adapter.py`
- Test: `tests/unit/test_teams_adapter.py`

**Interfaces:**
- Consumes: `BaseChannelAdapter`, `ChannelMessage`, `ChannelResponse`, `ChannelUser`, `format_teams_adaptive_card`.
- Produces: `TeamsChannelAdapter(BaseChannelAdapter)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_teams_adapter.py
import base64
import hashlib
import hmac
import json
import pytest
from starlette.requests import Request
from app.infrastructure.channels.teams.adapter import TeamsChannelAdapter
from app.infrastructure.channels.base import ChannelAuthenticationError, ChannelValidationError


def make_teams_request(payload: dict, secret: str = "", auth_header: str = "") -> Request:
    raw = json.dumps(payload).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
    ]
    if auth_header:
        headers.append((b"authorization", auth_header.encode("utf-8")))

    async def receive():
        return {"type": "http.request", "body": raw}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/channels/teams/messages",
        "headers": headers,
    }
    return Request(scope, receive)


@pytest.mark.asyncio
async def test_teams_adapter_parse_activity_and_strip_mentions():
    adapter = TeamsChannelAdapter(skip_auth=True)
    activity = {
        "type": "message",
        "id": "msg-123",
        "text": "<at>CompanyBot</at> When is the office open?",
        "from": {
            "id": "29:teams_user_id",
            "name": "Jane Doe",
            "userPrincipalName": "jane.doe@company.com",
        },
        "conversation": {"id": "19:thread_id"},
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
    }
    req = make_teams_request(activity)
    message = await adapter.parse_and_validate(req)

    assert message.channel_name == "teams"
    assert message.text == "When is the office open?"
    assert message.conversation_id == "19:thread_id"
    assert message.session_id == "teams:19:thread_id"
    assert message.sender.user_id == "29:teams_user_id"
    assert message.sender.email == "jane.doe@company.com"
    assert message.sender.display_name == "Jane Doe"


@pytest.mark.asyncio
async def test_teams_adapter_hmac_verification():
    secret = "my_secret_token"
    adapter = TeamsChannelAdapter(security_token=secret, skip_auth=False)
    activity = {
        "type": "message",
        "text": "Hello",
        "from": {"id": "user1"},
        "conversation": {"id": "conv1"},
    }
    body_bytes = json.dumps(activity).encode("utf-8")
    # Generate valid HMAC-SHA256 signature
    signature = base64.b64encode(hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).digest()).decode("utf-8")
    req = make_teams_request(activity, auth_header=f"HMAC {signature}")

    message = await adapter.parse_and_validate(req)
    assert message.text == "Hello"


@pytest.mark.asyncio
async def test_teams_adapter_rejects_invalid_hmac():
    adapter = TeamsChannelAdapter(security_token="secret", skip_auth=False)
    activity = {"type": "message", "text": "Hello", "from": {"id": "u"}, "conversation": {"id": "c"}}
    req = make_teams_request(activity, auth_header="HMAC invalid_sig")

    with pytest.raises(ChannelAuthenticationError):
        await adapter.parse_and_validate(req)


def test_teams_adapter_format_response():
    adapter = TeamsChannelAdapter()
    from app.domain.ports.channel_adapter import ChannelMessage, ChannelUser
    msg = ChannelMessage("teams", "c1", "question", ChannelUser("u1"))
    result = {"answer": "42 is the answer", "citations": []}

    response = adapter.format_response(msg, result)
    assert response.status_code == 200
    assert response.card_payload is not None
    assert response.card_payload["type"] == "message"
    assert response.card_payload["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_teams_adapter.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.infrastructure.channels.teams.adapter'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/infrastructure/channels/teams/adapter.py
import base64
import hashlib
import hmac
import logging
import re
from typing import Any, Dict, Optional
from starlette.requests import Request

from app.domain.ports.channel_adapter import (
    ChannelMessage,
    ChannelResponse,
    ChannelUser,
)
from app.infrastructure.channels.base import (
    BaseChannelAdapter,
    ChannelAuthenticationError,
    ChannelValidationError,
)
from app.infrastructure.channels.teams.formatter import (
    format_teams_adaptive_card,
    format_teams_text,
)

logger = logging.getLogger(__name__)

# Pattern to strip <at>BotName</at> mention tags from incoming Teams text
_AT_MENTION_PATTERN = re.compile(r"<at>.*?</at>", re.IGNORECASE)


class TeamsChannelAdapter(BaseChannelAdapter):
    """Production Teams Adapter supporting Outgoing Webhooks and Bot Framework Activity schema."""

    def __init__(
        self,
        security_token: Optional[str] = None,
        skip_auth: bool = False,
    ):
        self._security_token = security_token
        self._skip_auth = skip_auth

    @property
    def channel_name(self) -> str:
        return "teams"

    def _verify_hmac_signature(self, body_bytes: bytes, auth_header: Optional[str]) -> bool:
        if not self._security_token:
            return True
        if not auth_header:
            return False

        parts = auth_header.split(" ", 1)
        token_to_verify = parts[1].strip() if len(parts) == 2 else parts[0].strip()

        key = self._security_token.encode("utf-8")
        expected_digest = hmac.new(key, body_bytes, hashlib.sha256).digest()
        expected_token = base64.b64encode(expected_digest).decode("utf-8")

        return hmac.compare_digest(token_to_verify, expected_token)

    async def parse_and_validate(self, request: Request) -> ChannelMessage:
        body_bytes = await request.body()
        if not body_bytes:
            raise ChannelValidationError("Empty request body")

        if not self._skip_auth and self._security_token:
            auth_header = request.headers.get("authorization")
            if not self._verify_hmac_signature(body_bytes, auth_header):
                raise ChannelAuthenticationError("Invalid HMAC signature")

        try:
            import json
            payload: Dict[str, Any] = json.loads(body_bytes.decode("utf-8"))
        except Exception as exc:
            raise ChannelValidationError(f"Invalid JSON payload: {exc}") from exc

        # Teams activity validation
        raw_text = payload.get("text") or ""
        clean_text = _AT_MENTION_PATTERN.sub("", raw_text).strip()
        if not clean_text:
            raise ChannelValidationError("Message text is empty after mention removal")

        conversation = payload.get("conversation") or {}
        conversation_id = conversation.get("id") or payload.get("id") or "default_thread"

        sender_info = payload.get("from") or {}
        user_id = sender_info.get("id") or "unknown_user"
        email = (
            sender_info.get("userPrincipalName")
            or sender_info.get("email")
            or sender_info.get("aadObjectId")
        )
        display_name = sender_info.get("name")

        user = ChannelUser(
            user_id=user_id,
            email=email,
            display_name=display_name,
            tenant_id=payload.get("channelData", {}).get("tenant", {}).get("id"),
        )

        return ChannelMessage(
            channel_name=self.channel_name,
            conversation_id=conversation_id,
            text=clean_text,
            sender=user,
            raw_payload=payload,
            message_id=payload.get("id"),
            service_url=payload.get("serviceUrl"),
        )

    def format_response(self, message: ChannelMessage, result: Dict[str, Any]) -> ChannelResponse:
        plain_text = format_teams_text(result)
        card = format_teams_adaptive_card(result)

        activity_payload = {
            "type": "message",
            "text": plain_text,
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": card,
                }
            ],
        }

        return ChannelResponse(
            status_code=200,
            text=plain_text,
            card_payload=activity_payload,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_teams_adapter.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/channels/teams/adapter.py tests/unit/test_teams_adapter.py
git commit -m "feat(teams): implement TeamsChannelAdapter with HMAC and mention stripping"
```

---

### Task 6: Adapter Registry & FastAPI Webhook Route (`app/infrastructure/channels/registry.py`, `app/api/routes/channels.py`)

**Files:**
- Create: `app/infrastructure/channels/registry.py`
- Create: `app/api/routes/channels.py`
- Modify: `app/main.py:7-14, 78-85`
- Test: `tests/unit/test_channels_route.py`

**Interfaces:**
- Consumes: `ChannelAdapterPort`, `ChannelIdentityBridge`, `QueryOrchestrator`, `AuthorizationEngine`.
- Produces: `POST /api/channels/{channel_name}/messages` endpoint.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_channels_route.py
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.infrastructure.channels.registry import register_channel_adapter, clear_channel_registry
from app.infrastructure.channels.teams.adapter import TeamsChannelAdapter


@pytest.fixture(autouse=True)
def setup_teams():
    clear_channel_registry()
    adapter = TeamsChannelAdapter(skip_auth=True)
    register_channel_adapter(adapter)
    yield
    clear_channel_registry()


def test_channel_not_found():
    client = TestClient(app)
    response = client.post("/api/channels/unknown_channel/messages", json={"text": "hello"})
    assert response.status_code == 404
    assert "not supported" in response.json()["detail"]


def test_teams_message_dispatch(monkeypatch):
    from app.api.routes import channels

    class MockOrchestrator:
        def answer(self, question, **kwargs):
            return {
                "answer": f"Echo: {question}",
                "citations": [{"source": "test.txt", "section": "1", "text": "Citation quote"}],
            }

    monkeypatch.setattr(channels, "_get_orchestrator", lambda: MockOrchestrator())

    client = TestClient(app)
    payload = {
        "type": "message",
        "text": "<at>Bot</at> What is the vacation policy?",
        "from": {"id": "user123", "userPrincipalName": "jane@company.com"},
        "conversation": {"id": "thread456"},
    }
    response = client.post("/api/channels/teams/messages", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "Echo: What is the vacation policy?" in data["text"]
    assert data["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_channels_route.py -q`
Expected: FAIL with 404 Not Found on `/api/channels/teams/messages`

- [ ] **Step 3: Write registry and router implementation**

Create `app/infrastructure/channels/registry.py`:
```python
# app/infrastructure/channels/registry.py
from typing import Dict, Optional
from app.domain.ports.channel_adapter import ChannelAdapterPort

_REGISTRY: Dict[str, ChannelAdapterPort] = {}


def register_channel_adapter(adapter: ChannelAdapterPort) -> None:
    _REGISTRY[adapter.channel_name.lower()] = adapter


def get_channel_adapter(channel_name: str) -> Optional[ChannelAdapterPort]:
    return _REGISTRY.get(channel_name.lower())


def clear_channel_registry() -> None:
    _REGISTRY.clear()
```

Create `app/api/routes/channels.py`:
```python
# app/api/routes/channels.py
import logging
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.domain.ports.channel_adapter import ChannelMessage
from app.infrastructure.channels.identity_bridge import ChannelIdentityBridge
from app.infrastructure.channels.registry import get_channel_adapter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/channels", tags=["channels"])

_identity_bridge = ChannelIdentityBridge()


def _get_orchestrator():
    from app.api.routes.chat import _orchestrator, init_orchestrator
    if _orchestrator is None:
        init_orchestrator()
    from app.api.routes.chat import _orchestrator as active_orc
    return active_orc


@router.post("/{channel_name}/messages")
async def channel_webhook(channel_name: str, request: Request) -> Response:
    adapter = get_channel_adapter(channel_name)
    if adapter is None:
        raise HTTPException(
            status_code=404,
            detail=f"Channel '{channel_name}' is not supported or not enabled.",
        )

    async def chat_dispatcher(message: ChannelMessage) -> Dict[str, Any]:
        orchestrator = _get_orchestrator()
        principal = _identity_bridge.resolve_principal(message.sender)

        # Build authorization scope if authorization engine available
        from app.domain.services.authorization_engine import AuthorizationScope
        scope = AuthorizationScope(is_admin=False, project_ids=[], document_ids=None, include_unassigned=True)
        try:
            from app.api.dependencies import get_authorization_service
            authz_service = get_authorization_service()
            if authz_service:
                scope = authz_service.authorization_scope(principal)
        except Exception as exc:
            logger.debug("Failed to calculate channel scope: %s", exc)

        return orchestrator.answer(
            question=message.text,
            session_id=message.session_id,
            authorization_scope=scope,
            user_context=principal,
        )

    result = await adapter.handle_webhook(request, chat_dispatcher)

    content = result.card_payload if result.card_payload is not None else {"text": result.text}
    return JSONResponse(status_code=result.status_code, content=content, headers=result.headers)
```

Mount in `app/main.py`:
Import `from app.api.routes.channels import router as channels_router` and `app.include_router(channels_router)`.
In lifespan: register default `TeamsChannelAdapter(skip_auth=True)` (or driven by `TEAMS_SKIP_AUTH` / `TEAMS_SECURITY_TOKEN` settings).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_channels_route.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/channels/registry.py app/api/routes/channels.py app/main.py tests/unit/test_channels_route.py
git commit -m "feat(channels): add adapter registry and /api/channels/{channel_name}/messages router"
```

---

### Task 7: Full Unit & Regression Suite Execution & Merge

**Files:**
- Test: All tests in `tests/unit/`

- [ ] **Step 1: Run complete unit test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/unit -q`
Expected: All 54+ test files pass with 0 errors.

- [ ] **Step 2: Commit all remaining cleanups on `feat/teams-channel-adapter`**

```bash
git add .
git commit -m "feat(teams): complete Microsoft Teams channel integration with test suite"
```

- [ ] **Step 3: Checkout `p3-akaash` and merge `feat/teams-channel-adapter`**

```bash
git checkout p3-akaash
git merge feat/teams-channel-adapter --no-ff -m "merge: feat/teams-channel-adapter into p3-akaash"
```

- [ ] **Step 4: Verify test suite on `p3-akaash`**

Run: `.venv\Scripts\python.exe -m pytest tests/unit -q`
Expected: All tests pass.
