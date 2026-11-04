"""Idempotent provisioning of the initial role/permission catalog.

The seed only *creates* missing permissions and roles. Existing roles are left
untouched so that administrator edits through the API are never overwritten on
the next application start-up.
"""

import logging

from app.domain.entities.organization_models import Permission, Role
from app.domain.services.permission_catalog import (
    INITIAL_ROLE_DEFINITIONS,
    PERMISSION_DEFINITIONS,
    resolve_role_permissions,
)


logger = logging.getLogger("knowlayer.rbac")


def seed_rbac(unit_of_work_factory, granted_by_uid=None):
    permissions_created = 0
    roles_created = 0
    with unit_of_work_factory() as uow:
        permissions_by_name = {}
        for name, description in PERMISSION_DEFINITIONS:
            permission = uow.permissions.get_by_name(name)
            if permission is None:
                permission = uow.permissions.save(Permission(None, name, description))
                permissions_created += 1
            permissions_by_name[name] = permission

        for definition in INITIAL_ROLE_DEFINITIONS:
            if uow.roles.get_by_name(definition["name"]) is not None:
                continue
            role = uow.roles.save(Role(None, definition["name"], definition["description"], scope=definition["scope"]))
            permission_ids = [
                permissions_by_name[name].permission_id
                for name in resolve_role_permissions(definition["permissions"])
                if name in permissions_by_name
            ]
            uow.roles.set_permissions(role.role_id, permission_ids, granted_by_uid)
            roles_created += 1

        uow.commit()

    if permissions_created or roles_created:
        logger.info("rbac seed provisioned permissions=%s roles=%s", permissions_created, roles_created)
    return {"permissions_created": permissions_created, "roles_created": roles_created}
