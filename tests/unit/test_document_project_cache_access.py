"""
Unit tests validating Document-Project mapping and Cache ID access control.

Tests the core requirements:
1. doc_id map with proj_id (DocumentProjectMappingService).
2. If current user has a proj_id, doc_ids belonging to that project can be accessed.
3. Prevention of user viewing cached responses generated from documents they do not have access to,
   by mapping cache_id -> doc_id, proj_id.
"""

import pytest
from unittest.mock import MagicMock

from app.domain.services.document_project_service import DocumentProjectMappingService
from app.infrastructure.cache.dual_cache import DualCache, DualCacheEntry, JSONLocalCache
from app.infrastructure.cache.quality_aware_cache import (
    InMemoryQualityAwareCache,
    QualityAwareCacheEntry,
)


class MockDoc:
    def __init__(self, doc_id, proj_id, name="", filename=""):
        self.document_id = doc_id
        self.project_id = proj_id
        self.document_name = name or doc_id
        self.original_filename = filename or f"{doc_id}.docx"
        self.storage_location = f"/storage/{self.original_filename}"
        self.status = "active"


class MockDocRepo:
    def __init__(self, docs):
        self._docs = docs

    def list(self):
        return list(self._docs)


class MockUoW:
    def __init__(self, docs):
        self.documents = MockDocRepo(docs)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture
def sample_docs():
    return [
        MockDoc("DOC-001", "121", name="Project 121 Overview", filename="P121_Overview.docx"),
        MockDoc("DOC-005", "121", name="Three Page Test Document", filename="Three_Page_Test_Document.docx"),
        MockDoc("DOC-004", "7656", name="HR Policy Document", filename="HR_Policy_Knowledge_System.docx"),
        MockDoc("DOC-ORG", None, name="Company Wide Handbook", filename="Nexora_Handbook.docx"),
    ]


@pytest.fixture
def doc_proj_service(sample_docs):
    return DocumentProjectMappingService(unit_of_work_factory=lambda: MockUoW(sample_docs))


class TestDocumentProjectMappingService:
    def test_doc_id_to_project_map(self, doc_proj_service):
        mapping = doc_proj_service.get_doc_id_to_project_map()
        assert mapping["DOC-001"] == "121"
        assert mapping["DOC-005"] == "121"
        assert mapping["DOC-004"] == "7656"
        assert mapping["DOC-ORG"] is None

    def test_resolve_doc_and_project(self, doc_proj_service):
        # Resolve by canonical ID
        doc_id, proj_id = doc_proj_service.resolve_doc_and_project("DOC-005")
        assert doc_id == "DOC-005"
        assert proj_id == "121"

        # Resolve by filename
        doc_id, proj_id = doc_proj_service.resolve_doc_and_project("Three_Page_Test_Document.docx")
        assert doc_id == "DOC-005"
        assert proj_id == "121"

        # Resolve project 7656 doc
        doc_id, proj_id = doc_proj_service.resolve_doc_and_project("HR_Policy_Knowledge_System.docx")
        assert doc_id == "DOC-004"
        assert proj_id == "7656"

    def test_user_with_proj_id_accesses_project_documents(self, doc_proj_service):
        """User with proj_id 7656 can access docs in 7656, but not 121."""
        accessible_7656 = doc_proj_service.get_accessible_document_ids(
            project_ids=["7656"],
            include_unassigned=True,
        )
        assert "DOC-004" in accessible_7656
        assert "DOC-ORG" in accessible_7656
        assert "DOC-001" not in accessible_7656
        assert "DOC-005" not in accessible_7656

        # User with proj_id 121 can access 121 docs
        accessible_121 = doc_proj_service.get_accessible_document_ids(
            project_ids=["121"],
            include_unassigned=False,
        )
        assert "DOC-001" in accessible_121
        assert "DOC-005" in accessible_121
        assert "DOC-004" not in accessible_121

    def test_chunk_authorization(self, doc_proj_service):
        chunk_121 = {"document_id": "DOC-005", "project_id": "121", "text": "secret 121 info"}
        chunk_7656 = {"document_id": "DOC-004", "project_id": "7656", "text": "hr info"}

        # User in 7656
        assert doc_proj_service.is_chunk_authorized(chunk_121, authorized_project_ids=["7656"]) is False
        assert doc_proj_service.is_chunk_authorized(chunk_7656, authorized_project_ids=["7656"]) is True

        # Admin access
        assert doc_proj_service.is_chunk_authorized(chunk_121, is_admin=True) is True


