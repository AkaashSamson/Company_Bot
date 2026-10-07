import sys, os
sys.path.insert(0, os.getcwd())

from app.infrastructure.persistence.factory import create_unit_of_work
from app.domain.services.authorization_engine import AuthorizationEngine
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.use_cases.chat.retrieval_service import RetrievalService
from app.use_cases.chat.query_orchestrator import QueryOrchestrator
from app.infrastructure.cache.dual_cache import get_dual_cache

# 1. Setup Abhinav's principal and scope
auth = AuthorizationEngine(create_unit_of_work)
principal = AuthenticatedPrincipal("fbca51f22b6248698ee2b8122e94a3a7")
scope = auth.authorization_scope(principal)

print("Abhinav Scope:", scope)

retrieval = RetrievalService(collection_name="hr_policy_docs", persist_directory=".chroma")
cache = get_dual_cache()

# Dummy LLM to verify if LLM is called
class MockLLM:
    def __init__(self):
        self.called = False
    def generate(self, *args, **kwargs):
        self.called = True
        return "Generated answer from LLM."

mock_llm = MockLLM()

orchestrator = QueryOrchestrator(
    retrieval=retrieval,
    llm=mock_llm,
    response_cache=cache,
)

# Populate a cache entry for project 121 / DOC-005 if not already present
cache.put(
    cache_key="what should the objective be on the first day?",
    original_query="what should the objective be on the first day?",
    response="First-Week Objectives: focus on understanding core architecture.",
    cache_id="cch_p121_firstday",
    document_ids=["DOC-005"],
    project_ids=["121"],
)

# Test 1: Abhinav asks the question
# Should NOT get cache hit from project 121
# Retrieval should detect unauthorized relevance from project 121 and return manager contact prompt
res_abhinav = orchestrator.answer(
    question="what should the objective be on the first day?",
    authorization_scope=scope,
    user_context={"role": "Employee", "uid": "fbca51f22b6248698ee2b8122e94a3a7"},
    session_id="test_abhinav_sess",
)

print("\n--- ABHINAV RESPONSE ---")
print("Cache Hit:", res_abhinav.get("cache_hit"))
print("Answer:\n", res_abhinav.get("answer"))
print("LLM was called:", mock_llm.called)

# Test 2: Admin asks the question
from app.domain.services.authorization_engine import AuthorizationScope
admin_scope = AuthorizationScope(is_admin=True, project_ids=None, document_ids=None)
res_admin = orchestrator.answer(
    question="what should the objective be on the first day?",
    authorization_scope=admin_scope,
    user_context={"role": "Admin", "uid": "admin_uid"},
    session_id="test_admin_sess",
)

print("\n--- ADMIN RESPONSE ---")
print("Cache Hit:", res_admin.get("cache_hit"))
print("Answer:\n", res_admin.get("answer"))

# Test 3: User with Project 121 asks the question
p121_scope = AuthorizationScope(is_admin=False, project_ids=["121"], document_ids=None)
res_p121 = orchestrator.answer(
    question="what should the objective be on the first day?",
    authorization_scope=p121_scope,
    user_context={"role": "Employee", "uid": "p121_uid"},
    session_id="test_p121_sess",
)

print("\n--- PROJECT 121 USER RESPONSE ---")
print("Cache Hit:", res_p121.get("cache_hit"))
print("Answer:\n", res_p121.get("answer"))
