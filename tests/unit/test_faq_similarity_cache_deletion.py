import json
from unittest.mock import Mock, patch
import pytest

from app.infrastructure.faq.faq_similarity_cache import FAQSimilarityCache
from app.use_cases.chat.query_orchestrator import (
    QueryOrchestrator,
    _pending_citations,
    _last_interaction,
    _alternative_answer_given,
)


@pytest.fixture(autouse=True)
def clean_orchestrator_state():
    _pending_citations.clear()
    _last_interaction.clear()
    _alternative_answer_given.clear()
    yield
    _pending_citations.clear()
    _last_interaction.clear()
    _alternative_answer_given.clear()


def test_faq_similarity_cache_delete_entry_persists_and_reindexes(tmp_path):
    faqs_data = [
        {"id": "FAQ.1", "question": "What is the probation period?", "answer": "Probation is 3 months."},
        {"id": "FAQ.2", "question": "How do payment policies work?", "answer": "Salaries are paid monthly."},
    ]
    faq_file = tmp_path / "test_faqs.json"
    faq_file.write_text(json.dumps(faqs_data), encoding="utf-8")

    cache = FAQSimilarityCache(faq_path=str(faq_file), enabled=True)
    assert cache.size() == 2

    # Delete by ID
    deleted = cache.delete_entry("FAQ.2")
    assert deleted is True
    assert cache.size() == 1
    assert cache._entries[0]["id"] == "FAQ.1"

    # Verify JSON file on disk was updated
    disk_content = json.loads(faq_file.read_text(encoding="utf-8"))
    assert len(disk_content) == 1
    assert disk_content[0]["id"] == "FAQ.1"

    # Delete by question text (case-insensitive)
    deleted_q = cache.delete_entry("what is the probation period?")
    assert deleted_q is True
    assert cache.size() == 0
    assert cache._matrix is None

    disk_content_empty = json.loads(faq_file.read_text(encoding="utf-8"))
    assert len(disk_content_empty) == 0


def test_faq_similarity_cache_clear_and_reload(tmp_path):
    faqs_data = [
        {"id": "1", "question": "Sample question?", "answer": "Sample answer."}
    ]
    faq_file = tmp_path / "test_faqs.json"
    faq_file.write_text(json.dumps(faqs_data), encoding="utf-8")

    cache = FAQSimilarityCache(faq_path=str(faq_file), enabled=True)
    assert cache.size() == 1

    cache.clear()
    assert cache.size() == 0
    assert cache._matrix is None

    # Reload from disk
    reloaded = cache.reload()
    assert reloaded is True
    assert cache.size() == 1


def test_query_orchestrator_evicts_faq_cache_on_rejection(tmp_path):
    faqs_data = [
        {"id": "P.1", "question": "How are payment policies done?", "answer": "Overpaid salary will be deducted."}
    ]
    faq_file = tmp_path / "test_faqs.json"
    faq_file.write_text(json.dumps(faqs_data), encoding="utf-8")

    cache = FAQSimilarityCache(faq_path=str(faq_file), threshold=0.5, enabled=True)

    orchestrator = QueryOrchestrator(
        faq_cache=cache,
        response_cache=None,
    )

    # 1. Query hits the FAQ cache
    res1 = orchestrator.answer("How are payment policies done?", session_id="session-p1")
    assert res1["cache_hit"] is True
    assert "Overpaid salary will be deducted." in res1["answer"]
    assert cache.size() == 1

    # 2. User responds with negative feedback
    history = [
        {"role": "user", "content": "How are payment policies done?"},
        {"role": "assistant", "content": res1["answer"]},
    ]
    res2 = orchestrator.answer(
        "no, not relevant",
        conversation_history=history,
        session_id="session-p1",
    )

    # 3. Assert FAQ cache evicted the rejected entry
    assert cache.size() == 0
    disk_content = json.loads(faq_file.read_text(encoding="utf-8"))
    assert len(disk_content) == 0
