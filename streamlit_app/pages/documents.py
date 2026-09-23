import base64
from pathlib import Path

import streamlit as st

from streamlit_app.services.admin_api import AdminAPI
from streamlit_app.services.document_service import DocumentService
from streamlit_app.services.organization_service import OrganizationService
from streamlit_app.services.ui_helpers import format_error
from streamlit_app.session_auth import require_auth


st.set_page_config(page_title="Documents | KnowLayer")
require_auth()
st.title("Documents")
document_service = DocumentService()
organization_service = OrganizationService()
admin = AdminAPI()

projects = []
try:
    projects = organization_service.list_projects()
except Exception:
    st.warning("Projects are currently unavailable. Documents can still be registered without a project.")

project_options = {"Unassigned": None}
project_options.update({item["project_name"]: item["project_id"] for item in projects})

try:
    users = admin.list_users()
except Exception:
    users = []

try:
    roles = admin.list_roles()
except Exception:
    roles = []

try:
    documents = document_service.list_documents()
except Exception as error:
    st.error(
        "The document service is unavailable. "
        "Check that the FastAPI backend is running and that you are logged in."
    )
    st.caption(f"Technical detail: {error}")
    documents = []

project_name_by_id = {p["project_id"]: p["project_name"] for p in projects}
user_name_by_uid = {u["uid"]: u["name"] or u["uid"] for u in users}
role_name_by_id = {r["role_id"]: r["name"] for r in roles}
document_options = {d["document_name"]: d["document_id"] for d in documents}

with st.expander("Upload document", expanded=True):
    uploaded_file = st.file_uploader("Choose a file to provision for Q&A", type=["docx", "txt", "md", "rst"])
    if uploaded_file is not None:
        with st.form("upload-document"):
            document_id = st.text_input("Document ID", value=Path(uploaded_file.name).stem)
            document_name = st.text_input("Document name", value=uploaded_file.name)
            project_name = st.selectbox("Project", list(project_options), key="upload-project")
            submitted = st.form_submit_button("Upload and provision")
        if submitted:
            try:
                content = base64.b64encode(uploaded_file.getvalue()).decode("utf-8")
                document_service.create_document({
                    "document_id": document_id,
                    "document_name": document_name,
                    "project_id": project_options[project_name],
                    "content": content,
                })
                st.success("Document uploaded and provisioned for retrieval.")
                st.rerun()
            except Exception as error:
                st.error(str(error))

with st.expander("Register document (metadata only)"):
    with st.form("create-document"):
        document_id = st.text_input("Document ID", key="meta-doc-id")
        document_name = st.text_input("Document name", key="meta-doc-name")
        project_name = st.selectbox("Project", list(project_options), key="meta-project")
        submitted = st.form_submit_button("Register document")
    if submitted:
        try:
            document_service.create_document({
                "document_id": document_id,
                "document_name": document_name,
                "project_id": project_options[project_name],
            })
            st.success("Document registered.")
            st.rerun()
        except Exception as error:
            st.error(str(error))

# ------------------------------------------------------------ detail view

st.subheader("Document details")
if not document_options:
    st.info("No documents available.")
else:
    detail_label = st.selectbox("Document", list(document_options))
    detail_id = document_options[detail_label]
    detail = next((d for d in documents if d["document_id"] == detail_id), {})

    uploaded_by = detail.get("uploaded_by")
    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Project",
        project_name_by_id.get(detail.get("project_id"), detail.get("project_id") or "Unassigned"),
    )
    col2.metric("Uploader", user_name_by_uid.get(uploaded_by, uploaded_by or "-"))
    col3.metric("Status", detail.get("status", "-"))

    col1, col2, col3 = st.columns(3)
    col1.metric("Type", detail.get("file_type") or "-")
    col2.metric("Version", detail.get("version") or "-")
    col3.metric("Uploaded at", str(detail.get("uploaded_at") or "-")[:19])

    if detail.get("description"):
        st.caption(detail["description"])

# ------------------------------------------------- access configuration

st.subheader("Access configuration")
if not document_options:
    st.info("No documents available for access configuration.")
else:
    access_label = st.selectbox("Document", list(document_options), key="access-doc")
    access_id = document_options[access_label]

    try:
        grants = admin.list_document_access_grants(access_id)
    except Exception as error:
        st.error(format_error(error))
        grants = []
    if grants:
        grant_rows = []
        for grant in grants:
            grant_rows.append({
                "ID": grant.get("internal_id"),
                "Principal": "Role" if grant.get("principal_type") == "role" else "User",
                "Role/User": role_name_by_id.get(grant.get("role_id"), grant.get("role_id"))
                if grant.get("principal_type") == "role"
                else user_name_by_uid.get(grant.get("user_id"), grant.get("user_id")),
                "Permission": grant.get("permission"),
                "Status": grant.get("status"),
                "Granted by": user_name_by_uid.get(grant.get("granted_by_uid"), grant.get("granted_by_uid") or "-"),
            })
        st.dataframe(grant_rows, use_container_width=True)

        revoke_ids = [str(grant["internal_id"]) for grant in grants if grant.get("status") == "active"]
        if revoke_ids:
            revoke_id = st.selectbox("Grant to revoke", revoke_ids)
            if st.button("Revoke grant"):
                try:
                    admin.revoke_document_access(int(revoke_id))
                    st.success("Grant revoked.")
                    st.rerun()
                except Exception as error:
                    st.error(format_error(error))
    else:
        st.info("No access grants for this document.")

    with st.expander("Grant access"):
        principal_type = st.selectbox("Principal type", ["role", "user"])
        if principal_type == "role":
            role_names = list(role_name_by_id.values())
            role_label = st.selectbox("Role", role_names or ["No roles"])
            role_id = next((rid for rid, name in role_name_by_id.items() if name == role_label), None)
            principal_payload = {"principal_type": "role", "role_id": role_id}
        else:
            user_names = list(user_name_by_uid.values())
            user_label = st.selectbox("User", user_names or ["No users"])
            user_id = next((uid for uid, name in user_name_by_uid.items() if name == user_label), None)
            principal_payload = {"principal_type": "user", "user_id": user_id}
        permission = st.selectbox("Permission", ["read"])
        if st.button("Grant access"):
            try:
                admin.grant_document_access(access_id, {**principal_payload, "permission": permission})
                st.success("Access granted.")
                st.rerun()
            except Exception as error:
                st.error(format_error(error))

if documents:
    st.dataframe(documents, use_container_width=True)
    for document in documents:
        if st.button(f"Archive {document['document_name']}", key=f"archive-{document['document_id']}"):
            try:
                document_service.delete_document(document["document_id"])
                st.success("Document archived.")
                st.rerun()
            except Exception as error:
                st.error(str(error))
else:
    st.info("No documents found. Upload a file above to provision it for Q&A.")