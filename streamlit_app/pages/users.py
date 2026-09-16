import streamlit as st

from streamlit_app.services.admin_api import AdminAPI
from streamlit_app.services.organization_service import OrganizationService
from streamlit_app.services.ui_helpers import format_error


st.set_page_config(page_title="Users | KnowLayer")
st.title("Users")
service = OrganizationService()
admin = AdminAPI()

try:
    departments = service.list_departments()
except Exception as error:
    st.error(
        "The organization service is unavailable for departments. "
        "Check that the FastAPI backend is running and that you are logged in."
    )
    st.caption(f"Technical detail: {error}")
    departments = []

try:
    users = service.list_users()
except Exception as error:
    st.error(
        "The organization service is unavailable for users. "
        "Check that the FastAPI backend is running and that you are logged in."
    )
    st.caption(f"Technical detail: {error}")
    users = []

try:
    roles = admin.list_roles()
except Exception:
    roles = []

department_options = {item["department_name"]: item["department_id"] for item in departments}
user_options = {item["name"] or item["uid"]: item["uid"] for item in users}
role_options = {role["name"]: role["name"] for role in roles}

with st.expander("Add department"):
    department_id = st.text_input("Department ID")
    department_name = st.text_input("Department name")
    if st.button("Create department"):
        try:
            service.create_department({"department_id": department_id, "department_name": department_name})
            st.success("Department created.")
            st.rerun()
        except Exception as error:
            st.error(str(error))

with st.expander("Add user"):
    with st.form("create-user"):
        uid = st.text_input("UID")
        name = st.text_input("Name")
        email = st.text_input("Email")
        role = st.text_input("Role")
        initial_password = st.text_input(
            "Initial password",
            type="password",
            help="Leave blank to assign the configured default password; the new user must change it on first login. Minimum 8 characters.",
        )
        department_name = st.selectbox("Department", list(department_options) or ["No departments"])
        submitted = st.form_submit_button("Create user")
    if submitted:
        if initial_password and len(initial_password) < 8:
            st.error("Initial password must be at least 8 characters. Leave it blank to use the configured default password.")
        elif department_name not in department_options:
            st.error("No valid department selected. Create a department first.")
        else:
            try:
                service.create_user({
                    "uid": uid,
                    "name": name,
                    "email": email,
                    "role": role,
                    "department_id": department_options[department_name],
                    "initial_password": initial_password or None,
                })
                st.success("User created.")
                st.rerun()
            except Exception as error:
                st.error(format_error(error))

# ------------------------------------------------------------ manage user

with st.expander("Manage user"):
    if not user_options:
        st.info("No users available to manage.")
    else:
        selected_label = st.selectbox("User", list(user_options))
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
            submitted = st.form_submit_button("Save user")
        if submitted:
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

        col1, col2 = st.columns(2)
        with col1:
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

# ------------------------------------------------------ role + membership

with st.expander("View user access"):
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
                st.markdown("**Department memberships**")
                if memberships:
                    st.dataframe(memberships)
                else:
                    st.write("None")
            except Exception as error:
                st.error(format_error(error))

with st.expander("Assign billable status"):
    if not user_options or not department_options:
        st.info("Create users and departments before assigning a billable status.")
    else:
        billable_user = st.selectbox("User", list(user_options), key="billable-user")
        billable_department = st.selectbox("Department", list(department_options), key="billable-dept")
        billable_status = st.selectbox("Billable status", ["billable", "non-billable"])
        if st.button("Assign billable status"):
            try:
                admin.assign_department_member(department_options[billable_department], {
                    "user_id": user_options[billable_user],
                    "billable_status": billable_status,
                })
                st.success("Billable status assigned.")
                st.rerun()
            except Exception as error:
                st.error(format_error(error))

if users:
    st.dataframe(users, use_container_width=True)
else:
    st.info("No users found.")