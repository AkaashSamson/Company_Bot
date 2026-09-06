from app.domain.services.session_memory_service import SessionMemoryService
from app.use_cases.chat.conversation_query_resolver import ConversationQueryResolver


class MockLLM:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate(self, messages):
        self.calls.append(messages)
        return self.response


def history():
    return [
        {"role": "user", "content": "How many sick leaves do I get?"},
        {"role": "assistant", "content": "Eligible employees receive 10 days."},
    ]


def test_standalone_question_does_not_call_llm():
    llm = MockLLM("should not be used")
    resolver = ConversationQueryResolver(llm)

    result = resolver.resolve("What is the annual leave policy?", history())

    assert result == "What is the annual leave policy?"
    assert llm.calls == []


def test_dependent_follow_up_is_rewritten_for_retrieval():
    llm = MockLLM("What is the sick leave carry-forward policy?")
    resolver = ConversationQueryResolver(llm)

    result = resolver.resolve("What about carrying them forward?", history())

    assert result == "What is the sick leave carry-forward policy?"
    assert len(llm.calls) == 1
    assert "What about carrying them forward?" in llm.calls[0][1]["content"]


def test_history_is_bounded_before_rewrite_prompt():
    llm = MockLLM("standalone query")
    resolver = ConversationQueryResolver(
        llm,
        memory=SessionMemoryService(max_messages=2),
    )
    long_history = history() + [
        {"role": "user", "content": "Old question"},
        {"role": "assistant", "content": "Old answer"},
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier answer"},
    ]

    resolver.resolve("What about that?", long_history)

    prompt = llm.calls[0][1]["content"]
    assert "Old question" not in prompt
    assert "Earlier answer" in prompt


def test_unrelated_follow_up_can_remain_independent():
    llm = MockLLM("What are India's current tax rates?")
    resolver = ConversationQueryResolver(llm)

    result = resolver.resolve("What about India's current tax rates?", history())

    assert result == "What are India's current tax rates?"


def test_multi_part_follow_up_rewrite_preserves_all_information_needs():
    llm = MockLLM(
        "What are the policies for sick leave carry-forward and medical documentation?"
    )
    resolver = ConversationQueryResolver(llm)

    result = resolver.resolve(
        "What about carry-forward and medical documentation?",
        history(),
    )

    assert "carry-forward" in result
    assert "medical documentation" in result