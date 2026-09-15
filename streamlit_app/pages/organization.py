import streamlit as st

from streamlit_app.services.admin_api import AdminAPI
from streamlit_app.services.ui_helpers import format_error, unavailable

st.set_page_config(page_title="Organization | KnowLayer", page_icon="📊")
st.title("Organization Overview")

service = AdminAPI()

try:
    users = service.list_users()
except Exception as error:
    st.error(unavailable("user service"))
    st.caption(f"Technical detail: {format_error(error)}")
    users = []

try:
    departments = service.list_departments()
except Exception as error:
    departments = []

try:
    roles = service.list_roles()
except Exception as error:
    roles = []

try:
    projects = service.list_projects()
except Exception as error:
    projects = []

try:
    documents = service.list_documents()
except Exception as error:
    documents = []


def _safe_count(items, predicate=lambda item: True):
    return sum(1 for item in items if predicate(item))


st.subheader("Summary")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Users", _safe_count(users))
col2.metric("Active users", _safe_count(users, lambda u: u.get("status") == "active"))
col3.metric("Departments", _safe_count(departments))
col4.metric("Roles", _safe_count(roles))

col1, col2, col3 = st.columns(3)
col1.metric("Projects", _safe_count(projects))
col2.metric("Active projects", _safe_count(projects, lambda p: p.get("status") == "active"))
col3.metric("Documents", _safe_count(documents))


def _lookup_mapping(items, key, value):
    result = {}
    for item in items:
        result[item.get(key)] = item.get(value)
    return result


# ------------------------------------------------------------ breakdowns

department_names = _lookup_mapping(departments, "department_id", "department_name")
user_names = _lookup_mapping(users, "uid", "name")
project_names = _lookup_mapping(projects, "project_id", "project_name")

if users:
    st.subheader("Users by department")
    dept_counts = {}
    for user in users:
        department_id = user.get("department_id")
        label = department_names.get(department_id, department_id or "Unassigned")
        dept_counts[label] = dept_counts.get(label, 0) + 1
    st.dataframe(
        {"Department": list(dept_counts), "Users": list(dept_counts.values())},
        use_container_width=True,
    )

if projects:
    st.subheader("Projects")
    project_rows = []
    for project in projects:
        project_rows.append({
            "Project ID": project.get("project_id"),
            "Project": project.get("project_name"),
            "Department": department_names.get(project.get("department_id"), project.get("department_id") or "-"),
            "Manager": user_names.get(project.get("manager_uid"), project.get("manager_uid") or "-"),
            "Status": project.get("status"),
        })
    st.dataframe(project_rows, use_container_width=True)

if documents:
    st.subheader("Documents")
    document_rows = []
    for document in documents:
        document_rows.append({
            "Document ID": document.get("document_id"),
            "Document": document.get("document_name"),
            "Project": project_names.get(document.get("project_id"), document.get("project_id") or "Unassigned"),
            "Type": document.get("file_type") or "-",
            "Version": document.get("version") or "-",
            "Status": document.get("status"),
        })
    st.dataframe(document_rows, use_container_width=True)

if roles:
    st.subheader("Roles")
    role_rows = []
    for role in roles:
        role_rows.append({
            "Role": role.get("name"),
            "Scope": role.get("scope"),
            "Department": department_names.get(role.get("department_id"), role.get("department_id") or "-"),
            "Status": role.get("status"),
        })
    st.dataframe(role_rows, use_container_width=True)

# ------------------------------------------------------------ your access

st.subheader("Your access")
auth = st.session_state.get("auth")
if isinstance(auth, dict):
    uid = auth.get("uid") or auth.get("username")
    if uid:
        try:
            user = service.get_user(uid)
            st.markdown(f"Signed in as **{user.get('name') or user.get('uid')}**")
            roles_for_user = service.list_user_roles(uid)
            if roles_for_user:
                st.markdown("**Roles**")
                st.write(", ".join(role.get("name", "") for role in roles_for_user))
            permissions = service.list_user_permissions(uid)
            if permissions:
                granted = permissions.get("permissions")
                st.markdown("**Permissions**")
                st.write(", ".join(granted) if granted else "No direct permissions.")
        except Exception as error:
            st.caption(format_error(error))