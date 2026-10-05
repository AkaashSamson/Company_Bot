"""
Unit tests for Cache ID generation and RBAC document isolation (AB Roadblock Enhancement).

Validates:
1. Unique Cache ID (cch_<12-hex>) generated for every cached response with documents.
2. Strict RBAC role scoping: Only users matching the assigned role receive the cached response.
3. Cross-role cache isolation: Unauthorized roles receive cache miss (no leakage).
4. Document-level scoping: Users lacking access to cited documents receive cache miss.
5. Admin role / is_admin=True privileges: Admins can access cached entries across roles and documents.
6. Cache invalidation by document_id and role.
7. Direct lookup and deletion by cache_id.
8. QueryOrchestrator end-to-end integration: cache_id and assigned_role returned in response.
"""

import pytest
from unittest.mock import MagicMock

from app.domain.services.authorization_engine import AuthorizationScope
from app.infrastructure.cache.quality_aware_cache import (
    CacheEntryMetadata,
    CacheEntrySource,
    InMemoryQualityAwareCache,
    QualityAwareCacheEntry,
)
from app.use_cases.chat.query_orchestrator import QueryOrchestrator


class DummyValidator:
    """Validator that passes all responses for controlled testing."""
    def validate(self, **kwargs):
        decision = MagicMock()
        decision.value = "PASS"
        res = MagicMock()
        res.is_valid = True
        res.decision = decision
        res.metrics = {}
        return res


@pytest.fixture
def rbac_cache():
    cache = InMemoryQualityAwareCache(
        max_entries=50,
        ttl_seconds=3600.0,
        validator=DummyValidator(),
    )
    return cache


class TestCacheIdGeneration:
    def test_cache_id_auto_generated(self, rbac_cache):
        """Verify unique cache_id with 'cch_' prefix is generated on put."""
        success = rbac_cache.put(
            cache_key="q_health_benefits",
            original_query="What are the health benefits?",
            response="Full health coverage is provided under Plan A.",
            citations=[{"source": "Benefits_Guide_2026.pdf", "section": "Health"}],
            assigned_role="Employee",
            confidence=0.95,
        )
        assert success is True

        entry = rbac_cache.get("q_health_benefits", role="Employee")
        assert entry is not None
        assert entry.cache_id.startswith("cch_")
        assert len(entry.cache_id) >= 12
        assert entry.assigned_role == "Employee"
        assert "Benefits_Guide_2026.pdf" in entry.document_ids

    def test_custom_cache_id_preserved(self, rbac_cache):
        """Verify custom cache_id is preserved and retrievable."""
        success = rbac_cache.put(
            cache_key="q_custom_id",
            original_query="Custom query",
            response="Custom answer",
            cache_id="cch_custom_12345",
            assigned_role="Engineering",
            document_ids=["Architecture_Spec.docx"],
        )
        assert success is True

        entry = rbac_cache.get("q_custom_id", role="Engineering")
        assert entry is not None
        assert entry.cache_id == "cch_custom_12345"
        assert entry.assigned_role == "Engineering"

    def test_get_by_cache_id(self, rbac_cache):
        """Verify entries can be looked up directly by unique cache_id."""
        rbac_cache.put(
            cache_key="q_lookup",
            original_query="Query for lookup",
            response="Lookup answer",
            cache_id="cch_lookup_001",
            assigned_role="Finance",
            document_ids=["Q3_Budget.xlsx"],
        )

        # Lookup with matching role
        entry = rbac_cache.get_by_cache_id("cch_lookup_001", role="Finance")
        assert entry is not None
        assert entry.response == "Lookup answer"

        # Lookup with non-matching role is denied
        denied_entry = rbac_cache.get_by_cache_id("cch_lookup_001", role="Intern")
        assert denied_entry is None

        # Admin can access regardless
        admin_entry = rbac_cache.get_by_cache_id("cch_lookup_001", is_admin=True)
        assert admin_entry is not None

    def test_delete_by_cache_id(self, rbac_cache):
        """Verify entries can be deleted by cache_id."""
        rbac_cache.put(
            cache_key="q_del",
            original_query="Query to delete",
            response="Delete answer",
            cache_id="cch_del_999",
            assigned_role="HR",
        )

        assert rbac_cache.get_by_cache_id("cch_del_999", role="HR") is not None
        deleted = rbac_cache.delete_by_cache_id("cch_del_999")
        assert deleted is True
        assert rbac_cache.get_by_cache_id("cch_del_999", role="HR") is None
        assert rbac_cache.get("q_del", role="HR") is None


