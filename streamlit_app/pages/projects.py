import streamlit as st

from streamlit_app.services.organization_service import OrganizationService


st.set_page_config(page_title="Projects | KnowLayer")
st.title("Projects")
service = OrganizationService()

try:
    departments = service.list_departments()
    users = service.list_users()
    projects = service.list_projects()
except Exception as error:
    st.error(f"The organization service is unavailable: {error}")
    st.stop()

with st.expander("Add project"):
    with st.form("create-project"):
        project_id = st.text_input("Project ID")
        project_name = st.text_input("Project name")
        department_options = {item["department_name"]: item["department_id"] for item in departments}
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
    project_options = {item["project_name"]: item["project_id"] for item in projects}
    user_options = {item["name"]: item["uid"] for item in users}
    selected_project = st.selectbox("Project", list(project_options) or ["No projects"])
    selected_user = st.selectbox("User", list(user_options) or ["No users"])
    col_assign, col_revoke = st.columns(2)
    with col_assign:
        if st.button("Assign user"):
            try:
                service.assign_member(project_options[selected_project], user_options[selected_user])
                st.success("Membership assigned.")
            except Exception as error:
                st.error(str(error))
    with col_revoke:
        if st.button("Revoke user"):
            try:
                service.revoke_member(project_options[selected_project], user_options[selected_user])
                st.success("Membership revoked.")
            except Exception as error:
                st.error(str(error))

if projects:
    st.dataframe(projects, use_container_width=True)
else:
    st.info("No projects found.")
