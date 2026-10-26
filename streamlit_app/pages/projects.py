import streamlit as st

from streamlit_app.services.admin_api import AdminAPI
from streamlit_app.services.organization_service import OrganizationService
from streamlit_app.services.ui_helpers import format_error
from streamlit_app.session_auth import require_auth

st.set_page_config(page_title="Projects | KnowLayer", layout="wide")
auth = require_auth()
st.title("Projects")

auth_uid = auth.get("uid", "") if isinstance(auth, dict) else ""
user_info = auth.get("user", {}) if isinstance(auth, dict) else {}
user_role = (user_info.get("role") or "").lower()
permissions = auth.get("permissions", []) if isinstance(auth, dict) else []

can_manage = (
    user_role in ("admin", "manager")
    or auth_uid == "admin"
    or "*" in permissions
    or any(p in permissions for p in ("PROJECT_CREATE", "PROJECT_UPDATE", "PROJECT_DELETE", "PROJECT_MANAGE"))
)

service = OrganizationService()
admin = AdminAPI()

departments = []
users = []
projects = []

try:
    departments = service.list_departments()
except Exception:
    st.warning("Departments are currently unavailable.")

try:
    users = service.list_users()
except Exception:
    st.warning("Users are currently unavailable.")

try:
    projects = service.list_projects()
except Exception as error:
    st.error("The project service is unavailable. Check that FastAPI is running and you are logged in.")
    st.caption(f"Technical detail: {format_error(error)}")
    projects = []

department_name_by_id = {d["department_id"]: d["department_name"] for d in departments}
user_name_by_uid = {u["uid"]: u["name"] or u["uid"] for u in users}
department_options = {d["department_name"]: d["department_id"] for d in departments}
user_options = {u["name"] or u["uid"]: u["uid"] for u in users}
project_options = {p["project_name"]: p["project_id"] for p in projects}

PROJECT_STATUSES = ["active", "inactive", "completed", "archived"]

# Fetch user's project memberships for "My Projects"
user_memberships = []
if auth_uid:
    try:
        user_memberships = admin.list_user_memberships(auth_uid)
    except Exception:
        user_memberships = []

user_project_ids = {m["project_id"] for m in user_memberships if m.get("status") == "active"}
# User is also in project if they are the manager
for p in projects:
    if p.get("manager_uid") == auth_uid:
        user_project_ids.add(p["project_id"])

# ==============================================================================
# SECTION 1: My Projects
# ==============================================================================
st.header("My Projects")
my_projects = [p for p in projects if p["project_id"] in user_project_ids]

if not my_projects:
    st.info("You are not currently assigned to any projects.")
else:
    for proj in my_projects:
        p_id = proj["project_id"]
        p_name = proj["project_name"]
        dept_name = department_name_by_id.get(proj.get("department_id"), proj.get("department_id") or "Unassigned")
        mgr_uid = proj.get("manager_uid")
        mgr_name = user_name_by_uid.get(mgr_uid, mgr_uid or "Unassigned")
        st_val = proj.get("status", "active")
        is_manager = (mgr_uid == auth_uid)

        with st.container():
            col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 1, 2])
            col1.write(f"**{p_name}** (`{p_id}`)")
            col2.write(f"Department: {dept_name}" if dept_name else "No department")
            col3.write(f"Manager: {mgr_name}")
            col4.write(f"`{st_val}`")

            if is_manager:
                col5.caption("Manager (Transfer before leaving)")
            else:
                if col5.button("Leave Project", key=f"leave_{p_id}", help="Leave this project"):
                    try:
                        service.leave_project(p_id)
                        st.success(f"Left project {p_name}.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed to leave: {format_error(exc)}")
            st.divider()

# ==============================================================================
# SECTION 2: Project Details & Explorer
# ==============================================================================
st.header("Project Details & Explorer")
if not project_options:
    st.info("No projects available.")
