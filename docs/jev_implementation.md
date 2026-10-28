# TypeSafe Jev System-One — Guardrail Implementation

> **Single authoritative reference** for the Jev guardrail subsystem in Company Bot.  
> Architecture: Modular Monolith with Ports & Adapters.

---

## Table of Contents

1. [What is Jev?](#1-what-is-jev)
2. [Why NOT an LLM call?](#2-why-not-an-llm-call)
3. [Architecture & Layer Responsibilities](#3-architecture--layer-responsibilities)
4. [Decision API — Request & Response Shape](#4-decision-api--request--response-shape)
5. [Jev Primitives Reference](#5-jev-primitives-reference)
6. [The Six Guardrail Decisions](#6-the-six-guardrail-decisions)
7. [Security Model (Zero-Trust)](#7-security-model-zero-trust)
8. [Circuit Breaker & Local Fallback](#8-circuit-breaker--local-fallback)
9. [Configuration](#9-configuration)
10. [File Map](#10-file-map)
11. [Data Flow Diagram](#11-data-flow-diagram)
12. [Langfuse Traceability (Question, State, Selection)](#12-langfuse-traceability-question-state-selection)

---

## 1. What is Jev?

**TypeSafe Jev** is a **System-One classifier** built for fast, probabilistic decisions. It is fundamentally different from a language model:

| Property | LLM (e.g. GPT-4) | TypeSafe Jev |
|---|---|---|
| **Purpose** | Generate text | Classify, route, score |
| **Input** | Messages (prompt) | `state` + `questions` |
| **Output** | Free-form prose | Calibrated probability scores |
| **Output tokens** | Hundreds | **Zero** |
| **Latency** | 1-5 s | ~50-150 ms |
| **Endpoint** | `/api/v1/chat/completions` | `/api/alpha/decisions` |
| **Parsing** | JSON from prose | Typed `answers` object |

Jev is accessible **exclusively via OpenRouter** at `https://openrouter.ai/api/alpha/decisions`.  
Groq does **not** expose this endpoint.

---

## 2. Why NOT an LLM call?

The previous implementation sent chat-completion prompts to Groq / OpenRouter and parsed JSON from free-form text. This was:

- **Inaccurate** — LLMs hallucinate JSON fields, return inconsistent formats.
- **Expensive** — every safety check consumed 300-800 output tokens.
- **Slow** — 1-3 s per guardrail call vs. 50-150 ms with native Jev.
- **Architecturally wrong** — using a generative model for a classification problem.

The corrected implementation uses the **native Jev Decision API**, where:

- No prompt is engineered. No text is generated.
- Jev directly returns `{"noul": 0.94}` or `{"choice": "billing", "confidence": 0.98}`.
- Output tokens = **0** for all classification calls.

---

## 3. Architecture & Layer Responsibilities

```
+--------------------------------------------------------------------+
|  DOMAIN LAYER                                                      |
|                                                                    |
|  app/domain/ports/jev_guardrail.py                                 |
|    +-- JevGuardrailPort (Protocol -- the contract)                 |
|    +-- Typed result dicts: InputSafetyResult, OutputSafetyResult,  |
|        QueryIntentResult, FollowupIntentResult,                    |
|        ContextSufficiencyResult, GroundednessResult                |
|                                                                    |
|  app/domain/services/guardrails.py                                 |
|    +-- SecurityGuardrails -- accepts JevGuardrailPort, not concrete|
+--------------------------------------------------------------------+
         ^ depends on port only (Protocol)
+--------------------------------------------------------------------+
|  INFRASTRUCTURE LAYER (Adapter)                                    |
|                                                                    |
|  app/infrastructure/llm/jev_client.py                              |
|    +-- JevClient -- implements JevGuardrailPort                    |
|        +-- Calls POST /api/v1/decisions (TypeSafe Jev native API)  |
|        +-- Persistent httpx connection pool                        |
|        +-- Circuit breaker (3 fails -> 60 s open)                 |
|        +-- Local regex fallback (domain guardrails patterns)       |
+--------------------------------------------------------------------+
         ^ injected via constructor
+--------------------------------------------------------------------+
|  USE-CASE LAYER                                                    |
|                                                                    |
|  app/use_cases/chat/query_orchestrator.py                          |
|    +-- self.jev: JevGuardrailPort = jev or JevClient()             |
|        (typed as port, concrete only at wiring time)               |
+--------------------------------------------------------------------+
```

### Key Rules

- The **domain layer** never imports from `infrastructure`. It owns the port and result types.
- The **use-case layer** depends on `JevGuardrailPort`, not `JevClient` directly.
- The **infrastructure adapter** (`JevClient`) is wired in by the orchestrator constructor.
- `SecurityGuardrails.validate_input()` and `validate_output()` accept `Optional[JevGuardrailPort]`.

---

## 4. Decision API -- Request & Response Shape

### Request

```http
POST https://openrouter.ai/api/alpha/decisions
Authorization: Bearer <OPENROUTER_API_KEY>
Content-Type: application/json

{
  "model": "typesafe/jev-1.14",
  "state": "<sanitized context string describing the situation>",
  "questions": {
    "<question_key>": {
      "type": "noul",
      "instructions": "<true/false question Jev must evaluate>"
    },
    "<question_key>": {
      "type": "choice",
      "instructions": "<classification question>",
      "criteria": {
        "<label>": "<description of when this label applies>",
        ...
      }
    }
  }
}
```

### Response

```json
{
  "model": "typesafe/jev-1.14.0",
  "answers": {
    "is_safe": {
      "type": "noul",
      "noul": 0.94
    },
    "threat_type": {
      "type": "choice",
      "choice": "none",
      "confidence": 0.97,
      "probabilities": {
        "none": 0.97,
        "prompt_injection": 0.02,
        "jailbreak": 0.01
      }
    }
  },
  "usage": {
    "input_tokens": 84,
    "output_tokens": 0
  }
}
```

> **`output_tokens` is always 0** -- Jev produces no generated text. Only input tokens are billed.

---

## 5. Jev Primitives Reference

### `noul` -- Boolean Probability

Returns `P(true)` as a float between 0.0 and 1.0.

```json
{ "type": "noul", "noul": 0.94 }
```

**Thresholds used in this codebase:**

| Decision | Threshold | Meaning |
|---|---|---|
| `is_safe` (input) | >= 0.70 | P(safe) >= 70% -> safe |
| `has_leak` (output) | >= 0.65 | P(has_leak) >= 65% -> leak detected |
| `can_be_answered` | >= 0.55 | P(can_answer) >= 55% -> sufficient |
| `is_grounded` | >= 0.60 | P(grounded) >= 60% -> grounded |

### `choice` -- Enum Classification

Returns the highest-probability label with its confidence and full probability distribution.

```json
{
  "type": "choice",
  "choice": "document_query",
  "confidence": 0.91,
  "probabilities": {
    "document_query": 0.91,
    "conversational": 0.07,
    "unrelated": 0.02
  }
}
```

---

## 6. The Six Guardrail Decisions

### Decision 1 -- Input Safety (`check_input_safety`)

**Trigger**: Before any RAG retrieval.  
**State**: Sanitized user query only. Zero company documents.

| Question | Type | Output |
|---|---|---|
| `is_safe` | Noul | P(safe) >= 0.70 -> allowed |
| `threat_type` | Choice | `none | prompt_injection | jailbreak | system_prompt_extraction | script_injection | social_engineering | malicious_query` |

**Return type**: `InputSafetyResult`

---

### Decision 2 -- Output Safety (`check_output_safety`)

**Trigger**: After LLM generation, before response delivery.  
**State**: Pre-secret-redacted answer text.

| Question | Type | Output |
|---|---|---|
| `has_leak` | Noul | P(has_leak) >= 0.65 -> leak |
| `leak_type` | Choice | `none | credential | system_prompt | toxic_content | malicious_leak` |

**Return type**: `OutputSafetyResult`

---

### Decision 3 -- Query Intent (`classify_query_intent`)

**Trigger**: Before retrieval to route intent.  
**State**: Sanitized user query.

| Question | Type | Output |
|---|---|---|
| `intent_category` | Choice | `document_query | conversational | unrelated` |

**Return type**: `QueryIntentResult`

---

### Decision 4 -- Follow-up Intent (`classify_followup_intent`)

**Trigger**: When previous bot turn asked a confirmation/relevance question.  
**State**: Previous assistant message + current user reply.

| Question | Type | Output |
|---|---|---|
| `followup_intent` | Choice | `feedback_positive | feedback_negative | followup_query` |

**Return type**: `FollowupIntentResult`

---

### Decision 5 -- Context Sufficiency (`evaluate_context_sufficiency`)

**Trigger**: After retrieval, before LLM generation -- gates whether evidence is sufficient.  
**State**: Sanitized question + up to 5 secret-scrubbed chunk previews.

| Question | Type | Output |
|---|---|---|
| `can_be_answered` | Noul | P(can_answer) >= 0.55 -> generate |
| `supporting_chunks` | Choice | Chunk range label |

**Return type**: `ContextSufficiencyResult`

---

### Decision 6 -- Groundedness (`evaluate_groundedness`)

**Trigger**: After LLM generation -- verifies answer is strictly evidence-backed.  
**State**: Sanitized question + chunk previews + generated answer.

| Question | Type | Output |
|---|---|---|
| `is_grounded` | Noul | P(grounded) >= 0.60 -> pass |
| `hallucination_level` | Choice | `none | minor | moderate | severe | complete` |

**Return type**: `GroundednessResult`

---

## 7. Security Model (Zero-Trust)

### PII Scrubbing (before all external calls)

All text transmitted to Jev is run through `sanitize_text_for_external_decision()`:

- **Employee IDs**: `MSS-1234`, `DEPT-5` -> `[ID]`
- **Email addresses** -> `[EMAIL]`
- **Phone numbers** -> `[PHONE]`

### Secret Redaction (before output safety calls)

`sanitize_secrets_for_external_evaluation()` redacts:

- OpenAI / OpenRouter keys (`sk-...`)
- Groq keys (`gsk_...`)
- Bearer tokens
- Langfuse keys
- AWS Access Key IDs (`AKIA...`)
- GitHub PATs (`ghp_...`, `ghs_...`, etc.)
- Google Cloud API keys (`AIza...`)
- Slack tokens (`xox...`)
- PEM private keys
- MongoDB / PostgreSQL / SQLite connection strings

### Zero-Document Guarantee

**Decision 1 (Input Safety)** and **Decision 4 (Follow-up Intent)** transmit **only** the sanitized user query.  
**No company documents, no Chroma chunks, no proprietary content** ever reaches Jev for these critical decisions.

Decisions 5 (Context Sufficiency) and 6 (Groundedness) transmit **at most 5 chunk previews**, each capped at 600-800 characters, with secrets pre-redacted.

---

## 8. Circuit Breaker & Local Fallback

```
Attempt Jev Decision API
    |
    +-- Success --> _record_success() --> reset consecutive_failures = 0
    |
    +-- Failure --> _record_failure()
                    |
                    +-- consecutive_failures < 3  --> log warning, return local_fallback
                    |
                    +-- consecutive_failures >= 3 --> TRIP circuit
                                                      circuit_open_until = now + 60s
                                                      All calls return local_fallback for 60s
```

### Local Fallback Implementations

| Decision | Fallback Strategy |
|---|---|
| Input Safety | Regex patterns: `_PROMPT_INJECTION_PATTERNS`, `_SCRIPT_INJECTION_PATTERNS`, `_SQL_ARTIFACT_PATTERNS` |
| Output Safety | Regex patterns: `_API_KEY_PATTERNS`, `_SYSTEM_PROMPT_SIGNATURES` |
| Query Intent | Keyword matching (conversational signals list) |
| Follow-up Intent | Punctuation + keyword signal matching |
| Context Sufficiency | Optimistic pass-through if chunks present |
| Groundedness | Optimistic pass-through (assume grounded) |

All fallback results include `"provider": "local"` or `"provider": "local_fallback"` for observability.

---

## 9. Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | `""` | **Required.** OpenRouter API key (used for both LLM and Jev). |
| `JEV_API_KEY` | `OPENROUTER_API_KEY` | Override only if using a separate key for Jev. |
| `JEV_MODEL` | `typesafe/jev-1.14` | Jev model version. Check OpenRouter for latest. |
| `JEV_ENDPOINT` | `https://openrouter.ai/api/alpha/decisions` | OpenRouter native Decisions API endpoint. |

### `.env` Example

```env
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Optional Jev overrides (defaults derived from OPENROUTER_API_KEY)
# JEV_API_KEY=sk-or-v1-xxxxxxxx   # only if using a different key
# JEV_MODEL=typesafe/jev-1.14
# JEV_ENDPOINT=https://openrouter.ai/api/alpha/decisions
```

---

## 10. File Map

```
app/
+-- domain/
|   +-- ports/
|   |   +-- jev_guardrail.py          <-- Port (Protocol) + 6 TypedDict result contracts
|   +-- services/
|       +-- guardrails.py             <-- SecurityGuardrails -- accepts JevGuardrailPort
|
+-- infrastructure/
|   +-- llm/
|       +-- jev_client.py             <-- JevClient adapter (Decision API, circuit breaker, fallback)
|
+-- use_cases/
|   +-- chat/
|       +-- query_orchestrator.py     <-- Wires JevClient -> self.jev: JevGuardrailPort
|
+-- core/
    +-- settings.py                   <-- JEV_API_KEY, JEV_MODEL constants

docs/
+-- jev_implementation.md             <-- THIS FILE (single source of truth)
```

---

## 11. Data Flow Diagram

```
User Message
     |
     v
[QueryOrchestrator.answer()]
     |
     +--1--> SecurityGuardrails.validate_input(jev_client=self.jev)
     |          |
     |          +--> JevClient.check_input_safety()
     |                  +-- sanitize_text_for_external_decision(question)
     |                  +-- POST /api/v1/decisions  { state, questions: {is_safe, threat_type} }
     |                  +-- Returns InputSafetyResult
     |
     |   [If unsafe --> rejection response]
     |
     +--3--> JevClient.classify_query_intent(question)
     |          +-- POST /api/v1/decisions  { state, questions: {intent_category} }
     |          +-- Returns QueryIntentResult
     |
     |   [If conversational --> direct response]
     |
     +--4--> [If previous bot turn was a confirmation]
     |        JevClient.classify_followup_intent(current_input, prev_msg)
     |            +--> Returns FollowupIntentResult
     |
     +-- [Retrieval] --> ChromaDB --> ranked chunks
     |
     +--5--> JevClient.evaluate_context_sufficiency(question, chunks)
     |          +-- sanitize_secrets_for_external_evaluation(chunks)
     |          +-- POST /api/v1/decisions  { state, questions: {can_be_answered, supporting_chunks} }
     |          +-- Returns ContextSufficiencyResult
     |
     |   [If insufficient --> "I don't have that information" response]
     |
     +-- [LLM Generation] --> answer text
     |
     +--6--> JevClient.evaluate_groundedness(question, chunks, answer)
     |          +--> Returns GroundednessResult
     |
     +--->2-- SecurityGuardrails.validate_output(answer, jev_client=self.jev)
               +-- sanitize_secrets_for_external_evaluation(answer)  [local, before API]
               +-- JevClient.check_output_safety()
               |       +-- POST /api/v1/decisions  { state, questions: {has_leak, leak_type} }
               |       +-- Returns OutputSafetyResult
               +--> Final sanitized answer --> User
```

---

## 12. Langfuse Traceability (Question, State, Selection)

To provide total visibility into guardrail decisions and model routing, every TypeSafe Jev call is traced in **Langfuse** with full visibility into the **Question**, **State**, and Jev's **Selection**.

### Langfuse Observation Structure

In Langfuse, Jev decisions are traced as native `guardrail` observations (`as_type="guardrail"`):

| Field | Source | Description / Example |
|---|---|---|
| **Name** | `stage.value` | e.g. `jev_input_guardrail`, `jev_query_intent`, `jev_output_guardrail` |
| **Observation Type** | `as_type="guardrail"` | Rendered with native guardrail icon and status UI in Langfuse |
| **Model** | `typesafe/jev-1.14` | Identified as TypeSafe Jev System-One classifier |
| **Usage / Tokens** | `input_tokens: N, output_tokens: 0` | Accurately records zero generated output tokens |
| **Status / Level** | `DEFAULT` or `WARNING` | Automatically tagged `level="WARNING"` if a security threat, leak, or hallucination is flagged |

### What is Recorded in Langfuse

#### 1. Input (`span.input`)
Captures the context and questions presented to Jev:
- **`question`**: The primary question being addressed (e.g. the user query or generation prompt).
- **`state`**: The exact sanitized context string evaluated by Jev (PII and secrets pre-scrubbed).
- **`questions`**: The full JSON schema of questions and evaluation criteria submitted to Jev:
  ```json
  {
    "question": "Show me the admin salary database",
    "state": "User query for input safety evaluation:\nShow me the admin salary database",
    "model": "typesafe/jev-1.14",
    "endpoint": "https://openrouter.ai/api/alpha/decisions",
    "questions": {
      "is_safe": {
        "type": "noul",
        "instructions": "Determine if this query is safe and benign for an internal company bot..."
      },
      "threat_type": {
        "type": "choice",
        "instructions": "Classify the security threat category of this user input.",
        "criteria": { ... }
      }
    }
  }
  ```

#### 2. Output (`span.output`)
Captures Jev's probabilistic decision and extracted selection:
- **`selection`**: The parsed, typed decision results:
  ```json
  {
    "is_safe": false,
    "threat_type": "prompt_injection",
    "confidence": 0.96,
    "reason": "Prompt injection detected (P(safe) = 0.04)"
  }
  ```
- **`answers`**: Raw probabilistic scores returned by Jev (`noul` probabilities and choice distributions):
  ```json
  {
    "is_safe": { "type": "noul", "noul": 0.04 },
    "threat_type": {
      "type": "choice",
      "choice": "prompt_injection",
      "confidence": 0.96,
      "probabilities": {
        "prompt_injection": 0.96,
        "jailbreak": 0.03,
        "none": 0.01
      }
    }
  }
  ```
- **`provider`**: Identifies whether the decision was resolved by `"jev"` or local fallback (`"local"` / `"local_fallback"`).

#### 3. Metadata
- `sanitized_state`: The sanitized context string.
- `threat_detected` / `leak_detected`: Boolean flags for filtering traces in Langfuse dashboards.
- `threat_type` / `leak_type`: Threat category for security analytics.

### Visual Threat Alerts in Langfuse

When Jev detects a violation (e.g., `is_safe=False` or `has_leak=True`), the Langfuse observation status is immediately upgraded:
- `level = "WARNING"`
- `status_message = "THREAT_DETECTED: prompt_injection (confidence: 0.96)"`

This allows security and operations teams to filter and inspect blocked threats directly in the Langfuse UI without digging through logs.

### Trace Propagation Architecture

1. **Pipeline Tracing (`PipelineTracer`)**:
   During request handling, `PipelineTracer.span(PipelineStage.JEV_INPUT_GUARDRAIL)` creates an active span. The `_traced_jev` decorator in `JevClient` binds this span into a thread-safe `contextvars.ContextVar` (`_active_jev_span`).
2. **Dynamic Input & Output Recording**:
   When `_call_decisions` runs, it updates the span's inputs via `span.set_input(question=..., state=..., questions=...)` and upon receiving the HTTP 200 response attaches `selection`, `answers`, and `raw_answers`.
3. **Fallback Resiliency**:
   If the network fails or the circuit breaker trips, local fallback routines also invoke `span.set_input(...)` and record fallback `selection` and `answers`, ensuring 100% trace completeness.
4. **Direct / Standalone Tracing**:
   `ObservabilityManager.record_decision_call(...)` and `LangfuseProvider.record_decision_call(...)` provide a direct port method for logging standalone Jev decision calls outside pipeline spans.

