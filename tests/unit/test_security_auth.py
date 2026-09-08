import base64

from app.api.dependencies.auth import _parse_basic_auth, Identity
from app.core.security import hash_password, verify_password


def test_password_hash_and_verify_roundtrip():
    hashed = hash_password("s3cret")
    assert hashed != "s3cret"
    assert verify_password("s3cret", hashed)
    assert not verify_password("wrong", hashed)


def test_verify_password_rejects_malformed_hash():
    assert not verify_password("s3cret", "not-a-hash")


def test_parse_basic_auth_valid():
    token = base64.b64encode(b"roshan.yadav@mclarensv.com:secret").decode("utf-8")
    assert _parse_basic_auth(f"Basic {token}") == ("roshan.yadav@mclarensv.com", "secret")


def test_parse_basic_auth_missing_returns_none():
    assert _parse_basic_auth(None) is None
    assert _parse_basic_auth("Bearer abc") is None
    assert _parse_basic_auth("Basic ###") is None


def test_identity_to_dict():
    identity = Identity("MSS001", "MSS001", "manager")
    assert identity.to_dict() == {
        "user_id": "MSS001",
        "employee_id": "MSS001",
        "role_code": "manager",
    }