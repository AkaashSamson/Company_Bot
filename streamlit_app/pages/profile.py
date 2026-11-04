import streamlit as st

from streamlit_app.services.authentication_service import AuthenticationService
from streamlit_app.services.profile_api import ProfileAPI
from streamlit_app.services.ui_helpers import format_error
from streamlit_app.session_auth import require_auth

st.set_page_config(page_title="My Profile | KnowLayer", page_icon="👤", layout="wide")
auth = require_auth()
st.title("My Profile")

api = ProfileAPI()

try:
    profile = api.profile()
except Exception as error:
    st.error(
        "The profile service is unavailable. "
        "Check that the FastAPI backend is running at http://127.0.0.1:8000 and that you are logged in."
    )
    st.caption(f"Technical detail: {format_error(error)}")
    st.stop()

user = profile.get("user", {})
department = profile.get("department") or {}
access_source_labels = {
    "document_grant": "direct document grant",
    "project_access": "via project access",
    "org_wide": "org-wide (unassigned) document",
    "lead_or_manager": "lead or manager",
    "department": "department",
    "member": "project member",
    "grant": "project access grant",
}

# ------------------------------------------------------------ personal info
st.subheader("Personal Information")
with st.container(border=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**Full Name:** {user.get('name') or '—'}")
        st.markdown(f"**Username:** `{user.get('username') or user.get('uid') or '—'}`")
        st.markdown(f"**Employee ID:** `{user.get('employee_id') or '—'}`")
    with col2:
        st.markdown(f"**Email:** {user.get('email') or '—'}")
        st.markdown(f"**Department:** {department.get('department_name') or user.get('department') or '—'}")
        st.markdown(f"**Job Title:** {user.get('job_title') or '—'}")
    with col3:
        st.markdown(f"**Role:** `{user.get('role') or '—'}`")
        st.markdown(f"**Account Status:** `{user.get('status', 'active')}`")
        st.markdown(f"**Billable Status:** {profile.get('billable_status') or 'Not assigned'}")

# ------------------------------------------------------------- roles & permissions
st.subheader("Assigned Roles & Permissions")
roles = profile.get("roles") or []
permissions = profile.get("permissions") or []

with st.container(border=True):
    if roles:
        role_badges = []
        for r in roles:
            scope = r.get("scope", "global")
            loc = f" ({r.get('department_id')})" if scope == "department" and r.get("department_id") else ""
            role_badges.append(f"`{r.get('name')}` *({scope}{loc})*")
        st.markdown("**Roles:** " + " · ".join(role_badges))
    else:
        st.markdown(f"**Roles:** `{user.get('role', 'User')}` *(system default)*")

    with st.expander(f"Active Permissions ({len(permissions)})", expanded=False):
        if permissions:
            st.markdown(" ".join([f"`{p}`" for p in sorted(permissions)]))
        else:
            st.caption("No explicit permissions assigned.")

# ------------------------------------------------------------ security / password
st.subheader("Security & Password")
with st.expander("🔑 Change Password", expanded=False):
    with st.form("change-password-form"):
        current_password = st.text_input("Current password", type="password")
        new_password = st.text_input("New password", type="password", help="Minimum 8 characters.")
        confirm_password = st.text_input("Confirm new password", type="password")
        change_submitted = st.form_submit_button("Update Password", type="primary")

    if change_submitted:
        if not current_password:
            st.error("Current password is required.")
        elif not new_password:
            st.error("New password is required.")
        elif len(new_password) < 8:
            st.error("New password must be at least 8 characters long.")
        elif new_password != confirm_password:
            st.error("New password and confirmation do not match.")
        else:
            try:
                token = auth.get("access_token") if isinstance(auth, dict) else None
                if not token:
                    st.error("Active session token not found. Please log in again.")
                else:
                    AuthenticationService().change_password(
                        token=token,
                        current_password=current_password,
                        new_password=new_password,
                    )
                    st.success("Password changed successfully!")
            except Exception as error:
                st.error(format_error(error))

# ---------------------------------------------------------------- projects
st.subheader("Project Memberships")
projects = profile.get("projects") or []
current_projects = [project for project in projects if project.get("is_member")]

if not current_projects:
    st.info("You are not currently assigned to any project.")
else:
    project_rows = []
    for project in current_projects:
        membership = project.get("membership") or {}
        manager = project.get("manager") or {}
        project_rows.append({
            "Project ID": project.get("project_id"),
            "Project Name": project.get("project_name"),
            "Role": membership.get("membership_role") or "Member",
            "Manager": manager.get("name") or "—",
            "Status": membership.get("status") or "active",
        })
    st.dataframe(project_rows, use_container_width=True)

non_member_projects = [p for p in projects if not p.get("is_member") and p.get("project_status") == "active"]
if non_member_projects:
    with st.expander("Additional Project Access", expanded=False):
        st.dataframe(
            [
                {
                    "Project": item.get("project_name"),
                    "Access via": access_source_labels.get(item.get("access_source"), item.get("access_source")),
                }
                for item in non_member_projects
            ],
            use_container_width=True,
        )

# ------------------------------------------------------- document access
st.subheader("Accessible Documents")
documents = profile.get("documents") or []

if not documents:
    st.info("You do not currently have access to any documents.")
else:
    doc_rows = []
    for document in documents:
        doc_rows.append({
            "Document Name": document.get("document_name"),
            "Project": document.get("project_name") or "General / Unassigned",
            "Version": f"v{document.get('version')}" if document.get("version") else "—",
            "File Type": document.get("file_type") or "—",
            "Access Source": access_source_labels.get(document.get("access_source"), document.get("access_source")),
        })
    st.dataframe(doc_rows, use_container_width=True)
