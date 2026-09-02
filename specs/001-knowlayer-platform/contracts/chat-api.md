# Chat API Contract

## Overview

The MVP uses a simple internal chat contract between the Streamlit UI and the backend retrieval-answering service.

## Endpoint: POST /api/chat

### Request

```json
{
  "question": "What is the annual leave policy?",
  "session_id": "session-123",
  "conversation_history": [
    {"role": "user", "content": "What is the annual leave policy?"},
    {"role": "assistant", "content": "Annual leave is governed by the policy terms described in section 4.2."},
    {"role": "user", "content": "What about parental leave?"}
  ]
}
```

### Response

```json
{
  "session_id": "session-123",
  "answer": "Parental leave is covered under the separate policy section and follows the rules described in section 5.1.",
  "citations": [
    {
      "source": "hr_policy.pdf",
      "section": "5.1",
      "text": "Parental leave may be taken according to the approved policy and employee eligibility requirements."
    }
  ]
}
```

### Validation rules
- question must be a non-empty string
- session_id should be present for chat continuity
- conversation_history must contain only recent user and assistant messages from the active session window
- answer must be grounded in evidence from the configured document source
- citations must be included whenever a response is based on retrieved policy text

## Endpoint: POST /api/ingest

### Request

```json
{
  "source_path": "./documents/hr_policy.pdf"
}
```

### Response

```json
{
  "status": "success",
  "document_id": "doc-001",
  "chunks_created": 42
}
```

### Validation rules
- source_path must point to a valid file in the local document folder
- ingestion must parse and chunk the document before indexing into Chroma DB
- if ingestion fails, the API must return a clear error message without blocking the app

## Notes

This contract intentionally follows a simple internal pattern and does not yet include user auth, employee-specific data, or enterprise-grade policy enforcement because those requirements are deferred to later phases.
