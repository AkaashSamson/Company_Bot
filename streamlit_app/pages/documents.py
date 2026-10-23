import base64
import os
import streamlit as st

from streamlit_app.services.admin_api import AdminAPI
from streamlit_app.services.document_service import DocumentService
from streamlit_app.services.organization_service import OrganizationService
from streamlit_app.services.ui_helpers import format_error
from streamlit_app.session_auth import require_auth

st.set_page_config(page_title="Documents | KnowLayer", layout="wide")
auth = require_auth()
st.title("Documents")

user_info = auth.get("user", {}) if isinstance(auth, dict) else {}
user_role = (user_info.get("role") or "").lower()
auth_uid = auth.get("uid", "") if isinstance(auth, dict) else ""
user_permissions = auth.get("permissions", []) if isinstance(auth, dict) else []
is_manager_or_admin = (
    user_role in ("admin", "manager")
    or auth_uid == "admin"
    or "*" in user_permissions
    or any(p in user_permissions for p in ("DOCUMENT_DELETE", "DOCUMENT_MANAGE", "PROJECT_MANAGE"))
)

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
project_name_by_id = {p["project_id"]: p["project_name"] for p in projects}

try:
    users = admin.list_users()
except Exception:
    users = []

try:
    roles = admin.list_roles()
except Exception:
    roles = []

user_name_by_uid = {u["uid"]: u["name"] or u["uid"] for u in users}
role_name_by_id = {r["role_id"]: r["name"] for r in roles}

tab_library, tab_observability = st.tabs(["?? Document Library", "?? Chunk Inspector & Vector Search"])

