from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.infrastructure.persistence.sqlalchemy.models import (
    DepartmentRecord,
    DocumentRecord,
    PermissionRecord,
    ProjectRecord,
    RolePermissionRecord,
    RoleRecord,
    UserProjectRecord,
    UserRecord,
)
from app.infrastructure.persistence.sqlalchemy.session import (
    create_engine_and_session_factory,
    initialize_database,
)

EXPECTED_TABLES = {
    "users",
    "departments",
    "projects",
    "documents",
    "user_projects",
    "roles",
    "permissions",
    "role_permissions",
}


def _time() -> datetime:
    return datetime.now(timezone.utc)


def _save_role(session, name="admin"):
    role = RoleRecord(name=name)
    session.add(role)
    session.commit()
    return role


def _save_department_and_user(session, uid="u1", dept_id="d1"):
    dept = session.get(DepartmentRecord, dept_id)
    if not dept:
        dept = DepartmentRecord(department_id=dept_id, department_name=f"Engineering-{dept_id}", created_at=_time(), updated_at=_time())
        session.add(dept)
        session.flush()
    user = session.get(UserRecord, uid)
    if not user:
        user = UserRecord(
            uid=uid,
            username=uid,
            name="User One",
            email=f"{uid}@example.com",
            role="Member",
            department_id=dept_id,
            password_hash="hashed_secret",
            created_at=_time(),
            updated_at=_time(),
        )
        session.add(user)
        session.commit()
    return dept, user


def _save_project(session, project_id="p1", dept_id="d1", manager_uid=None):
    dept = session.get(DepartmentRecord, dept_id)
    if not dept:
        dept = DepartmentRecord(department_id=dept_id, department_name=f"Dept-{dept_id}", status="active", created_at=_time(), updated_at=_time())
        session.add(dept)
        session.flush()
    project = session.query(ProjectRecord).filter_by(project_id=project_id).first()
    if not project:
        project = ProjectRecord(
            project_id=project_id,
            project_name=f"Project-{project_id}",
            department_id=dept_id,
            manager_uid=manager_uid,
            status="active",
            created_at=_time(),
            updated_at=_time(),
        )
        session.add(project)
        session.commit()
    return project


@pytest.fixture
def database(tmp_path):
    database_path = tmp_path / "foundation.db"
    engine, session_factory = create_engine_and_session_factory(f"sqlite:///{database_path}")
    initialize_database(engine)
    yield engine, session_factory
    engine.dispose()


def test_initialize_database_creates_full_expected_schema(database):
    engine, _ = database
    tables = set(inspect(engine).get_table_names())
    assert tables == EXPECTED_TABLES


def _unique_columns(inspector, table):
    columns = {tuple(item["column_names"]) for item in inspector.get_unique_constraints(table)}
    for index in inspector.get_indexes(table):
        if index.get("unique"):
            columns.add(tuple(index["column_names"]))
    return columns


def test_consolidated_tables_have_expected_keys_and_indexes(database):
    engine, _ = database
    inspector = inspect(engine)

    assert inspector.get_pk_constraint("users")["constrained_columns"] == ["uid"]
    assert inspector.get_pk_constraint("departments")["constrained_columns"] == ["department_id"]
    assert inspector.get_pk_constraint("projects")["constrained_columns"] == ["id"]
    assert inspector.get_pk_constraint("documents")["constrained_columns"] == ["id"]
    assert set(inspector.get_pk_constraint("user_projects")["constrained_columns"]) == {"uid", "project_id"}
    assert inspector.get_pk_constraint("roles")["constrained_columns"] == ["id"]
    assert inspector.get_pk_constraint("permissions")["constrained_columns"] == ["id"]
    assert set(inspector.get_pk_constraint("role_permissions")["constrained_columns"]) == {"role_id", "permission_id"}

    assert ("name",) in _unique_columns(inspector, "roles")
    assert ("name",) in _unique_columns(inspector, "permissions")

    user_cols = {c["name"] for c in inspector.get_columns("users")}
    assert "password_hash" in user_cols
    assert "password_representation" not in user_cols
    assert "role_id" in user_cols
    assert "job_title" in user_cols

    # Foreign key checks
    user_fks = {item["referred_table"] for item in inspector.get_foreign_keys("users")}
    assert "departments" in user_fks
    assert "roles" in user_fks

    project_fks = {item["referred_table"]: item for item in inspector.get_foreign_keys("projects")}
    assert "departments" in project_fks
    assert "users" in project_fks

    user_project_fks = {item["referred_table"]: item for item in inspector.get_foreign_keys("user_projects")}
    assert "users" in user_project_fks
    assert "projects" in user_project_fks
    assert "roles" in user_project_fks

    document_fks = {item["referred_table"]: item for item in inspector.get_foreign_keys("documents")}
    assert "projects" in document_fks


def test_role_name_is_unique(database):
    _, session_factory = database
    with session_factory() as session:
        _save_role(session, "admin")
    with pytest.raises(IntegrityError):
        with session_factory() as session:
            _save_role(session, "admin")


def test_permission_name_is_unique(database):
    _, session_factory = database
    with session_factory() as session:
        session.add(PermissionRecord(name="documents.read"))
        session.commit()
    with pytest.raises(IntegrityError):
        with session_factory() as session:
            session.add(PermissionRecord(name="documents.read"))
            session.commit()


