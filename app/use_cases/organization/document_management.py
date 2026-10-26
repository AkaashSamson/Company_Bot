from datetime import datetime, timezone
from typing import Callable
import logging

from app.core.settings import DEPARTMENT_ID_PREFIX, DOCUMENT_ID_PREFIX, EMPLOYEE_ID_PREFIX, PROJECT_ID_PREFIX
from app.domain.entities.organization_models import Document
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationEngine
from app.domain.services.business_id_generator import build_business_id_generator
from app.domain.services.organization_errors import ConflictError, ForbiddenError, NotFoundError

logger = logging.getLogger("knowlayer.documents")

DESCRIPTION_MAX_LENGTH = 500


def utc_now():
    return datetime.now(timezone.utc)


class DocumentManagementService:
    def __init__(
        self,
        unit_of_work_factory: Callable,
        ingestion_handler: Callable | None = None,
        deletion_handler: Callable | None = None,
        business_id_generator=None,
        document_id_prefix: str = DOCUMENT_ID_PREFIX,
    ):
        self.unit_of_work_factory = unit_of_work_factory
        self.ingestion_handler = ingestion_handler
        self.deletion_handler = deletion_handler
        self.business_id_generator = business_id_generator or build_business_id_generator(
            user_prefix=EMPLOYEE_ID_PREFIX,
            department_prefix=DEPARTMENT_ID_PREFIX,
            project_prefix=PROJECT_ID_PREFIX,
            document_prefix=document_id_prefix,
        )
        self.authorization = AuthorizationEngine(unit_of_work_factory)

    @staticmethod
    def _actor(uow, principal):
        actor = uow.users.get_by_uid(principal.uid)
        if actor is None or actor.status != "active":
            raise ForbiddenError("Active authenticated user required")
        return actor

    def _check_project_upload(self, actor, project):
        if project is None:
            raise NotFoundError("Project not found")
        if not self.authorization.can_upload_document(AuthenticatedPrincipal(actor.uid), project.project_id):
            raise ForbiddenError("Only the project manager may upload documents to this project")

    def _check_project_view(self, actor, project):
        if project is None:
            raise NotFoundError("Project not found")
        if not self.authorization.can_view_project_documents(AuthenticatedPrincipal(actor.uid), project.project_id):
            raise ForbiddenError("Project documents are outside viewer scope")

    def _can_access(self, actor, document):
        if document.status == "archived":
            return False
        if document.status == "active":
            return self.authorization.can_read_document(AuthenticatedPrincipal(actor.uid), document.document_id)
        # Allow uploader or manager/admin to see documents while processing or failed
        if actor.role.casefold() == "admin" or document.uploaded_by == actor.uid:
            return True
        if document.project_id is None:
            return True
        with self.unit_of_work_factory() as uow:
            project = uow.projects.get(document.project_id)
            if project and self.authorization._can_manage_project(uow, actor, project):
                return True
            membership = uow.memberships.get(actor.uid, document.project_id)
            if membership and membership.status == "active":
                return True
        return False

    def get_document(self, principal: AuthenticatedPrincipal, document_id: str) -> Document:
        with self.unit_of_work_factory() as uow:
            actor = self._actor(uow, principal)
            document = uow.documents.get(document_id)
            if document is None or document.status == "archived":
                raise NotFoundError("Document not found")
            if not self._can_access(actor, document):
                raise ForbiddenError("Document is outside access scope")
            return document

    def list_documents(self, principal: AuthenticatedPrincipal):
        with self.unit_of_work_factory() as uow:
            actor = self._actor(uow, principal)
            return [document for document in uow.documents.list() if self._can_access(actor, document)]

    def list_project_documents(self, principal: AuthenticatedPrincipal, project_id: str):
        with self.unit_of_work_factory() as uow:
            actor = self._actor(uow, principal)
            project = uow.projects.get(project_id)
            self._check_project_view(actor, project)
            return [
                document
                for document in uow.documents.list()
                if document.project_id == project.project_id and document.status != "archived" and self._can_access(actor, document)
            ]

    def register_document(
        self,
        principal: AuthenticatedPrincipal,
        document_id: str | None = None,
        document_name: str | None = None,
        project_id: str | None = None,
        source_path: str | None = None,
        content: str | None = None,
        original_filename: str | None = None,
        file_type: str | None = None,
        description: str | None = None,
        version: str = "1.0",
        background_tasks: Any = None,
    ):
        with self.unit_of_work_factory() as uow:
            actor = self._actor(uow, principal)
            document_id = document_id or self.business_id_generator.next(uow, "document")
            if uow.documents.get(document_id):
                raise ConflictError("Document already exists")
            project = uow.projects.get(project_id) if project_id else None
            if project_id and project is None:
                raise NotFoundError("Project not found")
            if project is not None:
                self._check_project_upload(actor, project)
            elif not self.authorization.can_upload_document(AuthenticatedPrincipal(actor.uid), None):
                raise ForbiddenError("Unassigned document registration requires manager or admin access")
            if description is not None and len(description) > DESCRIPTION_MAX_LENGTH:
                raise ValueError(f"Description must not exceed {DESCRIPTION_MAX_LENGTH} characters")

            # Pre-validate content or source_path synchronously
            if source_path or content:
                from app.infrastructure.ingestion.provisioner import validate_upload_content

                _, detected_ext = validate_upload_content(
                    content=content,
                    source_path=source_path,
                    document_name=document_name or document_id,
                )
                if detected_ext and not file_type:
                    file_type = detected_ext.lstrip(".")

            now = utc_now()
            # If background_tasks is supplied and ingestion is needed, start in "processing" state
            is_async = background_tasks is not None and (source_path or content) and self.ingestion_handler
            initial_status = "processing" if is_async else "active"

            document = Document(
                document_id,
                document_name or document_id,
                project_id,
                status=initial_status,
                created_at=now,
                updated_at=now,
                original_filename=original_filename,
                file_type=file_type,
                description=description,
                version=version or "1.0",
                uploaded_by=actor.uid,
                uploaded_at=now if (source_path or content) else None,
            )

            # Synchronous path: run ingestion immediately before saving
            if not is_async and (source_path or content) and self.ingestion_handler:
                self.ingestion_handler(source_path, document, content)

            document = uow.documents.save(document)
            uow.commit()

        # Asynchronous path: dispatch ingestion to background worker
        if is_async:
            background_tasks.add_task(
                self.process_document_ingestion,
                document.document_id,
                source_path,
                content,
            )

        return document

    def process_document_ingestion(
        self,
        document_id: str,
        source_path: str | None = None,
        content: str | None = None,
    ):
        """Executes document ingestion in the background and updates document status."""
        logger.info("Starting background ingestion for document %r", document_id)
        try:
            with self.unit_of_work_factory() as uow:
                doc = uow.documents.get(document_id)
                if doc is None:
                    logger.warning("Document %r not found for background ingestion", document_id)
                    return

            if self.ingestion_handler:
                self.ingestion_handler(source_path, doc, content)

            with self.unit_of_work_factory() as uow:
                doc = uow.documents.get(document_id)
                if doc is not None:
                    doc.status = "active"
                    doc.updated_at = utc_now()
                    uow.documents.save(doc)
                    uow.commit()
                    logger.info("Background ingestion completed successfully for document %r (status: active)", document_id)
        except Exception as err:
            logger.error("Background ingestion failed for document %r: %s", document_id, err, exc_info=True)
            with self.unit_of_work_factory() as uow:
                doc = uow.documents.get(document_id)
                if doc is not None:
                    doc.status = "failed"
                    doc.updated_at = utc_now()
                    uow.documents.save(doc)
                    uow.commit()

    def register_project_document(
        self,
        principal: AuthenticatedPrincipal,
        project_id: str,
        background_tasks: Any = None,
        **fields,
    ):
        return self.register_document(principal, project_id=project_id, background_tasks=background_tasks, **fields)

    def delete_document(self, principal: AuthenticatedPrincipal, document_id: str):
        with self.unit_of_work_factory() as uow:
            actor = self._actor(uow, principal)
            document = uow.documents.get(document_id)
            if document is None:
                raise NotFoundError("Document not found")
            if not self.authorization.can_manage_document(AuthenticatedPrincipal(actor.uid), document_id):
                raise ForbiddenError("Document is outside manager scope")
            document.status = "archived"
            document.updated_at = utc_now()
            uow.documents.save(document)
            uow.commit()
        if self.deletion_handler:
            try:
                self.deletion_handler(document_id)
            except Exception as error:
                logger.warning("vector removal failed for document %r: %s", document_id, error)