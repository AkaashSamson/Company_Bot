from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import uuid4

import jwt

from app.core.settings import AUTH_REFRESH_TOKEN_EXPIRE_MINUTES, AUTH_TOKEN_EXPIRE_MINUTES
from app.domain.entities.organization_models import User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.organization_errors import AuthenticationError, ForbiddenError


def _authenticate_logger():
    import logging
    return logging.getLogger("knowlayer.authentication")


class AuthenticationServiceImpl:
    def __init__(
        self,
        unit_of_work_factory: Callable,
        password_hasher,
        secret_key: str,
        access_token_expires_minutes: int = AUTH_TOKEN_EXPIRE_MINUTES,
        refresh_token_expires_minutes: int = AUTH_REFRESH_TOKEN_EXPIRE_MINUTES,
    ):
        self.unit_of_work_factory = unit_of_work_factory
        self.password_hasher = password_hasher
        self.secret_key = secret_key
        self.access_token_expires_minutes = access_token_expires_minutes
        self.refresh_token_expires_minutes = refresh_token_expires_minutes

    def _encode_token(self, uid: str, token_type: str, expires_minutes: int) -> str:
        now = datetime.now(timezone.utc)
        return jwt.encode(
            {
                "sub": uid,
                "token_type": token_type,
                "iat": now,
                "exp": now + timedelta(minutes=expires_minutes),
                "jti": uuid4().hex,
            },
            self.secret_key,
            algorithm="HS256",
        )

    def authenticate(self, username: str, password: str) -> AuthenticatedPrincipal:
        logger = _authenticate_logger()
        with self.unit_of_work_factory() as uow:
            user = uow.users.get_by_username(username)
            identifier = username
            if user is None:
                user = uow.users.get_by_email(username)
                identifier = user.email if user else username
            if user is None:
                logger.warning("authentication failed: user not found for identifier %r", identifier)
                raise AuthenticationError("Invalid credentials")
            if user.status != "active":
                logger.warning("authentication failed: user %r is not active (status=%r)", user.uid, user.status)
                raise AuthenticationError("Invalid credentials")
            if not self.password_hasher.verify(password, user.password_representation):
                logger.warning("authentication failed: incorrect password for user %r", user.uid)
                raise AuthenticationError("Invalid credentials")
            logger.info("authentication succeeded for user %r", user.uid)
            token = self._encode_token(user.uid, "access", self.access_token_expires_minutes)
            refresh_token = self._encode_token(user.uid, "refresh", self.refresh_token_expires_minutes)
            return AuthenticatedPrincipal(user.uid, token, user.must_change_password, refresh_token)

    def resolve_token(self, token: str) -> AuthenticatedPrincipal:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            if payload.get("token_type") == "refresh":
                raise AuthenticationError("Invalid token")
            uid = payload.get("sub")
            if not uid:
                raise AuthenticationError("Invalid token")
            return AuthenticatedPrincipal(uid, token)
        except jwt.InvalidTokenError as error:
            raise AuthenticationError("Invalid token") from error

    def refresh_access_token(self, refresh_token: str) -> tuple[str, str, str]:
        logger = _authenticate_logger()
        try:
            payload = jwt.decode(refresh_token, self.secret_key, algorithms=["HS256"])
        except jwt.InvalidTokenError as error:
            raise AuthenticationError("Invalid refresh token") from error
        if payload.get("token_type") != "refresh":
            raise AuthenticationError("Invalid refresh token")
        uid = payload.get("sub")
        if not uid:
            raise AuthenticationError("Invalid refresh token")
        with self.unit_of_work_factory() as uow:
            user = uow.users.get_by_uid(uid)
            if user is None or user.status != "active":
                raise AuthenticationError("Invalid refresh token")
        logger.info("token refresh succeeded for user %r", uid)
        return (
            uid,
            self._encode_token(uid, "access", self.access_token_expires_minutes),
            self._encode_token(uid, "refresh", self.refresh_token_expires_minutes),
        )

    def change_password(self, principal: AuthenticatedPrincipal, current_password: str, new_password: str) -> None:
        if len(new_password) < 8:
            raise AuthenticationError("Password must be at least 8 characters")
        with self.unit_of_work_factory() as uow:
            user = uow.users.get_by_uid(principal.uid)
            if user is None or user.status != "active" or not self.password_hasher.verify(current_password, user.password_representation):
                raise AuthenticationError("Invalid credentials")
            user.password_representation = self.password_hasher.hash(new_password)
            user.password_changed_at = datetime.now(timezone.utc)
            user.must_change_password = False
            uow.users.save(user)
            uow.commit()

    def admin_change_password(self, actor: AuthenticatedPrincipal, target_uid: str, new_password: str) -> None:
        if len(new_password) < 8:
            raise AuthenticationError("Password must be at least 8 characters")
        with self.unit_of_work_factory() as uow:
            admin = uow.users.get_by_uid(actor.uid)
            target = uow.users.get_by_uid(target_uid)
            if admin is None or admin.status != "active" or admin.role.casefold() != "admin":
                raise ForbiddenError("Admin access required")
            if target is None or target.status != "active":
                raise AuthenticationError("User not found")
            target.password_representation = self.password_hasher.hash(new_password)
            target.password_changed_at = datetime.now(timezone.utc)
            target.must_change_password = True
            uow.users.save(target)
            uow.commit()