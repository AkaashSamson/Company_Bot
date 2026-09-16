"""End-to-end: the RAG chatbot never exposes unauthorized document chunks to the
LLM. When relevant content exists only outside the authorized scope, it returns
a safe access-request response and never invokes the LLM.

Runs against a real Chroma vector store (SentenceTransformer embeddings).
"""
import base64
import tempfile

import pytest

import app.infrastructure.ingestion.provisioner as provisioner
from app.domain.entities.organization_models import Document
from app.domain.services.authorization_engine import AuthorizationScope
from app.infrastructure.ingestion.provisioner import provision_document
from app.infrastructure.vector.chroma_client import ChromaVectorStore
from app.use_cases.chat.query_orchestrator import QueryOrchestrator
from app.use_cases.chat.retrieval_service import RetrievalService

UNAUTHORIZED_MARKER = "caboodle"

class CapturingLLM:
    def __init__(self):
        self.messages = None

    def generate(self, messages):
        self.messages = messages
        return "10 days per year."


class FixedResolver:
    def resolve(self, question, history):
        return question


class EvidenceProvenance:
    def build_citations(self, results):
        return [{"text": item["text"]} for item in results]


@pytest.fixture(scope="module")
def orchestrator_fixture():
    tmpdir = tempfile.mkdtemp(prefix="rag_authz_")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(provisioner, "DOCUMENTS_DIR", tmpdir)
    monkeypatch.setattr(provisioner, "COLLECTION_NAME", "test_rag_authz_collection")

    store = ChromaVectorStore(
        collection_name="test_rag_authz_collection",
        persist_directory=f"{tmpdir}/chroma",
    )

    doc_a = Document("docA", "Project_Alpha_Records.txt", project_id="p1", version="1.0")
    provision_document(
        None,
        doc_a,
        base64.b64encode(
            b"Project alpha accounting records contain trial balances for the "
            b"general ledger printed quarterly."
        ).decode("utf-8"),
        store=store,
    )

    doc_b = Document("docB", "Project_Bravo_Leave.txt", project_id="p2", version="1.0")
    provision_document(
        None,
        doc_b,
        base64.b64encode(
            b"the annual leave policy is held in the confidential caboodle "
            b"vault and employees receive twenty days"
        ).decode("utf-8"),
        store=store,
    )

    doc_c = Document("docC", "Global_Onboarding.txt", project_id=None, version="1.0")
    provision_document(
        None,
        doc_c,
        base64.b64encode(
            b"the global onboarding handbook covers manticore orientation "
            b"and first week buddy assignments."
        ).decode("utf-8"),
        store=store,
    )

    svc = RetrievalService.__new__(RetrievalService)
    svc.store = store

    def contact_lookup(project_id):
        return {
            "project_id": project_id,
            "project_name": "Project Bravo",
            "manager_name": "Sara Blake",
        }

    orchestrator = QueryOrchestrator(
        retrieval=svc,
        provenance=EvidenceProvenance(),
        query_resolver=FixedResolver(),
        project_contact_lookup=contact_lookup,
    )
    yield {"store": store, "svc": svc, "orchestrator": orchestrator}
    monkeypatch.undo()


def test_unauthorized_document_never_reaches_llm(orchestrator_fixture):
    llm = CapturingLLM()
    orchestrator_fixture["orchestrator"].llm = llm

    result = orchestrator_fixture["orchestrator"].answer(
        "What is the annual leave entitlement across the organization?",
        authorized_project_ids=["p1"],
    )

    assert llm.messages is None, "LLM must never be invoked for unauthorized content"
    assert result["citations"] == []
    assert UNAUTHORIZED_MARKER not in result["answer"]
    assert "do not currently have access to" in result["answer"]
    assert "Project Bravo" in result["answer"]
    assert "Sara Blake" in result["answer"]


def test_safe_response_uses_redacted_project_metadata_only(orchestrator_fixture):
    llm = CapturingLLM()
    orchestrator_fixture["orchestrator"].llm = llm

    result = orchestrator_fixture["orchestrator"].answer(
        "What is the annual leave entitlement across the organization?",
        authorized_project_ids=["p1"],
    )

    joined = " ".join(result["answer"].split()).lower()
    for leaked in [
        "twenty days",
        "vault",
        "buddy",
        "manticore",
        "trial balances",
        "Leave.txt",
    ]:
        assert leaked not in joined


def test_authorized_evidence_grounds_response_and_never_leaks_unauthorized_other(orchestrator_fixture):
    llm = CapturingLLM()
    orchestrator_fixture["orchestrator"].llm = llm

    result = orchestrator_fixture["orchestrator"].answer(
        "What is the accounting trial balance policy?",
        authorized_project_ids=["p1"],
    )

    assert llm.messages is not None
    assert result["citations"] != []
    content = " ".join(m["content"] for m in llm.messages if m.get("content"))
    assert UNAUTHORIZED_MARKER not in content
    assert "do not currently have access to" not in result["answer"]


def test_not_found_message_preserved_when_nothing_relevant_anywhere(orchestrator_fixture):
    llm = CapturingLLM()
    orchestrator_fixture["orchestrator"].llm = llm

    result = orchestrator_fixture["orchestrator"].answer(
        "What is the office nap entitlement?",
        authorized_project_ids=["p1"],
    )

    assert llm.messages is None
    assert "could not find" in result["answer"].lower()
    assert result["citations"] == []


def test_admin_scope_never_produces_access_denied_response(orchestrator_fixture):
    llm = CapturingLLM()
    orchestrator_fixture["orchestrator"].llm = llm

    result = orchestrator_fixture["orchestrator"].answer(
        "What is the annual leave policy?",
        authorization_scope=AuthorizationScope(is_admin=True),
    )

    assert llm.messages is not None
    assert result["citations"] != []
    assert "do not currently have access to" not in result["answer"]