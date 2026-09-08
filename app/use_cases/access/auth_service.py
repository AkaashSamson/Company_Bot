import re
from typing import Dict, List, Optional

from app.core import mongo_settings
from app.core.security import hash_password, verify_password
from app.db.documents_repository import DocumentsRepository
from app.db.roles_repository import RolesRepository
from app.db.sequences import next_employee_id
from app.db.users_repository import UsersRepository
from app.domain.entities.access_models import DocumentModel, UserModel


class AuthError(Exception):
    """Raised when credentials or a user operation are invalid."""


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.strip().lower())


def build_email(first_name: str, last_name: str) -> str:
    """Build ``firstname.lastname@<domain>`` from the user's names."""
    return f"{_slug(first_name)}.{_slug(last_name)}@{mongo_settings.EMAIL_DOMAIN}"


_EMAIL_PATTERN = re.compile(
    r"^[a-z0-9]+\.[a-z0-9]+(?:\.[a-z0-9]+)*@"
    + re.escape(mongo_settings.EMAIL_DOMAIN)
    + r"$"
)


def validate_email(email: str) -> Optional[str]:
    """Return a normalized email or ``None`` when the format is invalid."""
    normalized = (email or "").strip().lower()
    if not _EMAIL_PATTERN.match(normalized):
        return None
    return normalized


class UserManagementService:
    """Application service for user registration and authentication.

    The service coordinates repositories and keeps domain rules about users
    and roles out of the API layer.
    """

    def __init__(
        self,
        users: UsersRepository | None = None,
        roles: RolesRepository | None = None,
        seed_roles: bool = True,
    ):
        self.users = users or UsersRepository()
        self.roles = roles or RolesRepository()
        if seed_roles:
            from app.db.roles_repository import seed_default_roles

            seed_default_roles(self.roles)

    def register_user(
        self,
        first_name: str,
        last_name: str,
        role_code: str,
        email: Optional[str] = None,
        password: Optional[str] = None,
        extra: Optional[Dict] = None,
    ) -> Dict:
        """Create a user.

        employee_id is generated from a MongoDB counter (``MSS001``, ...).
        The email defaults to ``<first>.<last>@<domain>`` and must match that
        form when provided. Password defaults to the employee id for the MVP.
        """
        role_code = role_code.strip().lower()
        if not self.roles.exists(role_code):
            raise AuthError(f"Role '{role_code}' is not valid")
        if not first_name.strip() or not last_name.strip():
            raise AuthError("First name and last name are required")

        target_email = validate_email(email) if email else None
        if email and not target_email:
            raise AuthError(
                f"Invalid email format. Expected <first>.<last>@{mongo_settings.EMAIL_DOMAIN}"
            )

        employee_id = next_employee_id(self.users.database)
        if not target_email:
            target_email = build_email(first_name, last_name)
            if not validate_email(target_email):
                raise AuthError("Could not build a valid email from the given names")

        secret = password or employee_id

        user = UserModel(
            employee_id=employee_id,
            first_name=first_name.strip().title(),
            last_name=last_name.strip().title(),
            email=target_email,
            password_hash=hash_password(secret),
            role_code=role_code,
            extra=extra or {},
        )
        try:
            self.users.create(user)
        except ValueError as exc:
            raise AuthError(str(exc))

        return self._identity_dict(user)

    def authenticate(self, email: str, password: str) -> Dict:
        """Log a user in using their email and password (= employee id MVP)."""
        normalized_email = validate_email(email)
        if not normalized_email:
            raise AuthError("Invalid email format")
        user = self.users.get_by_email(normalized_email)
        if user is None or not verify_password(password, user.password_hash):
            raise AuthError("Invalid email or password")
        if not user.is_active:
            raise AuthError("User account is disabled")
        return self._identity_dict(user)

    def get_identity(self, employee_id: str) -> Optional[Dict]:
        user = self.users.get_by_employee_id(employee_id)
        if user is None:
            return None
        return self._identity_dict(user)

    def get_user(self, employee_id: str) -> Optional[Dict]:
        user = self.users.get_by_employee_id(employee_id)
        return self._user_dict(user) if user else None

    def list_users(self, role_code: Optional[str] = None) -> List[Dict]:
        return [self._user_dict(user) for user in self.users.list_users(role_code=role_code)]

    def update_user(self, employee_id: str, updates: Dict) -> Dict:
        """Update mutable profile fields and return the refreshed user."""
        allowed = {"first_name", "last_name", "email", "role_code", "extra"}
        unknown = set(updates) - allowed
        if unknown:
            raise AuthError(f"Unsupported fields: {', '.join(sorted(unknown))}")

        if "role_code" in updates:
            role_code = updates["role_code"].strip().lower()
            if not self.roles.exists(role_code):
                raise AuthError(f"Role '{role_code}' is not valid")
            updates["role_code"] = role_code

        if updates.get("email"):
            normalized = validate_email(updates["email"])
            if not normalized:
                raise AuthError(
                    f"Invalid email format. Expected <first>.<last>@{mongo_settings.EMAIL_DOMAIN}"
                )
            updates["email"] = normalized

        if "first_name" in updates:
            updates["first_name"] = updates["first_name"].strip().title()
        if "last_name" in updates:
            updates["last_name"] = updates["last_name"].strip().title()

        if not self.users.update(employee_id, updates):
            raise AuthError(f"User '{employee_id}' does not exist")
        updated = self.get_user(employee_id)
        if updated is None:
            raise AuthError(f"User '{employee_id}' does not exist")
        return updated

    def update_role(self, employee_id: str, role_code: str) -> Dict:
        return self.update_user(employee_id, {"role_code": role_code})

    def activate(self, employee_id: str) -> Dict:
        if not self.users.set_active(employee_id, True):
            raise AuthError(f"User '{employee_id}' does not exist")
        return self.get_user(employee_id)

    def deactivate(self, employee_id: str) -> Dict:
        if not self.users.set_active(employee_id, False):
            raise AuthError(f"User '{employee_id}' does not exist")
        return self.get_user(employee_id)

    @staticmethod
    def _identity_dict(user: UserModel) -> Dict:
        return {
            "employee_id": user.employee_id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "role_code": user.role_code,
        }

    @staticmethod
    def _user_dict(user: UserModel) -> Dict:
        return {
            "employee_id": user.employee_id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "role_code": user.role_code,
            "is_active": user.is_active,
            "created_at": str(user.created_at) if user.created_at else None,
        }


class DocumentRegistrationService:
    """Application service that registers a document and its access policy."""

    def __init__(
        self,
        documents: DocumentsRepository | None = None,
    ):
        self.documents = documents or DocumentsRepository()

    def register_document(
        self,
        filename: str,
        owner_employee_id: str,
        allowed_role_codes=None,
        allowed_user_ids=None,
        metadata=None,
    ) -> Dict:
        if self.documents.exists(filename):
            raise AuthError(f"Document '{filename}' is already registered")

        document_id = self.documents.create(
            DocumentModel(
                filename=filename,
                owner_user_id=owner_employee_id,
                allowed_role_codes=list(allowed_role_codes or []),
                allowed_user_ids=list(allowed_user_ids or []),
                metadata=metadata or {},
            )
        )
        return {
            "document_id": document_id,
            "filename": filename,
            "owner_user_id": owner_employee_id,
        }