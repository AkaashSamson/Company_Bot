import streamlit as st

from streamlit_app.services.document_service import DocumentService
from streamlit_app.services.organization_service import OrganizationService


st.set_page_config(page_title="Documents | KnowLayer")
st.title("Documents")
document_service = DocumentService()
organization_service = OrganizationService()

projects = []
try:
    projects = organization_service.list_projects()
except Exception:
    st.warning("Projects are currently unavailable. Documents can still be registered without a project.")

try:
    documents = document_service.list_documents()
except Exception as error:
    st.error(
        "The document service is unavailable. "
        "Check that the FastAPI backend is running and that you are logged in."
    )
    st.caption(f"Technical detail: {error}")
    documents = []

with st.expander("Register document"):
    with st.form("create-document"):
        document_id = st.text_input("Document ID")
        document_name = st.text_input("Document name")
        project_options = {"Unassigned": None}
        project_options.update({item["project_name"]: item["project_id"] for item in projects})
        project_name = st.selectbox("Project", list(project_options))
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
    st.info("No documents found. Use the form above to register a document.")