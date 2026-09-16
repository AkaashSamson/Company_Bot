"""Seed definitions for the configurable RBAC catalog.

The database (`permissions`, `roles`, `role_permissions`) is the source of
truth. These tuples only describe the initial catalog that is provisioned on
first start-up; administrators can create additional permissions and roles at
runtime through the API. Nothing here is consulted when authorizing a request.
"""

PERMISSION_DEFINITIONS = (
    ("USER_VIEW", "View users"),
    ("USER_CREATE", "Create users"),
    ("USER_UPDATE", "Update users"),
    ("USER_DELETE", "Deactivate or delete users"),
    ("DEPARTMENT_VIEW", "View departments"),
    ("DEPARTMENT_CREATE", "Create departments"),
    ("DEPARTMENT_UPDATE", "Update departments"),
    ("DEPARTMENT_ASSIGN_USERS", "Assign users to departments"),
    ("PROJECT_VIEW", "View projects"),
    ("PROJECT_CREATE", "Create projects"),
    ("PROJECT_UPDATE", "Update projects"),
    ("PROJECT_DELETE", "Delete projects"),
    ("PROJECT_MANAGE_MEMBERS", "Manage project members"),
    ("PROJECT_LEAVE", "Leave a project"),
    ("DOCUMENT_VIEW", "View documents"),
    ("DOCUMENT_UPLOAD", "Upload documents"),
    ("DOCUMENT_UPDATE", "Update documents"),
    ("DOCUMENT_DELETE", "Delete documents"),
    ("DOCUMENT_QUERY", "Query documents"),
    ("DOCUMENT_MANAGE_ACCESS", "Manage document access"),
    ("ROLE_VIEW", "View roles and permissions"),
    ("ROLE_CREATE", "Create roles"),
    ("ROLE_UPDATE", "Update roles"),
    ("ROLE_DELETE", "Delete roles"),
    ("PERMISSION_MANAGE", "Manage role permission assignments"),
)

ALL_PERMISSION_NAMES = tuple(name for name, _ in PERMISSION_DEFINITIONS)

# "*" expands to every permission in the catalog.
INITIAL_ROLE_DEFINITIONS = (
    {
        "name": "Admin",
        "description": "Full administrative access across the platform",
        "scope": "global",
        "permissions": "*",
    },
    {
        "name": "Manager",
        "description": "Manages users, projects and documents within a department",
        "scope": "global",
        "permissions": (
            "USER_VIEW", "USER_CREATE", "USER_UPDATE",
            "DEPARTMENT_VIEW", "DEPARTMENT_ASSIGN_USERS",
            "PROJECT_VIEW", "PROJECT_CREATE", "PROJECT_UPDATE", "PROJECT_MANAGE_MEMBERS", "PROJECT_LEAVE",
            "DOCUMENT_VIEW", "DOCUMENT_UPLOAD", "DOCUMENT_UPDATE", "DOCUMENT_QUERY", "DOCUMENT_MANAGE_ACCESS",
            "ROLE_VIEW", "ROLE_CREATE", "ROLE_UPDATE",
        ),
    },
    {
        "name": "Developer",
        "description": "Contributes to projects and documents",
        "scope": "global",
        "permissions": (
            "USER_VIEW", "DEPARTMENT_VIEW",
            "PROJECT_VIEW", "PROJECT_LEAVE",
            "DOCUMENT_VIEW", "DOCUMENT_UPLOAD", "DOCUMENT_UPDATE", "DOCUMENT_QUERY",
        ),
    },
    {
        "name": "Tester",
        "description": "Reviews and queries project documents",
        "scope": "global",
        "permissions": (
            "USER_VIEW", "DEPARTMENT_VIEW", "PROJECT_VIEW",
            "DOCUMENT_VIEW", "DOCUMENT_QUERY",
        ),
    },
    {
        "name": "Solution Architect",
        "description": "Designs and governs solution scope across documents",
        "scope": "global",
        "permissions": (
            "USER_VIEW", "DEPARTMENT_VIEW",
            "PROJECT_VIEW", "PROJECT_CREATE", "PROJECT_UPDATE",
            "DOCUMENT_VIEW", "DOCUMENT_UPLOAD", "DOCUMENT_UPDATE", "DOCUMENT_QUERY", "DOCUMENT_MANAGE_ACCESS",
            "ROLE_VIEW",
        ),
    },
)


def resolve_role_permissions(permission_names):
    if permission_names == "*":
        return ALL_PERMISSION_NAMES
    return tuple(permission_names)