# ==============================================================================
# TAB 1: Document Library
# ==============================================================================
with tab_library:
    with st.expander("?? Upload & Ingest New Document", expanded=False):
        uploaded_file = st.file_uploader(
            "Choose a document file",
            type=["pdf", "docx", "txt", "md", "rst"],
            key="doc_file_uploader",
        )
        if uploaded_file is not None:
            with st.form("upload-document-form"):
                document_name = st.text_input("Document Name", value=uploaded_file.name)
                project_name = st.selectbox("Project", list(project_options), key="upload-project-select")
                description = st.text_area("Description (optional)", max_chars=500)
                submitted = st.form_submit_button("Upload and Ingest", type="primary")

            if submitted:
                try:
                    content_b64 = base64.b64encode(uploaded_file.getvalue()).decode("utf-8")
                    payload = {
                        "document_name": document_name.strip() or uploaded_file.name,
                        "project_id": project_options[project_name],
                        "content": content_b64,
                        "description": description.strip() or None,
                    }
                    res = document_service.create_document(payload)
                    st.success(f"Document upload initiated (Status: {res.get('status', 'processing')}). Ingestion running in background.")
                    st.rerun()
                except Exception as error:
                    st.error(f"Upload failed: {format_error(error)}")

    # Fetch documents
    try:
        documents = document_service.list_documents()
    except Exception as error:
        st.error("The document service is unavailable. Check that FastAPI is running and you are logged in.")
        st.caption(f"Technical detail: {format_error(error)}")
        documents = []

    document_options = {d["document_name"]: d["document_id"] for d in documents}
    has_processing = any(d.get("status") == "processing" for d in documents)
    refresh_interval = int(os.getenv("DOC_INGESTION_REFRESH_INTERVAL", "5"))

    @st.fragment(run_every=refresh_interval if has_processing else None)
    def render_documents_table(docs):
        if has_processing:
            st.info(f"? Ingestion in progress. Auto-refreshing every {refresh_interval}s...")

        if not docs:
            st.info("No documents found. Upload a file above to provision it for Q&A.")
            return

        status_icons = {
            "active": "?? active",
            "processing": "? processing",
            "archived": "? archived",
            "failed": "?? failed",
        }

        # Table summary
        display_data = []
        for d in docs:
            st_val = d.get("status", "unknown")
            display_data.append({
                "Document": d.get("document_name"),
                "Project": project_name_by_id.get(d.get("project_id"), d.get("project_id") or "Unassigned"),
                "Status": status_icons.get(st_val, st_val),
                "Type": d.get("file_type") or "-",
                "Version": d.get("version") or "1.0",
                "Uploaded At": str(d.get("uploaded_at") or "-")[:19],
            })
        st.dataframe(display_data, use_container_width=True)

        st.subheader("Manage Documents")
        for doc in docs:
            d_id = doc["document_id"]
            d_name = doc["document_name"]
            st_val = doc.get("status")

            with st.container():
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                c1.write(f"**{d_name}** (`{d_id}`) - {status_icons.get(st_val, st_val)}")

                if st_val != "archived":
                    if c2.button("Archive", key=f"arch_{d_id}", help="Soft-archive: moves to archive folder, preserves vectors for chat toggle"):
                        try:
                            document_service.delete_document(d_id, permanent=False)
                            st.success(f"Archived {d_name}")
                            st.rerun()
                        except Exception as e:
                            st.error(format_error(e))

                if is_manager_or_admin:
                    if c3.button("Purge", key=f"del_{d_id}", type="secondary", help="Permanent delete: purges vectors from Chroma and unlinks file"):
                        try:
                            document_service.delete_document(d_id, permanent=True)
                            st.success(f"Permanently purged {d_name}")
                            st.rerun()
                        except Exception as e:
                            st.error(format_error(e))

    render_documents_table(documents)

    # ------------------------------------------------------------ detail view
    st.divider()
    st.subheader("Document Details")
    if document_options:
        detail_label = st.selectbox("Select document to inspect", list(document_options), key="detail-doc-select")
        detail_id = document_options[detail_label]
        detail = next((d for d in documents if d["document_id"] == detail_id), {})

        uploaded_by = detail.get("uploaded_by")
        col1, col2, col3 = st.columns(3)
        col1.metric("Project", project_name_by_id.get(detail.get("project_id"), detail.get("project_id") or "Unassigned"))
        col2.metric("Uploader", user_name_by_uid.get(uploaded_by, uploaded_by or "-"))
        col3.metric("Status", detail.get("status", "-"))

        col1, col2, col3 = st.columns(3)
        col1.metric("Type", detail.get("file_type") or "-")
        col2.metric("Version", detail.get("version") or "-")
        col3.metric("Uploaded at", str(detail.get("uploaded_at") or "-")[:19])

        if detail.get("storage_location"):
            st.caption(f"?? Storage location: `{detail.get('storage_location')}`")
        if detail.get("description"):
            st.caption(f"?? {detail['description']}")

    # ------------------------------------------------- access configuration
    st.divider()
    st.subheader("Access Configuration")
    if not document_options:
        st.info("No documents available for access configuration.")
    else:
        access_label = st.selectbox("Document", list(document_options), key="access-doc-select")
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
                revoke_id = st.selectbox("Grant to revoke", revoke_ids, key="revoke-grant-select")
                if st.button("Revoke grant"):
                    try:
                        admin.revoke_document_access(int(revoke_id))
                        st.success("Grant revoked.")
                        st.rerun()
                    except Exception as error:
                        st.error(format_error(error))
        else:
            st.info("No explicit access grants for this document.")

        with st.expander("Grant Access"):
            principal_type = st.selectbox("Principal type", ["role", "user"], key="grant-principal-type")
            if principal_type == "role":
                role_names = list(role_name_by_id.values())
                role_label = st.selectbox("Role", role_names or ["No roles"], key="grant-role-select")
                role_id = next((rid for rid, name in role_name_by_id.items() if name == role_label), None)
                principal_payload = {"principal_type": "role", "role_id": role_id}
            else:
                user_names = list(user_name_by_uid.values())
                user_label = st.selectbox("User", user_names or ["No users"], key="grant-user-select")
                user_id = next((uid for uid, name in user_name_by_uid.items() if name == user_label), None)
                principal_payload = {"principal_type": "user", "user_id": user_id}
            permission = st.selectbox("Permission", ["read"], key="grant-permission-select")
            if st.button("Grant access", key="grant-access-btn"):
                try:
                    admin.grant_document_access(access_id, {**principal_payload, "permission": permission})
                    st.success("Access granted.")
                    st.rerun()
                except Exception as error:
                    st.error(format_error(error))

