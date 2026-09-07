import streamlit as st

from streamlit_app.services.document_service import DocumentService, DocumentUploadError

st.set_page_config(page_title="Upload Document", page_icon="📄")
st.title("📄 Upload a New Document")

st.caption(
    "Upload a document to add it to the knowledge base. The file goes through the "
    "same processing pipeline used for the existing Nexora handbook before the "
    "chatbot can answer from it."
)

if "uploaded_document" not in st.session_state:
    st.session_state.uploaded_document = None

back = st.button("⬅ Back to chat", use_container_width=False)
if back:
    st.switch_page("app.py")

uploaded = st.file_uploader(
    "Choose a supported document (.docx, .txt, .md, .rst)",
    type=["docx", "txt", "md", "rst"],
)

if uploaded is not None:
    st.write(f"**Selected file:** {uploaded.name}")
    st.write(f"**Size:** {uploaded.size:,} bytes")

    overwrite = st.checkbox(
        "Replace the existing file if a document with the same name is already indexed",
        value=False,
    )

    if st.button("Process and Add Document", type="primary"):
        file_bytes = uploaded.getvalue()

        if not file_bytes:
            st.error("The selected file is empty and cannot be processed.")
        else:
            with st.spinner("Processing and indexing the document... this may take a moment."):
                try:
                    result = DocumentService().upload(
                        file_name=uploaded.name,
                        file_data=file_bytes,
                        overwrite=overwrite,
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
                    st.caption(
                        "You can now ask questions about the uploaded document "
                        "from the chat page."
                    )

if st.session_state.uploaded_document is not None:
    st.divider()
    st.subheader("Last upload result")
    st.json(st.session_state.uploaded_document)
