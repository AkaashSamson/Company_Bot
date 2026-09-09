import pytest

from app.infrastructure.channels.teams.handler import create_message_handler


class FakeOrchestrator:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or {"answer": "Mock answer", "citations": []}

    def answer(self, question, conversation_history=None):
        self.calls.append(
            {
                "question": question,
                "conversation_history": conversation_history,
            }
        )
        return self.result


class FakeActivity:
    def __init__(self, text):
        self.text = text


class FakeContext:
    def __init__(self, text):
        self.activity = FakeActivity(text)
        self.sent_messages = []

    async def send(self, message):
        self.sent_messages.append(message)


@pytest.mark.asyncio
async def test_handler_calls_orchestrator_and_sends_formatted_response():
    orchestrator = FakeOrchestrator(
        {
            "answer": "Employees receive annual leave.",
            "citations": [
                {
                    "source": "handbook.docx",
                    "section": "Annual Leave",
                    "text": "Employees receive 20 days.",
                }
            ],
        }
    )
    handler = create_message_handler(orchestrator)
    context = FakeContext("What is the leave policy?")

    await handler(context)

    assert orchestrator.calls == [
        {
            "question": "What is the leave policy?",
            "conversation_history": None,
        }
    ]
    assert len(context.sent_messages) == 1
    assert "Employees receive annual leave." in context.sent_messages[0]
    assert "Annual Leave" in context.sent_messages[0]


@pytest.mark.asyncio
async def test_handler_trims_incoming_message():
    orchestrator = FakeOrchestrator()
    handler = create_message_handler(orchestrator)
    context = FakeContext("  What is the leave policy?  ")

    await handler(context)

    assert orchestrator.calls[0]["question"] == "What is the leave policy?"


@pytest.mark.asyncio
async def test_handler_rejects_empty_message_without_calling_orchestrator():
    orchestrator = FakeOrchestrator()
    handler = create_message_handler(orchestrator)
    context = FakeContext("   ")

    await handler(context)

    assert orchestrator.calls == []
    assert context.sent_messages == ["Please send a question about the policy."]