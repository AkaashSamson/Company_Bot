# Project Membership Workflow

Projects belong to departments, while users and projects are connected through the `user_projects` associative table.

1. Users or Projects pages call the project and membership endpoints through `OrganizationService`.
2. The membership use case loads the actor, target user, and project in one Unit of Work.
3. Admin can operate across departments. Manager operations require both the target user and project to belong to the Manager's department.
4. Assignment is idempotent through the `(uid, project_id)` uniqueness constraint. Revocation changes membership status without deleting project data.
5. A failed transaction rolls back the Unit of Work, preventing a partial assignment or revocation.

Project reads expose active projects authorized for the current principal.
