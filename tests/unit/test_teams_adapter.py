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
    assert "42 is the answer" in response.card_payload["text"]
