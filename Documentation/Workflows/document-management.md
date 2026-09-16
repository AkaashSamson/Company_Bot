# Document Management Workflow

Documents are managed through FastAPI and may be temporarily unassigned to a project.

1. The Streamlit Documents page lists projects and documents through `DocumentService` and `OrganizationService`.
2. `POST /api/documents` validates the document identifier and name, checks optional project existence and Manager department scope, then registers an active `Document`.
3. The SQL repository stores a nullable `project_id`, allowing Project-Document partial participation. A document can therefore exist before project assignment.
4. An optional source path can be passed to the ingestion handler after registration. Ingestion metadata carries `document_id` and project identity to the vector layer.
5. `DELETE /api/documents/{document_id}` archives the record, preserving retention history and excluding it from new answers.
6. Unassigned, inactive, and archived documents are not usable for project-scoped retrieval.
