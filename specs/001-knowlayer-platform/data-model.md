# Data Model: KnowLayer MVP 1

## Overview

The MVP focuses on a single approved HR policy document and a small number of core entities required to ingest, retrieve, and answer questions grounded in that document.

## Core entities

### DocumentSource
Represents the approved source file used as the knowledge base for the MVP.

Fields:
- id: string
- title: string
- file_path: string
- content_type: string
- status: enum { active, archived }
- created_at: datetime
- updated_at: datetime

Validation rules:
- file_path must point to an existing source file
- title must not be empty
- status must be one of the allowed values

### DocumentChunk
Represents a chunk of text extracted from the HR policy document for retrieval.

Fields:
- id: string
- document_id: string
- chunk_index: integer
- text: string
- page_number: integer | null
- section_title: string | null
- metadata: object
- created_at: datetime

Validation rules:
- text must not be empty
- chunk_index must be >= 0
- document_id must reference an existing DocumentSource

### VectorRecord
Represents the embedding metadata for a document chunk.

Fields:
- id: string
- chunk_id: string
- embedding_model: string
- embedding_version: string
- collection_name: string
- created_at: datetime

Validation rules:
- chunk_id must reference an existing DocumentChunk
- embedding_model must not be empty
- collection_name must not be empty

### QuerySession
Represents a single user interaction in the chat interface.

Fields:
- id: string
- user_input: string
- created_at: datetime
- session_status: enum { active, completed, failed }

Validation rules:
- user_input must not be empty
- session_status must be one of the allowed values

### RetrievedEvidence
Represents the evidence selected from the vector store to answer a question.

Fields:
- id: string
- query_session_id: string
- chunk_id: string
- score: float
- citation_text: string
- source_reference: string
- retrieved_at: datetime

Validation rules:
- score must be numeric
- query_session_id must reference a valid QuerySession
- chunk_id must reference a valid DocumentChunk

### AnswerResponse
Represents the answer returned to the user.

Fields:
- id: string
- query_session_id: string
- answer_text: string
- citations: list[string]
- created_at: datetime

Validation rules:
- answer_text must not be empty
- citations must not be empty for grounded responses
- query_session_id must reference a valid QuerySession

## Relationships

- DocumentSource has many DocumentChunk records.
- DocumentChunk has one VectorRecord.
- QuerySession has many RetrievedEvidence records.
- QuerySession has one AnswerResponse.

## Example lifecycle

1. A document is stored in the local folder.
2. The ingestion service parses the document and splits it into chunks.
3. Each chunk is embedded and saved to Chroma DB.
4. The user submits a question through the Streamlit UI.
5. The retrieval service searches the vector store for the most relevant chunks.
6. The answer generation service constructs a grounded answer using the retrieved chunks.
7. The system stores the question, evidence, and answer in the query session trail.

## Notes

This model intentionally excludes employee data, role-based authorization, and HR systems because those concerns are explicitly outside MVP 1 scope.
