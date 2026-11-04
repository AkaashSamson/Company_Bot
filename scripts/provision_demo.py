"""Provision a fresh demo dataset for KnowLayer using the application's own services.

Creates departments, users, projects, department memberships, project memberships,
and project grants. Passwords are hashed with the same PasswordHasher the app uses;
business IDs (DEPT-/MSS-/PROJ-…) are allocated through the same generator.
"""

import json

from app.infrastructure.persistence.factory import get_session_factory, initialize_persistence
from app.use_cases.organization.user_management import UserManagementService
from app.use_cases.organization.project_management import ProjectManagementService
from app.use_cases.organization.department_membership import DepartmentMembershipService
from app.use_cases.organization.membership_management import MembershipManagementService
from app.use_cases.organization.role_management import RoleManagementService
from app.use_cases.organization.project_access import ProjectAccessService
from app.infrastructure.authentication.password_hasher import PasswordHasher
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.infrastructure.persistence.factory import create_unit_of_work
from app.api.dependencies import get_business_id_generator

ADMIN_UID = "admin"
DEFAULT_PASSWORD = "ChangeMe123!"


def main():
    initialize_persistence(get_session_factory)
    uow_factory = create_unit_of_work
    users_svc = UserManagementService(uow_factory, PasswordHasher(), business_id_generator=get_business_id_generator())
    projects_svc = ProjectManagementService(uow_factory, business_id_generator=get_business_id_generator())
    dept_members_svc = DepartmentMembershipService(uow_factory)
    proj_members_svc = MembershipManagementService(uow_factory)
    roles_svc = RoleManagementService(uow_factory)
    grant_svc = ProjectAccessService(uow_factory)

    created = {"departments": [], "users": [], "projects": [], "memberships": [], "grants": []}

    # ---------------------------------------------------------------- departments
    department_names = [
        ("Human Resources", "Recruitment, onboarding and employee relations.", "billable"),
        ("Engineering", "Product development and platform engineering.", "billable"),
        ("Marketing", "Brand, campaigns and market research.", "both"),
        ("Finance", "Accounting, payroll and budgeting.", "non-billable"),
    ]
    department_ids = {}
    for name, description, billable in department_names:
        department = users_svc.create_department(ADMIN_UID, department_name=name, description=description, default_billable=billable)
        department_ids[name] = department.department_id
        created["departments"].append({"department_id": department.department_id, "name": name, "billable": billable})
        print("department:", department.department_id, name)

    # --------------------------------------------------------------------- users
    user_specs = [
        # (uid, username, name, email, role, department_name)
        ("aarav.sharma", "aarav", "Aarav Sharma", "aarav.sharma@nexora.local", "Manager", "Human Resources"),
        ("priya.nair", "priya", "Priya Nair", "priya.nair@nexora.local", "Tester", "Human Resources"),
        ("rohan.yadav", "rohan", "Rohan Yadav", "rohan.yadav@nexora.local", "Manager", "Engineering"),
        ("vikram.singh", "vikram", "Vikram Singh", "vikram.singh@nexora.local", "Developer", "Engineering"),
        ("anita.gupta", "anita", "Anita Gupta", "anita.gupta@nexora.local", "Developer", "Engineering"),
        ("meera.iyer", "meera", "Meera Iyer", "meera.iyer@nexora.local", "Solution Architect", "Engineering"),
        ("karan.mehta", "karan", "Karan Mehta", "karan.mehta@nexora.local", "Manager", "Marketing"),
        ("sneha.patel", "sneha", "Sneha Patel", "sneha.patel@nexora.local", "Tester", "Marketing"),
        ("ritu.sharma", "ritu", "Ritu Sharma", "ritu.sharma@nexora.local", "Manager", "Finance"),
        ("deepak.kumar", "deepak", "Deepak Kumar", "deepak.kumar@nexora.local", "Developer", "Finance"),
    ]
    user_records = []
    for uid, username, name, email, role, dept_name in user_specs:
        user = users_svc.create_user(
            ADMIN_UID, uid, name, email, role, department_ids[dept_name],
            username=username, initial_password=DEFAULT_PASSWORD,
            first_name=name.split()[0], last_name=name.split()[-1],
        )
        user_records.append({
            "uid": user.uid, "username": username, "name": name, "email": email,
            "role": role, "department": dept_name,
            "department_id": department_ids[dept_name],
            "employee_id": user.employee_id,
            "password": DEFAULT_PASSWORD, "must_change_password": True,
        })
        created["users"].append(user_records[-1])
        print("user:", user.uid, role, dept_name)

    # ---------------------------------------------------- custom department role
    lead_role = roles_svc.create_role(
        ADMIN_UID, "Project Coordinator",
        description="Coordinates project deliverables and documents",
        scope="department", department_id=department_ids["Engineering"],
        permission_ids=[],
    )
    co_perm_ids = []
    with uow_factory() as uow:
        for perm_name in ("PROJECT_VIEW", "DOCUMENT_VIEW", "DOCUMENT_QUERY", "USER_VIEW", "DEPARTMENT_VIEW"):
            perm = uow.permissions.get_by_name(perm_name)
            if perm is not None:
                co_perm_ids.append(perm.permission_id)
    roles_svc.set_role_permissions(ADMIN_UID, lead_role.role_id, co_perm_ids)
    print("role: Project Coordinator (dept Engineering)")

    # ------------------------------------------------------------------- projects
    project_specs = [
        ("Employee Handbook Refresh", "Human Resources", "aarav.sharma"),
        ("Company Bot Platform", "Engineering", "rohan.yadav"),
        ("Brand Website Rebuild", "Marketing", "karan.mehta"),
        ("Payroll Upgrade", "Finance", "ritu.sharma"),
    ]
    projects = {}
    for name, dept_name, manager_uid in project_specs:
        project = projects_svc.create_project(
            ADMIN_UID, project_name=name, department_id=department_ids[dept_name],
            description=f"{name} initiative", manager_uid=manager_uid,
        )
        projects[dept_name] = project.project_id
        created["projects"].append({"project_id": project.project_id, "name": name, "manager": manager_uid})
        print("project:", project.project_id, name)

    # ---------------------------------------------------- department memberships
    for record in user_records:
        dept_members_svc.assign(ADMIN_UID, record["uid"], record["department_id"], billable_status="billable", membership_role=record["role"])
        created["memberships"].append({"type": "department", "user": record["uid"], "target": record["department_id"]})

    # ------------------------------------------------------- project memberships
    dept_to_project = {r["department"]: projects[r["department"]] for r in user_records}
    for record in user_records:
        proj_members_svc.assign(ADMIN_UID, record["uid"], dept_to_project[record["department"]], membership_role=record["role"])
        created["memberships"].append({"type": "project", "user": record["uid"], "target": dept_to_project[record["department"]]})

    # -------------------------------------------------------------- project grants
    admin_principal = AuthenticatedPrincipal(ADMIN_UID)
    with uow_factory() as uow:
        developer_role = uow.roles.get_by_name("Developer")
        tester_role = uow.roles.get_by_name("Tester")
        lead_role_id = uow.roles.get_by_name("Project Coordinator")
    grant_svc.grant(admin_principal, projects["Engineering"], "role", role_id=developer_role.role_id)
    grant_svc.grant(admin_principal, projects["Engineering"], "role", role_id=lead_role_id.role_id)
    grant_svc.grant(admin_principal, projects["Human Resources"], "role", role_id=tester_role.role_id)
    grant_svc.grant(admin_principal, projects["Marketing"], "user", user_id="sneha.patel")
    created["grants"] = [
        {"project": projects["Engineering"], "role": "Developer"},
        {"project": projects["Engineering"], "role": "Project Coordinator"},
        {"project": projects["Human Resources"], "role": "Tester"},
        {"project": projects["Marketing"], "user": "sneha.patel"},
    ]
    print("grants: done")

    with open("data/seeded_users.json", "w", encoding="utf-8") as fh:
        json.dump(user_records, fh, indent=2)
    print("wrote data/seeded_users.json with", len(user_records), "users")


if __name__ == "__main__":
    main()