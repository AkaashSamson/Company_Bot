from datetime import datetime, timezone
from typing import Callable

import jwt

from app.domain.entities.organization_models import User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.organization_errors import AuthenticationError, ForbiddenError


def _authenticate_logger():
    import logging
    return logging.getLogger("knowlayer.authentication")


class AuthenticationServiceImpl:
    def __init__(self, unit_of_work_factory: Callable, password_hasher, secret_key: str):
        self.unit_of_work_factory = unit_of_work_factory
        self.password_hasher = password_hasher
        self.secret_key = secret_key

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
            token = jwt.encode({"sub": user.uid}, self.secret_key, algorithm="HS256")
            return AuthenticatedPrincipal(user.uid, token, user.must_change_password)

    def resolve_token(self, token: str) -> AuthenticatedPrincipal:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            uid = payload.get("sub")
            if not uid:
                raise AuthenticationError("Invalid token")
            return AuthenticatedPrincipal(uid, token)
        except jwt.InvalidTokenError as error:
            raise AuthenticationError("Invalid token") from error

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