"""
Integration test verifying multi-turn topic fidelity and no-substitution rule.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_authorization_service, get_chat_principal
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationScope
from app.main import app


class AdminAuthorization:
    def is_admin(self, principal):
        return True

    def authorization_scope(self, principal, selected_project_id=None):
        return AuthorizationScope(
            is_admin=True,
            project_ids=None,
            document_ids=None,
            include_unassigned=True,
        )


@pytest.fixture(autouse=True)
def _auth_override():
    app.dependency_overrides[get_chat_principal] = lambda: AuthenticatedPrincipal("admin")
    app.dependency_overrides[get_authorization_service] = lambda: AdminAuthorization()
    yield
    app.dependency_overrides.clear()


def test_sick_leave_followup_topic_fidelity():
    """Verify follow-up question adheres to topic memory and does not substitute unrelated policy."""
    client = TestClient(app)
    session_id = "test-session-sick-followup-multi"

    # Turn 1: Ask about sick leaves
    r1 = client.post(
        "/api/chat",
        json={
            "question": "how many sick leaves I have?",
            "session_id": session_id,
            "conversation_history": [],
        },
    )
    assert r1.status_code == 200, f"Turn 1 failed: {r1.text}"
    body1 = r1.json()
    a1 = body1.get("answer", "")
    assert len(a1) > 0, "Turn 1 answer should not be empty"

    # Turn 2: Follow-up question with conversation history
    r2 = client.post(
        "/api/chat",
        json={
            "question": "how many get carried forward?",
            "session_id": session_id,
            "conversation_history": [
                {"role": "user", "content": "how many sick leaves I have?"},
                {"role": "assistant", "content": a1},
            ],
        },
    )
    assert r2.status_code == 200, f"Turn 2 failed: {r2.text}"
    body2 = r2.json()
    a2 = body2.get("answer", "").lower()

    print(f"\n[TURN 1 ANSWER]:\n{a1}")
    print(f"\n[TURN 2 ANSWER]:\n{body2.get('answer')}")

    # The model must not present Annual Leave as the primary answer to the sick leave follow-up
    # It should mention sick leave or state that carry forward is not specified for sick leave
    assert (
        "sick" in a2
        or "not specify" in a2
        or "does not mention" in a2
        or "could not find" in a2
        or "not normally" in a2
        or "cannot" in a2
    ), f"Expected answer to address sick leave context or state lack of info, got: {body2.get('answer')}"
