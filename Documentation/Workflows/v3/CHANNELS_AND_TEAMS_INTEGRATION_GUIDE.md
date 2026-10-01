# Inbound Driving Channels & Microsoft Teams Integration Guide (V3)

**Author:** Akaash Samson  
**Module:** `app.infrastructure.channels` & `app.domain.ports.channel_adapter`  
**Tasks Implemented:** Task AK-2.1, Task AK-2.2, Task AK-2.3, Task AK-2.4 (Phase 3 Subsystem 5), Task AK-2.5 (Phase 5)  
**Target Audience:** Core Pipeline Contributors (Akaash, Abhinav, Neha, Roshan)

---

## 1. Executive Summary & Problem Context

### The Problem in V2
In V2, KnowLayer was accessible solely via the Streamlit web interface (`streamlit_app/`). There was no standard mechanism for driving external chat interfaces (Microsoft Teams, Slack, Webhooks) into the core RAG question-answering pipeline. Early prototypes attempted to mount ad-hoc framework SDKs (such as `microsoft-teams-apps`) directly into FastAPI routes, which tightly coupled the HTTP transport to vendor-specific SDK lifecycles and bypassed company RBAC scoping, user identity mapping, and session auditing.

### The V3 Solution: Hexagonal Driving Channels
V3 introduces a clean **Hexagonal Driving Ports & Adapters** architecture:
- **Driving Port (`ChannelAdapterPort`):** [app/domain/ports/channel_adapter.py](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/domain/ports/channel_adapter.py) defines the structural protocol (`typing.Protocol`) and domain value objects (`ChannelMessage`, `ChannelResponse`, `ChannelUser`).
- **Template Method Base Adapter (`BaseChannelAdapter`):** [app/infrastructure/channels/base.py](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/channels/base.py) encapsulates the invariant webhook execution lifecycle (signature validation -> payload extraction -> query dispatch -> response formatting -> error catching) using the GoF Template Method pattern.
- **Enterprise Identity & RBAC Bridge (`ChannelIdentityBridge`):** [app/infrastructure/channels/identity_bridge.py](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/channels/identity_bridge.py) maps external channel senders (Teams email/UPN/ID) to internal SQL user records (`UserRecord`), generating domain `AuthenticatedPrincipal` tokens to enforce role-based access control.
- **Concrete Teams Adapter:** [app/infrastructure/channels/teams/adapter.py](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/channels/teams/adapter.py) handles Bot Framework activities, Outgoing Webhook HMAC signatures, and multi-turn dispatching.
- **Teams Formatter:** [app/infrastructure/channels/teams/formatter.py](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/channels/teams/formatter.py) formats answers and citation footnotes into clean markdown and Microsoft Adaptive Cards (v1.4 schema).
- **Channel Registry & Unified Routing:** [app/infrastructure/channels/registry.py](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/channels/registry.py) and [app/api/routes/channels.py](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/api/routes/channels.py) expose a single extensible route: `POST /api/channels/{channel_name}/messages`.

---

## 2. End-to-End Architecture & Request Flow

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                INBOUND CHANNEL CLIENTS                                 │
│      Microsoft Teams Outgoing Webhook    /    Microsoft 365 Agents Playground          │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ HTTP POST (HMAC or unauthenticated dev)
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              FASTAPI CHANNEL ROUTER                                    │
│       POST /api/channels/{channel_name}/messages  ([app/api/routes/channels.py])       │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ Resolves adapter via channel_name
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                       CHANNEL REGISTRY ([registry.py])                                 │
│            Holds registered adapters: {"teams": TeamsChannelAdapter(...)}              │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ Invokes handle_webhook()
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│               TEMPLATE METHOD LIFECYCLE ([BaseChannelAdapter.handle_webhook])          │
│                                                                                        │
│   1. Subclass Hook: parse_and_validate(request)                                        │
│      - Verifies HMAC-SHA256 signature (if configured)                                  │
│      - Strips <at>mention tags                                                         │
│      - Normalizes payload into domain [ChannelMessage]                                 │
│                                                                                        │
│   2. Injected Callback: chat_dispatcher(message)                                       │
│      - [ChannelIdentityBridge]: Maps ChannelUser email/ID -> AuthenticatedPrincipal    │
│      - [AuthorizationService]: Calculates AuthorizationScope (project & doc grants)    │
│      - [QueryOrchestrator]: answer(question, scope, user_context)                       │
│                                                                                        │
│   3. Subclass Hook: format_response(message, result)                                   │
│      - Formats text and Adaptive Card activity payload                                 │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Subsystem 5 Task Breakdown & Implementation Details

### Task AK-2.1: Channel Interfaces & Driving Port Protocol
- **Files:** [`app/domain/ports/channel_adapter.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/domain/ports/channel_adapter.py), [`app/infrastructure/channels/base.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/channels/base.py)
- **Contracts Defined:**
  - `ChannelUser`: Value object carrying `user_id`, `email`, `display_name`, and `tenant_id`.
  - `ChannelMessage`: Normalized message carrying `channel_name`, `conversation_id`, `text`, `sender`, and `service_url`. Includes a unified `session_id` property (`"{channel_name}:{conversation_id}"`) for stateful memory continuity.
  - `ChannelResponse`: Normalized response carrying `status_code`, `text`, `card_payload`, and HTTP `headers`.
  - `ChannelAdapterPort`: `@runtime_checkable Protocol` enforcing `channel_name`, `parse_and_validate()`, `format_response()`, and `handle_webhook()`.
  - `BaseChannelAdapter(ChannelAdapterPort, ABC)`: Implements the GoF Template Method pattern, consolidating error-handling (401 on `ChannelAuthenticationError`, 400 on `ChannelValidationError`, 500 on dispatcher errors) into one place.

