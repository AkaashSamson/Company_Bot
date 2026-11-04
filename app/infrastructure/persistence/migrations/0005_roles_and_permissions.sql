PRAGMA foreign_keys = ON;

ALTER TABLE roles ADD COLUMN scope VARCHAR(32) NOT NULL DEFAULT 'global';
ALTER TABLE roles ADD COLUMN department_id VARCHAR(128) NULL REFERENCES departments(department_id);
ALTER TABLE roles ADD COLUMN created_by_uid VARCHAR(128) NULL REFERENCES users(uid);
CREATE INDEX IF NOT EXISTS ix_roles_department_id ON roles (department_id);
