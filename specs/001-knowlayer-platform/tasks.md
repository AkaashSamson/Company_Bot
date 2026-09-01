# Tasks: KnowLayer Platform

**Input**: Design documents from `/specs/001-knowlayer-platform/`

**Prerequisites**: plan.md (required), spec.md (required for user stories)

**Tests**: Security regression tests and adapter contract tests are required for this feature.

**Organization**: Tasks are grouped by user story to support independent delivery of MVP value.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the repository structure and core tooling for the modular monolith.

- [ ] T001 Create repository structure under backend/, streamlit_app/, and tests/ according to plan.md
- [ ] T002 Initialize Python project configuration and dependency management for backend and UI
- [ ] T003 [P] Configure linting, formatting, and Python test tooling
- [ ] T004 [P] Create environment configuration, settings schema, and secret handling conventions
- [ ] T005 Create project documentation index and development notes for KnowLayer MVP

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the core architecture that all user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T006 Define domain interfaces and abstract boundaries for LLM, storage, vector search, and enterprise connectors
- [ ] T007 Implement identity, role, and access-scoping models for employees and documents
- [ ] T008 [P] Implement authorization policy service and permission evaluation flow
- [ ] T009 Implement structured audit logging with sensitive-data redaction conventions
- [ ] T010 Create document metadata model and repository contract for ingested files
- [ ] T011 Implement document ingestion and storage adapter interfaces for raw files and metadata
- [ ] T012 Implement chunking and retrieval preparation contracts for document processing
- [ ] T013 Set up vector indexing contract and retrieval abstraction with source provenance metadata
- [ ] T014 Implement backend API skeleton with health, auth, query, and retrieval endpoints
- [ ] T015 Create dependency injection and app composition boundary for domain/service wiring
- [ ] T016 Set up the Streamlit UI shell and navigation structure for internal knowledge access

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel.

---

## Phase 3: User Story 1 - Policy and document knowledge access (Priority: P1) 🎯 MVP

**Goal**: Allow authenticated employees to ask policy and handbook questions and receive grounded answers with citations.

**Independent Test**: A user can submit a document-based policy question, receive the relevant result, and confirm all citations are present and traceable.

### Tests for User Story 1

- [ ] T017 [P] [US1] Write security regression test for unauthorized document access in backend/tests/security/test_document_access.py
- [ ] T018 [P] [US1] Write integration test for policy question flow in backend/tests/integration/test_policy_query.py
- [ ] T019 [P] [US1] Write contract test for document retrieval interface in backend/tests/contract/test_document_repo_contract.py

### Implementation for User Story 1

- [ ] T020 [P] [US1] Implement document ingestion pipeline in backend/app/services/document_ingestion.py
- [ ] T021 [P] [US1] Implement metadata extraction and indexing model in backend/app/domain/document_models.py
- [ ] T022 [US1] Implement authorized document retrieval service in backend/app/services/retrieval_service.py
- [ ] T023 [US1] Implement citation and provenance assembly in backend/app/services/provenance_service.py
- [ ] T024 [US1] Implement policy question answering orchestration in backend/app/services/query_orchestrator.py
- [ ] T025 [US1] Connect the backend query API to the Streamlit UI in streamlit_app/services/query_service.py
- [ ] T026 [US1] Add user-facing policy question UI in streamlit_app/pages/policy_chat.py
- [ ] T027 [US1] Add logging and trace metadata for document retrieval and answer generation

**Checkpoint**: At this point, User Story 1 should be fully functional and independently testable.

---

## Phase 4: User Story 2 - Employee-specific authoritative data (Priority: P1)

**Goal**: Support employee-specific questions that require real-time HR or enterprise data and must use the authoritative source.

**Independent Test**: A user can ask for leave balance or appraisal information and receive only the data the system authorizes for that user.

### Tests for User Story 2

- [ ] T028 [P] [US2] Write security regression test for employee access isolation in backend/tests/security/test_employee_isolation.py
- [ ] T029 [P] [US2] Write integration test for HR balance lookup in backend/tests/integration/test_hr_lookup.py
- [ ] T030 [P] [US2] Write adapter contract test for HR connector boundary in backend/tests/contract/test_hr_adapter_contract.py

### Implementation for User Story 2

- [ ] T031 [P] [US2] Create authoritative data interface definitions under backend/app/domain/enterprise_interfaces.py
- [ ] T032 [US2] Implement a mock HR adapter and data contract for testing and development in backend/app/infra/mock_hr_adapter.py
- [ ] T033 [US2] Implement authorization-aware employee lookup workflow in backend/app/services/employee_data_service.py
- [ ] T034 [US2] Wire authoritative data routing into the query orchestrator in backend/app/services/query_orchestrator.py
- [ ] T035 [US2] Add employee-specific UI for leave and profile queries in streamlit_app/pages/employee_data.py
- [ ] T036 [US2] Add provenance metadata for HR sources and retrieval timestamps