### Task AK-2.2: Channel Identity & RBAC Bridge
- **File:** [`app/infrastructure/channels/identity_bridge.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/channels/identity_bridge.py)
- **Identity Resolution Strategy:**
  1. Primary: Lookup in SQL `UserRepository` by sender's normalized email / userPrincipalName (`repo.get_by_email`).
  2. Secondary: Lookup in SQL `UserRepository` by sender's channel user ID as username (`repo.get_by_username`).
  3. Fallback: Return guest identity `AuthenticatedPrincipal(uid="channel_guest:<user_id>")`.
- **RBAC Alignment:** Once resolved, any registered SQL user automatically receives `include_unassigned=True` within `AuthorizationEngine`, granting immediate access to organization-wide policies and unassigned documentation.

### Task AK-2.3: Teams Channel Adapter & Formatter
- **Files:** [`app/infrastructure/channels/teams/adapter.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/channels/teams/adapter.py), [`app/infrastructure/channels/teams/formatter.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/channels/teams/formatter.py)
- **Features:**
  - **HMAC Verification:** Constant-time comparison (`hmac.compare_digest`) against `Authorization: HMAC <hash>` using SHA-256 and base64 encoding.
  - **Bot Framework Activity Compatibility:** Extracts sender information, conversation thread ID, and service URLs.
  - **Mention Stripping:** Regex filter `re.compile(r"<at>.*?</at>", re.IGNORECASE)` strips bot mention XML tags so queries to `QueryOrchestrator` are clean.
  - **Single Response Formatting:** Formats answer and citation sources directly into Bot Framework activity payloads. Supports both Outgoing Webhook format and Bot Framework `expectReplies` (`activities` list).

### Task AK-2.4 & AK-2.5: Channel Registry, Route & Lifespan
- **Files:** [`app/infrastructure/channels/registry.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/channels/registry.py), [`app/api/routes/channels.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/api/routes/channels.py), [`app/main.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/main.py)
- **Features:**
  - `register_channel_adapter(adapter)` and `get_channel_adapter(name)` provide thread-safe dictionary management for driving adapters.
  - In `app/main.py`, the adapter is registered in the lifespan context manager:
    ```python
    skip_auth = os.getenv("TEAMS_SKIP_AUTH", "true").lower() == "true"
    security_token = os.getenv("TEAMS_SECURITY_TOKEN")
    register_channel_adapter(TeamsChannelAdapter(security_token=security_token, skip_auth=skip_auth))
    ```
  - `app/api/routes/channels.py` mounts `POST /api/channels/{channel_name}/messages`, resolving the adapter dynamically from the registry and delegating to `QueryOrchestrator`.

---

## 4. Local Testing & Verification with Microsoft 365 Agents Playground

Developers without an Azure subscription or Microsoft 365 tenant administrator rights can test the Teams integration completely locally using the official Microsoft 365 Agents Playground (`@microsoft/teams-app-test-tool`).

### Step 1: Start the Backend Server
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Step 2: Start the Playground CLI
```bash
npx -y @microsoft/teams-app-test-tool --app-endpoint http://localhost:8000/api/channels/teams/messages --delivery-mode expectReplies
```

### Step 3: Test Personas in Database
The Playground transmits activities as `user_id = "user-id-0"`. A seeded record in SQL (`instance/knowlayer.db`) exists for this user:
- **UID / Username:** `user-id-0`
- **Role:** `Employee`
- **Department:** `IT (d001)`
- **Permissions:** Unassigned policy document access (`include_unassigned=True`).

When querying *"What is the annual leave policy?"* in the playground, the bot retrieves chunks from `NEXORA TECHNOLOGIES PVT.docx` and returns the exact 18-day annual leave entitlement with source citations.

---

## 5. Verification & Test Suite

All driving channel functionality is validated through comprehensive unit tests:

```bash
pytest tests/unit/test_channel_base_adapter.py \
       tests/unit/test_channel_identity_bridge.py \
       tests/unit/test_teams_adapter.py \
       tests/unit/test_teams_adaptive_card_formatter.py \
       tests/unit/test_channels_route.py
```

### Test Coverage Summary
- `test_channel_base_adapter.py`: Validates Template Method execution order, 401 on auth failure, 400 on malformed payloads, and 500 handling.
- `test_channel_identity_bridge.py`: Validates email lookup, username fallback, and guest principal prefixing.
- `test_teams_adapter.py`: Validates HMAC signature verification, mention tag stripping, and activity formatting.
- `test_teams_adaptive_card_formatter.py`: Validates Adaptive Card schema (v1.4, `$schema`), TextBlock generation, and FactSet citation lists.
- `test_channels_route.py`: Validates dynamic channel route dispatching and 404 handling for unknown channels.
