import streamlit as st

from streamlit_app.services.admin_api import AdminAPI
from streamlit_app.services.organization_service import OrganizationService
from streamlit_app.services.ui_helpers import format_error
from streamlit_app.session_auth import require_auth

st.set_page_config(page_title="Users | KnowLayer", layout="wide")
auth = require_auth()
st.title("Users")

permissions = set(auth.get("permissions", []) if isinstance(auth, dict) else [])
user_info = auth.get("user", {}) if isinstance(auth, dict) else {}
user_role = (user_info.get("role") or "").lower()
auth_uid = auth.get("uid", "") if isinstance(auth, dict) else ""
is_admin = user_role == "admin" or auth_uid == "admin" or "*" in permissions or "ADMIN" in permissions

# Write Implies Read
can_view = is_admin or any(p.startswith("USER_") for p in permissions)
if not can_view:
    st.warning("You do not have permission to view users.")
    st.stop()

service = OrganizationService()
admin = AdminAPI()

departments = []
users = []
roles = []

try:
    departments = service.list_departments()
except Exception as error:
    st.warning("Departments are currently unavailable.")
    departments = []

try:
    users = service.list_users()
except Exception as error:
    st.error("The organization service is unavailable for users.")
    st.caption(f"Technical detail: {format_error(error)}")
    users = []

try:
    roles = admin.list_roles()
except Exception:
    roles = []

department_options = {item["department_name"]: item["department_id"] for item in departments}
user_options = {item["name"] or item["uid"]: item["uid"] for item in users}
role_options = {role["name"]: role["name"] for role in roles}

# ------------------------------------------------------------ Add User (Gated: USER_CREATE)
can_create = is_admin or "USER_CREATE" in permissions
if can_create:
    with st.expander("? Add User", expanded=False):
        with st.form("create-user"):
            username = st.text_input("Username", help="Login handle; leave blank to use the generated employee ID.")
            name = st.text_input("Name *")
            email = st.text_input("Email *")
            role = st.selectbox("Role", list(role_options) or ["Employee"])
            initial_password = st.text_input(
                "Initial password",
                type="password",
                help="Leave blank to assign the default password; user must change it on first login. Minimum 8 characters.",
            )
            department_name = st.selectbox("Department", list(department_options) or ["No departments"])
            submitted = st.form_submit_button("Create user", type="primary")

        if submitted:
            if not name.strip() or not email.strip():
                st.error("Name and Email are required.")
            elif initial_password and len(initial_password) < 8:
                st.error("Initial password must be at least 8 characters.")
            elif department_name not in department_options:
                st.error("No valid department selected. Create a department first.")
            else:
                try:
                    service.create_user({
                        "username": username.strip() or None,
                        "name": name.strip(),
                        "email": email.strip(),
                        "role": role,
                        "department_id": department_options[department_name],
                        "initial_password": initial_password or None,
                    })
                    st.success(f"User {name} created successfully.")
                    st.rerun()
                except Exception as error:
                    st.error(format_error(error))

# ------------------------------------------------------------ Manage User (Gated: USER_UPDATE / USER_DELETE)
can_update = is_admin or "USER_UPDATE" in permissions
can_delete = is_admin or "USER_DELETE" in permissions

if (can_update or can_delete) and user_options:
    with st.expander("?? Manage User", expanded=False):
        selected_label = st.selectbox("Select User", list(user_options))
        selected_uid = user_options[selected_label]
        current = next((u for u in users if u["uid"] == selected_uid), {})
        role_names = list(role_options)
        role_index = role_names.index(current.get("role")) if current.get("role") in role_names else 0
        department_names = list(department_options)
        department_index = next(
            (i for i, name in enumerate(department_names)
             if department_options[name] == current.get("department_id")),
            0,
        )

        if can_update:
            with st.form("update-user"):
                new_name = st.text_input("Name", value=current.get("name", ""))
                new_email = st.text_input("Email", value=current.get("email", ""))
                new_role = st.selectbox("Role", role_names or [current.get("role", "")], index=role_index)
                new_department = st.selectbox(
                    "Department",
                    department_names or ["No departments"],
                    index=department_index,
                )
                new_status = st.selectbox(
                    "Status",
                    ["active", "inactive"],
                    index=0 if current.get("status", "active") == "active" else 1,
                )
                submitted_update = st.form_submit_button("Save User Changes", type="primary")

            if submitted_update:
                try:
                    payload = {}
                    if new_name:
                        payload["name"] = new_name
                    if new_email:
                        payload["email"] = new_email
                    if new_role and new_role in role_options:
                        payload["role"] = role_options[new_role]
                    if new_department in department_options:
                        payload["department_id"] = department_options[new_department]
                    if new_status:
                        payload["status"] = new_status
                    admin.update_user(selected_uid, payload)
                    st.success("User updated.")
                    st.rerun()
                except Exception as error:
                    st.error(format_error(error))

        if can_delete:
            col1, col2 = st.columns(2)
            with col1:
                if current.get("status") == "active":
                    if st.button("Deactivate user", key=f"deactivate-{selected_uid}"):
                        try:
                            admin.deactivate_user(selected_uid)
                            st.success("User deactivated.")
                            st.rerun()
                        except Exception as error:
                            st.error(format_error(error))
            with col2:
                if current.get("status") == "inactive":
                    if st.button("Reactivate user", key=f"reactivate-{selected_uid}"):
                        try:
                            admin.update_user(selected_uid, {"status": "active"})
                            st.success("User reactivated.")
                            st.rerun()
                        except Exception as error:
                            st.error(format_error(error))

# ------------------------------------------------------------ View user access
with st.expander("?? View User Access & Permissions", expanded=False):
    if not user_options:
        st.info("No users available.")
    else:
        access_label = st.selectbox("User", list(user_options), key="access-user")
        access_uid = user_options[access_label]
        if st.button("Load access details", key=f"load-access-{access_uid}"):
            try:
                with st.spinner("Loading access details..."):
                    user_roles = admin.list_user_roles(access_uid)
                    user_permissions = admin.list_user_permissions(access_uid)
                    memberships = admin.list_user_memberships(access_uid)
                st.markdown("**Roles**")
                st.write(", ".join(role.get("name", "") for role in user_roles) if user_roles else "None")
                granted = user_permissions.get("permissions")
                st.markdown("**Permissions**")
                st.write(", ".join(granted) if granted else "None")
                st.markdown("**Department Memberships**")
                if memberships:
                    st.dataframe(memberships)
                else:
                    st.write("None")
            except Exception as error:
                st.error(format_error(error))

# ------------------------------------------------------------ Users Table
st.divider()
st.subheader("All Users")
if users:
    st.dataframe(users, use_container_width=True)
else:
    st.info("No users found.")
