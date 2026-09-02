# Tasks: KnowLayer Platform

**Input**: Design documents from `/specs/001-knowlayer-platform/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Test tasks are included for the MVP flows because the chat, retrieval, and follow-up behavior are core user value in v1.

**Organization**: Tasks are grouped by user story so each story can be implemented and validated independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the repository structure and tooling for the modular monolith MVP.

- [ ] T001 Create project structure under app/, streamlit_app/, tests/, and scripts/ according to plan.md
- [ ] T002 Initialize Python project configuration and dependency management for the backend and Streamlit app
- [ ] T003 [P] Configure linting, formatting, and Python test tooling
- [ ] T004 [P] Create environment template, settings schema, and local config conventions
- [ ] T005 Create developer notes for local setup, document ingestion, and run steps

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the shared architecture that all user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T006 Define domain interfaces and abstraction boundaries for document ingestion, retrieval, and LLM provider access
- [ ] T007 Implement document source and chunk domain models in app/domain/entities/document_models.py
- [ ] T008 Implement session and message domain models for chat continuity in app/domain/entities/chat_models.py
- [ ] T009 Implement local document loader and file management contract in app/infrastructure/document/local_document_loader.py
- [ ] T010 [P] Implement Chroma vector store adapter and retrieval abstraction in app/infrastructure/vector/chroma_client.py
- [ ] T011 [P] Implement chunking and embedding preparation contract in app/use_cases/ingestion/document_processing.py
- [ ] T012 Implement backend API skeleton and route registration in app/api/routes/
- [ ] T013 Create Streamlit UI shell and session state structure in streamlit_app/app.py and streamlit_app/state/
- [ ] T014 Add structured logging and environment-driven runtime configuration in app/core/
- [ ] T015 Define the query orchestration contract for policy retrieval and answer assembly in app/use_cases/chat/

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel.

---

## Phase 3: User Story 1 - Ask an HR policy question with grounded citations (Priority: P1) 🎯 MVP

**Goal**: Allow a user to ask a policy question and receive a grounded answer with citations from the approved HR document.

**Independent Test**: A user can submit a policy question, receive a relevant answer, and confirm the answer includes citations and source references.

### Tests for User Story 1

- [ ] T016 [P] [US1] Write integration test for single-document policy Q&A in tests/integration/test_policy_chat.py
- [ ] T017 [P] [US1] Write contract test for chat API response format in tests/contract/test_chat_api_contract.py

### Implementation for User Story 1

- [ ] T018 [P] [US1] Create the document ingestion script in scripts/ingest_documents.py
- [ ] T019 [P] [US1] Implement ingestion pipeline and document indexing in app/use_cases/ingestion/ingest_documents.py
- [ ] T020 [US1] Implement retrieval service for the approved HR document in app/use_cases/chat/retrieval_service.py
- [ ] T021 [US1] Implement provenance and citation assembly in app/use_cases/chat/provenance_service.py
- [ ] T022 [US1] Implement the query orchestrator for policy answer generation in app/use_cases/chat/query_orchestrator.py
- [ ] T023 [US1] Implement the chat endpoint in app/api/routes/chat.py and response schemas in app/api/schemas/chat.py
- [ ] T024 [US1] Connect the Streamlit UI to the backend chat API in streamlit_app/services/chat_service.py and streamlit_app/app.py
- [ ] T025 [US1] Add the policy chat page and answer rendering with citations in streamlit_app/pages/policy_chat.py

**Checkpoint**: At this point, User Story 1 should be fully functional and independently testable.

---

## Phase 4: User Story 2 - Follow-up questions in the same session (Priority: P2)

**Goal**: Keep a short rolling conversation window so follow-up questions like “What about parental leave?” are answered in context.

**Independent Test**: A user can ask an initial question and then a follow-up question in the same session and receive a context-aware answer grounded in the same document.

### Tests for User Story 2

- [ ] T026 [P] [US2] Write integration test for follow-up question continuity in tests/integration/test_followup_chat.py
- [ ] T027 [P] [US2] Write unit test for bounded conversation window memory in tests/unit/test_session_memory.py

### Implementation for User Story 2

- [ ] T028 [P] [US2] Add LangChain ConversationWindowBufferMemory integration in app/use_cases/chat/session_memory.py
- [ ] T029 [US2] Add session persistence contract for recent conversation state in app/domain/services/session_memory_service.py
- [ ] T030 [US2] Update the chat API to accept recent messages and session_id for context-aware calls in app/api/schemas/chat.py
- [ ] T031 [US2] Update the Streamlit session state to store recent user and assistant messages in streamlit_app/state/chat_state.py
- [ ] T032 [US2] Add follow-up question UI support and message history rendering in streamlit_app/pages/policy_chat.py
- [ ] T033 [US2] Add graceful fallback when the history window is empty or no prior context exists

**Checkpoint**: User Story 2 should work independently by preserving chat continuity within a bounded memory window.

---

## Phase 5: User Story 3 - Simple policy search and retrieval experience (Priority: P2)

**Goal**: Support a lightweight retrieval experience where users can search the approved HR document and get the most relevant section with citations.

**Independent Test**: A user can search for a topic and receive the most relevant policy section and citation metadata without leaving the app.

### Tests for User Story 3

- [ ] T034 [P] [US3] Write integration test for policy search retrieval in tests/integration/test_policy_search.py
- [ ] T035 [P] [US3] Write contract test for retrieval result structure in tests/contract/test_retrieval_contract.py

### Implementation for User Story 3

- [ ] T036 [P] [US3] Implement document search service over the approved HR source in app/use_cases/chat/document_search.py
- [ ] T037 [US3] Implement relevant chunk ranking and evidence extraction in app/use_cases/chat/chunk_selector.py
- [ ] T038 [US3] Add retrieval result formatting with page/section context and citations in app/use_cases/chat/result_formatter.py
- [ ] T039 [US3] Add policy search UI in streamlit_app/pages/search_policy.py
- [ ] T040 [US3] Add answer rendering logic for both direct Q&A and search-based lookup in streamlit_app/components/result_card.py

**Checkpoint**: The document-backed retrieval experience is independently usable and demonstrates the value of the policy chatbot.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, lightweight quality checks, and operational readiness for the MVP.

- [ ] T041 [P] Review and clean up shared app configuration, environment, and startup behavior
- [ ] T042 [P] Add smoke tests for ingestion, retrieval, and chat flow in scripts/smoke_test.py
- [ ] T043 Run the relevant test suite for unit, contract, and integration coverage
- [ ] T044 Validate the quickstart flow and ensure all main user journeys work end-to-end
- [ ] T045 Update project documentation to match the implemented MVP and the deferred future roadmap

---

## Phase 7: Convergence

- [x] T046 Implement the end-to-end US1 retrieval and answer workflow for the approved HR policy document in app/use_cases/chat/ and app/api/routes/chat.py (DONE: QueryOrchestrator, RetrievalService, ProvenanceService implemented; FR-002, FR-003, FR-004, US1/AC1)
- [x] T047 Replace the sample Streamlit response with an actual backend call and citation rendering in streamlit_app/app.py and streamlit_app/services/chat_service.py (DONE: Streamlit now calls ChatService backend; citations rendered; FR-012, US1/AC1, US3/AC1)
- [ ] T048 Add bounded session memory and follow-up question handling for US2 in app/use_cases/chat/session_memory.py, app/domain/services/session_memory_service.py, and app/api/schemas/chat.py (partial; US2/AC1, plan: rolling memory decision)
- [ ] T049 Add the retrieval/search flow and result formatting for US3 using the approved policy document and citation metadata in app/use_cases/chat/ and streamlit_app/pages/ (missing; US3/AC1, FR-003, FR-004)
- [ ] T050 Implement provider abstraction and runtime error handling for OpenRouter/Groq so the app can call the configured LLM provider without hardcoded sample logic (partial; FR-011, FR-015, plan: provider abstraction decision)
- [ ] T051 Add end-to-end smoke validation for ingestion, retrieval, and chat flow in scripts/smoke_test.py and the relevant test suite (partial; NFR-006, T042, T043, T044)
- [ ] T052 Align the implemented MVP behavior with the spec and quickstart documentation so the project reflects the actual single-document HR chatbot scope and future extensibility boundaries (partial; T045, plan: MVP scope, future extensibility)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup completion; blocks all user stories
- **User Stories (Phase 3+)**: Depend on Foundational completion
- **Polish (Phase 6)**: Depends on all required user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can begin after Phase 2 and is the core MVP deliverable
- **User Story 2 (P2)**: Can begin after Phase 2 and depends only on the session/chat foundation
- **User Story 3 (P2)**: Can begin after the core retrieval flow is working and can be developed in parallel with US2 where possible

### Parallel Opportunities

- Setup tasks marked [P] can run in parallel
- Foundational tasks marked [P] can run in parallel
- User story tests marked [P] can run in parallel
- Different story tasks can proceed in parallel after the foundational phase is complete

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. Validate the MVP independently against the policy Q&A flow
5. Add follow-up and retrieval enhancements after the core story is proven

### Incremental Delivery

1. Setup + Foundational → Platform anchor for the MVP
2. Add User Story 1 → Policy Q&A with citations
3. Add User Story 2 → Follow-up question continuity
4. Add User Story 3 → Search and retrieval experience
5. Finish with polish and validation

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Developer A: User Story 1
3. Developer B: User Story 2
4. Developer C: User Story 3
5. Final polish and smoke validation together
