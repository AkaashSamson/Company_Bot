from app.core.security import verify_password
from app.domain.entities.access_models import UserModel
from app.use_cases.access.auth_service import (
    AuthError,
    UserManagementService,
    build_email,
    validate_email,
)


class FakeCounters:
    def __init__(self):
        self.counters = {}

    def find_one_and_update(self, query, update, upsert=False, return_document=None):
        name = query["_id"]
        inc = update.get("$inc", {}).get("seq", 0)
        self.counters[name] = self.counters.get(name, 0) + inc
        return {"_id": name, "seq": self.counters[name]}


class FakeDatabase:
    def __init__(self):
        self.counters = FakeCounters()

    def __getitem__(self, name):
        if name == "counters":
            return self.counters
        raise KeyError(name)


class StubUsersRepository:
    def __init__(self):
        self._db = FakeDatabase()
        self.storage = {}

    @property
    def database(self):
        return self._db

    def create(self, user):
        if any(u.employee_id == user.employee_id or u.email == user.email for u in self.storage.values()):
            raise ValueError("duplicate")
        self.storage[user.employee_id] = user
        return user.employee_id

    def get_by_employee_id(self, employee_id):
        return self.storage.get(employee_id)

    def get_by_email(self, email):
        return next((u for u in self.storage.values() if u.email == email), None)

    def list_users(self, role_code=None):
        users = list(self.storage.values())
        if role_code:
            users = [u for u in users if u.role_code == role_code]
        return users

    def update(self, employee_id, updates):
        user = self.storage.get(employee_id)
        if not user:
            return False
        for key, value in updates.items():
            if key == "updated_at":
                continue
            setattr(user, key, value)
        return True

    def set_active(self, employee_id, is_active):
        return self.update(employee_id, {"is_active": is_active})


class StubRolesRepository:
    VALID = {"manager", "tester", "solution_architect", "developer"}

    def exists(self, code):
        return code in self.VALID


def _service():
    return UserManagementService(
        users=StubUsersRepository(),
        roles=StubRolesRepository(),
        seed_roles=False,
    )


def test_build_email_uses_first_dot_last_at_domain():
    assert build_email("Roshan", "Yadav") == "roshan.yadav@mclarensv.com"


def test_validate_email_accepts_correct_format():
    assert validate_email("roshan.yadav@mclarensv.com") == "roshan.yadav@mclarensv.com"


def test_validate_email_rejects_foreign_domain_and_bad_shape():
    assert validate_email("roshan.yadav@gmail.com") is None
    assert validate_email("ros hanyadav@mclarensv.com") is None
    assert validate_email("roshan@mclarensv.com") is None


def test_register_user_generates_employee_id_and_email():
    service = _service()
    identity = service.register_user("Roshan", "Yadav", "manager")
    assert identity["employee_id"] == "MSS001"
    assert identity["email"] == "roshan.yadav@mclarensv.com"
    assert identity["role_code"] == "manager"


def test_register_user_increments_employee_id():
    service = _service()
    first = service.register_user("A", "One", "manager")
    second = service.register_user("B", "Two", "developer")
    assert first["employee_id"] == "MSS001"
    assert second["employee_id"] == "MSS002"


def test_register_user_password_defaults_to_employee_id():
    service = _service()
    identity = service.register_user("Ro", "Ya", "manager")
    user = service.users.get_by_employee_id(identity["employee_id"])
    assert verify_password(identity["employee_id"], user.password_hash)


def test_register_user_custom_password_is_hashed():
    service = _service()
    identity = service.register_user("Ro", "Ya", "manager", password="secret123")
    user = service.users.get_by_employee_id(identity["employee_id"])
    assert verify_password("secret123", user.password_hash)
    assert not verify_password(identity["employee_id"], user.password_hash)


def test_register_user_rejects_invalid_email_format():
    service = _service()
    try:
        service.register_user("Ro", "Ya", "manager", email="nope@gmail.com")
        assert False, "expected AuthError"
    except AuthError:
        pass


def test_authenticate_valid_credentials():
    service = _service()
    identity = service.register_user("Ro", "Ya", "manager")
    logged_in = service.authenticate(
        identity["email"], identity["employee_id"]
    )
    assert logged_in["employee_id"] == identity["employee_id"]


def test_authenticate_wrong_password_denied():
    service = _service()
    identity = service.register_user("Ro", "Ya", "manager")
    try:
        service.authenticate(identity["email"], "wrong")
        assert False, "expected AuthError"
    except AuthError:
        pass


def test_authenticate_inactive_user_denied():
    service = _service()
    identity = service.register_user("Ro", "Ya", "manager")
    service.deactivate(identity["employee_id"])
    try:
        service.authenticate(identity["email"], identity["employee_id"])
        assert False, "expected AuthError"
    except AuthError:
        pass


def test_update_role_and_status_cycle():
    service = _service()
    identity = service.register_user("Ro", "Ya", "manager")
    updated = service.update_role(identity["employee_id"], "developer")
    assert updated["role_code"] == "developer"
    assert service.activate(identity["employee_id"])["is_active"] is True
    deactivated = service.deactivate(identity["employee_id"])
    assert deactivated["is_active"] is False


def test_update_user_updates_names():
    service = _service()
    identity = service.register_user("Ro", "Ya", "manager")
    updated = service.update_user(
        identity["employee_id"], {"first_name": "Randy", "last_name": "Young"}
    )
    assert updated["first_name"] == "Randy"
    assert updated["last_name"] == "Young"