import streamlit as st

from streamlit_app.services.admin_api import AdminAPI
from streamlit_app.services.organization_service import OrganizationService
from streamlit_app.services.ui_helpers import format_error
from streamlit_app.session_auth import require_auth


st.set_page_config(page_title="Projects | KnowLayer")
require_auth()
st.title("Projects")
service = OrganizationService()
admin = AdminAPI()

departments = []
users = []
try:
    departments = service.list_departments()
except Exception:
    st.warning("Departments are currently unavailable. Creating a project is disabled.")

try:
    users = service.list_users()
except Exception:
    st.warning("Users are currently unavailable. Membership management is disabled.")

try:
    projects = service.list_projects()
except Exception as error:
    st.error(
        "The project service is unavailable. "
        "Check that the FastAPI backend is running and that you are logged in."
    )
    st.caption(f"Technical detail: {error}")
    projects = []

department_name_by_id = {d["department_id"]: d["department_name"] for d in departments}
user_name_by_uid = {u["uid"]: u["name"] or u["uid"] for u in users}
department_options = {d["department_name"]: d["department_id"] for d in departments}
user_options = {u["name"] or u["uid"]: u["uid"] for u in users}
project_options = {p["project_name"]: p["project_id"] for p in projects}

PROJECT_STATUSES = ["active", "inactive", "completed", "archived"]

with st.expander("Add project"):
    with st.form("create-project"):
        project_id = st.text_input("Project ID")
        project_name = st.text_input("Project name")
        department_name = st.selectbox("Department", list(department_options) or ["No departments"])
        submitted = st.form_submit_button("Create project")
    if submitted:
        try:
            service.create_project({
                "project_id": project_id,
                "project_name": project_name,
                "department_id": department_options[department_name],
            })
            st.success("Project created.")
            st.rerun()
        except Exception as error:
            st.error(str(error))

with st.expander("Manage membership"):
    project_name = st.selectbox("Project", list(project_options) or ["No projects"])
    user_name = st.selectbox("User", list(user_options) or ["No users"])
    col_assign, col_revoke = st.columns(2)
    with col_assign:
        if st.button("Assign user"):
            try:
                service.assign_member(project_options[project_name], user_options[user_name])
                st.success("Membership assigned.")
            except Exception as error:
                st.error(str(error))
    with col_revoke:
        if st.button("Revoke user"):
            try:
                service.revoke_member(project_options[project_name], user_options[user_name])
                st.success("Membership revoked.")
            except Exception as error:
                st.error(str(error))

# ------------------------------------------------------------ project view

st.subheader("Project details")
if not project_options:
    st.info("No projects available.")
else:
    detail_label = st.selectbox("Project", list(project_options), key="detail-project")
    detail_id = project_options[detail_label]
    detail = next((p for p in projects if p["project_id"] == detail_id), {})
    manager_uid = detail.get("manager_uid")

    col1, col2, col3 = st.columns(3)
    col1.metric("Status", detail.get("status", "-"))
    col2.metric(
        "Department",
        department_name_by_id.get(detail.get("department_id"), detail.get("department_id") or "-"),
    )
    col3.metric(
        "Manager",
        user_name_by_uid.get(manager_uid, manager_uid or "-"),
    )
    if detail.get("description"):
        st.caption(detail["description"])
    if detail.get("start_date") or detail.get("end_date"):
        st.caption(
            f"Duration: {detail.get('start_date') or '?'} to {detail.get('end_date') or '?'}"
        )

    member_col, document_col = st.columns(2)
    with member_col:
        st.markdown("**Members**")
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
            st.dataframe(member_rows, use_container_width=True, height=240)
        else:
            st.write("No members.")
    with document_col:
        st.markdown("**Documents**")
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
                height=240,
            )
        else:
            st.write("No documents.")

# ------------------------------------------------------------ update

with st.expander("Update project"):
    if not project_options:
        st.info("No projects available to update.")
    else:
        update_label = st.selectbox("Project", list(project_options), key="update-project")
        update_id = project_options[update_label]
        current = next((p for p in projects if p["project_id"] == update_id), {})
        manager_names = list(user_options)
        manager_index = next(
            (i for i, name in enumerate(manager_names) if user_options[name] == current.get("manager_uid")),
            0,
        )
        with st.form("update-project"):
            new_name = st.text_input("Project name", value=current.get("project_name", ""))
            new_description = st.text_input("Description", value=current.get("description") or "")
            new_manager = st.selectbox("Manager", manager_names or ["Unassigned"], index=manager_index)
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
            submitted = st.form_submit_button("Save project")
        if submitted:
            try:
                payload = {"status": new_status}
                if new_name:
                    payload["project_name"] = new_name
                if new_description:
                    payload["description"] = new_description
                if new_department in department_options:
                    payload["department_id"] = department_options[new_department]
                if new_manager in user_options:
                    payload["manager_uid"] = user_options[new_manager]
                admin.update_project(update_id, payload)
                st.success("Project updated.")
                st.rerun()
            except Exception as error:
                st.error(format_error(error))

if projects:
    st.dataframe(projects, use_container_width=True)
else:
    st.info("No projects found. Use the form above to create a project.")