class TestDualCacheProjectDocumentIsolation:
    @pytest.fixture
    def dual_cache(self, tmp_path, monkeypatch, doc_proj_service):
        monkeypatch.setattr(
            "app.domain.services.document_project_service.get_document_project_service",
            lambda: doc_proj_service,
        )
        json_file = str(tmp_path / "test_dual_cache.json")
        primary_mock = MagicMock()
        primary_mock.is_available = False
        primary_mock.get.return_value = None
        cache = DualCache(
            primary_cache=primary_mock,
            fallback_cache=JSONLocalCache(json_file),
            enable_sync=False,
        )
        return cache

    def test_cache_id_mapped_to_doc_id_and_proj_id(self, dual_cache):
        """Put caches response and maps cache_id to doc_id and proj_id."""
        cache_id = "cch_project121_qa"
        dual_cache.put(
            cache_key="what is the test objective?",
            original_query="what is the test objective?",
            response="The objective is on page 1 of Three Page Test Document.",
            cache_id=cache_id,
            document_ids=["DOC-005"],  # Belongs to project 121
        )

        assert cache_id in dual_cache._cache_id_to_meta
        meta = dual_cache._cache_id_to_meta[cache_id]
        assert "DOC-005" in meta["document_ids"]
        assert "121" in meta["project_ids"]

    def test_user_without_project_access_denied_cached_response(self, dual_cache):
        """User with project 7656 cannot view cached response from project 121."""
        cache_id = "cch_project121_qa"
        dual_cache.put(
            cache_key="what is the test objective?",
            original_query="what is the test objective?",
            response="The objective is on page 1 of Three Page Test Document.",
            cache_id=cache_id,
            document_ids=["DOC-005"],
        )

        # User in project 7656 receives cache miss
        denied_entry = dual_cache.get(
            cache_key="what is the test objective?",
            project_ids=["7656"],
        )
        assert denied_entry is None

        # User directly requesting by cache_id is also denied
        denied_by_id = dual_cache.get_by_cache_id(
            cache_id=cache_id,
            project_ids=["7656"],
        )
        assert denied_by_id is None

    def test_user_with_project_access_receives_cached_response(self, dual_cache):
        """User with project 121 CAN view cached response from project 121."""
        cache_id = "cch_project121_qa"
        dual_cache.put(
            cache_key="what is the test objective?",
            original_query="what is the test objective?",
            response="The objective is on page 1 of Three Page Test Document.",
            cache_id=cache_id,
            document_ids=["DOC-005"],
        )

        # User in project 121 receives cache hit
        allowed_entry = dual_cache.get(
            cache_key="what is the test objective?",
            project_ids=["121"],
        )
        assert allowed_entry is not None
        assert allowed_entry.cache_id == cache_id
        assert allowed_entry.response == "The objective is on page 1 of Three Page Test Document."

        # User directly requesting by cache_id is allowed
        allowed_by_id = dual_cache.get_by_cache_id(
            cache_id=cache_id,
            project_ids=["121"],
        )
        assert allowed_by_id is not None
        assert allowed_by_id.cache_id == cache_id

    def test_admin_has_universal_cache_access(self, dual_cache):
        """Admin can view cached response regardless of project."""
        cache_id = "cch_project121_qa"
        dual_cache.put(
            cache_key="what is the test objective?",
            original_query="what is the test objective?",
            response="The objective is on page 1 of Three Page Test Document.",
            cache_id=cache_id,
            document_ids=["DOC-005"],
        )

        admin_entry = dual_cache.get(
            cache_key="what is the test objective?",
            is_admin=True,
        )
        assert admin_entry is not None

        admin_by_id = dual_cache.get_by_cache_id(cache_id=cache_id, is_admin=True)
        assert admin_by_id is not None

    def test_delete_by_cache_id(self, dual_cache):
        """Deleting by cache_id clears entry and index."""
        cache_id = "cch_delete_test"
        dual_cache.put(
            cache_key="q_delete",
            original_query="q_delete",
            response="To be deleted",
            cache_id=cache_id,
            document_ids=["DOC-004"],
        )

        assert dual_cache.get_by_cache_id(cache_id, project_ids=["7656"]) is not None
        deleted = dual_cache.delete_by_cache_id(cache_id)
        assert deleted is True
        assert dual_cache.get_by_cache_id(cache_id, project_ids=["7656"]) is None
        assert dual_cache.get("q_delete", project_ids=["7656"]) is None


class TestQualityAwareCacheProjectDocumentIsolation:
    @pytest.fixture
    def qa_cache(self, monkeypatch, doc_proj_service):
        monkeypatch.setattr(
            "app.domain.services.document_project_service.get_document_project_service",
            lambda: doc_proj_service,
        )
        validator = MagicMock()
        val_res = MagicMock()
        val_res.is_valid = True
        val_res.decision.value = "PASS"
        val_res.metrics = {}
        validator.validate.return_value = val_res

        cache = InMemoryQualityAwareCache(
            max_entries=20,
            ttl_seconds=3600.0,
            validator=validator,
        )
        return cache

    def test_quality_cache_prevents_unauthorized_project_view(self, qa_cache):
        cache_id = "cch_qa_121"
        qa_cache.put(
            cache_key="q_qa_test",
            original_query="q_qa_test",
            response="Secret 121 answer",
            cache_id=cache_id,
            document_ids=["DOC-005"],  # Belongs to project 121
        )

        # Denied for project 7656
        assert qa_cache.get("q_qa_test", project_ids=["7656"]) is None
        assert qa_cache.get_by_cache_id(cache_id, project_ids=["7656"]) is None

        # Allowed for project 121
        entry_121 = qa_cache.get("q_qa_test", project_ids=["121"])
        assert entry_121 is not None
        assert entry_121.cache_id == cache_id
