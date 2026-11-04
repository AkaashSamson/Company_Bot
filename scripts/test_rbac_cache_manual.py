"""
KnowLayer - RBAC Cache Manual Validation Script.

Run directly via:
    .venv\\Scripts\\python.exe scripts/test_rbac_cache_manual.py

Validates the 5 Core RBAC Caching Guarantees:
1. Strict Role Scoping: Only the matching role receives a cache hit.
2. Cross-Role Isolation: Unauthorized roles receive a cache miss (zero leakage).
3. Document & Project Authorization Scoping: Users missing document/project permissions receive a cache miss.
4. Admin Universal Bypass: Admins can retrieve cached responses across all roles/documents.
5. Real-Time Document Freshness Eviction: Updating a document's timestamp automatically evicts stale cache entries.
"""

import sys
import os
import time

sys.path.insert(0, os.path.abspath("."))

from app.infrastructure.cache.quality_aware_cache import (
    InMemoryQualityAwareCache,
    CacheEntrySource,
)

def run_rbac_cache_manual_test():
    print("=" * 70)
    print("  KNOWLAYER - MANUAL RBAC CACHING VERIFICATION")
    print("=" * 70)

    cache = InMemoryQualityAwareCache(
        max_entries=100,
        ttl_seconds=3600.0,
        min_confidence_threshold=0.60,
    )

    # -------------------------------------------------------------------------
    # TEST CASE 1: Role-Scoped Entry
    # -------------------------------------------------------------------------
    print("\n[Step 1] Putting Role-Restricted Entry into Cache...")
    put_ok = cache.put(
        cache_key="q_engineering_deploy",
        original_query="What is the production deployment procedure?",
        response="Deployments require CI approval from @lead-dev and must be performed on Tuesdays.",
        confidence=0.95,
        assigned_role="Developer",
        document_ids=["doc_engineering_ops_01"],
        project_ids=["proj_core_platform"],
        doc_last_updated={"doc_engineering_ops_01": 1000.0},
        source=CacheEntrySource.RAG_GENERATED,
    )
    print(f"  --> Stored successfully: {put_ok}")
    assert put_ok, "Failed to put entry into cache!"

    # -------------------------------------------------------------------------
    # TEST CASE 2: Developer Queries (Role Match + Document Match) -> HIT
    # -------------------------------------------------------------------------
    print("\n[Step 2] Testing Authorized Developer Access (Role='Developer', Has Doc & Project)...")
    res_dev = cache.get(
        "q_engineering_deploy",
        role="Developer",
        document_ids=["doc_engineering_ops_01", "doc_public_faq"],
        project_ids=["proj_core_platform"],
    )
    if res_dev:
        print(f"  --> [PASS] CACHE HIT! Response: \"{res_dev.response[:50]}...\"")
        print(f"             Cache ID: {res_dev.metadata.cache_id} | Assigned Role: {res_dev.metadata.assigned_role}")
    else:
        print("  --> [FAIL] Expected CACHE HIT but got MISS!")
    assert res_dev is not None

    # -------------------------------------------------------------------------
    # TEST CASE 3: Role Mismatch (Role='Finance') -> MISS (RBAC Denial)
    # -------------------------------------------------------------------------
    print("\n[Step 3] Testing Cross-Role Access (Role='Finance')...")
    res_finance = cache.get(
        "q_engineering_deploy",
        role="Finance",
        document_ids=["doc_engineering_ops_01"],
        project_ids=["proj_core_platform"],
    )
    if res_finance is None:
        print("  --> [PASS] CACHE MISS (Protected): Finance user denied access to Developer cache.")
    else:
        print("  --> [FAIL] Security Leak: Finance received Developer response!")
    assert res_finance is None

    # -------------------------------------------------------------------------
    # TEST CASE 4: Missing Document Authorization -> MISS (Doc Denial)
    # -------------------------------------------------------------------------
    print("\n[Step 4] Testing Missing Document Access (Role='Developer', Lacks Cited Doc)...")
    res_nodoc = cache.get(
        "q_engineering_deploy",
        role="Developer",
        document_ids=["doc_some_unrelated_doc"],
        project_ids=["proj_core_platform"],
    )
    if res_nodoc is None:
        print("  --> [PASS] CACHE MISS (Protected): Developer without doc permission denied.")
    else:
        print("  --> [FAIL] Security Leak: User without doc access received cached response!")
    assert res_nodoc is None

    # -------------------------------------------------------------------------
    # TEST CASE 5: Missing Project Authorization -> MISS (Project Denial)
    # -------------------------------------------------------------------------
    print("\n[Step 5] Testing Missing Project Access (Role='Developer', Unassigned Project)...")
    res_noproj = cache.get(
        "q_engineering_deploy",
        role="Developer",
        document_ids=["doc_engineering_ops_01"],
        project_ids=["proj_marketing_campaign"],
    )
    if res_noproj is None:
        print("  --> [PASS] CACHE MISS (Protected): Developer without project permission denied.")
    else:
        print("  --> [FAIL] Security Leak: User without project access received cached response!")
    assert res_noproj is None

    # -------------------------------------------------------------------------
    # TEST CASE 6: Admin Universal Access -> HIT
    # -------------------------------------------------------------------------
    print("\n[Step 6] Testing Admin Access (is_admin=True)...")
    res_admin = cache.get(
        "q_engineering_deploy",
        is_admin=True,
    )
    if res_admin:
        print(f"  --> [PASS] CACHE HIT! Admin bypassed role restrictions as expected.")
    else:
        print("  --> [FAIL] Expected Admin CACHE HIT but got MISS!")
    assert res_admin is not None

    # -------------------------------------------------------------------------
    # TEST CASE 7: Document Freshness Invalidation -> EVICTION & MISS
    # -------------------------------------------------------------------------
    print("\n[Step 7] Testing Document Freshness Invalidation (doc_engineering_ops_01 updated to 1500.0)...")
    res_stale = cache.get(
        "q_engineering_deploy",
        role="Developer",
        document_ids=["doc_engineering_ops_01"],
        project_ids=["proj_core_platform"],
        document_timestamps={"doc_engineering_ops_01": 1500.0},  # Newer than 1000.0
    )
    if res_stale is None:
        print("  --> [PASS] CACHE MISS: Stale entry evicted automatically due to document update.")
    else:
        print("  --> [FAIL] Stale response was served after document update!")
    assert res_stale is None

    # -------------------------------------------------------------------------
    # Summary of Cache Stats
    # -------------------------------------------------------------------------
    stats = cache.get_stats()
    print("\n" + "=" * 70)
    print("  RBAC CACHE STATS SUMMARY")
    print("=" * 70)
    print(f"  Total Cache Hits:            {stats.get('hits', 0)}")
    print(f"  Total Cache Misses:          {stats.get('misses', 0)}")
    print(f"  RBAC Access Denials:         {stats.get('rbac_denials', 0)} (Cross-role/doc access prevented)")
    print(f"  Stale Document Evictions:    {stats.get('stale_document_evictions', 0)}")
    print("=" * 70)
    print("  ALL RBAC CACHING GATES VERIFIED SUCCESSFULLY!\n")

if __name__ == "__main__":
    run_rbac_cache_manual_test()
