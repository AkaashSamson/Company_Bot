import streamlit as st

from streamlit_app.auth import identity_headers, logout, render_login
from streamlit_app.services.auth_service import AuthError, AuthService
from streamlit_app.services.document_service import DocumentService, DocumentUploadError

st.set_page_config(page_title="Upload Document", page_icon="📄")

user = render_login()
if user is None:
    st.stop()

col_title, col_logout = st.columns([5, 1])
with col_title:
    st.title("📄 Upload a New Document")
with col_logout:
    if st.button("Logout", use_container_width=False):
        logout()

st.caption(
    "Upload a document to add it to the knowledge base. The file goes through the "
    "same processing pipeline used for the existing Nexora handbook before the "
    "chatbot can answer from it. Only the roles and employees you select below "
    "(plus yourself) will be able to ask questions answered from this document."
)

if "uploaded_document" not in st.session_state:
    st.session_state.uploaded_document = None

back = st.button("⬅ Back to chat", use_container_width=False)
if back:
    st.switch_page("app.py")

headers = identity_headers()

roles = []
employees = []
with st.spinner("Loading roles and employees..."):
    try:
        roles = AuthService().list_roles(headers)
    except (AuthError, Exception):
        roles = []
    try:
        employees = AuthService().list_users(headers)
    except (AuthError, Exception):
        employees = []

role_options = {role["name"]: role["code"] for role in roles}
employee_options = {
    f'{emp["employee_id"]} · {emp["first_name"]} {emp["last_name"]} ({emp["role_code"]})'.strip():
        emp["employee_id"]
    for emp in employees
    if emp.get("is_active")
}

uploaded = st.file_uploader(
    "Choose a supported document (.docx, .txt, .md, .rst)",
    type=["docx", "txt", "md", "rst"],
)

if uploaded is not None:
    st.write(f"**Selected file:** {uploaded.name}")
    st.write(f"**Size:** {uploaded.size:,} bytes")

    allowed_roles_display = st.multiselect(
        "Allowed Roles",
        options=list(role_options.keys()),
        help="Users with any selected role can ask questions from this document.",
    )
    allowed_employees_display = st.multiselect(
        "Allowed Employees",
        options=list(employee_options.keys()),
        help="The listed employees can ask questions from this document even if their role differs.",
    )

    overwrite = st.checkbox(
        "Replace the existing file if a document with the same name is already indexed",
        value=False,
    )

    if st.button("Process and Add Document", type="primary"):
        file_bytes = uploaded.getvalue()

        if not file_bytes:
            st.error("The selected file is empty and cannot be processed.")
        else:
            allowed_role_codes = [role_options[name] for name in allowed_roles_display]
            allowed_user_ids = [employee_options[label] for label in allowed_employees_display]
            with st.spinner("Processing and indexing the document... this may take a moment."):
                try:
                    result = DocumentService().upload(
                        file_name=uploaded.name,
                        file_data=file_bytes,
                        overwrite=overwrite,
                        allowed_role_codes=allowed_role_codes,
                        allowed_user_ids=allowed_user_ids,
                        headers=headers,
                    )
                except DocumentUploadError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Unexpected error during upload: {exc}")
                else:
                    st.session_state.uploaded_document = result
                    status = result.get("status", "unknown")
                    if status == "duplicate":
                        st.warning(result.get("message", ""))
                    else:
                        st.success(result.get("message", ""))
                        chunks = result.get("chunks_count")
                        if chunks is not None:
                            st.info(f"Indexed **{chunks}** chunks into the knowledge base.")
                    access = result.get("document_id")
                    if access:
                        st.info(
                            f"Document id: **{access}** · Roles: "
                            f"{', '.join(result.get('allowed_role_codes', [])) or 'owner only'} · "
                            f"Employees: {', '.join(result.get('allowed_user_ids', [])) or 'owner only'}"
                        )
                    st.caption(
                        "You can now ask questions about the uploaded document "
                        "from the chat page."
                    )

if st.session_state.uploaded_document is not None:
    st.divider()
    st.subheader("Last upload result")
    st.json(st.session_state.uploaded_document)