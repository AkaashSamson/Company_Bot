PRAGMA foreign_keys = ON;

CREATE TABLE
    IF NOT EXISTS roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(100) NOT NULL UNIQUE,
        description VARCHAR(255),
        status VARCHAR(32) NOT NULL DEFAULT 'active',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

CREATE TABLE
    IF NOT EXISTS permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(150) NOT NULL UNIQUE,
        description VARCHAR(255),
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

CREATE TABLE
    IF NOT EXISTS role_permissions (
        role_id INTEGER NOT NULL REFERENCES roles (id) ON DELETE CASCADE,
        permission_id INTEGER NOT NULL REFERENCES permissions (id) ON DELETE CASCADE,
        granted_by_uid VARCHAR(128) REFERENCES users (uid),
        granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (role_id, permission_id)
    );

CREATE TABLE
    IF NOT EXISTS department_members (
        user_id VARCHAR(128) NOT NULL REFERENCES users (uid) ON DELETE CASCADE,
        department_id VARCHAR(128) NOT NULL REFERENCES departments (department_id) ON DELETE CASCADE,
        membership_role VARCHAR(200) NOT NULL DEFAULT 'Member',
        assigned_by_uid VARCHAR(128) REFERENCES users (uid),
        status VARCHAR(32) NOT NULL DEFAULT 'active',
        assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, department_id)
    );

CREATE TABLE
    IF NOT EXISTS document_permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id VARCHAR(128) NOT NULL REFERENCES documents (document_id) ON DELETE CASCADE,
        principal_type VARCHAR(12) NOT NULL,
        role_id INTEGER REFERENCES roles (id) ON DELETE CASCADE,
        user_id VARCHAR(128) REFERENCES users (uid) ON DELETE CASCADE,
        permission VARCHAR(32) NOT NULL,
        granted_by_uid VARCHAR(128) REFERENCES users (uid),
        status VARCHAR(32) NOT NULL DEFAULT 'active',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_document_permission UNIQUE (
            document_id,
            principal_type,
            role_id,
            user_id,
            permission
        ),
        CONSTRAINT ck_document_permissions_principal CHECK (
            principal_type IN ('role', 'user')
            AND (
                (
                    principal_type = 'role'
                    AND role_id IS NOT NULL
                    AND user_id IS NULL
                )
                OR (
                    principal_type = 'user'
                    AND user_id IS NOT NULL
                    AND role_id IS NULL
                )
            )
        )
    );

CREATE INDEX IF NOT EXISTS ix_role_permissions_permission_id ON role_permissions (permission_id);

CREATE INDEX IF NOT EXISTS ix_department_members_department_id ON department_members (department_id);

CREATE INDEX IF NOT EXISTS ix_document_permissions_document_id ON document_permissions (document_id);

CREATE INDEX IF NOT EXISTS ix_document_permissions_role_id ON document_permissions (role_id);

CREATE INDEX IF NOT EXISTS ix_document_permissions_user_id ON document_permissions (user_id);