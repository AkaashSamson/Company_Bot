import streamlit as st

from streamlit_app.services.admin_api import AdminAPI
from streamlit_app.services.ui_helpers import format_error, unavailable
from streamlit_app.session_auth import require_auth

st.set_page_config(page_title="Departments | KnowLayer", page_icon="🏢", layout="wide")
auth = require_auth()
st.title("Departments")

permissions = set(auth.get("permissions", []) if isinstance(auth, dict) else [])
user_info = auth.get("user", {}) if isinstance(auth, dict) else {}
user_role = (user_info.get("role") or "").lower()
auth_uid = auth.get("uid", "") if isinstance(auth, dict) else ""
is_admin = user_role == "admin" or auth_uid == "admin" or "*" in permissions or "ADMIN" in permissions

# Write Implies Read
can_view = is_admin or any(p.startswith("DEPARTMENT_") for p in permissions)
if not can_view:
    st.warning("You do not have permission to view departments.")
    st.stop()

can_create = is_admin or "DEPARTMENT_CREATE" in permissions
can_update = is_admin or "DEPARTMENT_UPDATE" in permissions
can_assign = is_admin or "DEPARTMENT_ASSIGN_USERS" in permissions

service = AdminAPI()

try:
    departments = service.list_departments()
except Exception as error:
    st.error(unavailable("department service"))
    st.caption(f"Technical detail: {format_error(error)}")
    departments = []

try:
    users = service.list_users()
except Exception as error:
    st.error(unavailable("user service"))
    st.caption(f"Technical detail: {format_error(error)}")
    users = []

BILLABLE_POLICIES = ["billable", "non-billable", "both"]
BILLABLE_STATUSES = ["", "billable", "non-billable"]

department_options = {d["department_name"]: d["department_id"] for d in departments}
user_options = {u["name"] or u["uid"]: u["uid"] for u in users}

# ------------------------------------------------------------------ create
if can_create:
    with st.expander("Create Department", expanded=False):
        with st.form("create-department"):
            department_name = st.text_input("Department name *")
            description = st.text_area("Description")
            default_billable = st.selectbox("Default billable policy", BILLABLE_POLICIES)
            submitted = st.form_submit_button("Create department", type="primary")
        if submitted:
            if not department_name.strip():
                st.error("Department name is required.")
            else:
                try:
                    service.create_department({
                        "department_name": department_name.strip(),
                        "description": description.strip() or None,
                        "default_billable": default_billable,
                    })
                    st.success("Department created successfully.")
                    st.rerun()
                except Exception as error:
                    st.error(format_error(error))

# ------------------------------------------------------------------ update
if can_update and department_options:
    with st.expander("Update Department", expanded=False):
        selected_label = st.selectbox("Select Department", list(department_options), key="update-dept-select")
        department_id = department_options[selected_label]
        current = next((d for d in departments if d["department_id"] == department_id), {})
        with st.form("update-department"):
            new_name = st.text_input("Department name", value=current.get("department_name", ""))
            new_description = st.text_area("Description", value=current.get("description") or "")
            new_billable = st.selectbox(
                "Default billable policy",
                BILLABLE_POLICIES,
                index=BILLABLE_POLICIES.index(current.get("default_billable", "billable"))
                if current.get("default_billable") in BILLABLE_POLICIES
                else 0,
            )
            new_status = st.selectbox(
                "Status",
                ["active", "inactive"],
                index=0 if current.get("status", "active") == "active" else 1,
            )
            submitted = st.form_submit_button("Save changes", type="primary")
        if submitted:
            try:
                service.update_department(department_id, {
                    "department_name": new_name,
                    "description": new_description or None,
                    "default_billable": new_billable,
                    "status": new_status,
                })
                st.success("Department updated.")
                st.rerun()
            except Exception as error:
                st.error(format_error(error))

# ------------------------------------------------------------------ assign
if can_assign and department_options and user_options:
    with st.expander("Assign Employee to Department", expanded=False):
        dept_label = st.selectbox("Department", list(department_options), key="assign-dept")
        user_label = st.selectbox("User", list(user_options), key="assign-user")
        membership_role = st.text_input("Membership role", value="Member")
        billable = st.selectbox("Billable status", ["Unset (department default)", "billable", "non-billable"])
        billable_value = None if billable.startswith("Unset") else billable
        if st.button("Assign employee", key="assign-emp-btn"):
            try:
                service.assign_department_member(department_options[dept_label], {
                    "user_id": user_options[user_label],
                    "membership_role": membership_role,
                    "billable_status": billable_value,
                })
                st.success("Employee assigned to department.")
                st.rerun()
            except Exception as error:
                st.error(format_error(error))

# ------------------------------------------------------------------ members view
st.divider()
st.subheader("Department Members")
if not department_options:
    st.info("No departments available.")
else:
    member_dept_label = st.selectbox("Select Department to inspect", list(department_options), key="members-dept")
    member_dept_id = department_options[member_dept_label]
    try:
        members = service.list_department_members(member_dept_id)
    except Exception as error:
        st.error(format_error(error))
        members = []
    if members:
        member_rows = []
        uid_to_name = {u["uid"]: u["name"] or u["uid"] for u in users}
        for member in members:
            row = dict(member)
            row["name"] = uid_to_name.get(member["user_id"], member["user_id"])
            member_rows.append(row)
        st.dataframe(member_rows, use_container_width=True)

        if can_assign:
            with st.expander("Update / Remove Member"):
                member_id_label = st.selectbox(
                    "Member",
                    [f"{m['user_id']} ({uid_to_name.get(m['user_id'], '')})" for m in members],
                    key="member-edit-select",
                )
                selected_member = next(m for m in members if member_id_label.startswith(m["user_id"] + " "))
                col1, col2, col3 = st.columns(3)
                with col1:
                    new_billable = st.selectbox(
                        "Billable status",
                        BILLABLE_STATUSES,
                        index=BILLABLE_STATUSES.index(selected_member.get("billable_status") or "")
                        if selected_member.get("billable_status") in BILLABLE_STATUSES
                        else 0,
                    )
                with col2:
                    new_role = st.text_input("Membership role", value=selected_member.get("membership_role") or "Member")
                with col3:
                    new_status = st.selectbox(
                        "Status",
                        ["", "active", "inactive"],
                        index=["", "active", "inactive"].index(selected_member.get("status") or "active"),
                    )
                col_save, col_rem = st.columns(2)
                with col_save:
                    if st.button("Save member changes"):
                        payload = {}
                        if new_billable:
                            payload["billable_status"] = new_billable
                        if new_role:
                            payload["membership_role"] = new_role
                        if new_status:
                            payload["status"] = new_status
                        try:
                            service.update_department_member(member_dept_id, selected_member["user_id"], payload)
                            st.success("Member updated.")
                            st.rerun()
                        except Exception as error:
                            st.error(format_error(error))
                with col_rem:
                    if st.button("Remove from department"):
                        try:
                            service.remove_department_member(member_dept_id, selected_member["user_id"])
                            st.success("Member removed.")
                            st.rerun()
                        except Exception as error:
                            st.error(format_error(error))
    else:
        st.info("No members in this department yet.")

# ------------------------------------------------------------------ list
st.divider()
st.subheader("All Departments")
if departments:
    st.dataframe(departments, use_container_width=True)
else:
    st.info("No departments found.")
