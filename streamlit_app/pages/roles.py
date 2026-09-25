import streamlit as st

from streamlit_app.services.admin_api import AdminAPI
from streamlit_app.services.ui_helpers import format_error, unavailable
from streamlit_app.session_auth import require_auth

st.set_page_config(page_title="Roles | KnowLayer", page_icon="🔑")
require_auth()
st.title("Roles & Permissions")

service = AdminAPI()

try:
    permissions = service.list_permissions()
except Exception as error:
    st.error(unavailable("role service"))
    st.caption(f"Technical detail: {format_error(error)}")
    permissions = []

try:
    roles = service.list_roles()
except Exception as error:
    st.error(unavailable("role service"))
    st.caption(f"Technical detail: {format_error(error)}")
    roles = []

try:
    departments = service.list_departments()
except Exception as error:
    departments = []

permission_id_to_name = {p["permission_id"]: p["name"] for p in permissions}
role_options = {r["name"]: r["role_id"] for r in roles}
department_options = {d["department_name"]: d["department_id"] for d in departments}


def permission_checkboxes(title, selected_ids, key_prefix):
    selected = set(selected_ids)
    checked = []
    with st.container(border=True):
        st.markdown(f"**{title}**")
        cols = st.columns(2)
        for index, permission in enumerate(permissions):
            target = cols[index % 2]
            is_checked = permission["permission_id"] in selected
            value = target.checkbox(
                permission["name"],
                value=is_checked,
                key=f"{key_prefix}-perm-{permission['permission_id']}",
            )
            if value:
                checked.append(permission["permission_id"])
    return checked

# ------------------------------------------------------------------ create

with st.expander("Create role"):
    with st.form("create-role"):
        name = st.text_input("Role name")
        description = st.text_input("Description")
        scope = st.selectbox("Scope", ["global", "department"])
        department_label = st.selectbox(
            "Department (required for department-scoped roles)",
            list(department_options) or ["No departments"],
        )
        selected_permissions = permission_checkboxes(
            "Permissions",
            [],
            "create",
        )
        submitted = st.form_submit_button("Create role")
    if submitted:
        payload = {
            "name": name,
            "description": description or None,
            "scope": scope,
            "permission_ids": selected_permissions,
        }
        if scope == "department":
            payload["department_id"] = department_options.get(department_label)
        try:
            service.create_role(payload)
            st.success("Role created.")
            st.rerun()
        except Exception as error:
            st.error(format_error(error))

# ------------------------------------------------------------------ update

with st.expander("Update role"):
    if not role_options:
        st.info("No roles available to update.")
    else:
        role_label = st.selectbox("Role", list(role_options))
        role_id = role_options[role_label]
        current = next((r for r in roles if r["role_id"] == role_id), {})
        with st.form("update-role"):
            new_name = st.text_input("Role name", value=current.get("name", ""))
            new_description = st.text_input("Description", value=current.get("description") or "")
            new_scope = st.selectbox(
                "Scope",
                ["global", "department"],
                index=0 if current.get("scope", "global") == "global" else 1,
            )
            new_department = st.selectbox(
                "Department",
                list(department_options) or ["No departments"],
                index=next(
                    (i for i, name in enumerate(department_options)
                     if department_options[name] == current.get("department_id")),
                    0,
                ),
            )
            new_status = st.selectbox(
                "Status",
                ["active", "inactive"],
                index=0 if current.get("status", "active") == "active" else 1,
            )
            submitted = st.form_submit_button("Save role")
        if submitted:
            try:
                payload = {
                    "name": new_name,
                    "description": new_description or None,
                    "scope": new_scope,
                    "status": new_status,
                }
                if new_scope == "department":
                    payload["department_id"] = department_options.get(new_department)
                service.update_role(role_id, payload)
                st.success("Role updated.")
                st.rerun()
            except Exception as error:
                st.error(format_error(error))

# ----------------------------------------------------- permission assignment

st.subheader("Assign permissions to role")
if not role_options:
    st.info("No roles available for permission assignment.")
else:
    assign_role_label = st.selectbox("Role", list(role_options), key="assign-role")
    assign_role_id = role_options[assign_role_label]
    if assign_role_label == "Admin":
        st.info(
            "The system Admin role cannot be modified. Admin access is granted "
            "by role identity, so permission assignment is disabled for this role."
        )
    else:
        try:
            current_permissions = {
                p["permission_id"]
                for p in service.list_role_permissions(assign_role_id).get("permissions", [])
            }
        except Exception as error:
            st.error(format_error(error))
            current_permissions = set()

        selected = set()
        with st.form("permission-assignment"):
            selected = set(permission_checkboxes(
                "Permissions",
                current_permissions,
                f"assign-{assign_role_id}",
            ))
            submitted = st.form_submit_button("Save permissions")
        if submitted:
            try:
                service.set_role_permissions(assign_role_id, {"permission_ids": sorted(selected)})
                st.success("Permissions saved.")
                st.rerun()
            except Exception as error:
                st.error(format_error(error))

# ------------------------------------------------------------------ delete

with st.expander("Delete role"):
    if not role_options:
        st.info("No roles available to delete.")
    else:
        delete_role_label = st.selectbox("Role", list(role_options), key="delete-role")
        if st.button("Delete role"):
            try:
                service.delete_role(role_options[delete_role_label])
                st.success("Role deleted.")
                st.rerun()
            except Exception as error:
                st.error(format_error(error))

# ------------------------------------------------------------------ list

st.subheader("All roles")
if roles:
    role_rows = []
    for role in roles:
        row = dict(role)
        row["department_name"] = next(
            (d["department_name"] for d in departments if d["department_id"] == role.get("department_id")),
            role.get("department_id") or "-",
        )
        role_rows.append(row)
    st.dataframe(role_rows, use_container_width=True)
else:
    st.info("No roles found.")

st.subheader("Permission catalog")
if permissions:
    st.dataframe(permissions, use_container_width=True)
else:
    st.info("No permissions found.")