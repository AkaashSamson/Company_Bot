from app.core.prompt_config import load_prompt


def test_load_prompt_existing_section():
    prompt = load_prompt("conversation_query_rewrite")
    assert "Rewrite a dependent follow-up as one standalone search query" in prompt


def test_load_prompt_rag_answer_generation():
    prompt = load_prompt("rag_answer_generation")
    assert "You are a helpful company knowledge assistant" in prompt


def test_load_prompt_nonexistent_returns_fallback_or_empty():
    assert load_prompt("non_existent_section_xyz") == ""