**Checkpoint**: User Story 2 should work independently without using stale document data for authoritative facts.

---

## Phase 5: User Story 3 - Hybrid policy + personal synthesis (Priority: P1)

**Goal**: Combine organizational policies and employee-specific data into a single grounded answer.

**Independent Test**: A user can ask a hybrid question that combines policy and personal facts and receive one answer with source provenance from both sources.

### Tests for User Story 3

- [ ] T037 [P] [US3] Write integration test for hybrid answer synthesis in backend/tests/integration/test_hybrid_query.py
- [ ] T038 [P] [US3] Write security regression test for cross-employee hybrid leakage in backend/tests/security/test_hybrid_leakage.py
- [ ] T039 [P] [US3] Write contract test for synthesis boundary and provenance in backend/tests/contract/test_synthesis_contract.py

### Implementation for User Story 3

- [ ] T040 [P] [US3] Define hybrid answer payload model in backend/app/domain/answer_models.py
- [ ] T041 [US3] Implement answer synthesis and evidence aggregation in backend/app/services/hybrid_answer_service.py
- [ ] T042 [US3] Ensure provenance and citation rendering includes document and enterprise source references
- [ ] T043 [US3] Add UI support for combined policy and personal answers in streamlit_app/pages/hybrid_queries.py
- [ ] T044 [US3] Add guardrails to prevent unauthorized cross-employee data in the synthesis layer

**Checkpoint**: At this point, the hybrid use case is independently functional and secure.

---

## Phase 6: User Story 4 - Organizational knowledge discovery (Priority: P2)

**Goal**: Support cross-document search for architecture, project, and technical knowledge with citations and authorization checks.

**Independent Test**: A user can search authorized organizational documents and receive only relevant knowledge from accessible sources.

### Tests for User Story 4

- [ ] T045 [P] [US4] Write integration test for document search and citation output in backend/tests/integration/test_document_search.py
- [ ] T046 [P] [US4] Write security regression test for restricted project-document visibility in backend/tests/security/test_project_document_access.py

### Implementation for User Story 4

- [ ] T047 [P] [US4] Implement project knowledge search service in backend/app/services/project_search_service.py
- [ ] T048 [US4] Add project-document query UI in streamlit_app/pages/project_knowledge.py
- [ ] T049 [US4] Ensure search results include document identifiers, chunk IDs, and retrieval timestamps
- [ ] T050 [US4] Add organization-level document filters for team and role permissions

**Checkpoint**: Organizational knowledge discovery can be tested independently and used without exposing unauthorized sources.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Hardening and operational quality across all user stories.

- [ ] T051 [P] Performance tuning for retrieval, indexing, and response assembly
- [ ] T052 [P] Documentation updates for setup, usage, and security assumptions
- [ ] T053 Security hardening review for logs, tokens, and sensitive configuration handling
- [ ] T054 Cross-story validation of provider abstraction and dependency seams
- [ ] T055 Run the full regression suite for unit, contract, integration, and security tests
- [ ] T056 Validate the quickstart flow and evidence traceability in the Streamlit app

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup completion; blocks all user stories
- **User Stories (Phase 3+)**: Depend on Foundational completion
- **Polish (Phase 7)**: Depends on all required stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Phase 2, independent MVP set
- **User Story 2 (P1)**: Requires Phase 2 and can proceed in parallel with US1 once foundation is ready
- **User Story 3 (P1)**: Requires US1/US2 foundation and orchestrator support
- **User Story 4 (P2)**: Can start after the retrieval platform is stable

### Parallel Opportunities

- Setup tasks marked [P] can run in parallel
- Foundational tasks marked [P] can run in parallel
- User story tests marked [P] can run in parallel
- Different user stories can proceed in parallel by separate team members after the foundation is complete

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. Validate independent MVP output and security gates
5. Extend progressively to US2 and US3

### Incremental Delivery

1. Setup + Foundational → stable platform foundation
2. Add User Story 1 → secure policy answer flow
3. Add User Story 2 → authoritative employee data access
4. Add User Story 3 → hybrid synthesis with citations
5. Add User Story 4 → broader organizational knowledge discovery

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Split work by story:
   - Developer A: US1
   - Developer B: US2
   - Developer C: US3
   - Developer D: US4 / polish
3. Validate security boundaries after each story is produced

---

## Notes

- Tasks marked [P] are independent and can be worked in parallel where the repository allows it.
- Security and authorization tasks are not optional and must be validated before release.
- Each user story must remain independently testable and not depend on hidden coupling across stories.
- The MVP must avoid microservices, Kubernetes, multi-agent orchestration, and premature complexity.
- Keep all protocol contracts explicit and domain-led rather than UI-driven.
