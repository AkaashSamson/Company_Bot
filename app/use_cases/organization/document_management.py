from datetime import datetime, timezone
from typing import Callable

from app.domain.entities.organization_models import Document
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.organization_errors import ConflictError, ForbiddenError, NotFoundError


def utc_now():
    return datetime.now(timezone.utc)


class DocumentManagementService:
    def __init__(self, unit_of_work_factory: Callable, ingestion_handler: Callable | None = None):
        self.unit_of_work_factory = unit_of_work_factory
        self.ingestion_handler = ingestion_handler

    def _actor(self, uow, principal):
        actor = uow.users.get_by_uid(principal.uid)
        if actor is None or actor.status != "active" or actor.role.casefold() not in {"admin", "manager"}:
            raise ForbiddenError("Document management access required")
        return actor

    def _can_access(self, actor, document, uow):
        if actor.role.casefold() == "admin":
            return True
        if document.project_id is None:
            return True
        project = uow.projects.get(document.project_id)
        return project is not None and project.department_id == actor.department_id

    def list_documents(self, principal: AuthenticatedPrincipal):
        with self.unit_of_work_factory() as uow:
            actor = self._actor(uow, principal)
            return [document for document in uow.documents.list() if self._can_access(actor, document, uow)]

    def register_document(
        self,
        principal: AuthenticatedPrincipal,
        document_id: str,
        document_name: str,
        project_id: str | None = None,
        source_path: str | None = None,
    ):
        with self.unit_of_work_factory() as uow:
            actor = self._actor(uow, principal)
            if uow.documents.get(document_id):
                raise ConflictError("Document already exists")
            project = uow.projects.get(project_id) if project_id else None
            if project_id and project is None:
                raise NotFoundError("Project not found")
            if project and actor.role.casefold() != "admin" and project.department_id != actor.department_id:
                raise ForbiddenError("Project is outside manager scope")
            now = utc_now()
            document = Document(document_id, document_name, project_id, created_at=now, updated_at=now)
            uow.documents.save(document)
            uow.commit()
            if source_path and self.ingestion_handler:
                self.ingestion_handler(source_path, document)
            return document

    def delete_document(self, principal: AuthenticatedPrincipal, document_id: str):
        with self.unit_of_work_factory() as uow:
            actor = self._actor(uow, principal)
            document = uow.documents.get(document_id)
            if document is None:
                raise NotFoundError("Document not found")
            if not self._can_access(actor, document, uow):
                raise ForbiddenError("Document is outside manager scope")
            document.status = "archived"
            document.updated_at = utc_now()
            uow.documents.save(document)
            uow.commit()
