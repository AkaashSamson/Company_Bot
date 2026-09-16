PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS departments (
    department_id VARCHAR(128) PRIMARY KEY,
    department_name VARCHAR(200) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    uid VARCHAR(128) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(320) NOT NULL UNIQUE,
    role VARCHAR(200) NOT NULL,
    department_id VARCHAR(128) NOT NULL REFERENCES departments(department_id),
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    project_id VARCHAR(128) PRIMARY KEY,
    project_name VARCHAR(200) NOT NULL,
    department_id VARCHAR(128) NOT NULL REFERENCES departments(department_id),
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    document_id VARCHAR(128) PRIMARY KEY,
    document_name VARCHAR(255) NOT NULL,
    project_id VARCHAR(128) REFERENCES projects(project_id),
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS user_projects (
    uid VARCHAR(128) NOT NULL REFERENCES users(uid),
    project_id VARCHAR(128) NOT NULL REFERENCES projects(project_id),
    assigned_by_uid VARCHAR(128) REFERENCES users(uid),
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    assigned_at DATETIME NOT NULL,
    PRIMARY KEY (uid, project_id)
);

CREATE INDEX IF NOT EXISTS ix_users_department_id ON users(department_id);
CREATE INDEX IF NOT EXISTS ix_projects_department_id ON projects(department_id);
CREATE INDEX IF NOT EXISTS ix_documents_project_id ON documents(project_id);
CREATE INDEX IF NOT EXISTS ix_user_projects_project_id ON user_projects(project_id);
