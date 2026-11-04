PRAGMA foreign_keys = ON;

ALTER TABLE users ADD COLUMN employee_id VARCHAR(64) NULL;
ALTER TABLE users ADD COLUMN first_name VARCHAR(200) NULL;
ALTER TABLE users ADD COLUMN last_name VARCHAR(200) NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_employee_id ON users (employee_id);

ALTER TABLE departments ADD COLUMN description VARCHAR(500) NULL;
ALTER TABLE departments ADD COLUMN default_billable VARCHAR(32) NOT NULL DEFAULT 'billable';

ALTER TABLE department_members ADD COLUMN billable_status VARCHAR(32) NULL;
ALTER TABLE department_members ADD COLUMN left_at DATETIME NULL;