import pytest
from starlette.requests import Request
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
