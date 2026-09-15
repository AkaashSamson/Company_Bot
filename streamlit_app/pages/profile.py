import streamlit as st

from streamlit_app.services.profile_api import ProfileAPI
from streamlit_app.services.ui_helpers import format_error


st.set_page_config(page_title="My Profile | KnowLayer")
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
    "manager_scope": "manager scope",
    "lead_or_manager": "lead or manager",
    "department": "department",
    "member": "project member",
    "grant": "project access grant",
}

st.caption("Read-only view. Only actions the backend explicitly allows are surfaced here.")

# ------------------------------------------------------------ personal info

st.subheader("Personal information")
info = {
    "Name": user.get("name"),
    "Employee ID": user.get("employee_id"),
    "Email": user.get("email"),
    "Department": department.get("department_name") or user.get("department"),
    "Role": user.get("role"),
    "Billable status": profile.get("billable_status") or "Not assigned",
}
columns = st.columns(3)
for index, (label, value) in enumerate(info.items()):
    with columns[index % len(columns)]:
        st.markdown(f"**{label}**")
        st.write(value if value is not None else "—")

# ---------------------------------------------------------------- projects

st.subheader("Current projects")
projects = profile.get("projects") or []
current_projects = [project for project in projects if project.get("is_member")]

if not current_projects:
    st.info("You are not currently assigned to any project.")

for project in current_projects:
    membership = project.get("membership") or {}
    manager = project.get("manager") or {}
    with st.expander(project.get("project_name"), expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Project ID:** {project.get('project_id')}")
            st.markdown(f"**Project manager:** {manager.get('name') or '—'}")
            st.markdown(f"**Project role:** {membership.get('membership_role') or '—'}")
        with col2:
            st.markdown(f"**Membership status:** {membership.get('status') or '—'}")
            joined = membership.get("joined_at")
            if joined:
                try:
                    joined = joined.replace("T", " ").split(".")[0] + " UTC"
                except (AttributeError, TypeError):
                    pass
                st.markdown(f"**Joined:** {joined}")
            else:
                st.markdown("**Joined:** —")
        is_current = membership.get("status") == "active"
        if is_current:
            if st.button(
                "Leave project",
                key=f"leave-{project.get('project_id')}",
                type="secondary",
                help="Leaving a project removes it from your current projects. The backend decides whether this is permitted.",
            ):
                try:
                    api.leave_project(project.get("project_id"))
                    st.success(f"You left {project.get('project_name')}.")
                    st.rerun()
                except Exception as error:
                    st.error(format_error(error))

# ------------------------------------------------------ additional access

non_member_projects = [p for p in projects if not p.get("is_member") and p.get("project_status") == "active"]
if non_member_projects:
    with st.expander("Additional project access", expanded=False):
        st.write(
            "Projects you can access that are not counted as current memberships. "
            "This is informational only and read-only."
        )
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

st.subheader("Document access")
documents = profile.get("documents") or []

if not documents:
    st.info("You do not currently have access to any documents.")

grouped = {}
for document in documents:
    key = document.get("project_name") or document.get("project_id") or "Unassigned"
    grouped.setdefault(key, []).append(document)

for project_label, items in grouped.items():
    st.markdown(f"**Project: {project_label}**")
    for document in items:
        badge = access_source_labels.get(document.get("access_source"), document.get("access_source"))
        details = []
        if document.get("version"):
            details.append(f"v{document.get('version')}")
        if document.get("file_type"):
            details.append(document.get("file_type"))
        suffix = f" ({', '.join(details)})" if details else ""
        st.markdown(f"- ☑ **{document.get('document_name')}**{suffix} — {badge}")

# ------------------------------------------------------------- permissions

st.subheader("Permissions")
roles = profile.get("roles") or []
permissions = profile.get("permissions") or []

if roles:
    st.markdown("**Role(s)**")
    for role in roles:
        scope = role.get("scope")
        if scope == "department":
            location = role.get("department_id") or "your department"
            scope_text = f"department-scoped ({location})"
        else:
            scope_text = "global"
        st.write(f"- {role.get('name')} — {scope_text}")
else:
    st.write("No role-based permissions assigned.")

st.markdown("**Effective permissions**")
if permissions:
    st.write(", ".join(permissions))
else:
    st.write("None")

grant_documents = [
    document for document in documents if document.get("access_source") == "document_grant"
]
if grant_documents:
    with st.expander("Document-specific access", expanded=False):
        st.write(
            "These documents are readable only through an explicit per-document grant, "
            "not through a project you belong to."
        )
        for document in grant_documents:
            st.write(
                f"- {document.get('document_name')} — access via direct document grant"
            )