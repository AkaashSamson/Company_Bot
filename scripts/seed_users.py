"""Seed the four system roles and one demo user per role.

Passwords default to the auto-generated employee id (MSS001, ...).

Usage:
    python -m scripts.seed_users
"""

from app.use_cases.access.auth_service import AuthError, UserManagementService

DEMO_USERS = [
    {"first_name": "Roshan", "last_name": "Yadav", "role_code": "manager"},
    {"first_name": "Priya", "last_name": "Sharma", "role_code": "tester"},
    {"first_name": "Arjun", "last_name": "Mehta", "role_code": "solution_architect"},
    {"first_name": "Sneha", "last_name": "Patil", "role_code": "developer"},
]


def main():
    service = UserManagementService(seed_roles=True)
    for user in DEMO_USERS:
        try:
            result = service.register_user(**user)
            print(
                f"Created {result['first_name']} {result['last_name']} "
                f"-> {result['employee_id']} "
                f"(email: {result['email']}, password: {result['employee_id']}, "
                f"role: {result['role_code']})"
            )
        except AuthError as exc:
            print(f"Skip {user['first_name']} {user['last_name']}: {exc}")


if __name__ == "__main__":
    main()