# ==============================================================================
# TAB 2: Chunk Inspector & Vector Search Sandbox
# ==============================================================================
with tab_observability:
    st.header("?? Chunk Observability & Vector Search Sandbox")

    # 1. Chunk Inspector Sub-panel
    st.subheader("1. In-Page Chunk Inspector")
    st.caption("Inspect how the ingestion pipeline parsed and chunked stored documents.")

    if not document_options:
        st.info("No documents available to inspect.")
    else:
        insp_col1, insp_col2 = st.columns([3, 1])
        selected_insp_label = insp_col1.selectbox("Select document to inspect chunks", list(document_options), key="chunk-doc-select")
        selected_insp_id = document_options[selected_insp_label]

        if selected_insp_id:
            try:
                chunks = document_service.get_chunks(selected_insp_id)
                st.write(f"**Total chunks in ChromaDB:** `{len(chunks)}`")
                if chunks:
                    for chunk in chunks:
                        idx = chunk.get("index", 0)
                        text = chunk.get("text", "")
                        meta = chunk.get("metadata", {})
                        heading = meta.get("section_heading") or meta.get("hierarchy_path") or "General"

                        with st.expander(f"Chunk #{idx} | {heading} ({len(text)} chars)"):
                            st.code(text, language="text")
                            st.json(meta)
                else:
                    st.warning("No chunks found in vector store for this document.")
            except Exception as e:
                st.error(f"Failed to load chunks: {format_error(e)}")

    st.divider()

    # 2. Vector Search Sandbox Sub-panel
    st.subheader("2. Vector Search Sandbox")
    st.caption("Simulate how user questions retrieve chunk candidates across active projects.")

    with st.form("vector-search-sandbox-form"):
        search_query = st.text_input("Test Query", placeholder="e.g. travel reimbursement policy or API keys")
        s_col1, s_col2, s_col3 = st.columns([2, 1, 1])

        search_project = s_col1.selectbox("Filter Project Scope", ["All Projects"] + [p["project_name"] for p in projects])
        top_k = s_col2.slider("Top K Results", min_value=1, max_value=10, value=4)
        include_archived = s_col3.checkbox("Include Archived", value=False)

        search_btn = st.form_submit_button("Run Vector Search", type="primary")

    if search_btn and search_query.strip():
        chosen_project_id = None
        if search_project != "All Projects":
            chosen_project_id = next((p["project_id"] for p in projects if p["project_name"] == search_project), None)

        search_payload = {
            "query": search_query.strip(),
            "project_id": chosen_project_id,
            "top_k": top_k,
            "include_archived": include_archived,
        }

        try:
            results = document_service.search_chunks(search_payload)
            if not results:
                st.info("No matching chunks retrieved for this query.")
            else:
                st.success(f"Retrieved {len(results)} chunks ranked by similarity score:")
                for rank, res in enumerate(results, start=1):
                    c_id = res.get("id", f"chunk-{rank}")
                    score = res.get("score", 0.0)
                    dist = res.get("distance")
                    text = res.get("text", "")
                    meta = res.get("metadata", {})
                    doc_id_val = meta.get("document_id", "Unknown Doc")
                    status_val = meta.get("status", "active")

                    with st.container():
                        st.markdown(f"### Rank #{rank} | Score: `{score:.4f}` (Dist: `{dist}`) | Doc: `{doc_id_val}` [{status_val}]")
                        st.code(text, language="text")
                        with st.expander(f"Chunk metadata ({c_id})"):
                            st.json(meta)
                        st.divider()
        except Exception as error:
            st.error(f"Search failed: {format_error(error)}")
