import streamlit as st

from streamlit_app.services.explorer_api import ExplorerAPI
from streamlit_app.services.ui_helpers import format_error


st.set_page_config(page_title="Organization Explorer | KnowLayer")
st.title("Organization Explorer")

access_labels = {
    "document_grant": "available through a direct document grant",
    "project_access": "available through project access",
    "manager_scope": "available in manager scope",
}


def _person(person):
    if not person:
        return "—"
    return person.get("name") or person.get("uid")


def _date(value):
    if not value:
        return "—"
    try:
        return str(value).replace("T", " ").split(".")[0] + " UTC"
    except (AttributeError, TypeError):
        return value


def _render_document(document):
    details = [
        f"**Document ID:** {document.get('document_id')}",
        f"**Type:** {document.get('file_type') or '—'}",
        f"**Version:** {document.get('version') or '—'}",
        f"**Uploaded by:** {_person(document.get('uploaded_by'))}",
        f"**Upload date:** {_date(document.get('uploaded_at'))}",
    ]
    access = document.get("access")
    details.append(f"**Access:** {access_labels.get(access, access)}")
    if access == "document_grant":
        if document.get("granted_by"):
            details.append(f"**Granted by:** {_person(document.get('granted_by'))}")
        if document.get("granted_at"):
            details.append(f"**Granted on:** {_date(document.get('granted_at'))}")

    with st.expander(document.get("document_name"), expanded=False):
        for line in details:
            st.markdown(line)
        description = document.get("description")
        if description:
            st.markdown("**Description**")
            st.write(description)
        else:
            st.markdown("**Description:** —")


def _render_project(project, expand_all):
    members_count = len(project.get("members") or [])
    label = project.get("project_name")
    with st.container(border=True):
        st.markdown(f"### {label}")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"**Project ID:** {project.get('project_id')}")
            st.markdown(f"**Status:** {project.get('status')}")
        with col2:
            st.markdown(f"**Department:** {project.get('department_name')}")
            st.markdown(f"**Manager:** {_person(project.get('manager'))}")
        with col3:
            st.markdown(f"**Members:** {members_count}")
        if project.get("description"):
            st.write(project.get("description"))

        if project.get("members_visible"):
            members = project.get("members") or []
            if members:
                with st.expander("Project members", expanded=expand_all):
                    st.dataframe(
                        [
                            {
                                "Name": member.get("name") or member.get("uid"),
                                "Role": member.get("membership_role"),
                                "Status": member.get("status"),
                                "Joined": _date(member.get("joined_at")),
                            }
                            for member in members
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )
            else:
                st.caption("No active members to display.")
        else:
            st.caption("Member details are available to the project manager, project lead, or department manager only.")

        documents = project.get("documents") or []
        if documents:
            with st.expander(f"Project documents ({len(documents)})", expanded=expand_all):
                for document in documents:
                    _render_document(document)
        else:
            st.caption("No documents available in your view of this project.")


api = ExplorerAPI()

try:
    with st.spinner("Loading organization..."):
        organization = api.organization()
except Exception as error:
    st.error(
        "The organization explorer service is unavailable. "
        "Check that the FastAPI backend is running at http://127.0.0.1:8000 and that you are logged in."
    )
    st.caption(f"Technical detail: {format_error(error)}")
    st.stop()

st.caption("Read-only, authorization-scoped view. Only information you are authorized to see is shown.")

expand_all = st.checkbox("Expand all sections", value=False)

departments = organization.get("departments") or []
unassigned = organization.get("unassigned_documents") or []
additional = organization.get("additional_documents") or []

if not departments and not unassigned and not additional:
    st.info("You do not currently have access to any departments or documents.")
    st.stop()

for department in departments:
    with st.expander(f"Department: {department.get('department_name')}", expanded=expand_all):
        st.caption(f"Department ID: {department.get('department_id')}")
        for project in department.get("projects") or []:
            _render_project(project, expand_all)

if unassigned or additional:
    st.subheader("Additional documents")
    if unassigned:
        with st.expander("Unassigned documents", expanded=expand_all):
            for document in unassigned:
                _render_document(document)
    if additional:
        with st.expander("Documents accessible by direct grant", expanded=expand_all):
            st.write(
                "Documents you can read through an explicit grant that are attached to "
                "projects outside your current scope."
            )
            for document in additional:
                _render_document(document)