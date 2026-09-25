"""
RAG context builder — formats retrieved ChromaDB results into LLM prompts.

This module handles the construction of system and user prompts optimized for
generating answers based on retrieved document chunks from ChromaDB.
"""

import logging
from typing import Optional
from datetime import datetime

from app.core.settings import RAG_MAX_CONTEXT_CHARS

logger = logging.getLogger(__name__)


class RAGContextBuilder:
    """Builds optimized prompts from ChromaDB retrieval results."""

    def __init__(
        self,
        max_context_chars: int = RAG_MAX_CONTEXT_CHARS,
        include_metadata: bool = True,
        include_timestamp: bool = False,
    ):
        self.max_context_chars = max_context_chars
        self.include_metadata = include_metadata
        self.include_timestamp = include_timestamp

    def build_system_prompt(self) -> str:
        """
        Build a system prompt that guides the LLM to use only provided context.

        Returns
        -------
        str
            System prompt for the LLM to follow when generating answers.
        """
        return (
            "You are a helpful HR assistant. Your role is to provide accurate answers "
            "based exclusively on the HR policy documents provided to you.\n\n"
            "Guidelines:\n"
            "- Answer ONLY using the provided document context\n"
            "- Be concise (2-4 sentences)\n"
            "- If information is not in the context, say 'I could not find that information in the available documents'\n"
            "- Cite relevant sections when applicable\n"
            "- Do not add external knowledge or assumptions\n"
            "- End with: 'Was this response relevant to your question?'"
        )

    def build_user_prompt(
        self,
        question: str,
        context_chunks: list[dict],
        include_references: bool = True,
    ) -> str:
        """
        Build a user prompt with formatted context from ChromaDB.

        Parameters
        ----------
        question : str
            The user's question.
        context_chunks : list[dict]
            List of document chunks retrieved from ChromaDB, each with:
            - 'text': the chunk content
            - 'metadata': (optional) chunk metadata
            - 'distance': (optional) similarity distance
        include_references : bool
            Whether to indicate that references will be provided.

        Returns
        -------
        str
            Formatted user prompt ready for the LLM.
        """
        if not context_chunks:
            return f"Question: {question}\n\nNo relevant documents were found."

        # Format context with optional metadata
        formatted_chunks = []
        total_chars = 0

        for i, chunk in enumerate(context_chunks, 1):
            text = chunk.get("text", "").strip()
            if not text:
                continue

            # Build chunk header with metadata if available
            chunk_lines = []
            if self.include_metadata and "metadata" in chunk:
                metadata = chunk["metadata"]
                section = metadata.get("section", f"Section {i}")
                chunk_lines.append(f"[{section}]")

            # Add chunk content
            chunk_lines.append(text)

            # Add distance indicator if available (for debugging)
            if "distance" in chunk:
                distance = chunk["distance"]
                chunk_lines.append(f"(relevance: {1 - distance:.2%})")

            chunk_text = "\n".join(chunk_lines)
            chunk_size = len(chunk_text)

            # Respect max context size
            if total_chars + chunk_size > self.max_context_chars:
                logger.debug(
                    "Context size limit reached: %d chars (max: %d)",
                    total_chars,
                    self.max_context_chars,
                )
                break

            formatted_chunks.append(chunk_text)
            total_chars += chunk_size + 2  # +2 for separator

        context = "\n\n".join(formatted_chunks)

        # Build final prompt
        prompt_parts = [
            "Document Context:",
            "=" * 50,
            context,
            "=" * 50,
            f"\nQuestion: {question}",
        ]

        if include_references:
            prompt_parts.append(
                "\nInstructions: Answer using ONLY the document context above. "
                "Write 2-4 sentences. No analysis or reasoning — just the answer. "
                "End with: 'Was this response relevant to your question?'"
            )

        if self.include_timestamp:
            prompt_parts.append(f"\nProcessed at: {datetime.now().isoformat()}")

        return "\n".join(prompt_parts)

    def build_messages(
        self,
        question: str,
        context_chunks: list[dict],
        include_system_prompt: bool = True,
    ) -> list[dict]:
        """
        Build a complete messages list ready for LLM generation.

        Parameters
        ----------
        question : str
            The user's question.
        context_chunks : list[dict]
            ChromaDB retrieved chunks.
        include_system_prompt : bool
            Whether to include a system prompt.

        Returns
        -------
        list[dict]
            Messages in OpenAI format: [{"role": "system"/"user", "content": "..."}]
        """
        messages = []

        if include_system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": self.build_system_prompt(),
                }
            )

        messages.append(
            {
                "role": "user",
                "content": self.build_user_prompt(question, context_chunks),
            }
        )

        return messages

    @staticmethod
    def format_evidence_for_citations(
        context_chunks: list[dict],
    ) -> list[dict]:
        """
        Extract citation information from context chunks.

        Parameters
        ----------
        context_chunks : list[dict]
            ChromaDB retrieved chunks.

        Returns
        -------
        list[dict]
            List of citations ready for presentation to the user.
        """
        citations = []
        for chunk in context_chunks:
            citation = {}

            # Extract section from metadata
            if "metadata" in chunk:
                metadata = chunk["metadata"]
                citation["section"] = metadata.get("section", "Unknown Section")
                citation["source"] = metadata.get("source", "HR Policy")
            else:
                citation["section"] = "Document Reference"
                citation["source"] = "HR Policy Handbook"

            # Add text
            citation["text"] = chunk.get("text", "")

            citations.append(citation)

        return citations
