import base64
import binascii
from typing import Optional

from fastapi import Header, HTTPException, status

from app.use_cases.access.auth_service import AuthError, UserManagementService


class Identity:
    """Resolved identity of the calling user.

    ``user_id`` is the employee id (e.g. ``MSS001``), kept stable and usable in
    database and Chroma metadata filters. ``role_code`` is the single role
    assigned to the user in the MVP.
    """

    def __init__(
        self,
        user_id: Optional[str],
        employee_id: str,
        role_code: Optional[str],
    ):
        self.user_id = user_id
        self.employee_id = employee_id
        self.role_code = role_code

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "employee_id": self.employee_id,
            "role_code": self.role_code,
        }


def _parse_basic_auth(authorization: Optional[str]) -> Optional[tuple]:
    if not authorization:
        return None
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "basic" or not credentials:
        return None
    try:
        decoded = base64.b64decode(credentials).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None
    email, _, password = decoded.partition(":")
    if not email or not password:
        return None
    return (email, password)


def get_current_user(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> Identity:
    """Resolve the calling user.

    Supports two simple identity mechanisms for the MVP:

    1. HTTP Basic auth using ``email:password`` against the users collection.
    2. Trusted headers ``X-User-Id`` (employee id) and ``X-User-Role`` (used by
       Streamlit for demo/local deployments).
    """
    credentials = _parse_basic_auth(authorization)
    if not credentials and not x_user_id:
        return Identity(user_id=None, employee_id="anonymous", role_code=None)

    service = UserManagementService(seed_roles=False)

    if credentials:
        try:
            identity = service.authenticate(*credentials)
        except AuthError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
            )
        return Identity(
            user_id=identity["employee_id"],
            employee_id=identity["employee_id"],
            role_code=identity["role_code"],
        )

    if x_user_id:
        identity = service.get_identity(x_user_id)
        if not identity:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Unknown employee '{x_user_id}'",
            )
        return Identity(
            user_id=identity["employee_id"],
            employee_id=identity["employee_id"],
            role_code=x_user_role or identity["role_code"],
        )

    return Identity(user_id=None, employee_id="anonymous", role_code=None)


def require_role(allowed_roles: set[str]):
    """Build a dependency that enforces a role on the resolved identity."""

    def checker(identity: Identity = get_current_user) -> Identity:
        if identity.role_code not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{identity.role_code}' is not allowed. "
                    f"Required: {', '.join(sorted(allowed_roles))}"
                ),
            )
        return identity

    return checker