import base64
from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import shutil
from typing import Any, Callable, Optional

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


def _next_version(v: str | None) -> str:
    if not v:
        return "1.1"
    parts = str(v).split(".")
    try:
        if len(parts) >= 2:
            parts[-1] = str(int(parts[-1]) + 1)
            return ".".join(parts)
        return f"{int(parts[0]) + 1}.0"
    except ValueError:
        return f"{v}.1"


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

    def _can_access(self, actor, document, include_archived: bool = False):
        if document.status == "archived":
            if not include_archived:
                return False
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

    def get_document(self, principal: AuthenticatedPrincipal, document_id: str, include_archived: bool = True) -> Document:
        with self.unit_of_work_factory() as uow:
            actor = self._actor(uow, principal)
            document = uow.documents.get(document_id)
            if document is None or (document.status == "archived" and not include_archived):
                raise NotFoundError("Document not found")
            if not self._can_access(actor, document, include_archived=include_archived):
                raise ForbiddenError("Document is outside access scope")
            return document

    def list_documents(self, principal: AuthenticatedPrincipal, include_archived: bool = False):
        with self.unit_of_work_factory() as uow:
            actor = self._actor(uow, principal)
            return [document for document in uow.documents.list() if self._can_access(actor, document, include_archived=include_archived)]

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
        replace_existing: bool = False,
        defer_ingestion: bool = False,
        background_tasks: Any = None,
    ):
        raw_bytes = None
        file_hash = None
        parse_name = (
            original_filename
            or document_name
            or source_path
            or (f"{document_id}{file_type}" if file_type else document_id)
        )
        if (source_path or content) and parse_name:
            ext = Path(parse_name).suffix.lower()
            if ext:
                from app.infrastructure.document.processor_factory import build_document_processor

                proc = build_document_processor()
                if not proc.supports(parse_name):
                    supported = ", ".join(sorted(proc.supported_extensions()))
                    raise ValueError(
                        f"Unsupported document type: {ext or '(none)'} (supported: {supported})"
                    )

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

        # Pre-validate content or source_path synchronously
        if source_path or content:
            from app.infrastructure.ingestion.provisioner import validate_upload_content

            _, detected_ext = validate_upload_content(
                content=content,
                source_path=source_path,
                document_name=document_name or original_filename or document_id or "upload",
            )
            if detected_ext and not file_type:
                file_type = detected_ext.lstrip(".")

        with self.unit_of_work_factory() as uow:
            actor = self._actor(uow, principal)

            if file_hash:
                for existing in uow.documents.list():
                    if (
                        existing.project_id == project_id
                        and getattr(existing, "file_hash", None) == file_hash
                        and existing.status != "archived"
                    ):
                        existing_name = existing.document_name or existing.original_filename or existing.document_id
                        scope_desc = "in this project" if project_id else "in unassigned documents"
                        raise ConflictError(
                            f"Identical file content already exists {scope_desc} with name '{existing_name}'"
                        )

            target_name = (
                document_name
                or original_filename
                or (Path(source_path).name if source_path else None)
            )
            if target_name:
                for existing in uow.documents.list():
                    if (
                        existing.project_id == project_id
                        and existing.status != "archived"
                        and (existing.document_name == target_name or existing.original_filename == target_name)
                    ):
                        if not replace_existing:
                            scope_desc = "in this project" if project_id else "in unassigned documents"
                            raise ConflictError(
                                f"Document '{target_name}' already exists {scope_desc}. Confirm replacement to overwrite it."
                            )
                        if not self.authorization.can_manage_document(AuthenticatedPrincipal(actor.uid), existing.document_id):
                            raise ForbiddenError("Only managers or administrators may replace existing documents")
                        if description is not None and len(description) > DESCRIPTION_MAX_LENGTH:
                            raise ValueError(f"Description must not exceed {DESCRIPTION_MAX_LENGTH} characters")

                        # Purge old storage file
                        if existing.storage_location:
                            try:
                                p = Path(existing.storage_location)
                                if p.exists():
                                    p.unlink()
                            except Exception as exc:
                                logger.warning("Failed to unlink replaced document %s file: %s", existing.document_id, exc)

                        # Purge old vectors before deleting
                        if self.deletion_handler:
                            try:
                                self.deletion_handler(existing.document_id)
                            except Exception as exc:
                                logger.warning("vector removal failed during replacement of %r: %s", existing.document_id, exc)

                        # Delete old document record from database
                        if hasattr(uow.documents, "purge"):
                            uow.documents.purge(existing.document_id)
                        else:
                            try:
                                uow.documents.delete(existing.document_id, permanent=True)
                            except TypeError:
                                uow.documents.delete(existing.document_id)
                        uow.commit()
                        break

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
            is_async = (defer_ingestion or background_tasks is not None) and (source_path or content) and self.ingestion_handler
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
                storage_location=None,
                uploaded_by=actor.uid,
                uploaded_at=now if (source_path or content) else None,
                file_hash=file_hash,
            )

            # Synchronous path: run ingestion immediately before saving
            if not is_async and (source_path or content) and self.ingestion_handler:
                self.ingestion_handler(source_path, document, content)
                document.status = "active"

            document = uow.documents.save(document)
            uow.commit()

        # Asynchronous path: dispatch ingestion if background_tasks was passed directly
        if background_tasks is not None and is_async:
            background_tasks.add_task(
                self.ingest_document,
                document.document_id,
                source_path,
                content,
            )

        return document

    def ingest_document(
        self,
        document_id: str,
        source_path: str | None = None,
        content: str | None = None,
    ):
        """Executes document ingestion in the background and updates document status."""
        logger.info("Starting background ingestion for document %r", document_id)
        with self.unit_of_work_factory() as uow:
            document = uow.documents.get(document_id)
            if not document:
                logger.warning("Document %r not found for background ingestion", document_id)
                return
            try:
                if self.ingestion_handler:
                    self.ingestion_handler(source_path, document, content)
                latest_doc = uow.documents.get(document_id)
                if latest_doc and latest_doc.status == "archived":
                    document.status = "archived"
                else:
                    document.status = "active"
                document.updated_at = utc_now()
                uow.documents.save(document)
                uow.commit()
                logger.info("Background ingestion completed successfully for document %r (status: active)", document_id)
            except Exception as exc:
                logger.error("Async ingestion failed for document %s: %s", document_id, exc, exc_info=True)
                document.status = "failed"
                document.description = f"{document.description or ''} [Failed: {exc}]".strip()
                document.updated_at = utc_now()
                uow.documents.save(document)
                uow.commit()

    # Alias for backwards compatibility with tests
    process_document_ingestion = ingest_document

    def register_project_document(
        self,
        principal: AuthenticatedPrincipal,
        project_id: str,
        defer_ingestion: bool = False,
        background_tasks: Any = None,
        replace_existing: bool = False,
        **fields,
    ):
        return self.register_document(
            principal,
            project_id=project_id,
            defer_ingestion=defer_ingestion,
            background_tasks=background_tasks,
            replace_existing=replace_existing,
            **fields,
        )

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

    def restore_document(self, principal: AuthenticatedPrincipal, document_id: str):
        with self.unit_of_work_factory() as uow:
            actor = self._actor(uow, principal)
            document = uow.documents.get(document_id)
            if document is None:
                raise NotFoundError("Document not found")
            if not self.authorization.can_manage_document(AuthenticatedPrincipal(actor.uid), document_id):
                raise ForbiddenError("Document is outside manager scope")

            document.status = "active"
            document.updated_at = utc_now()

            # Relocate file back from archived directory if present
            if document.storage_location:
                src_path = Path(document.storage_location)
                if src_path.exists() and src_path.parent.name == "archived":
                    dest_dir = src_path.parent.parent
                    dest_path = dest_dir / src_path.name
                    shutil.move(str(src_path), str(dest_path))
                    document.storage_location = str(dest_path)

            document = uow.documents.save(document)
            uow.commit()
            return document

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
                try:
                    uow.documents.delete(document_id, permanent=True)
                except TypeError:
                    uow.documents.delete(document_id)
            uow.commit()

        if self.deletion_handler:
            try:
                self.deletion_handler(document_id)
            except Exception as error:
                logger.warning("vector removal failed for document %r: %s", document_id, error)
