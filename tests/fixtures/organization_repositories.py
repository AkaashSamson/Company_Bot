import threading

from app.domain.entities.organization_models import (
    Department,
    DepartmentMember,
    Document,
    DocumentGrant,
    Permission,
    Project,
    ProjectGrant,
    Role,
    User,
    UserProject,
)


class InMemoryUserRepository:
    def __init__(self, users=None):
        self.users = {user.uid: user for user in (users or [])}

    def get_by_uid(self, uid):
        return self.users.get(uid)

    def get_by_email(self, email):
        return next((user for user in self.users.values() if user.email == email), None)

    def get_by_username(self, username):
        return next((user for user in self.users.values() if user.username == username), None)

    def get_by_employee_id(self, employee_id):
        return next((user for user in self.users.values() if user.employee_id == employee_id), None)

    def list(self):
        return list(self.users.values())

    def save(self, user):
        self.users[user.uid] = user
        return user

    def delete(self, uid):
        self.users.pop(uid, None)


class InMemoryDepartmentRepository:
    def __init__(self, departments=None):
        self.departments = {item.department_id: item for item in (departments or [])}

    def get(self, department_id):
        return self.departments.get(department_id)

    def list(self):
        return list(self.departments.values())

    def save(self, department):
        self.departments[department.department_id] = department
        return department


class InMemoryProjectRepository:
    def __init__(self, projects=None):
        self.projects = {}
        self._next_id = 1
        for item in (projects or []):
            if item.internal_id is None:
                item.internal_id = self._next_id
            else:
                self._next_id = max(self._next_id, item.internal_id + 1)
            self.projects[item.project_id] = item
            if item.internal_id >= self._next_id:
                self._next_id = item.internal_id + 1

    def get(self, project_id):
        return self.projects.get(project_id)

    def get_by_internal_id(self, internal_id):
        return next((item for item in self.projects.values() if item.internal_id == internal_id), None)

    def list(self):
        return list(self.projects.values())

    def list_active(self):
        return [item for item in self.projects.values() if item.status == "active"]

    def save(self, project):
        if project.internal_id is None:
            project.internal_id = self._next_id
            self._next_id += 1
        else:
            self._next_id = max(self._next_id, project.internal_id + 1)
        self.projects[project.project_id] = project
        return project


class InMemoryMembershipRepository:
    def __init__(self, memberships=None):
        self.memberships = {(item.uid, item.project_id): item for item in (memberships or [])}

    def get(self, uid, project_id):
        return self.memberships.get((uid, project_id))

    def list_for_user(self, uid):
        return [item for item in self.memberships.values() if item.uid == uid]

    def list_for_project(self, project_id):
        return [item for item in self.memberships.values() if item.project_id == project_id]

    def save(self, membership):
        self.memberships[(membership.uid, membership.project_id)] = membership
        return membership

    def revoke(self, uid, project_id):
        membership = self.memberships.get((uid, project_id))
        if membership:
            membership.status = "revoked"


class InMemoryDocumentRepository:
    def __init__(self, documents=None):
        self.documents = {}
        self._next_id = 1
        for item in (documents or []):
            if item.internal_id is None:
                item.internal_id = self._next_id
            else:
                self._next_id = max(self._next_id, item.internal_id + 1)
            self.documents[item.document_id] = item
            if item.internal_id >= self._next_id:
                self._next_id = item.internal_id + 1

    def get(self, document_id):
        return self.documents.get(document_id)

    def get_by_internal_id(self, internal_id):
        return next((item for item in self.documents.values() if item.internal_id == internal_id), None)

    def list(self):
        return list(self.documents.values())

    def save(self, document):
        if document.internal_id is None:
            document.internal_id = self._next_id
            self._next_id += 1
        else:
            self._next_id = max(self._next_id, document.internal_id + 1)
        self.documents[document.document_id] = document
        return document

    def delete(self, document_id, permanent=False):
        if permanent:
            self.documents.pop(document_id, None)
        else:
            document = self.documents.get(document_id)
            if document:
                document.status = "archived"

    def purge(self, document_id):
        self.documents.pop(document_id, None)


class InMemoryDepartmentMemberRepository:
    def __init__(self, members=None):
        self.members = {(item.user_id, item.department_id): item for item in (members or [])}

    def get(self, user_id, department_id):
        return self.members.get((user_id, department_id))

    def list_for_user(self, user_id):
        return [item for item in self.members.values() if item.user_id == user_id]

    def list_for_department(self, department_id):
        return [item for item in self.members.values() if item.department_id == department_id]

    def save(self, member):
        self.members[(member.user_id, member.department_id)] = member
        return member


class InMemoryPermissionRepository:
    def __init__(self, permissions=None):
        self.permissions = {}
        self._next_id = 1
        for permission in (permissions or []):
            self.save(permission)

    def get(self, permission_id):
        return self.permissions.get(permission_id)

    def get_by_name(self, name):
        return next((permission for permission in self.permissions.values() if permission.name == name), None)

    def list(self):
        return sorted(self.permissions.values(), key=lambda permission: permission.name)

    def save(self, permission):
        if permission.permission_id is None:
            permission.permission_id = self._next_id
            self._next_id += 1
        else:
            self._next_id = max(self._next_id, permission.permission_id + 1)
        self.permissions[permission.permission_id] = permission
        return permission


