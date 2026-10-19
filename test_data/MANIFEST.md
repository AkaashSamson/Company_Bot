# Test Data Manifest & Document Catalog

This directory contains the curated **golden document set** used to populate ChromaDB, benchmark RAG retrieval, measure chunking quality, and test RBAC authorization.

---

## Document Catalog

| Document File | Chunk ID Pattern | Category | Content Description | Key Test Topics Covered |
| :--- | :--- | :--- | :--- | :--- |
| **`NEXORA TECHNOLOGIES PVT.pdf`** | `NEXORA TECHNOLOGIES PVT-*` | Company Handbook | The complete 50+ page official employee handbook. | Working hours, probation period, attendance, annual leave, sick leave, travel policies, remote work, IT equipment, resignation, code of conduct. |
| **`NEXORA TECHNOLOGIES PVT.docx`** | `NEXORA TECHNOLOGIES PVT-*` | Company Handbook | Editable Word version of the handbook for Word parser benchmarking. | Same as PDF, used to evaluate DOCX vs PDF parser consistency and page mapping. |
| **`HR_Policy_Manual.docx`** | `HR_Policy_Manual-*` | Enterprise Policy | Comprehensive HR operational manual. | Remote and hybrid work eligibility, expense reimbursement, leave entitlement calculation, carry-forward limits. |
| **`POSH_Policy.docx`** | `POSH_Policy-*` | Legal & Compliance | Prevention of Sexual Harassment (POSH) statutory policy. | Internal Complaints Committee (ICC), complaint filing workflow, inquiry timelines, confidentiality rules, redressal procedures. |
| **`DOC-001.docx`** | `DOC-001-*` | General Policy | High-level organizational overview and RAG architecture principles. | RAG approach overview, success criteria, department directory. |
| **`DOC-002.docx`** | `DOC-002-*` | Project Policy | Project delivery policies and role definitions. | Project lead duties, code reviews, deployment checklist. |
| **`DOC-003.docx`** | `DOC-003-*` | Technical Standards | Architecture guidelines and API contracts. | Microservices standards, caching policies, authentication tokens. |
| **`DOC-004.docx`** | `DOC-004-*` | Operational SOP | Leave application workflows and approval chains. | Leave management system steps, manager sign-off, medical certificate requirements. |
| **`DOC-005.docx`** | `DOC-005-*` | Disciplinary Rules | Ethics, disciplinary guidelines, and workplace conduct. | Conflict of interest, confidentiality breach consequences, appeal process. |
| **`DOC-006.docx`** | `DOC-006-*` | Project Architecture | System specification and task lifecycle. | Ownership models, sprint reviews, documentation requirements. |
| **`DOC-007.docx`** | `DOC-007-*` | System Architecture | Scalability, database replication, and cache invalidation. | Vertical vs horizontal scaling, cache-aside pattern, database sharding. |
| **`TEST-001.docx`** | `TEST-001-*` | Project Apollo SOP | Confidential project documentation (`project_id='121'`). | RBAC isolation testing, unauthorized access detection, project contact lookup. |

---

## Role in RAG Pipeline Validation

1. **General Knowledge Baseline:** `NEXORA TECHNOLOGIES PVT.pdf`, `HR_Policy_Manual.docx`, `POSH_Policy.docx` form the public ground truth for company-wide queries.
2. **Procedural Workflows:** `DOC-004.docx` and the Handbook Section 6 test step-by-step instructions.
3. **RBAC Isolation:** `TEST-001.docx` and `DOC-002.docx` carry project scopes to test cross-role permission guards.
