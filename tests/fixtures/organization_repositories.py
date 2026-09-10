from app.domain.entities.organization_models import Department, Document, Project, User, UserProject


class InMemoryUserRepository:
    def __init__(self, users=None):
        self.users = {user.uid: user for user in (users or [])}

    def get_by_uid(self, uid):
        return self.users.get(uid)

    def get_by_email(self, email):
        return next((user for user in self.users.values() if user.email == email), None)

    def get_by_username(self, username):
        return next((user for user in self.users.values() if user.username == username), None)

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
        self.projects = {item.project_id: item for item in (projects or [])}

    def get(self, project_id):
        return self.projects.get(project_id)

    def list_active(self):
        return [item for item in self.projects.values() if item.status == "active"]

    def save(self, project):
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
        self.documents = {item.document_id: item for item in (documents or [])}

    def get(self, document_id):
        return self.documents.get(document_id)

    def list(self):
        return list(self.documents.values())

    def save(self, document):
        self.documents[document.document_id] = document
        return document

    def delete(self, document_id):
        document = self.documents.get(document_id)
        if document:
            document.status = "archived"


class InMemoryUnitOfWork:
    def __init__(self, users=None, departments=None, projects=None, memberships=None, documents=None):
        self.users = InMemoryUserRepository(users)
        self.departments = InMemoryDepartmentRepository(departments)
        self.projects = InMemoryProjectRepository(projects)
        self.documents = InMemoryDocumentRepository(documents)
        self.memberships = InMemoryMembershipRepository(memberships)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None