class InMemoryRoleRepository:
    def __init__(self, roles=None, permissions=None):
        self.roles = {}
        self.role_permissions = {}
        self.permissions = permissions
        self._next_id = 1
        for role in (roles or []):
            self.save(role)

    def get(self, role_id):
        return self.roles.get(role_id)

    def get_by_name(self, name):
        return next((role for role in self.roles.values() if role.name == name), None)

    def list(self):
        return sorted(self.roles.values(), key=lambda role: role.name)

    def save(self, role):
        if role.role_id is None:
            role.role_id = self._next_id
            self._next_id += 1
        else:
            self._next_id = max(self._next_id, role.role_id + 1)
        self.roles[role.role_id] = role
        return role

    def delete(self, role_id):
        self.roles.pop(role_id, None)
        self.role_permissions.pop(role_id, None)

    def permissions_for_role(self, role_id):
        store = self.permissions.permissions if self.permissions else {}
        return [store[permission_id] for permission_id in sorted(self.role_permissions.get(role_id, set())) if permission_id in store]

    def set_permissions(self, role_id, permission_ids, granted_by_uid=None):
        self.role_permissions[role_id] = set(permission_ids)


class InMemoryProjectGrantRepository:
    def __init__(self, grants=None):
        self.grants = {}
        self._next_id = 1
        for grant in (grants or []):
            self.save(grant)

    def _key(self, project_id, principal_type, role_id, user_id):
        return (project_id, principal_type, role_id, user_id)

    def get(self, project_id, principal_type, role_id=None, user_id=None):
        return self.grants.get(self._key(project_id, principal_type, role_id, user_id))

    def get_by_id(self, grant_id):
        return next((grant for grant in self.grants.values() if grant.internal_id == grant_id), None)

    def list_for_project(self, project_id):
        return sorted(
            (grant for grant in self.grants.values() if grant.project_id == project_id and grant.status == "active"),
            key=lambda grant: grant.internal_id,
        )

    def project_ids_for_principal(self, user_id, role_ids):
        project_ids = set()
        for grant in self.grants.values():
            if grant.status != "active":
                continue
            if grant.principal_type == "user" and grant.user_id == user_id:
                project_ids.add(grant.project_id)
            elif grant.principal_type == "role" and grant.role_id in set(role_ids):
                project_ids.add(grant.project_id)
        return list(project_ids)

    def list(self):
        return list(self.grants.values())

    def save(self, grant):
        if grant.internal_id is None:
            grant.internal_id = self._next_id
            self._next_id += 1
        else:
            self._next_id = max(self._next_id, grant.internal_id + 1)
        self.grants[self._key(grant.project_id, grant.principal_type, grant.role_id, grant.user_id)] = grant
        return grant

    def delete(self, grant_id):
        grant = self.get_by_id(grant_id)
        if grant:
            grant.status = "revoked"


class InMemoryDocumentGrantRepository:
    def __init__(self, grants=None):
        self.grants = {}
        self._next_id = 1
        for grant in (grants or []):
            self.save(grant)

    def _key(self, document_id, principal_type, role_id, user_id, permission):
        return (document_id, principal_type, role_id, user_id, permission)

    def get(self, grant_id):
        return next((grant for grant in self.grants.values() if grant.internal_id == grant_id), None)

    def for_document(self, document_id):
        return sorted(
            (grant for grant in self.grants.values() if grant.document_id == document_id and grant.status == "active"),
            key=lambda grant: grant.internal_id,
        )

    def document_ids_for_principal(self, user_id, role_ids):
        document_ids = set()
        role_id_set = set(role_ids)
        for grant in self.grants.values():
            if grant.status != "active" or grant.permission != "read":
                continue
            if grant.principal_type == "user" and grant.user_id == user_id:
                document_ids.add(grant.document_id)
            elif grant.principal_type == "role" and grant.role_id in role_id_set:
                document_ids.add(grant.document_id)
        return list(document_ids)

    def list(self):
        return list(self.grants.values())

    def save(self, grant):
        if grant.internal_id is None:
            grant.internal_id = self._next_id
            self._next_id += 1
        else:
            self._next_id = max(self._next_id, grant.internal_id + 1)
        self.grants[self._key(grant.document_id, grant.principal_type, grant.role_id, grant.user_id, grant.permission)] = grant
        return grant

    def delete(self, grant_id):
        grant = self.get(grant_id)
        if grant:
            grant.status = "revoked"


class InMemorySequenceRepository:
    def __init__(self):
        self._values = {}
        self._prefixes = {}
        self._lock = threading.Lock()

    def get(self, sequence_key):
        with self._lock:
            return self._values.get(sequence_key)

    def initialize(self, sequence_key, prefix, last_value):
        with self._lock:
            if sequence_key not in self._values:
                self._values[sequence_key] = last_value
                self._prefixes[sequence_key] = prefix

    def allocate(self, sequence_key, by=1):
        with self._lock:
            self._values[sequence_key] = self._values.get(sequence_key, 0) + by
            return self._values[sequence_key]


class InMemoryUnitOfWork:
    def __init__(self, users=None, departments=None, projects=None, memberships=None, documents=None, department_members=None, roles=None, permissions=None, project_grants=None, document_grants=None, sequences=None):
        self.users = InMemoryUserRepository(users)
        self.departments = InMemoryDepartmentRepository(departments)
        self.projects = InMemoryProjectRepository(projects)
        self.documents = InMemoryDocumentRepository(documents)
        self.memberships = InMemoryMembershipRepository(memberships)
        self.department_members = InMemoryDepartmentMemberRepository(department_members)
        self.permissions = InMemoryPermissionRepository(permissions)
        self.roles = InMemoryRoleRepository(roles, self.permissions)
        self.project_grants = InMemoryProjectGrantRepository(project_grants)
        self.document_grants = InMemoryDocumentGrantRepository(document_grants)
        self.sequences = sequences or InMemorySequenceRepository()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None