def test_role_permission_composite_key_rejects_duplicate(database):
    _, session_factory = database
    with session_factory() as session:
        _save_role(session, "admin")
        session.add(PermissionRecord(name="documents.read"))
        session.commit()
        session.add(RolePermissionRecord(role_id=1, permission_id=1))
        session.commit()
    with pytest.raises(IntegrityError):
        with session_factory() as session:
            session.add(RolePermissionRecord(role_id=1, permission_id=1))
            session.commit()


def test_role_permission_cascades_on_role_delete(database):
    _, session_factory = database
    with session_factory() as session:
        _save_role(session, "admin")
        session.add(PermissionRecord(name="documents.read"))
        session.commit()
        session.add(RolePermissionRecord(role_id=1, permission_id=1))
        session.commit()
        session.delete(session.query(RoleRecord).filter_by(id=1).one())
        session.commit()
        assert session.query(RolePermissionRecord).filter_by(role_id=1, permission_id=1).first() is None


def test_project_cascade_deletes_user_projects_and_documents(database):
    _, session_factory = database
    with session_factory() as session:
        _save_department_and_user(session, uid="u1", dept_id="d1")
        _save_project(session, project_id="p1", dept_id="d1")
        role = _save_role(session, "Dev")

        session.add(UserProjectRecord(
            uid="u1",
            project_id="p1",
            role_id=role.id,
            assigned_at=_time(),
        ))
        session.add(DocumentRecord(
            document_id="doc1",
            document_name="Architecture",
            project_id="p1",
            created_at=_time(),
            updated_at=_time(),
        ))
        session.commit()

        # Delete project
        project = session.query(ProjectRecord).filter_by(project_id="p1").one()
        session.delete(project)
        session.commit()

    with session_factory() as session:
        # Verify cascades in fresh session
        assert session.query(UserProjectRecord).filter_by(project_id="p1").count() == 0
        assert session.query(DocumentRecord).filter_by(project_id="p1").count() == 0


def test_user_deletion_sets_project_manager_and_creator_to_null(database):
    _, session_factory = database
    with session_factory() as session:
        _, user = _save_department_and_user(session, uid="mgr1", dept_id="d1")
        project = ProjectRecord(
            project_id="p1",
            project_name="Management Proj",
            department_id="d1",
            manager_uid="mgr1",
            created_by_uid="mgr1",
            created_at=_time(),
            updated_at=_time(),
        )
        session.add(project)
        session.commit()

        # Delete user
        session.delete(session.query(UserRecord).filter_by(uid="mgr1").one())
        session.commit()

    with session_factory() as session:
        # Verify project fields set to NULL in fresh session
        reloaded = session.query(ProjectRecord).filter_by(project_id="p1").one()
        assert reloaded.manager_uid is None
        assert reloaded.created_by_uid is None


def test_legacy_cleanup_and_migration(tmp_path):
    from sqlalchemy import text, create_engine
    db_path = tmp_path / "legacy.db"
    raw_engine = create_engine(f"sqlite:///{db_path}")

    with raw_engine.begin() as conn:
        conn.execute(text("CREATE TABLE department_members (user_id TEXT, department_id TEXT)"))
        conn.execute(text("CREATE TABLE document_permissions (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE project_grants (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE business_id_sequences (sequence_key TEXT PRIMARY KEY)"))
        conn.execute(text(
            "CREATE TABLE users (uid TEXT PRIMARY KEY, username TEXT, name TEXT, email TEXT, "
            "role TEXT, department_id TEXT, status TEXT, created_at TEXT, updated_at TEXT, "
            "password_representation TEXT)"
        ))
        conn.execute(text(
            "INSERT INTO users VALUES ('u1', 'u1', 'Old User', 'u1@example.com', 'Dev', 'd1', "
            "'active', '2026-01-01', '2026-01-01', 'legacy_hash_123')"
        ))

    # Run initialize_database which must run the migration
    initialize_database(raw_engine)

    inspector = inspect(raw_engine)
    table_names = set(inspector.get_table_names())
    assert "department_members" not in table_names
    assert "document_permissions" not in table_names
    assert "project_grants" not in table_names
    assert "business_id_sequences" not in table_names

    with raw_engine.connect() as conn:
        row = conn.execute(text("SELECT password_hash FROM users WHERE uid = 'u1'")).mappings().one()
        assert row["password_hash"] == "legacy_hash_123"

    user_cols = {c["name"] for c in inspector.get_columns("users")}
    assert "role_id" in user_cols
    assert "job_title" in user_cols


def test_sqlalchemy_user_repository_crud(database):
    _, session_factory = database
    with session_factory() as session:
        from app.infrastructure.persistence.sqlalchemy.repositories import SqlAlchemyUserRepository
        from app.domain.entities.organization_models import User
        repo = SqlAlchemyUserRepository(session)

        _save_department_and_user(session, uid="seed_dept", dept_id="d1")
        role = _save_role(session, "Staff")

        user = User(
            uid="u_test",
            name="Test User",
            email="test_user@example.com",
            role="Staff",
            department_id="d1",
            role_id=role.id,
            job_title="Cosmetic Title",
            password_hash="secure_hash_val",
        )
        saved = repo.save(user)
        session.commit()

    with session_factory() as session:
        from app.infrastructure.persistence.sqlalchemy.repositories import SqlAlchemyUserRepository
        repo = SqlAlchemyUserRepository(session)
        loaded = repo.get_by_uid("u_test")

        assert loaded is not None
        assert loaded.role_id == role.id
        assert loaded.job_title == "Cosmetic Title"
        assert loaded.password_hash == "secure_hash_val"
        assert loaded.password_representation == "secure_hash_val"
