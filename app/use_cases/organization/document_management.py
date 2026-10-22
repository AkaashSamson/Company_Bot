from datetime import datetime, timezone
from pathlib import Path
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
            return self.authorization.can_manage_document(
                AuthenticatedPrincipal(actor.uid), document.document_id, allow_archived=True
            )
        return self.authorization.can_read_document(AuthenticatedPrincipal(actor.uid), document.document_id)

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
                if document.project_id == project.project_id and document.status == "active"
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
            now = utc_now()
            document = Document(
                document_id,
                document_name or document_id,
                project_id,
                created_at=now,
                updated_at=now,
                original_filename=original_filename,
                file_type=file_type,
                description=description,
                version=version or "1.0",
                uploaded_by=actor.uid,
                uploaded_at=now if (source_path or content) else None,
            )
            if (source_path or content) and self.ingestion_handler:
                self.ingestion_handler(source_path, document, content)
            document = uow.documents.save(document)
            uow.commit()
            return document

    def register_project_document(
        self,
        principal: AuthenticatedPrincipal,
        project_id: str,
        **fields,
    ):
        return self.register_document(principal, project_id=project_id, **fields)

    def archive_document(self, principal: AuthenticatedPrincipal, document_id: str):
        with self.unit_of_work_factory() as uow:
            actor = self._actor(uow, principal)
            document = uow.documents.get(document_id)
            if document is None:
                raise NotFoundError("Document not found")
            if not self.authorization.can_manage_document(
                AuthenticatedPrincipal(actor.uid), document_id, allow_archived=True
            ):
                raise ForbiddenError("Document is outside manager scope")
            document.status = "archived"
            document.updated_at = utc_now()
            saved_doc = uow.documents.save(document)
            uow.commit()
        if self.deletion_handler:
            try:
                self.deletion_handler(document_id)
            except Exception as error:
                logger.warning("vector removal failed for document %r: %s", document_id, error)
        return saved_doc

    def unarchive_document(self, principal: AuthenticatedPrincipal, document_id: str):
        with self.unit_of_work_factory() as uow:
            actor = self._actor(uow, principal)
            document = uow.documents.get(document_id)
            if document is None:
                raise NotFoundError("Document not found")
            if not self.authorization.can_manage_document(
                AuthenticatedPrincipal(actor.uid), document_id, allow_archived=True
            ):
                raise ForbiddenError("Document is outside manager scope")
            document.status = "active"
            document.updated_at = utc_now()

            source_path = getattr(document, "storage_location", None)
            if source_path and Path(source_path).exists() and self.ingestion_handler:
                try:
                    self.ingestion_handler(source_path, document, None)
                except Exception as error:
                    logger.warning("re-indexing failed while unarchiving document %r: %s", document_id, error)

            saved_doc = uow.documents.save(document)
            uow.commit()
            return saved_doc

    def delete_document(self, principal: AuthenticatedPrincipal, document_id: str, permanent: bool = False):
        if not permanent:
            return self.archive_document(principal, document_id)

        storage_location = None
        with self.unit_of_work_factory() as uow:
            actor = self._actor(uow, principal)
            document = uow.documents.get(document_id)
            if document is None:
                raise NotFoundError("Document not found")
            if not self.authorization.can_manage_document(
                AuthenticatedPrincipal(actor.uid), document_id, allow_archived=True
            ):
                raise ForbiddenError("Document is outside manager scope")
            storage_location = getattr(document, "storage_location", None)

            if hasattr(uow, "document_grants") and hasattr(uow.document_grants, "for_document"):
                for grant in list(uow.document_grants.for_document(document_id)):
                    if hasattr(uow.document_grants, "delete"):
                        uow.document_grants.delete(grant.internal_id)

            uow.documents.delete(document_id)
            uow.commit()

        if self.deletion_handler:
            try:
                import inspect
                sig = inspect.signature(self.deletion_handler)
                if "storage_location" in sig.parameters:
                    self.deletion_handler(document_id, storage_location=storage_location)
                else:
                    self.deletion_handler(document_id)
            except Exception as error:
                logger.warning("vector removal failed for document %r: %s", document_id, error)
        return True

    def hard_delete_document(self, principal: AuthenticatedPrincipal, document_id: str):
        return self.delete_document(principal, document_id, permanent=True)