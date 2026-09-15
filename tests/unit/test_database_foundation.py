from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, update
from sqlalchemy.exc import IntegrityError

from app.infrastructure.persistence.sqlalchemy.foundation_models import (
    DepartmentMemberRecord,
    DocumentPermissionRecord,
    PermissionRecord,
    ProjectGrantRecord,
    RolePermissionRecord,
    RoleRecord,
)
from app.infrastructure.persistence.sqlalchemy.models import (
    BusinessIdSequenceRecord,
    DepartmentRecord,
    DocumentRecord,
    ProjectRecord,
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
    "department_members",
    "document_permissions",
    "project_grants",
    "business_id_sequences",
}


def _time() -> datetime:
    return datetime.now(timezone.utc)


def _save_role(session, name="admin"):
    session.add(RoleRecord(name=name))
    session.commit()


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


def test_foundation_tables_have_expected_keys_and_indexes(database):
    engine, _ = database
    inspector = inspect(engine)

    assert inspector.get_pk_constraint("roles")["constrained_columns"] == ["id"]
    assert inspector.get_pk_constraint("permissions")["constrained_columns"] == ["id"]
    assert inspector.get_pk_constraint("role_permissions")["constrained_columns"] == ["role_id", "permission_id"]
    assert inspector.get_pk_constraint("department_members")["constrained_columns"] == ["user_id", "department_id"]
    assert inspector.get_pk_constraint("document_permissions")["constrained_columns"] == ["id"]
    assert inspector.get_pk_constraint("business_id_sequences")["constrained_columns"] == ["sequence_key"]

    assert ("name",) in _unique_columns(inspector, "roles")
    assert ("name",) in _unique_columns(inspector, "permissions")
    assert ("document_id", "principal_type", "role_id", "user_id", "permission") in _unique_columns(inspector, "document_permissions")

    department_member_fks = {item["referred_table"] for item in inspector.get_foreign_keys("department_members")}
    assert department_member_fks == {"departments", "users"}
    document_permission_fks = {item["referred_table"] for item in inspector.get_foreign_keys("document_permissions")}
    assert document_permission_fks == {"documents", "roles", "users"}
    role_permission_fks = {item["referred_table"] for item in inspector.get_foreign_keys("role_permissions")}
    assert role_permission_fks == {"permissions", "roles", "users"}

    indexed_columns = {name for column in inspector.get_indexes("role_permissions") for name in column["column_names"]}
    assert "permission_id" in indexed_columns
    indexed_columns = {name for column in inspector.get_indexes("department_members") for name in column["column_names"]}
    assert "department_id" in indexed_columns
    indexed_columns = {name for column in inspector.get_indexes("document_permissions") for name in column["column_names"]}
    assert {"document_id", "role_id", "user_id"} <= indexed_columns


def test_foundation_tables_default_timestamps_and_status(database):
    _, session_factory = database
    with session_factory() as session:
        _save_role(session, "defaults")
        role = session.query(RoleRecord).filter_by(name="defaults").one()
    assert role.status == "active"
    assert role.created_at is not None
    assert role.updated_at is not None


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


def test_department_member_composite_key_rejects_duplicate(database):
    _, session_factory = database
    with session_factory() as session:
        _save_department_and_user(session)
        session.add(DepartmentMemberRecord(user_id="u1", department_id="d1"))
        session.commit()
    with pytest.raises(IntegrityError):
        with session_factory() as session:
            session.add(DepartmentMemberRecord(user_id="u1", department_id="d1"))
            session.commit()


def test_department_member_requires_existing_user_and_department(database):
    _, session_factory = database
    with session_factory() as session:
        _save_department_and_user(session)
    with pytest.raises(IntegrityError):
        with session_factory() as session:
            session.add(DepartmentMemberRecord(user_id="u-missing", department_id="d1"))
            session.commit()
    with pytest.raises(IntegrityError):
        with session_factory() as session:
            session.add(DepartmentMemberRecord(user_id="u1", department_id="d-missing"))
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


def test_document_permission_cascades_on_document_delete(database):
    _, session_factory = database
    with session_factory() as session:
        _save_role(session, "admin")
        _save_document(session)
        session.add(DocumentPermissionRecord(document_id="doc1", principal_type="role", role_id=1, permission="read"))
        session.commit()
        session.delete(session.query(DocumentRecord).filter_by(document_id="doc1").one())
        session.commit()
        assert session.query(DocumentPermissionRecord).filter_by(document_id="doc1").first() is None