class TestRBACRoleIsolation:
    def test_role_matching_allows_access(self, rbac_cache):
        """User with matching role receives cached response."""
        rbac_cache.put(
            cache_key="q_salary_bands",
            original_query="What are salary bands?",
            response="Executive salary bands are confidential.",
            assigned_role="Manager",
            document_ids=["Compensation_2026.pdf"],
        )

        entry = rbac_cache.get("q_salary_bands", role="Manager")
        assert entry is not None
        assert entry.response == "Executive salary bands are confidential."

    def test_role_mismatch_denies_access_and_records_stats(self, rbac_cache):
        """User with different role receives cache miss (no unauthorized leak)."""
        rbac_cache.put(
            cache_key="q_confidential_exec",
            original_query="What is the CEO bonus formula?",
            response="Formula is 3x EBITDA target.",
            assigned_role="Executive",
            document_ids=["Board_Minutes.pdf"],
        )

        # Intern attempts access -> None
        entry = rbac_cache.get("q_confidential_exec", role="Intern")
        assert entry is None

        # Employee attempts access -> None
        entry2 = rbac_cache.get("q_confidential_exec", role="Employee")
        assert entry2 is None

        # Anonymous / no role -> None
        entry3 = rbac_cache.get("q_confidential_exec")
        assert entry3 is None

        # Stats track RBAC denials
        stats = rbac_cache.get_stats()
        assert stats["rbac_denials"] >= 3

    def test_admin_bypasses_role_restriction(self, rbac_cache):
        """Admin role or is_admin=True can read any role-restricted cached response."""
        rbac_cache.put(
            cache_key="q_restricted",
            original_query="Restricted query",
            response="Top secret answer",
            assigned_role="Executive",
            document_ids=["Secret.pdf"],
        )

        # is_admin=True
        entry1 = rbac_cache.get("q_restricted", is_admin=True)
        assert entry1 is not None
        assert entry1.response == "Top secret answer"

        # role="admin"
        entry2 = rbac_cache.get("q_restricted", role="admin")
        assert entry2 is not None
        assert entry2.response == "Top secret answer"


class TestRBACDocumentIsolation:
    def test_document_scoping_enforces_membership(self, rbac_cache):
        """Requester must be authorized for all cited documents in the cache entry."""
        rbac_cache.put(
            cache_key="q_multi_doc",
            original_query="Compare payroll and healthcare policies",
            response="Payroll on 1st, Health via BlueCross.",
            assigned_role="Employee",
            document_ids=["doc_payroll_v1", "doc_healthcare_v2"],
        )

        # User has access to BOTH documents -> Granted
        entry_both = rbac_cache.get(
            "q_multi_doc",
            role="Employee",
            document_ids=["doc_payroll_v1", "doc_healthcare_v2", "doc_other"],
        )
        assert entry_both is not None

        # User only has access to doc_payroll_v1 -> Denied (prevent partial leakage)
        entry_partial = rbac_cache.get(
            "q_multi_doc",
            role="Employee",
            document_ids=["doc_payroll_v1"],
        )
        assert entry_partial is None

    def test_project_scoping_enforces_membership(self, rbac_cache):
        """Requester's authorized projects must include entry's project."""
        rbac_cache.put(
            cache_key="q_project_roadmap",
            original_query="What is the Q4 milestone?",
            response="Q4 milestone is launch alpha version.",
            assigned_role="Engineer",
            project_ids=["proj_apollo"],
            document_ids=["Apollo_Roadmap.pdf"],
        )

        # User authorized for proj_apollo -> Hit
        entry = rbac_cache.get(
            "q_project_roadmap",
            role="Engineer",
            project_ids=["proj_apollo", "proj_gemini"],
            document_ids=["Apollo_Roadmap.pdf"],
        )
        assert entry is not None

        # User authorized only for proj_gemini -> Miss
        denied = rbac_cache.get(
            "q_project_roadmap",
            role="Engineer",
            project_ids=["proj_gemini"],
            document_ids=["Apollo_Roadmap.pdf"],
        )
        assert denied is None


