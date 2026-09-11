"""
Example: How to use the LLM with ChromaDB-retrieved context.

This file demonstrates the complete RAG pipeline and how to configure
the LLM to generate answers based exclusively on ChromaDB retrieval.
"""

from app.use_cases.chat.retrieval_service import RetrievalService
from app.use_cases.chat.rag_context_builder import RAGContextBuilder
from app.infrastructure.llm.openrouter_client import OpenRouterClient
from app.infrastructure.llm.fallback_llm_provider import FallbackLLMProvider
from app.infrastructure.llm.groq_client import GroqClient


def example_1_basic_chromadb_rag():
    """
    Example 1: Basic RAG pipeline
    Retrieve from ChromaDB and generate answer based on context.
    """
    print("=" * 60)
    print("EXAMPLE 1: Basic ChromaDB RAG Pipeline")
    print("=" * 60)

    # Step 1: Retrieve relevant documents from ChromaDB
    retrieval = RetrievalService()
    question = "What is the leave policy?"
    documents = retrieval.retrieve(question, top_k=3)

    print(f"\n1. Retrieved {len(documents)} documents from ChromaDB")
    for i, doc in enumerate(documents, 1):
        print(f"\n   [{i}] Distance: {doc.get('distance', 'N/A'):.4f}")
        print(f"       Text: {doc.get('text', '')[:100]}...")

    # Step 2: Format documents into LLM prompt
    context_builder = RAGContextBuilder()
    messages = context_builder.build_messages(
        question=question,
        context_chunks=documents,
        include_system_prompt=True,
    )

    print(f"\n2. Built {len(messages)} messages for LLM")
    print("\n   User Message Preview:")
    user_msg = [m for m in messages if m["role"] == "user"][0]
    print(f"   {user_msg['content'][:200]}...")

    # Step 3: Generate answer using LLM
    llm = OpenRouterClient()
    answer = llm.generate(messages)

    print(f"\n3. LLM Generated Answer:")
    print(f"   {answer}")

    # Step 4: Build citations
    citations = context_builder.format_evidence_for_citations(documents)
    print(f"\n4. Extracted {len(citations)} citations:")
    for i, cite in enumerate(citations, 1):
        print(f"   [{i}] {cite.get('section', 'N/A')}")


def example_2_with_fallback():
    """
    Example 2: RAG with fallback LLM provider
    Uses OpenRouter as primary, falls back to Groq if unavailable.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 2: RAG with Fallback LLM Provider")
    print("=" * 60)

    # Step 1: Create LLM provider with fallback
    primary = OpenRouterClient()
    fallback = GroqClient()
    llm = FallbackLLMProvider(primary=primary, fallback=fallback)

    # Step 2: Retrieve and build context (same as Example 1)
    retrieval = RetrievalService()
    question = "What are the benefits?"
    documents = retrieval.retrieve(question, top_k=3)

    context_builder = RAGContextBuilder()
    messages = context_builder.build_messages(
        question=question,
        context_chunks=documents,
        include_system_prompt=True,
    )

    # Step 3: Generate with fallback (tries OpenRouter, uses Groq if fails)
    try:
        answer = llm.generate(messages)
        print(f"\nAnswer from LLM:")
        print(f"   {answer}")
    except Exception as e:
        print(f"\nLLM Error: {e}")


def example_3_custom_system_prompt():
    """
    Example 3: Custom system prompt for specific behavior
    Shows how to customize the LLM's behavior.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Custom System Prompt")
    print("=" * 60)

    # Create context builder with default settings
    context_builder = RAGContextBuilder()

    # Retrieve documents
    retrieval = RetrievalService()
    question = "What is the remote work policy?"
    documents = retrieval.retrieve(question, top_k=3)

    # Build messages with custom system prompt
    custom_system = (
        "You are an expert HR consultant. Answer questions about the company's "
        "HR policies based ONLY on the provided documents. If you don't know, "
        "say so clearly. Format your answer in numbered points if applicable."
    )

    messages = [
        {"role": "system", "content": custom_system},
        {
            "role": "user",
            "content": context_builder.build_user_prompt(question, documents),
        },
    ]

    print(f"\nCustom System Prompt:")
    print(f"   {custom_system}")

    # Generate with custom prompt
    llm = OpenRouterClient()
    answer = llm.generate(messages)

    print(f"\nAnswer with Custom Prompt:")
    print(f"   {answer}")


