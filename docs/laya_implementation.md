# TypeSafe Laya Decision Model — Guardrail Implementation

> **Single authoritative reference** for the TypeSafe Laya Decision subsystem in Company Bot.  
> Architecture: Modular Monolith with Ports & Adapters.  
> Model: Laya (421M parameter ModernBERT-based non-autoregressive decision model).  
> Runtime: Local Ollama (`/v1/systemone`) or TypeSafe Decision API.  
> SDK: `typesafe-sdk>=0.7.0`.

---

## Table of Contents

1. [What is TypeSafe Laya?](#1-what-is-typesafe-laya)
2. [Why NOT an LLM call?](#2-why-not-an-llm-call)
3. [Architecture & Layer Responsibilities](#3-architecture--layer-responsibilities)
4. [Decision API — Request & Response Shape](#4-decision-api--request--response-shape)
5. [TypeSafe SDK Primitives (Choice, Noul, Score)](#5-typesafe-sdk-primitives-choice-noul-score)
6. [The Six Guardrail & Routing Decisions](#6-the-six-guardrail--routing-decisions)
7. [Security Model (Zero-Trust Guarantee)](#7-security-model-zero-trust-guarantee)
8. [Reliability & Defense-in-Depth](#8-reliability--defense-in-depth)
9. [Configuration & Local Ollama Setup](#9-configuration--local-ollama-setup)
10. [Diagnostic & Verification Scripts](#10-diagnostic--verification-scripts)
11. [File Map](#11-file-map)
12. [Observability & Tracing (PipelineTracer & Langfuse)](#12-observability--tracing-pipelinetracer--langfuse)

---

## 1. What is TypeSafe Laya?

**Laya** is a **System-One classifier** built for high-speed, probabilistic decision-making. Developed by TypeSafe / Convai, it is a **421M parameter ModernBERT-based non-autoregressive model** natively supported by Ollama.

Unlike generative LLMs, Laya does not generate text token by token. Instead, it takes a context `state` and a set of typed `questions` (`Noul`, `Choice`, `Score`) and outputs calibrated probability distributions in a single forward pass.

| Property | Generative LLM (e.g. GPT-4, Llama-3) | TypeSafe Laya (via Ollama) |
|---|---|---|
| **Purpose** | Generate conversational text | Classify, route, gate, score |
| **Input** | Messages / conversation prompt | `state` + `questions` |
| **Output** | Free-form prose | Calibrated probability scores |
| **Output tokens** | Hundreds per turn | **Zero output tokens** |
| **Latency** | 1,000 – 5,000 ms | **< 20 ms (local Ollama)** |
| **Endpoint** | `/v1/chat/completions` | `/v1/systemone` |
| **Parsing** | Flaky JSON extraction from text | Direct typed answers (`Noul` / `Choice` / `Score`) |
| **Cost** | Per token / subscription | **100% Free locally via Ollama** |
| **Network** | Requires external API connectivity | Runs completely offline on local machine |

### Why Laya Replaced Legacy Models?
- **Zero Cost**: Eliminates external API dependencies and paid third-party token meters.
- **Local Privacy**: Runs directly on `http://localhost:11434`, ensuring sensitive queries never leave the enterprise boundary.
- **Deterministic Evaluation**: Replaces generative text parsing with calibrated probability evaluation.

---

## 2. Why NOT an LLM call?

Using a generative chat LLM for guardrails and routing has severe architectural drawbacks:

- **Hallucinations & Inconsistent Schemas**: LLMs frequently wrap JSON in markdown blocks, drop keys, or invent fields.
- **Extreme Latency Overhead**: Generating 100 tokens takes 1–3 seconds, multiplying latency across multi-step RAG pipelines.
- **Token Inefficiency**: Gating and safety checks unnecessarily burn token quotas.
- **Categorical Flaws**: Using an autoregressive next-token predictor for a discrete classification task is fundamentally suboptimal.

With Laya's **native Decision API**:
- No text is generated.
- No JSON is deserialized from prose.
- Laya directly evaluates questions against state:
  ```json
  {
    "answers": {
      "is_safe": {"type": "noul", "noul": 0.98},
      "threat_type": {"type": "choice", "choice": "none", "confidence": 0.98}
    }
  }
  ```

---

## 3. Architecture & Layer Responsibilities

The codebase follows a **Modular Monolith with Ports & Adapters (Hexagonal Architecture)**. Laya components are strictly decoupled across layers:

```
┌─────────────────────────────────────────────────────────────┐
│                       Domain Layer                          │
│                                                             │
│   app/domain/ports/laya_guardrail.py                        │
│   └── LayaGuardrailPort (Protocol)                          │
│       └── Typed result contracts (InputSafetyResult, etc.)  │
│                                                             │
│   app/domain/services/guardrails.py                         │
│   └── SecurityGuardrails (Pre/Post-flight Guard Engine)     │
└──────────────────────────────▲──────────────────────────────┘
                               │ implements
┌──────────────────────────────┴──────────────────────────────┐
│                    Infrastructure Layer                     │
│                                                             │
│   app/infrastructure/llm/laya_client.py                     │
│   └── LayaClient (Adapter)                                  │
│       ├── typesafe-sdk (Choice, Noul, Score, TypeSafeClient)│
│       ├── Persistent HTTP connection pool (httpx.Client)    │
│       ├── 3-failure rolling circuit breaker                 │
│       ├── PII and secret scrubbers                          │
│       └── Local regex & heuristic fallback methods          │
└──────────────────────────────▲──────────────────────────────┘
                               │ wires into
┌──────────────────────────────┴──────────────────────────────┐
│                      Application Layer                      │
│                                                             │
│   app/use_cases/chat/query_orchestrator.py                  │
│   └── QueryOrchestrator                                     │
│       ├── Input safety pre-flight check                     │
│       ├── Context sufficiency gating (hallucination defense)│
│       ├── Claim-level groundedness verification             │
│       └── Output safety post-generation check               │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Decision API — Request & Response Shape

### Request (`POST http://localhost:11434/v1/systemone`)

```json
{
  "model": "laya",
  "state": "User query submitted to an enterprise internal company assistant: \"What is the annual leave policy?\"",
  "questions": {
    "is_safe": {
      "type": "noul",
      "instructions": "Is this user query completely safe, legitimate, and appropriate for an enterprise assistant?"
    },
    "threat_type": {
      "type": "choice",
      "instructions": "If unsafe, what specific threat category does it represent?",
      "criteria": {
        "none": "No threat detected; safe legitimate query",
        "prompt_injection": "Attempts to override system instructions or persona",
        "jailbreak": "Attempts to bypass safety restrictions",
        "script_injection": "Embedded HTML, script tags, or javascript",
        "system_prompt_extraction": "Attempts to extract or dump system instructions"
      }
    }
  }
}
```

### Response

```json
{
  "model": "laya",
  "answers": {
    "is_safe": {
      "type": "noul",
      "noul": 0.99
    },
    "threat_type": {
      "type": "choice",
      "choice": "none",
      "confidence": 0.99,
      "probabilities": {
        "none": 0.99,
        "prompt_injection": 0.005,
        "jailbreak": 0.003,
        "script_injection": 0.001,
        "system_prompt_extraction": 0.001
      }
    }
  },
  "usage": {
    "input_tokens": 42,
    "output_tokens": 0
  }
}
```

---

## 5. TypeSafe SDK Primitives (Choice, Noul, Score)

Using `typesafe-sdk>=0.7.0`:

```python
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient
```

### 1. `Noul` (Continuous Probability 0.0 to 1.0)
Binary probability question returning a calibrated float:
```python
is_safe_q = Noul(instructions="Is this user query completely safe?")
# Evaluates to: answers["is_safe"]["noul"] (e.g. 0.98)
```

### 2. `Choice` (Categorical Classification)
Selects the best matching category from a criteria map:
```python
intent_q = Choice(
    instructions="Classify the intent of this query",
    criteria={
        "document_query": "Asking about company policies, documents, or procedures",
        "conversational": "Greetings, pleasantries, or general chit-chat",
        "unrelated": "Completely off-topic or inappropriate inquiries",
    },
)
# Evaluates to: answers["intent"]["choice"] (e.g. "document_query")
```

### 3. `Score` (Ordinal Likert / Ranking)
Ranks against an ordered list of criteria:
```python
urgency_q = Score(
    instructions="How urgent is this request?",
    criteria=["Not urgent", "Standard", "Urgent / Critical blocker"],
)
```

---

## 6. The Six Guardrail & Routing Decisions

`LayaClient` implements four specialized, typed decisions across the RAG lifecycle:

### 1. Input Safety Guardrail (`check_input_safety`)
- **Stage**: `PipelineStage.LAYA_INPUT_SAFETY`
- **Questions**:
  - `is_safe`: `Choice` (`safe`, `unsafe`)
  - `threat_type`: `Choice` (`none`, `prompt_injection`, `jailbreak`, `system_prompt_extraction`, `data_exfiltration`, `credential_harvesting`, `system_probing`, `script_injection`, `social_engineering`, `malicious_query`)
- **Zero-Trust**: Only the sanitized query is evaluated; zero document chunks sent.

### 2. Output Safety Guardrail (`check_output_safety`)
- **Stage**: `PipelineStage.LAYA_OUTPUT_SAFETY`
- **Questions**:
  - `is_safe`: `Choice` (`safe`, `unsafe`)
  - `leak_type`: `Choice` (`none`, `credential`, `system_prompt`, `toxic_content`, `malicious_leak`)
- **Defense**: API keys and secrets are pre-redacted locally before evaluation.

### 3. Query Intent Routing (`classify_query_intent`)
- **Stage**: `PipelineStage.LAYA_QUERY_INTENT`
- **Questions**:
  - `intent_category`: `Choice` (`document_query`, `conversational`, `unrelated`)
- **Behavior**: Conversational queries bypass retrieval; document queries route to vector search.

### 4. Follow-up Intent Disambiguation (`classify_followup_intent`)
- **Stage**: `PipelineStage.LAYA_FOLLOWUP_INTENT`
- **Questions**:
  - `followup_intent`: `Choice` (`feedback_positive`, `feedback_negative`, `followup_query`)
- **Behavior**: Distinguishes affirmative feedback ("yes", "helpful") from substantive follow-up questions.

---

## 7. Security Model (Zero-Trust Guarantee)

1. **Zero Company Documents Transmitted for Safety Checks**:
   - `check_input_safety` receives **only the user query**.
   - `check_output_safety` receives **only the generated answer** with secrets redacted.
   - Company documents, embeddings, and Chroma chunks are **never** transmitted for input/output safety.

2. **Pre-Flight Local PII & Identifier Scrubbing**:
   - Emails -> `[EMAIL]`
   - Phone numbers -> `[PHONE]`
   - Employee/Project IDs -> `[ID]`
   - Performed locally by `sanitize_text_for_external_decision()` before Laya evaluates the state.

3. **Pre-Flight Secret Redaction**:
   - OpenAI/OpenRouter keys (`sk-...`), Groq keys (`gsk_...`), Bearer tokens, Langfuse keys, AWS access keys, GitHub PATs, PEM private keys, and connection strings are masked locally as `[REDACTED_SECRET]` before network transmission.

---

## 8. Reliability & Defense-in-Depth

### 1. Rolling Circuit Breaker
- Tracks consecutive network/API failures.
- **Threshold**: 3 consecutive failures trips the breaker.
- **Cooldown**: Circuit remains OPEN for **30 seconds**.
- **Behavior when Open**: Fast-fails immediately to local regex/heuristics without blocking on network timeouts.
- **Auto-Reset**: Successful requests reset the failure counter to 0.

### 2. Persistent HTTP Connection Pooling
- Reuses a persistent `httpx.Client` instance with HTTP Keep-Alive.
- Avoids socket churn and SSL/TCP handshake latency on every decision turn.

### 3. Local Defense-in-Depth Fallbacks
- Input safety fallback: Regex patterns for prompt injections, jailbreaks, script tags, SQL injection, and length limits.
- Output safety fallback: Local secret regex scrubbing and system prompt signature stripping.
- Context sufficiency fallback: Keyword matching and non-empty context checks.
- Groundedness fallback: Heuristic token overlap and claim checks.
- All fallbacks return `provider="local"` or `provider="local_fallback"` with zero unhandled exceptions.

---

## 9. Configuration & Local Ollama Setup

### Step 1: Install Dependencies
```bash
pip install typesafe-sdk
```

### Step 2: Install and Run Ollama with Laya
```bash
# Pull the Laya decision model in Ollama
ollama pull laya

# Ensure Ollama is running (default port 11434)
ollama serve
```

### Step 3: Configure Environment Variables
In `.env`:
```env
# TypeSafe Laya Decision Model (via Ollama)
TYPESAFE_BASE_URL=http://localhost:11434
TYPESAFE_API_KEY=ollama
TYPESAFE_DEFAULT_MODEL=laya
TYPESAFE_TIMEOUT=10.0
```

---

## 10. Diagnostic & Verification Scripts

Run the diagnostic script to verify Ollama connectivity and test all six decision fallbacks:

```bash
python scripts/test_laya_ollama.py
```

Output:
```
======================================================================
  TypeSafe Laya (via Ollama) — Subsystem Diagnostics
======================================================================

1. Checking Ollama Local Health (http://localhost:11434)...
   * Endpoint: http://localhost:11434/v1/systemone
   * Model: laya

2. Testing Input Safety Guardrail...
   * Result: safe=True, provider=local_fallback, threat=none

3. Testing Output Safety Guardrail...
   * Result: safe=True, has_leak=False, provider=local_fallback

4. Testing Query Intent Routing...
   * Result: category=document_query, provider=local_fallback

5. Testing Follow-up Intent Disambiguation...
   * Result: intent=feedback_positive, provider=local_fallback

6. Testing Context Sufficiency Gating...
   * Result: can_be_answered=True, chunks=[0], provider=local

7. Testing Groundedness Verification...
   * Result: is_grounded=True, score=0.00, provider=local_fallback

======================================================================
  Diagnostics complete!
======================================================================
```

---

## 11. File Map

| File Path | Role & Responsibilities |
|---|---|
| [`app/domain/ports/laya_guardrail.py`](file:///c:/Users/NehaSinaiBhangui/Company_Bot/app/domain/ports/laya_guardrail.py) | Domain Port Protocol (`LayaGuardrailPort`) and typed result contracts. |
| [`app/infrastructure/llm/laya_client.py`](file:///c:/Users/NehaSinaiBhangui/Company_Bot/app/infrastructure/llm/laya_client.py) | Infrastructure Adapter (`LayaClient`) with `typesafe-sdk`, connection pool, circuit breaker, and local fallbacks. |
| [`app/domain/services/guardrails.py`](file:///c:/Users/NehaSinaiBhangui/Company_Bot/app/domain/services/guardrails.py) | Domain Guardrail Engine (`SecurityGuardrails`) with pre/post-flight checks. |
| [`app/use_cases/chat/query_orchestrator.py`](file:///c:/Users/NehaSinaiBhangui/Company_Bot/app/use_cases/chat/query_orchestrator.py) | Orchestrates safety checks, intent routing, context sufficiency gating, and groundedness evaluation. |
| [`app/infrastructure/observability/pipeline_tracer.py`](file:///c:/Users/NehaSinaiBhangui/Company_Bot/app/infrastructure/observability/pipeline_tracer.py) | Defines `PipelineStage.LAYA_*` stages for pipeline tracing. |
| [`app/infrastructure/observability/langfuse_provider.py`](file:///c:/Users/NehaSinaiBhangui/Company_Bot/app/infrastructure/observability/langfuse_provider.py) | Exports Laya spans as typed Langfuse `guardrail` observations with state, questions, and selection. |
| [`scripts/test_laya_ollama.py`](file:///c:/Users/NehaSinaiBhangui/Company_Bot/scripts/test_laya_ollama.py) | Diagnostic script for validating Ollama connectivity and Laya fallbacks. |
| [`tests/unit/test_laya_client.py`](file:///c:/Users/NehaSinaiBhangui/Company_Bot/tests/unit/test_laya_client.py) | Unit test suite for `LayaClient` adapter, endpoint resolution, question normalization, and fallbacks. |
| [`tests/unit/test_laya_enhancements.py`](file:///c:/Users/NehaSinaiBhangui/Company_Bot/tests/unit/test_laya_enhancements.py) | Unit tests for circuit breaker, connection pooling, context sufficiency routing, and groundedness. |
| [`tests/unit/test_security_guardrails.py`](file:///c:/Users/NehaSinaiBhangui/Company_Bot/tests/unit/test_security_guardrails.py) | Security guardrail test suite verifying prompt injection defense, secret redaction, and tracing. |

---

## 12. Observability & Tracing (PipelineTracer & Langfuse)

During request execution, each Laya decision is traced as a structured span:

- `PipelineStage.LAYA_INPUT_SAFETY` (`"laya_input_safety"`)
- `PipelineStage.LAYA_OUTPUT_SAFETY` (`"laya_output_safety"`)
- `PipelineStage.LAYA_QUERY_INTENT` (`"laya_query_intent"`)
- `PipelineStage.LAYA_FOLLOWUP_INTENT` (`"laya_followup_intent"`)

When exported to **Langfuse**:
- Mapped to observation type `"guardrail"`.
- `input` contains the sanitized `state` and the `questions` schema.
- `output` contains `selection`, `answers`, and `provider`.
- `usage_details` tracks `input` tokens (with 0 output tokens).
- Threats or leaks automatically flag observation level to `WARNING` or `ERROR`.