class TestCacheInvalidation:
    def test_invalidate_by_document(self, rbac_cache):
        """Updating or deleting a document invalidates all associated cached answers."""
        rbac_cache.put(
            cache_key="q_holiday_1",
            original_query="What are winter holidays?",
            response="Dec 24-26 are holidays.",
            document_ids=["Holiday_Policy_2025.docx"],
            assigned_role="Employee",
        )
        rbac_cache.put(
            cache_key="q_holiday_2",
            original_query="Can I carry over PTO for holidays?",
            response="Up to 5 days carry over.",
            document_ids=["Holiday_Policy_2025.docx"],
            assigned_role="Employee",
        )
        rbac_cache.put(
            cache_key="q_unrelated",
            original_query="Office parking policy?",
            response="Parking spots are in lot B.",
            document_ids=["Facilities_Guide.pdf"],
            assigned_role="Employee",
        )

        assert rbac_cache.get("q_holiday_1", role="Employee") is not None
        assert rbac_cache.get("q_holiday_2", role="Employee") is not None

        # Document updated -> invalidate
        count = rbac_cache.invalidate_document("Holiday_Policy_2025.docx")
        assert count == 2

        # Holiday queries are now cache misses
        assert rbac_cache.get("q_holiday_1", role="Employee") is None
        assert rbac_cache.get("q_holiday_2", role="Employee") is None

        # Unrelated query remains cached
        assert rbac_cache.get("q_unrelated", role="Employee") is not None

    def test_invalidate_by_role(self, rbac_cache):
        """Invalidating a role removes all cache entries assigned to that role."""
        rbac_cache.put(
            cache_key="q_intern_1",
            original_query="Intern stipend date?",
            response="Stipend is paid bi-weekly.",
            assigned_role="Intern",
        )
        rbac_cache.put(
            cache_key="q_eng_1",
            original_query="Git commit policy?",
            response="Conventional commits are required.",
            assigned_role="Engineer",
        )

        count = rbac_cache.invalidate_role("Intern")
        assert count == 1
        assert rbac_cache.get("q_intern_1", role="Intern") is None
        assert rbac_cache.get("q_eng_1", role="Engineer") is not None


class TestQueryOrchestratorRBACIntegration:
    def test_orchestrator_generates_cache_id_and_assigned_role(self, rbac_cache):
        """Orchestrator generates unique cache_id and respects user role in caching."""
        mock_retrieval = MagicMock()
        mock_retrieval.retrieve.return_value = [
            {
                "text": "Engineers must submit timesheets on Fridays by 5 PM.",
                "metadata": {
                    "source": "Engineering_Handbook.pdf",
                    "document_id": "doc_eng_handbook",
                    "section": "Timesheets",
                },
            }
        ]
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "Timesheets are due Fridays by 5 PM."

        orchestrator = QueryOrchestrator(
            retrieval=mock_retrieval,
            llm=mock_llm,
            response_cache=rbac_cache,
            employee_id_provider=MagicMock(get_employee_id=lambda *_: None),
        )

        user_context = {"role": "Engineer", "uid": "u_101"}
        scope = AuthorizationScope(
            is_admin=False,
            project_ids=["proj_core"],
            document_ids=["doc_eng_handbook"],
        )

        # 1. First call -> Cache Miss, generated answer with unique cache_id
        res1 = orchestrator.answer(
            question="When are timesheets due?",
            authorization_scope=scope,
            user_context=user_context,
        )
        assert res1["cache_hit"] is False
        assert res1["cache_id"] is not None
        assert res1["cache_id"].startswith("cch_")
        assert res1["assigned_role"] == "Engineer"

        first_cache_id = res1["cache_id"]

        # 2. Second call with matching role -> Cache Hit with same cache_id
        res2 = orchestrator.answer(
            question="When are timesheets due?",
            authorization_scope=scope,
            user_context=user_context,
        )
        assert res2["cache_hit"] is True
        assert res2["cache_id"] == first_cache_id
        assert res2["assigned_role"] == "Engineer"

        # 3. Third call by different role (Sales) lacking document permission -> Cache Miss (isolated)
        sales_context = {"role": "Sales", "uid": "u_202"}
        sales_scope = AuthorizationScope(
            is_admin=False,
            project_ids=["proj_sales"],
            document_ids=["doc_sales_catalog"],
        )
        # Configure retrieval to return empty for Sales to verify no cache hit leaks engineering data
        mock_retrieval.retrieve.return_value = []
        res3 = orchestrator.answer(
            question="When are timesheets due?",
            authorization_scope=sales_scope,
            user_context=sales_context,
        )
        # Must NOT return cached response from Engineer role
        assert res3["cache_hit"] is False