else:
    detail_label = st.selectbox("Select Project", list(project_options), key="detail-project-select")
    detail_id = project_options[detail_label]
    detail = next((p for p in projects if p["project_id"] == detail_id), {})
    manager_uid = detail.get("manager_uid")

    col1, col2, col3 = st.columns(3)
    col1.metric("Status", detail.get("status", "-"))
    col2.metric("Department", department_name_by_id.get(detail.get("department_id"), detail.get("department_id") or "-"))
    col3.metric("Manager", user_name_by_uid.get(manager_uid, manager_uid or "Unassigned"))

    if detail.get("description"):
        st.caption(detail['description'])

    member_col, document_col = st.columns(2)
    with member_col:
        st.markdown("**Project Members**")
        try:
            members = admin.list_project_members(detail_id)
        except Exception as error:
            st.error(format_error(error))
            members = []
        if members:
            member_rows = []
            for member in members:
                row = dict(member)
                row["name"] = user_name_by_uid.get(member["uid"], member["uid"])
                member_rows.append(row)
            st.dataframe(member_rows, use_container_width=True, height=220)
        else:
            st.write("No members assigned.")

    with document_col:
        st.markdown("**Project Documents**")
        try:
            project_documents = admin.list_project_documents(detail_id)
        except Exception as error:
            st.error(format_error(error))
            project_documents = []
        if project_documents:
            st.dataframe(
                [
                    {
                        "ID": doc.get("document_id"),
                        "Name": doc.get("document_name"),
                        "Type": doc.get("file_type") or "-",
                        "Version": doc.get("version") or "-",
                        "Status": doc.get("status"),
                    }
                    for doc in project_documents
                ],
                use_container_width=True,
                height=220,
            )
        else:
            st.write("No documents in this project.")

# ==============================================================================
# SECTION 3: Project Administration (Gated)
# ==============================================================================
if can_manage:
    st.divider()
    st.header("Project Administration")

    with st.expander("Create New Project", expanded=False):
        with st.form("create-project-form"):
            new_prj_id = st.text_input("Project ID (optional, auto-generated if blank)")
            new_prj_name = st.text_input("Project Name *")
            new_prj_dept = st.selectbox("Department *", list(department_options) or ["No departments"], key="create-prj-dept")
            new_prj_mgr = st.selectbox("Manager", ["Unassigned"] + list(user_options), key="create-prj-mgr")
            new_prj_desc = st.text_area("Description (optional)")
            submitted = st.form_submit_button("Create Project", type="primary")

        if submitted:
            if not new_prj_name.strip():
                st.error("Project Name is required.")
            else:
                try:
                    payload = {
                        "project_name": new_prj_name.strip(),
                        "department_id": department_options.get(new_prj_dept),
                        "description": new_prj_desc.strip() or None,
                    }
                    if new_prj_id.strip():
                        payload["project_id"] = new_prj_id.strip()
                    if new_prj_mgr != "Unassigned":
                        payload["manager_uid"] = user_options.get(new_prj_mgr)

                    service.create_project(payload)
                    st.success("Project created successfully.")
                    st.rerun()
                except Exception as error:
                    st.error(f"Failed to create project: {format_error(error)}")

    with st.expander("Manage Project Membership", expanded=False):
        sel_proj_name = st.selectbox("Project", list(project_options) or ["No projects"], key="mem-proj-select")
        sel_user_name = st.selectbox("User", list(user_options) or ["No users"], key="mem-user-select")
        col_assign, col_revoke = st.columns(2)

        with col_assign:
            if st.button("Assign Member", key="assign-mem-btn"):
                try:
                    service.assign_member(project_options[sel_proj_name], user_options[sel_user_name])
                    st.success("Member assigned successfully.")
                    st.rerun()
                except Exception as error:
                    st.error(format_error(error))

        with col_revoke:
            if st.button("Revoke Member", key="revoke-mem-btn"):
                try:
                    service.revoke_member(project_options[sel_proj_name], user_options[sel_user_name])
                    st.success("Membership revoked.")
                    st.rerun()
                except Exception as error:
                    st.error(format_error(error))

    with st.expander("Update Project", expanded=False):
        if not project_options:
            st.info("No projects available to update.")
        else:
            update_label = st.selectbox("Project to Update", list(project_options), key="update-project-select")
            update_id = project_options[update_label]
            current = next((p for p in projects if p["project_id"] == update_id), {})

            manager_names = list(user_options)
            manager_index = next(
                (i + 1 for i, name in enumerate(manager_names) if user_options[name] == current.get("manager_uid")),
                0,
            )
            with st.form("update-project-form"):
                new_name = st.text_input("Project Name", value=current.get("project_name", ""))
                new_description = st.text_area("Description", value=current.get("description") or "")
                new_manager = st.selectbox("Manager", ["Unassigned"] + manager_names, index=manager_index)
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
                    PROJECT_STATUSES,
                    index=PROJECT_STATUSES.index(current.get("status"))
                    if current.get("status") in PROJECT_STATUSES
                    else 0,
                )
                update_submitted = st.form_submit_button("Save Changes", type="primary")

            if update_submitted:
                try:
                    payload = {"status": new_status}
                    if new_name:
                        payload["project_name"] = new_name
                    payload["description"] = new_description
                    if new_department in department_options:
                        payload["department_id"] = department_options[new_department]
                    payload["manager_uid"] = user_options.get(new_manager) if new_manager != "Unassigned" else None

                    admin.update_project(update_id, payload)
                    st.success("Project updated successfully.")
                    st.rerun()
                except Exception as error:
                    st.error(format_error(error))
