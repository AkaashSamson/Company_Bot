from datetime import datetime, timezone

from app.core.settings import ADMIN_INITIAL_PASSWORD, ADMIN_USERNAME
from app.domain.entities.organization_models import Department, User
from app.infrastructure.audit.authentication_events import record_authentication_event


def bootstrap_admin(unit_of_work_factory, password_hasher, username=ADMIN_USERNAME, password=ADMIN_INITIAL_PASSWORD):
    if not password:
        return False
    with unit_of_work_factory() as uow:
        existing = uow.users.get_by_username(username)
        if existing:
            return False
        department_id = "admin"
        if not uow.departments.get(department_id):
            now = datetime.now(timezone.utc)
            uow.departments.save(Department(department_id, "Administration", created_at=now, updated_at=now))
        now = datetime.now(timezone.utc)
        uow.users.save(User(
            "admin", "Administrator", "admin@localhost", "Admin", department_id,
            created_at=now, updated_at=now, username=username,
            password_representation=password_hasher.hash(password),
            password_changed_at=None, must_change_password=True,
        ))
        uow.commit()
        record_authentication_event("bootstrap", uid="admin", success=True)
        return True