<!--
Sync Impact Report
Version change: N/A -> 1.0.0
List of modified principles: N/A -> I. Architectural Boundaries & Modularity; II. Ground Truth & Authoritative State; III. Security & Access Control Gates; IV. Spec-Driven Development Governance; V. Quality, Testing & Complexity Guardrails
Added sections: Additional Constraints; Development Workflow
Removed sections: None
Deferred items: None
-->

# KnowLayer Constitution

## Core Principles

### I. Architectural Boundaries & Modularity
KnowLayer MUST maintain a modular monolith and hexagonal architecture with strict isolation between the core domain and external infrastructure. The core intelligence layer MUST NOT import or depend on any specific UI, LLM provider, database, vector store, object store, or enterprise connector. All external touchpoints, including LLMs, storage, identity, and enterprise APIs, MUST be accessed through domain-defined abstract interfaces and ports so the business logic remains portable and reviewable.

This rule prevents implementation drift and keeps domain contracts stable. External providers are replaceable adapters, not design dependencies, and the domain remains the single source of truth for business rules.

### II. Ground Truth & Authoritative State
The LLM is an orchestration and synthesis engine, not the system of record for real-time or sensitive enterprise facts. The query orchestrator MUST determine whether a request requires static document knowledge, real-time authoritative lookup, or hybrid synthesis, and MUST route to the correct retrieval path without guessing. Knowledge from policies, documents, and live enterprise systems may inform synthesis, but the architecture MUST treat authoritative facts as sourced from trusted systems with explicit provenance.

Every synthesized response MUST return strict source citations including document IDs, chunk IDs, page or section references, and retrieval timestamps. This requirement ensures traceability, reviewability, and accountability for every answer produced by the system.

### III. Security & Access Control Gates
Before retrieval occurs, identity, security context, and document or record-level authorization MUST be evaluated. Post-retrieval filtering and LLM-based redaction are strictly prohibited because they allow sensitive data to be exposed in the retrieval path. The system MUST enforce user-context injection for employee_id, role, team_ids, and access_scopes in every query pipeline and MUST prevent one employee's private records from appearing in another employee's results.

Every query, tool invocation, retrieved context set, and LLM call MUST produce structured, traceable audit logs without logging sensitive raw data in cleartext. This is a non-negotiable control for compliance, incident investigation, and secure operation.

### IV. Spec-Driven Development Governance
Code MUST follow approved specifications. No feature implementation may begin without an approved spec.md, plan.md, and tasks.md. The Spec-Driven Development workflow is the governing process for design, implementation, and review, and all work MUST be traceable to approved artifacts.

If an implementation edge case exposes an architectural or contract flaw, the developer MUST halt immediately, update the specification through a PR, obtain review, and only then resume coding. This drift rule preserves contract integrity and prevents silent divergence between plan and implementation. Teams MUST distribute work across abstract boundaries and validate against mock adapters such as MockLLMProvider and MockVectorStore until real adapters are reviewed and merged.

### V. Quality, Testing & Complexity Guardrails
KnowLayer MUST favor simplicity over premature complexity. During MVP, the team MUST avoid microservices, Kubernetes, multi-agent frameworks, knowledge graphs, and complex event brokers unless a concrete, justified requirement forces them. The default posture is simple integration, explicit interfaces, and direct operational clarity.

Mandatory test gates apply to all work:
- Unit tests MUST cover core domain logic using mock-based tests where appropriate.
- Security regression tests MUST assert that unauthorized users receive zero hits on restricted documents or records.
- Adapter contract tests MUST verify that provider swaps, such as Ollama to OpenRouter, do not break the domain workflows or contracts.

## Additional Constraints
KnowLayer MUST preserve tenant and employee data isolation across all retrieval, orchestration, and synthesis flows. No pipeline may combine user context and enterprise data in a way that bypasses access boundaries. Sensitive enterprise facts, including leave balances, appraisals, and Jira tickets, MUST never be treated as a writable source by the LLM, which may only synthesize from retrieved authoritative data and system-approved context.

The system MUST also support multi-source routing when a query requires static document knowledge, real-time enterprise lookups, or a hybrid result. This ensures that the architecture stays faithful to source-of-truth rules while enabling correct responses across both policy and operational data domains.

## Development Workflow
All changes MUST remain aligned with the approved specification, planning artifacts, and review workflow. Implementation work MUST be broken along abstract boundaries, reviewed by the team, and validated against contract tests before the real provider adapters are promoted to production. The team MUST treat the architecture as the contract boundary and the spec as the source of truth for behavior.

Review and compliance checks MUST include explicit verification that security rules, architecture boundaries, and evidence requirements remain intact. Any exception or compromise in these rules MUST be documented and approved before merge, with a clear remediation plan and governance follow-up.

## Governance
This Constitution supersedes informal team conventions and governs all AI agents, plans, tasks, code reviews, and pull requests for KnowLayer. Amendments require clear rationale, implementation impact review, and documentation of any migration or compliance implications before merge. The project MUST retain an auditable record of governance changes, and every amendment MUST be traceable to the versioned constitution.

Versioning follows semantic versioning:
- MAJOR: backward-incompatible governance or principle removals or redefinitions.
- MINOR: new principle or section added or materially expanded guidance.
- PATCH: clarifications, wording fixes, non-semantic refinements, or editorial improvements.

All PRs and reviews MUST verify compliance with this Constitution. If a team member identifies a violation, drift, or ambiguity, the issue MUST be escalated through the review process and resolved before the work is considered complete.

**Version**: 1.0.0 | **Ratified**: 2026-09-01 | **Last Amended**: 2026-09-01
