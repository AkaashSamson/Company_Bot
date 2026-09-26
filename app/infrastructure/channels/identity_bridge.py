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
