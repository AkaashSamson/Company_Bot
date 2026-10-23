import base64
from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import shutil
from typing import Callable, Optional

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

    def get_document(self, principal: AuthenticatedPrincipal, document_id: str) -> Document:
        with self.unit_of_work_factory() as uow:
            actor = self._actor(uow, principal)
            document = uow.documents.get(document_id)
            if document is None:
                raise NotFoundError("Document not found")
            if not self._can_access(actor, document):
                raise ForbiddenError("Document is outside viewer scope")
            return document

    def get_document_status(self, principal: AuthenticatedPrincipal, document_id: str) -> dict:
        doc = self.get_document(principal, document_id)
        return {
            "document_id": doc.document_id,
            "status": doc.status,
            "progress": 100 if doc.status == "active" else (0 if doc.status == "processing" else None),
            "message": doc.description or ("Ready" if doc.status == "active" else doc.status),
        }

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
        defer_ingestion: bool = False,
    ):
        raw_bytes = None
        file_hash = None
        if content is not None:
            try:
                raw_bytes = base64.b64decode(content, validate=True)
            except Exception as error:
                raise ValueError("Document content is not valid base64") from error
            file_hash = hashlib.sha256(raw_bytes).hexdigest()
        elif source_path is not None:
            p = Path(source_path)
            if p.exists():
                raw_bytes = p.read_bytes()
                file_hash = hashlib.sha256(raw_bytes).hexdigest()

        with self.unit_of_work_factory() as uow:
            actor = self._actor(uow, principal)
            document_id = document_id or self.business_id_generator.next(uow, "document")
            if uow.documents.get(document_id):
                raise ConflictError("Document already exists")

            if file_hash and project_id:
                for existing in uow.documents.list():
                    if (
                        existing.project_id == project_id
                        and getattr(existing, "file_hash", None) == file_hash
                        and existing.status != "archived"
                    ):
                        raise ConflictError("Exact file already exists in this project")

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
            initial_status = "processing" if (source_path or content) and (defer_ingestion or self.ingestion_handler) else "active"
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
                storage_location=None,
                uploaded_by=actor.uid,
                uploaded_at=now if (source_path or content) else None,
                file_hash=file_hash,
            )
            if (source_path or content) and self.ingestion_handler and not defer_ingestion:
                self.ingestion_handler(source_path, document, content)
                document.status = "active"

            document = uow.documents.save(document)
            uow.commit()
            return document

    def ingest_document(
        self,
        document_id: str,
        source_path: str | None = None,
        content: str | None = None,
    ):
        with self.unit_of_work_factory() as uow:
            document = uow.documents.get(document_id)
            if not document:
                return
            try:
                if self.ingestion_handler:
                    self.ingestion_handler(source_path, document, content)
                document.status = "active"
                document.updated_at = utc_now()
                uow.documents.save(document)
                uow.commit()
            except Exception as exc:
                logger.error("Async ingestion failed for document %s: %s", document_id, exc)
                document.status = "failed"
                document.description = f"{document.description or ''} [Failed: {exc}]".strip()
                document.updated_at = utc_now()
                uow.documents.save(document)
                uow.commit()

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
            if not self.authorization.can_manage_document(AuthenticatedPrincipal(actor.uid), document_id):
                raise ForbiddenError("Document is outside manager scope")

            document.status = "archived"
            document.updated_at = utc_now()

            # Relocate file to archived directory
            if document.storage_location:
                src_path = Path(document.storage_location)
                if src_path.exists():
                    archive_dir = src_path.parent / "archived"
                    archive_dir.mkdir(parents=True, exist_ok=True)
                    dest_path = archive_dir / src_path.name
                    shutil.move(str(src_path), str(dest_path))
                    document.storage_location = str(dest_path)
            elif document.project_id:
                project_dir = Path("input") / document.project_id
                if project_dir.exists():
                    matches = list(project_dir.glob(f"{document_id}_*"))
                    if matches:
                        src_path = matches[0]
                        archive_dir = project_dir / "archived"
                        archive_dir.mkdir(parents=True, exist_ok=True)
                        dest_path = archive_dir / src_path.name
                        shutil.move(str(src_path), str(dest_path))
                        document.storage_location = str(dest_path)

            uow.documents.save(document)
            uow.commit()

    def delete_document(self, principal: AuthenticatedPrincipal, document_id: str, permanent: bool = False):
        if not permanent:
            return self.archive_document(principal, document_id)

        with self.unit_of_work_factory() as uow:
            actor = self._actor(uow, principal)
            document = uow.documents.get(document_id)
            if document is None:
                raise NotFoundError("Document not found")
            if not self.authorization.can_manage_document(AuthenticatedPrincipal(actor.uid), document_id):
                raise ForbiddenError("Document is outside manager scope")

            if document.storage_location:
                try:
                    p = Path(document.storage_location)
                    if p.exists():
                        p.unlink()
                except Exception as exc:
                    logger.warning("Failed to unlink document %s file: %s", document_id, exc)

            if hasattr(uow.documents, "purge"):
                uow.documents.purge(document_id)
            else:
                uow.documents.delete(document_id, permanent=True)
            uow.commit()

        if self.deletion_handler:
            try:
                self.deletion_handler(document_id)
            except Exception as error:
                logger.warning("vector removal failed for document %r: %s", document_id, error)
