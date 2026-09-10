import streamlit as st

from streamlit_app.services.organization_service import OrganizationService


st.set_page_config(page_title="Users | KnowLayer")
st.title("Users")
service = OrganizationService()

try:
    departments = service.list_departments()
    users = service.list_users()
except Exception as error:
    st.error(f"The organization service is unavailable: {error}")
    st.stop()

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
        department_options = {item["department_name"]: item["department_id"] for item in departments}
        department_name = st.selectbox("Department", list(department_options) or ["No departments"])
        submitted = st.form_submit_button("Create user")
    if submitted:
        try:
            service.create_user({
                "uid": uid,
                "name": name,
                "email": email,
                "role": role,
                "department_id": department_options[department_name],
            })
            st.success("User created.")
            st.rerun()
        except Exception as error:
            st.error(str(error))

if users:
    st.dataframe(users, use_container_width=True)
else:
    st.info("No users found.")