def example_4_no_context_handling():
    """
    Example 4: Handling when no relevant documents are found
    Shows graceful degradation when ChromaDB retrieval fails.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 4: No Context Handling")
    print("=" * 60)

    retrieval = RetrievalService()
    context_builder = RAGContextBuilder()

    # Use a very specific question unlikely to match
    question = "What is the exact DNA sequence of the CEO?"
    documents = retrieval.retrieve(question, top_k=3)

    print(f"\nQuestion: {question}")
    print(f"Retrieved documents: {len(documents)}")

    if not documents:
        print("\n✓ No documents retrieved - returning fallback message")
        fallback_message = "I could not find that information in the available documents."
        print(f"Fallback: {fallback_message}")
    else:
        # Normal flow
        messages = context_builder.build_messages(
            question=question,
            context_chunks=documents,
        )
        llm = OpenRouterClient()
        answer = llm.generate(messages)
        print(f"\nAnswer: {answer}")


def example_5_performance_tuning():
    """
    Example 5: Performance tuning parameters
    Shows how different configuration affects retrieval and generation.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 5: Performance Tuning")
    print("=" * 60)

    retrieval = RetrievalService()
    context_builder = RAGContextBuilder()
    question = "What is the payment policy?"

    # Configuration 1: More context (accuracy-focused)
    print("\nConfiguration 1: Accuracy-Focused")
    print("  RAG_MAX_EVIDENCE=5 (more context)")
    print("  RAG_DISTANCE_THRESHOLD=0.60 (lower threshold = more docs)")
    docs_accurate = retrieval.retrieve(question, top_k=5)
    print(f"  → Retrieved {len(docs_accurate)} documents")

    # Configuration 2: Less context (speed-focused)
    print("\nConfiguration 2: Speed-Focused")
    print("  RAG_MAX_EVIDENCE=1 (less context)")
    print("  RAG_DISTANCE_THRESHOLD=0.40 (higher threshold = fewer docs)")
    docs_fast = retrieval.retrieve(question, top_k=1)
    print(f"  → Retrieved {len(docs_fast)} documents")

    # Build messages for both
    messages_accurate = context_builder.build_messages(
        question=question,
        context_chunks=docs_accurate,
    )
    messages_fast = context_builder.build_messages(
        question=question,
        context_chunks=docs_fast,
    )

    print(f"\nAccuracy-Focused Context Size: {len(messages_accurate[1]['content'])} chars")
    print(f"Speed-Focused Context Size: {len(messages_fast[1]['content'])} chars")


def example_6_batch_processing():
    """
    Example 6: Batch processing multiple questions
    Shows how to efficiently process multiple questions.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 6: Batch Processing")
    print("=" * 60)

    questions = [
        "What is the leave policy?",
        "How is salary paid?",
        "What is the remote work policy?",
    ]

    retrieval = RetrievalService()
    context_builder = RAGContextBuilder()
    llm = OpenRouterClient()

    for i, question in enumerate(questions, 1):
        print(f"\n[{i}/{len(questions)}] {question}")

        # Retrieve documents
        documents = retrieval.retrieve(question, top_k=3)

        # Build messages
        messages = context_builder.build_messages(
            question=question,
            context_chunks=documents,
        )

        # Generate answer
        answer = llm.generate(messages)
        print(f"  Answer: {answer[:100]}...")


if __name__ == "__main__":
    # Run examples
    example_1_basic_chromadb_rag()
    example_2_with_fallback()
    example_3_custom_system_prompt()
    example_4_no_context_handling()
    example_5_performance_tuning()
    example_6_batch_processing()

    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)
