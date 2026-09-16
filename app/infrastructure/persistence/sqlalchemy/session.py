from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.persistence.sqlalchemy.models import Base

import app.infrastructure.persistence.sqlalchemy.foundation_models as _foundation_models  # noqa: F401  (registers tables on Base.metadata)

_COLUMN_ADDITIONS = {
    "users": {
        "username": "VARCHAR(128) NOT NULL DEFAULT ''",
        "password_representation": "VARCHAR(512) NOT NULL DEFAULT ''",
        "password_changed_at": "DATETIME NULL",
        "must_change_password": "BOOLEAN NOT NULL DEFAULT 0",
        "employee_id": "VARCHAR(64) NULL",
        "first_name": "VARCHAR(200) NULL",
        "last_name": "VARCHAR(200) NULL",
    },
    "departments": {
        "description": "VARCHAR(500) NULL",
        "default_billable": "VARCHAR(32) NOT NULL DEFAULT 'billable'",
    },
    "department_members": {
        "billable_status": "VARCHAR(32) NULL",
        "left_at": "DATETIME NULL",
    },
    "roles": {
        "scope": "VARCHAR(32) NOT NULL DEFAULT 'global'",
        "department_id": "VARCHAR(128) NULL",
        "created_by_uid": "VARCHAR(128) NULL",
    },
    "projects": {
        "description": "VARCHAR(500) NULL",
        "manager_uid": "VARCHAR(128) NULL",
        "start_date": "DATETIME NULL",
        "end_date": "DATETIME NULL",
        "created_by_uid": "VARCHAR(128) NULL",
    },
    "user_projects": {
        "membership_role": "VARCHAR(64) NOT NULL DEFAULT 'Member'",
        "left_at": "DATETIME NULL",
    },
    "documents": {
        "original_filename": "VARCHAR(255) NULL",
        "file_type": "VARCHAR(32) NULL",
        "description": "VARCHAR(500) NULL",
        "version": "VARCHAR(32) NOT NULL DEFAULT '1.0'",
        "storage_location": "VARCHAR(1024) NULL",
        "uploaded_by": "VARCHAR(128) NULL",
        "uploaded_at": "DATETIME NULL",
    },
}

_INDEX_ADDITIONS = [
    ("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_employee_id ON users (employee_id)",),
    ("CREATE INDEX IF NOT EXISTS ix_roles_department_id ON roles (department_id)",),
    ("CREATE INDEX IF NOT EXISTS ix_projects_department_id ON projects (department_id)",),
    ("CREATE UNIQUE INDEX IF NOT EXISTS ix_projects_project_id ON projects (project_id)",),
    ("CREATE INDEX IF NOT EXISTS ix_documents_project_id ON documents (project_id)",),
    ("CREATE UNIQUE INDEX IF NOT EXISTS ix_documents_document_id ON documents (document_id)",),
]

_LEGACY_PROJECTS_COLUMNS = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "project_id": "VARCHAR(128) NOT NULL",
    "project_name": "VARCHAR(200) NOT NULL",
    "department_id": "VARCHAR(128) NOT NULL",
    "status": "VARCHAR(32) NOT NULL DEFAULT 'active'",
    "created_at": "DATETIME NOT NULL",
    "updated_at": "DATETIME NOT NULL",
    "description": "VARCHAR(500) NULL",
    "manager_uid": "VARCHAR(128) NULL",
    "start_date": "DATETIME NULL",
    "end_date": "DATETIME NULL",
    "created_by_uid": "VARCHAR(128) NULL",
}

_LEGACY_DOCUMENTS_COLUMNS = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "document_id": "VARCHAR(128) NOT NULL",
    "document_name": "VARCHAR(255) NOT NULL",
    "project_id": "VARCHAR(128) NULL",
    "status": "VARCHAR(32) NOT NULL DEFAULT 'active'",
    "created_at": "DATETIME NOT NULL",
    "updated_at": "DATETIME NOT NULL",
    "original_filename": "VARCHAR(255) NULL",
    "file_type": "VARCHAR(32) NULL",
    "description": "VARCHAR(500) NULL",
    "version": "VARCHAR(32) NOT NULL DEFAULT '1.0'",
    "storage_location": "VARCHAR(1024) NULL",
    "uploaded_by": "VARCHAR(128) NULL",
    "uploaded_at": "DATETIME NULL",
}


def _rebuild_legacy_table(engine, table_name, column_spec, index_statements):
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        existing = {column["name"] for column in inspect(connection).get_columns(table_name)}
        if "id" in existing:
            return
        preserved = [name for name in column_spec if name in existing]
        explicit = ["id"] + preserved
        create_statement = ", ".join(
            f"{name} {column_spec[name]}" for name in explicit
        )
        connection.execute(text(f"CREATE TABLE {table_name}_new ({create_statement})"))
        select_clause = ", ".join("rowid" if name == "id" else name for name in explicit)
        connection.execute(
            text(
                "INSERT INTO {}_new ({}) SELECT {} FROM {}".format(
                    table_name, ", ".join(explicit), select_clause, table_name
                )
            )
        )
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text(f"DROP TABLE {table_name}"))
        connection.execute(text(f"ALTER TABLE {table_name}_new RENAME TO {table_name}"))
        connection.execute(text("PRAGMA foreign_keys=ON"))
        for (statement,) in index_statements:
            connection.execute(text(statement))


def create_engine_and_session_factory(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, future=True)

    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine, sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def initialize_database(engine) -> None:
    Path("instance").mkdir(exist_ok=True)
    Base.metadata.create_all(engine)
    if engine.url.drivername.startswith("sqlite"):
        with engine.begin() as connection:
            inspector = inspect(connection)
            for table, additions in _COLUMN_ADDITIONS.items():
                columns = {column["name"] for column in inspector.get_columns(table)}
                for name, definition in additions.items():
                    if name not in columns:
                        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
            connection.execute(text("UPDATE users SET username = uid WHERE username = ''"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)"))
            for (statement,) in _INDEX_ADDITIONS:
                connection.execute(text(statement))
        _rebuild_legacy_table(
            engine, "projects", _LEGACY_PROJECTS_COLUMNS,
            [statement for statement in _INDEX_ADDITIONS if "projects" in statement],
        )
        _rebuild_legacy_table(
            engine, "documents", _LEGACY_DOCUMENTS_COLUMNS,
            [statement for statement in _INDEX_ADDITIONS if "documents" in statement],
        )