class TestDocumentLastUpdatedCacheInvalidation:
    def test_document_update_invalidates_cache_and_forces_llm_regeneration(self, rbac_cache):
        """
        When a document's Last_updated (updated_at) timestamp increases,
        any cached response citing that document must be invalidated,
        forcing QueryOrchestrator to generate a fresh LLM answer.
        """
        # Dynamic document timestamps dictionary simulating database state
        db_doc_timestamps = {
            "doc_hr_2026": 1000.0,
        }

        mock_retrieval = MagicMock()
        mock_retrieval.retrieve.return_value = [
            {
                "text": "Annual leave entitlement is 20 days per year.",
                "metadata": {
                    "source": "HR_Policy_2026.pdf",
                    "document_id": "doc_hr_2026",
                    "section": "Annual Leave",
                },
            }
        ]

        mock_llm = MagicMock()
        mock_llm.generate.return_value = "Employees receive 20 days of annual leave."

        orchestrator = QueryOrchestrator(
            retrieval=mock_retrieval,
            llm=mock_llm,
            faq_cache=None,
            response_cache=rbac_cache,
            employee_id_provider=MagicMock(get_employee_id=lambda *_: None),
            document_timestamp_lookup=lambda doc_id: db_doc_timestamps.get(doc_id),
        )

        user_context = {"role": "Employee", "uid": "u_301"}
        scope = AuthorizationScope(
            is_admin=False,
            project_ids=[],
            document_ids=["doc_hr_2026"],
        )

        # 1. First call: Cache miss -> LLM generates v1 answer
        res1 = orchestrator.answer(
            question="What is the annual leave entitlement?",
            authorization_scope=scope,
            user_context=user_context,
        )
        assert res1["cache_hit"] is False
        assert "20 days" in res1["answer"]
        v1_cache_id = res1["cache_id"]
        assert v1_cache_id is not None
        assert mock_llm.generate.call_count == 1

        # 2. Second call (document NOT updated): Cache Hit -> LLM is NOT called
        res2 = orchestrator.answer(
            question="What is the annual leave entitlement?",
            authorization_scope=scope,
            user_context=user_context,
        )
        assert res2["cache_hit"] is True
        assert "20 days" in res2["answer"]
        assert res2["cache_id"] == v1_cache_id
        assert mock_llm.generate.call_count == 1  # No additional LLM call

        # 3. Simulate Document Update in database:
        # Last_updated changes from 1000.0 -> 2000.0, and updated policy increases leave to 25 days
        db_doc_timestamps["doc_hr_2026"] = 2000.0
        mock_retrieval.retrieve.return_value = [
            {
                "text": "Annual leave entitlement has been increased to 25 days per year.",
                "metadata": {
                    "source": "HR_Policy_2026.pdf",
                    "document_id": "doc_hr_2026",
                    "section": "Annual Leave",
                },
            }
        ]
        mock_llm.generate.return_value = "Employees receive 25 days of annual leave under the revised policy."

        # 4. Third call: Cache detects document is updated -> Evicts stale cache -> Forces LLM generation
        res3 = orchestrator.answer(
            question="What is the annual leave entitlement?",
            authorization_scope=scope,
            user_context=user_context,
        )
        assert res3["cache_hit"] is False  # Stale cache was bypassed/evicted
        assert "25 days" in res3["answer"]  # Fresh LLM answer used!
        assert mock_llm.generate.call_count == 2  # LLM was invoked to generate fresh answer
        v2_cache_id = res3["cache_id"]
        assert v2_cache_id is not None
        assert v2_cache_id != v1_cache_id  # Fresh cache ID assigned

        # 5. Fourth call (at new document timestamp): Cache Hit with fresh answer
        res4 = orchestrator.answer(
            question="What is the annual leave entitlement?",
            authorization_scope=scope,
            user_context=user_context,
        )
        assert res4["cache_hit"] is True
        assert "25 days" in res4["answer"]
        assert res4["cache_id"] == v2_cache_id
        assert mock_llm.generate.call_count == 2  # Still 2 calls, served from new cache

    def test_multi_document_staleness_any_document_update_triggers_llm(self, rbac_cache):
        """If ANY of multiple cited documents is updated, stale cache is evicted and LLM is invoked."""
        db_doc_timestamps = {
            "doc_security_guideline": 500.0,
            "doc_remote_work": 500.0,
        }

        mock_retrieval = MagicMock()
        mock_retrieval.retrieve.return_value = [
            {
                "text": "VPN is required for all remote work.",
                "metadata": {"document_id": "doc_security_guideline", "source": "Security.pdf"},
            },
            {
                "text": "Remote work is permitted 2 days a week.",
                "metadata": {"document_id": "doc_remote_work", "source": "Remote.pdf"},
            },
        ]
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "Remote work requires VPN and is permitted 2 days per week."

        orchestrator = QueryOrchestrator(
            retrieval=mock_retrieval,
            llm=mock_llm,
            faq_cache=None,
            response_cache=rbac_cache,
            employee_id_provider=MagicMock(get_employee_id=lambda *_: None),
            document_timestamp_lookup=lambda doc_id: db_doc_timestamps.get(doc_id),
        )

        scope = AuthorizationScope(is_admin=False, project_ids=[], document_ids=["doc_security_guideline", "doc_remote_work"])
        user_context = {"role": "Employee", "uid": "u_302"}

        # Initial call -> LLM generated & cached
        res1 = orchestrator.answer("What is the remote work policy?", authorization_scope=scope, user_context=user_context)
        assert res1["cache_hit"] is False
        assert mock_llm.generate.call_count == 1

        # Second call -> Cache Hit
        res2 = orchestrator.answer("What is the remote work policy?", authorization_scope=scope, user_context=user_context)
        assert res2["cache_hit"] is True
        assert mock_llm.generate.call_count == 1

        # Update only ONE document: doc_remote_work updated to 800.0 (security doc untouched)
        db_doc_timestamps["doc_remote_work"] = 800.0
        mock_llm.generate.return_value = "Remote work now permitted 3 days a week with VPN."

        # Third call -> Single document update triggers eviction and LLM re-generation
        res3 = orchestrator.answer("What is the remote work policy?", authorization_scope=scope, user_context=user_context)
        assert res3["cache_hit"] is False
        assert mock_llm.generate.call_count == 2
        assert "3 days" in res3["answer"]

    def test_in_memory_cache_direct_document_staleness_eviction(self, rbac_cache):
        """Direct cache get evicts stale entry when document timestamp advances."""
        rbac_cache.put(
            cache_key="q_health_benefits",
            original_query="What are health benefits?",
            response="Dental and vision included.",
            assigned_role="Employee",
            document_ids=["doc_benefits"],
            doc_last_updated={"doc_benefits": 100.0},
        )

        # 1. At current timestamp (100.0) -> Cache Hit
        entry = rbac_cache.get(
            "q_health_benefits",
            role="Employee",
            document_timestamps={"doc_benefits": 100.0},
        )
        assert entry is not None
        assert entry.response == "Dental and vision included."

        # 2. Document updated to 150.0 -> Cache Miss & Stale Eviction
        entry_stale = rbac_cache.get(
            "q_health_benefits",
            role="Employee",
            document_timestamps={"doc_benefits": 150.0},
        )
        assert entry_stale is None
        stats = rbac_cache.get_stats()
        assert stats["stale_document_evictions"] >= 1

        # 3. Entry is completely evicted from internal cache dict
        assert "q_health_benefits" not in rbac_cache._cache

    def test_not_satisfied_feedback_clears_cache_and_shows_references(self, rbac_cache):
        """When user responds 'not satisfied', cache for that question is evicted and references are displayed."""
        mock_retrieval = MagicMock()
        mock_retrieval.retrieve.return_value = [
            {
                "text": "Salary payments are processed on the 1st of every month.",
                "metadata": {"document_id": "doc_payroll", "source": "Payroll_Policy.docx", "section": "Payments"},
            }
        ]
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "Salary payments are processed on the 1st."

        orchestrator = QueryOrchestrator(
            retrieval=mock_retrieval,
            llm=mock_llm,
            faq_cache=None,
            response_cache=rbac_cache,
            employee_id_provider=MagicMock(get_employee_id=lambda *_: None),
        )

        user_context = {"role": "Admin", "uid": "u_admin"}
        scope = AuthorizationScope(is_admin=True, project_ids=[], document_ids=["doc_payroll"])

        # 1. User asks question -> Answer generated and cached
        res1 = orchestrator.answer("how are Payments done?", authorization_scope=scope, user_context=user_context, session_id="s1")
        assert res1["cache_hit"] is False
        assert res1["is_latest"] is True

        # 2. User repeats question -> Cache Hit
        res2 = orchestrator.answer("how are Payments done?", authorization_scope=scope, user_context=user_context, session_id="s1")
        assert res2["cache_hit"] is True
        assert res2["is_latest"] is True

        # 3. User expresses dissatisfaction: "not satisfied"
        res3 = orchestrator.answer("not satisfied", authorization_scope=scope, user_context=user_context, session_id="s1")
        assert res3["cache_hit"] is False
        assert res3["show_citations"] is True
        assert len(res3["citations"]) > 0
        assert "references" in res3["answer"].lower()
        assert res3["is_latest"] is True

        # 4. User asks question again -> Cache Miss because "not satisfied" evicted it! Fresh LLM called!
        res4 = orchestrator.answer("how are Payments done?", authorization_scope=scope, user_context=user_context, session_id="s1")
        assert res4["cache_hit"] is False
        assert res4["is_latest"] is True


