import logging
from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

OBSOLETE_TABLES = (
    "department_members",
    "document_permissions",
    "project_grants",
    "business_id_sequences",
)


def apply_legacy_schema_migration(engine) -> None:
    """Migrate legacy SQLite database schemas to the consolidated 8-table model.

    Drops obsolete tables, ensures users.password_hash is populated from
    legacy password_representation, and adds any missing columns.
    """
    if not engine.url.drivername.startswith("sqlite"):
        return

    with engine.begin() as connection:
        inspector = inspect(connection)
        existing_tables = set(inspector.get_table_names())

        # 1. Drop obsolete tables
        for table in OBSOLETE_TABLES:
            if table in existing_tables:
                logger.info("Dropping obsolete legacy table: %s", table)
                connection.execute(text(f"DROP TABLE IF EXISTS {table}"))

        # 2. Migrate users table columns
        if "users" in existing_tables:
            user_columns = {col["name"] for col in inspector.get_columns("users")}

            if "password_hash" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(512) NOT NULL DEFAULT ''"))
                if "password_representation" in user_columns:
                    connection.execute(text("UPDATE users SET password_hash = password_representation WHERE password_hash = ''"))
            elif "password_representation" in user_columns:
                connection.execute(text("UPDATE users SET password_hash = password_representation WHERE password_hash = '' AND password_representation != ''"))

            if "role_id" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN role_id INTEGER NULL"))
            if "job_title" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN job_title VARCHAR(200) NULL"))
            if "employee_id" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN employee_id VARCHAR(64) NULL"))
            if "first_name" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN first_name VARCHAR(200) NULL"))
            if "last_name" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN last_name VARCHAR(200) NULL"))
            if "password_changed_at" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN password_changed_at DATETIME NULL"))
            if "must_change_password" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0"))

            connection.execute(text("UPDATE users SET username = uid WHERE username = '' OR username IS NULL"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_employee_id ON users (employee_id)"))

        # 3. Ensure foreign key indexes exist
        if "projects" in existing_tables:
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_projects_department_id ON projects (department_id)"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_projects_project_id ON projects (project_id)"))
        if "documents" in existing_tables:
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_documents_project_id ON documents (project_id)"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_documents_document_id ON documents (document_id)"))
        if "roles" in existing_tables:
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_roles_department_id ON roles (department_id)"))
