# Chat API Contract

## Overview

The MVP uses a simple internal chat contract between the Streamlit UI and the backend retrieval-answering service.

## Endpoint: POST /api/chat

### Request

```json
{
  "question": "What is the annual leave policy?",
  "session_id": "session-123"
}
```

### Response

```json
{
  "session_id": "session-123",
  "answer": "According to the HR policy, annual leave is available under the policy terms described in section 4.2.",
  "citations": [
    {
      "source": "hr_policy.pdf",
      "section": "4.2",
      "text": "Annual leave is granted according to the employee's eligibility and policy terms."
    }
  ]
}
```

### Validation rules
- question must be a non-empty string
- session_id may be optional for anonymous sessions but should be present for tracking
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
