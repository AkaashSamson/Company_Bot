from unittest.mock import MagicMock

from app.infrastructure.faq.mongo_faq_store import MongoFAQStore


def test_faq_store_is_disabled_without_mongodb_uri():
    store = MongoFAQStore(uri="")

    store.save("Question", "Answer", [])

    assert store.enabled is False


def test_faq_store_upserts_normalized_question():
    collection = MagicMock()
    client = MagicMock()
    client.__getitem__.return_value.__getitem__.return_value = collection
    store = MongoFAQStore(uri="mongodb://localhost", client=client)

    store.save(
        "  How many leave days do I get? ",
        "18 days.",
        [{"source": "handbook.docx", "text": "18 days."}],
    )

    collection.create_index.assert_called_once_with("question_key", unique=True)
    collection.update_one.assert_called_once()
    filter_document, update_document = collection.update_one.call_args.args[:2]
    assert filter_document == {"question_key": "how many leave days do i get?"}
    assert update_document["$set"]["question"] == "How many leave days do I get?"
    assert update_document["$set"]["answer"] == "18 days."
    assert update_document["$setOnInsert"]["created_at"]
    assert collection.update_one.call_args.kwargs["upsert"] is True