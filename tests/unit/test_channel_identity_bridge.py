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