def test_document_permission_requires_a_principal(database):
    _, session_factory = database
    with session_factory() as session:
        _save_document(session)
    with pytest.raises(IntegrityError):
        with session_factory() as session:
            session.add(DocumentPermissionRecord(document_id="doc1", principal_type="role", role_id=None, user_id=None, permission="read"))
            session.commit()


def _save_department_and_user(session):
    session.add(DepartmentRecord(department_id="d1", department_name="Engineering", created_at=_time(), updated_at=_time()))
    session.add(UserRecord(uid="u1", username="u1", name="User One", email="u1@example.com", role="Member", department_id="d1", created_at=_time(), updated_at=_time()))
    session.commit()


def _save_document(session):
    session.add(DocumentRecord(document_id="doc1", document_name="Policy v1", created_at=_time(), updated_at=_time()))
    session.commit()


def _save_project(session):
    session.add(DepartmentRecord(department_id="d1", department_name="Engineering", status="active", created_at=_time(), updated_at=_time()))
    session.flush()
    session.add(ProjectRecord(project_id="p1", project_name="Proj", department_id="d1", status="active", created_at=_time(), updated_at=_time()))
    session.commit()


def test_project_grant_requires_a_principal(database):
    _, session_factory = database
    with session_factory() as session:
        _save_project(session)
    with pytest.raises(IntegrityError):
        with session_factory() as session:
            session.add(ProjectGrantRecord(project_id="p1", principal_type="role", role_id=None, user_id=None, granted_at=_time()))
            session.commit()


def test_project_grant_cascades_on_project_delete(database):
    _, session_factory = database
    with session_factory() as session:
        _save_project(session)
        _save_role(session, "tester")
        session.add(ProjectGrantRecord(project_id="p1", principal_type="role", role_id=1, granted_at=_time()))
        session.commit()
        session.delete(session.query(ProjectRecord).filter_by(project_id="p1").one())
        session.commit()
        assert session.query(ProjectGrantRecord).filter_by(project_id="p1").first() is None


def test_project_grants_unique_constraint_allows_distinct_principals(database):
    _, session_factory = database
    with session_factory() as session:
        _save_project(session)
        _save_role(session, "r1")
        _save_role(session, "r2")
        session.add(ProjectGrantRecord(project_id="p1", principal_type="role", role_id=1, user_id=None, granted_at=_time()))
        session.add(ProjectGrantRecord(project_id="p1", principal_type="role", role_id=2, user_id=None, granted_at=_time()))
        session.commit()
        assert session.query(ProjectGrantRecord).count() == 2


def test_sequence_rows_are_isolated_per_business_id_family(database):
    _, session_factory = database
    with session_factory() as session:
        session.add(BusinessIdSequenceRecord(sequence_key="user", prefix="MSS", last_value=2, updated_at=_time()))
        session.add(BusinessIdSequenceRecord(sequence_key="project", prefix="PROJ", last_value=5, updated_at=_time()))
        session.commit()
    with session_factory() as session:
        assert session.get(BusinessIdSequenceRecord, "user").last_value == 2
        assert session.get(BusinessIdSequenceRecord, "project").last_value == 5
    with pytest.raises(IntegrityError):
        with session_factory() as session:
            session.add(BusinessIdSequenceRecord(sequence_key="user", prefix="MSS", last_value=99, updated_at=_time()))
            session.commit()


def test_sequence_counter_is_advanced_by_atomic_update(database):
    _, session_factory = database
    with session_factory() as session:
        session.add(BusinessIdSequenceRecord(sequence_key="user", prefix="MSS", last_value=0, updated_at=_time()))
        session.commit()
    with session_factory() as session:
        value = session.execute(
            update(BusinessIdSequenceRecord)
            .where(BusinessIdSequenceRecord.sequence_key == "user")
            .values(last_value=BusinessIdSequenceRecord.last_value + 1)
            .returning(BusinessIdSequenceRecord.last_value)
        ).scalar_one()
        session.commit()
        assert value == 1
    with session_factory() as session:
        assert session.get(BusinessIdSequenceRecord, "user").last_value == 1