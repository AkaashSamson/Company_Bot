"""
Document-Project Mapping and Authorization Service.

Provides centralized mapping between doc_id and proj_id, allowing:
1. Lookup of doc_id -> project_id (and alias/filename -> doc_id, project_id).
2. Calculation of all document IDs accessible to a user given their project_ids.
3. Verification of document and chunk access during retrieval and cache lookups.
"""

import logging
from typing import Any, Iterable, Optional, Sequence, Set

logger = logging.getLogger("knowlayer.document_project_service")


class DocumentProjectMappingService:
    def __init__(self, unit_of_work_factory: Any = None):
        if unit_of_work_factory is None:
            from app.infrastructure.persistence.factory import create_unit_of_work
            unit_of_work_factory = create_unit_of_work
        self.unit_of_work_factory = unit_of_work_factory

    def get_doc_id_to_project_map(self) -> dict[str, Optional[str]]:
        """
        Returns a mapping of canonical document_id -> project_id.
        None indicates an unassigned document.
        """
        mapping: dict[str, Optional[str]] = {}
        try:
            with self.unit_of_work_factory() as uow:
                for doc in uow.documents.list():
                    p_id = str(doc.project_id).strip() if getattr(doc, "project_id", None) else None
                    if p_id and p_id.lower() in ("none", "null", "unassigned"):
                        p_id = None
                    mapping[str(doc.document_id).strip()] = p_id
        except Exception as exc:
            logger.warning("Failed building doc_id -> project_id map: %s", exc)
        return mapping

    def get_alias_to_doc_meta_map(self) -> dict[str, tuple[str, Optional[str]]]:
        """
        Returns mapping of lowercased identifier (doc_id, document_name, original_filename, storage_path)
        to (canonical_doc_id, project_id).
        """
        aliases: dict[str, tuple[str, Optional[str]]] = {}
        try:
            with self.unit_of_work_factory() as uow:
                for doc in uow.documents.list():
                    d_id = str(doc.document_id).strip()
                    p_id = str(doc.project_id).strip() if getattr(doc, "project_id", None) else None
                    if p_id and p_id.lower() in ("none", "null", "unassigned"):
                        p_id = None
                    tuple_val = (d_id, p_id)
                    aliases[d_id.lower()] = tuple_val
                    if doc.document_name:
                        aliases[str(doc.document_name).strip().lower()] = tuple_val
                    if doc.original_filename:
                        aliases[str(doc.original_filename).strip().lower()] = tuple_val
                    loc = getattr(doc, "storage_location", None)
                    if loc:
                        aliases[str(loc).strip().lower()] = tuple_val
        except Exception as exc:
            logger.warning("Failed building alias map: %s", exc)
        return aliases

    def resolve_doc_and_project(self, doc_identifier: str) -> tuple[Optional[str], Optional[str]]:
        """
        Resolves any doc_id, document_name, or filename to (canonical_doc_id, project_id).
        """
        if not doc_identifier or not str(doc_identifier).strip():
            return None, None
        ident_lower = str(doc_identifier).strip().lower()
        alias_map = self.get_alias_to_doc_meta_map()
        if ident_lower in alias_map:
            return alias_map[ident_lower]
        # Partial match if needed (e.g. filename in path)
        for k, val in alias_map.items():
            if ident_lower in k or k in ident_lower:
                return val
        return doc_identifier, None

    def get_accessible_document_ids(
        self,
        project_ids: Optional[Iterable[str]] = None,
        explicit_document_ids: Optional[Iterable[str]] = None,
        include_unassigned: bool = True,
        is_admin: bool = False,
    ) -> Optional[Set[str]]:
        """
        Calculates all document IDs accessible to a user.
        If user is admin, returns None (meaning unrestricted access).
        Otherwise returns a set of accessible canonical document IDs.
        """
        if is_admin:
            return None

        accessible_docs: Set[str] = set()
        user_proj_set = {str(p).strip().lower() for p in project_ids or [] if p}

        if explicit_document_ids:
            for did in explicit_document_ids:
                if did:
                    accessible_docs.add(str(did).strip())

        try:
            with self.unit_of_work_factory() as uow:
                for doc in uow.documents.list():
                    if getattr(doc, "status", "active") != "active":
                        continue
                    p_id = str(doc.project_id).strip() if getattr(doc, "project_id", None) else None
                    if p_id and p_id.lower() in ("none", "null", "unassigned"):
                        p_id = None

                    if p_id is not None:
                        if p_id.lower() in user_proj_set:
                            accessible_docs.add(str(doc.document_id).strip())
                    elif include_unassigned:
                        accessible_docs.add(str(doc.document_id).strip())
        except Exception as exc:
            logger.warning("Failed calculating accessible document IDs: %s", exc)

        return accessible_docs

    def is_chunk_authorized(
        self,
        chunk_metadata: dict[str, Any],
        authorized_project_ids: Optional[Iterable[str]] = None,
        authorized_document_ids: Optional[Iterable[str]] = None,
        include_unassigned: bool = True,
        is_admin: bool = False,
    ) -> bool:
        """
        Validates if a retrieved chunk is strictly authorized for the user.
        """
        if is_admin or authorized_project_ids is None and authorized_document_ids is None:
            return True

        user_proj_set = {str(p).strip().lower() for p in (authorized_project_ids or []) if p}
        user_doc_set = {str(d).strip().lower() for d in (authorized_document_ids or []) if d}

        raw_doc_id = (
            chunk_metadata.get("document_id")
            or chunk_metadata.get("doc_id")
            or chunk_metadata.get("source")
            or chunk_metadata.get("filename")
        )
        raw_proj_id = chunk_metadata.get("project_id") or chunk_metadata.get("proj_id")

        canonical_doc_id, resolved_proj_id = self.resolve_doc_and_project(raw_doc_id)
        effective_proj_id = raw_proj_id or resolved_proj_id

        # Normalize project_id
        if effective_proj_id and str(effective_proj_id).strip().lower() in ("none", "null", "unassigned"):
            effective_proj_id = None

        # Check explicit document grant
        if canonical_doc_id and canonical_doc_id.lower() in user_doc_set:
            return True
        if raw_doc_id and str(raw_doc_id).strip().lower() in user_doc_set:
            return True

        # Check project membership
        if effective_proj_id is not None:
            return str(effective_proj_id).strip().lower() in user_proj_set

        # Unassigned document
        return include_unassigned


_default_service: Optional[DocumentProjectMappingService] = None


def get_document_project_service() -> DocumentProjectMappingService:
    global _default_service
    if _default_service is None:
        _default_service = DocumentProjectMappingService()
    return _default_service
