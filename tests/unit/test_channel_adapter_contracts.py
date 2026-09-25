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
