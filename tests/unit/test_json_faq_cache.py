import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.infrastructure.faq.json_faq_cache import JsonFAQCache


def test_json_faq_cache_load_non_existent_file(tmp_path):
    cache = JsonFAQCache(tmp_path / "missing.json")
    assert cache.load() is None


def test_json_faq_cache_save_and_load(tmp_path):
    file_path = tmp_path / "faqs.json"
    cache = JsonFAQCache(file_path)
    data = {
        "faqs": "1. What is the policy?",
        "citations": [{"source": "doc.docx"}],
    }

    cache.save(data)
    loaded = cache.load()

    assert loaded is not None
    assert loaded["faqs"] == "1. What is the policy?"
    assert loaded["citations"] == [{"source": "doc.docx"}]


def test_json_faq_cache_load_with_entries(tmp_path):
    file_path = tmp_path / "faqs_entries.json"
    cache = JsonFAQCache(file_path)
    data = {
        "entries": [
            {"input": "Q1?", "output": "A1"},
            {"input": "Q2?", "output": "A2"},
        ]
    }
    cache.save(data)
    loaded = cache.load()

    assert loaded is not None
    assert "faqs" in loaded
    assert "Q1?\nA1\n\nQ2?\nA2" in loaded["faqs"]


def test_json_faq_cache_load_invalid_json(tmp_path):
    file_path = tmp_path / "corrupted.json"
    file_path.write_text("invalid json content", encoding="utf-8")
    cache = JsonFAQCache(file_path)

    assert cache.load() is None


@patch("app.infrastructure.faq.json_faq_cache.SentenceTransformer")
def test_json_faq_cache_migrate_to_entries(mock_transformer_cls, tmp_path):
    mock_model = MagicMock()
    mock_model.encode.return_value.tolist.return_value = [0.1, 0.2]
    mock_transformer_cls.return_value = mock_model

    file_path = tmp_path / "faqs_legacy.json"
    cache = JsonFAQCache(file_path)
    legacy_data = {
        "faqs": "19.1 How do I apply?\nSubmit via HR portal.\n20. What is annual leave?\n18 days per year.",
        "citations": [{"source": "handbook.pdf"}],
    }
    cache.save(legacy_data)

    migrated = cache.migrate_to_entries()
    assert migrated is not None
    assert "entries" in migrated
    assert len(migrated["entries"]) == 2
    assert migrated["entries"][0]["input"] == "19.1 How do I apply?"
    assert migrated["entries"][0]["output"] == "Submit via HR portal."
    assert migrated["entries"][0]["input_vector"] == [0.1, 0.2]
