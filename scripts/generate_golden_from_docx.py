"""
Generates the Golden Benchmark Dataset directly from the official .docx files in input/
Sources:
- input/NEXORA TECHNOLOGIES PVT.docx (Employee Handbook v2.0)
- input/POSH_Policy.docx (Prevention of Sexual Harassment Policy)
- input/DOC-001.docx (Employee Onboarding Guide)
- input/DOC-004.docx (HR Policy Knowledge System Architecture Overview)
"""

import json
import hashlib
from pathlib import Path
import docx

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = WORKSPACE_ROOT / "input"
OUTPUT_FILE = WORKSPACE_ROOT / "tests" / "fixtures" / "cache_golden_dataset.json"

def get_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]

def build_dataset():
    # Load input documents
    doc_nexora = docx.Document(INPUT_DIR / "NEXORA TECHNOLOGIES PVT.docx")
    nexora_paras = [p.text.strip() for p in doc_nexora.paragraphs if p.text.strip()]

    doc_posh = docx.Document(INPUT_DIR / "POSH_Policy.docx")
    posh_paras = [p.text.strip() for p in doc_posh.paragraphs if p.text.strip()]

    doc_onboard = docx.Document(INPUT_DIR / "DOC-001.docx")
    onboard_paras = [p.text.strip() for p in doc_onboard.paragraphs if p.text.strip()]

    # Extract exact ground-truth paragraphs
    # NEXORA:
    # P1930: Annual leave = 18 days
    p_annual_leave = nexora_paras[1930]
    # P1932: Carry forward annual leave = up to 10 days
    p_carry_annual = nexora_paras[1932]
    # P1934: Casual leave expires at end of calendar year
    p_casual_expire = nexora_paras[1934]
    # P1938: Attendance correction within 2 working days
    p_attend_correct = nexora_paras[1938]
    # P1940: Standard schedule = 9:30 AM to 6:30 PM, Monday to Friday
    p_work_hours = nexora_paras[1940]
    # P1942: 15-minute grace period
    p_grace_period = nexora_paras[1942]
    # P1948: Remote work international = Not without prior written approval
    p_intl_remote = nexora_paras[1948]
    # P1955: Vendor cash gifts = Cash and cash-equivalent gifts must not be accepted
    p_vendor_gifts = nexora_paras[1955]
    # P677: Compensation confidentiality
    p_comp_confidential = nexora_paras[677]

    # POSH:
    # P152: Under Section 9, complaint within 3 months, extendable by 3 months
    p_posh_timeline = posh_paras[152]
    # P65: Managers must not independently investigate a formal POSH complaint
    p_posh_manager = posh_paras[65]

    # ONBOARDING:
    p_info_sec = [p for p in onboard_paras if "Passwords, authentication tokens" in p][0]

    golden_cases = [
        # 1. NUMERIC: Annual leave days
        {
            "id": "GOLDEN-DOCX-NUM-01",
            "category": "NUMERIC_CONTRADICTION",
            "source_document": "NEXORA TECHNOLOGIES PVT.docx",
            "description": "Annual Leave days entitlement was updated to 18 days; stale cache has 12 days.",
            "current_user_query": "How many days of Annual Leave do eligible regular employees get each year?",
            "cached_query": "how many annual leave days per year",
            "cached_answer": "Eligible regular employees receive 12 days of Annual Leave per calendar year.",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "Eligible regular employees receive 12 days of Annual Leave per calendar year.",
                    "is_material": True
                }
            ],
            "source_evidence_chunks": [
                {
                    "chunk_id": "nexora_handbook_chunk_1930",
                    "document_id": "NEXORA TECHNOLOGIES PVT.docx",
                    "chunk_hash": get_hash(p_annual_leave),
                    "text": p_annual_leave
                }
            ],
            "user_context": {"user_id": "usr_nex_01", "roles": ["employee"], "project_ids": ["default"], "is_admin": False},
            "cached_metadata": {"tenant_id": "nexora", "project_id": "default", "assigned_role": "employee", "risk_level": "LOW", "intent": "LEAVE"},
            "ground_truth_decision": "REJECT_FALLBACK_RAG",
            "current_pipeline_expected": {
                "action": "REUSE",
                "reason": "Token overlap is 86%. Vector distance < 0.45. C.R.E.A.T.E. gate approves and leaks 12 days.",
                "is_correct": False,
                "failure_type": "FATAL_FALSE_REUSE"
            },
            "hybrid_pipeline_expected": {
                "nli_verdict": "CONTRADICTION",
                "nli_confidence": 0.95,
                "jev_decision": "REJECT",
                "action": "REJECT_FALLBACK_RAG",
                "is_correct": True,
                "explanation": "NLI detects numeric contradiction: document states 18 days, cached answer claims 12 days."
            }
        },

        # 2. NUMERIC: Annual leave carry-forward limit
        {
            "id": "GOLDEN-DOCX-NUM-02",
            "category": "NUMERIC_CONTRADICTION",
            "source_document": "NEXORA TECHNOLOGIES PVT.docx",
            "description": "Annual Leave carry-forward allows 10 days; stale cache has 5 days.",
            "current_user_query": "How many unused Annual Leave days can I carry forward to next year?",
            "cached_query": "carry forward unused annual leave limit",
            "cached_answer": "Yes. Up to 5 unused Annual Leave days may normally be carried forward to the following calendar year.",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "Up to 5 unused Annual Leave days may normally be carried forward to the following calendar year.",
                    "is_material": True
                }
            ],
            "source_evidence_chunks": [
                {
                    "chunk_id": "nexora_handbook_chunk_1932",
                    "document_id": "NEXORA TECHNOLOGIES PVT.docx",
                    "chunk_hash": get_hash(p_carry_annual),
                    "text": p_carry_annual
                }
            ],
            "user_context": {"user_id": "usr_nex_02", "roles": ["employee"], "project_ids": ["default"], "is_admin": False},
            "cached_metadata": {"tenant_id": "nexora", "project_id": "default", "assigned_role": "employee", "risk_level": "LOW", "intent": "LEAVE"},
            "ground_truth_decision": "REJECT_FALLBACK_RAG",
            "current_pipeline_expected": {
                "action": "REUSE",
                "reason": "Token intersection is 91%. Distance < 0.40. C.R.E.A.T.E. approves.",
                "is_correct": False,
                "failure_type": "FATAL_FALSE_REUSE"
            },
            "hybrid_pipeline_expected": {
                "nli_verdict": "CONTRADICTION",
                "nli_confidence": 0.93,
                "jev_decision": "REJECT",
                "action": "REJECT_FALLBACK_RAG",
                "is_correct": True,
                "explanation": "NLI flags 5 days vs 10 days as numeric contradiction."
            }
        },

        # 3. NUMERIC: Attendance correction deadline
        {
            "id": "GOLDEN-DOCX-NUM-03",
            "category": "NUMERIC_CONTRADICTION",
            "source_document": "NEXORA TECHNOLOGIES PVT.docx",
            "description": "Attendance correction window is 2 working days; stale cache claims 7 working days.",
            "current_user_query": "What is the time limit to submit an attendance correction if I forgot to mark attendance?",
            "cached_query": "attendance correction deadline days",
            "cached_answer": "You should submit an attendance correction request through the designated system, normally within seven working days of the missed entry.",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "Submit attendance correction request within seven working days of missed entry.",
                    "is_material": True
                }
            ],
            "source_evidence_chunks": [
                {
                    "chunk_id": "nexora_handbook_chunk_1938",
                    "document_id": "NEXORA TECHNOLOGIES PVT.docx",
                    "chunk_hash": get_hash(p_attend_correct),
                    "text": p_attend_correct
                }
            ],
            "user_context": {"user_id": "usr_nex_03", "roles": ["employee"], "project_ids": ["default"], "is_admin": False},
            "cached_metadata": {"tenant_id": "nexora", "project_id": "default", "assigned_role": "employee", "risk_level": "LOW", "intent": "ATTENDANCE"},
            "ground_truth_decision": "REJECT_FALLBACK_RAG",
            "current_pipeline_expected": {
                "action": "REUSE",
                "reason": "Token overlap is 88%. Distance < 0.42. Passes C.R.E.A.T.E.",
                "is_correct": False,
                "failure_type": "FATAL_FALSE_REUSE"
            },
            "hybrid_pipeline_expected": {
                "nli_verdict": "CONTRADICTION",
                "nli_confidence": 0.96,
                "jev_decision": "REJECT",
                "action": "REJECT_FALLBACK_RAG",
                "is_correct": True,
                "explanation": "NLI detects contradiction between 2 working days and 7 working days."
            }
        },

        # 4. NUMERIC: POSH filing window
        {
            "id": "GOLDEN-DOCX-NUM-04",
            "category": "NUMERIC_CONTRADICTION",
            "source_document": "POSH_Policy.docx",
            "description": "POSH complaint must be filed within 3 months; stale cache claims 12 months.",
            "current_user_query": "Within what timeframe must a sexual harassment complaint be filed with the Internal Committee?",
            "cached_query": "posh complaint filing timeframe months",
            "cached_answer": "Under the POSH policy, a complaint must ordinarily be made in writing to the Internal Committee within 12 months of the incident.",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "Complaint must ordinarily be made in writing to Internal Committee within 12 months.",
                    "is_material": True
                }
            ],
            "source_evidence_chunks": [
                {
                    "chunk_id": "posh_policy_chunk_152",
                    "document_id": "POSH_Policy.docx",
                    "chunk_hash": get_hash(p_posh_timeline),
                    "text": p_posh_timeline
                }
            ],
            "user_context": {"user_id": "usr_posh_01", "roles": ["employee"], "project_ids": ["default"], "is_admin": False},
            "cached_metadata": {"tenant_id": "nexora", "project_id": "default", "assigned_role": "employee", "risk_level": "HIGH", "intent": "POSH"},
            "ground_truth_decision": "REJECT_FALLBACK_RAG",
            "current_pipeline_expected": {
                "action": "REUSE",
                "reason": "Lexical token overlap is 85%. Distance < 0.40. C.R.E.A.T.E. leaks 12 months.",
                "is_correct": False,
                "failure_type": "FATAL_FALSE_REUSE"
            },
            "hybrid_pipeline_expected": {
                "nli_verdict": "CONTRADICTION",
                "nli_confidence": 0.98,
                "jev_decision": "REJECT",
                "action": "REJECT_FALLBACK_RAG",
                "is_correct": True,
                "explanation": "NLI flags 3 months vs 12 months contradiction. Jev confirms high-risk compliance rejection."
            }
        },

        # 5. NEGATION: Casual leave carry-forward
        {
            "id": "GOLDEN-DOCX-NEG-01",
            "category": "NEGATION_INVERSION",
            "source_document": "NEXORA TECHNOLOGIES PVT.docx",
            "description": "Handbook specifies Casual Leave CANNOT be carried forward; inverted cache says it CAN be carried forward.",
            "current_user_query": "Can unused Casual Leave be carried forward to the following year?",
            "cached_query": "can unused casual leave be carried forward",
            "cached_answer": "Unused Casual Leave does not expire at the end of the calendar year and can normally be carried forward.",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "Unused Casual Leave does not expire and can normally be carried forward.",
                    "is_material": True
                }
            ],
            "source_evidence_chunks": [
                {
                    "chunk_id": "nexora_handbook_chunk_1934",
                    "document_id": "NEXORA TECHNOLOGIES PVT.docx",
                    "chunk_hash": get_hash(p_casual_expire),
                    "text": p_casual_expire
                }
            ],
            "user_context": {"user_id": "usr_nex_04", "roles": ["employee"], "project_ids": ["default"], "is_admin": False},
            "cached_metadata": {"tenant_id": "nexora", "project_id": "default", "assigned_role": "employee", "risk_level": "LOW", "intent": "LEAVE"},
            "ground_truth_decision": "REJECT_FALLBACK_RAG",
            "current_pipeline_expected": {
                "action": "REUSE",
                "reason": "90% of words overlap. Only negation particles differ. C.R.E.A.T.E. approves.",
                "is_correct": False,
                "failure_type": "FATAL_FALSE_REUSE"
            },
            "hybrid_pipeline_expected": {
                "nli_verdict": "CONTRADICTION",
                "nli_confidence": 0.97,
                "jev_decision": "REJECT",
                "action": "REJECT_FALLBACK_RAG",
                "is_correct": True,
                "explanation": "NLI detects polar negation: document says 'cannot normally be carried forward' vs cache 'can normally be carried forward'."
            }
        },

        # 6. NEGATION: International remote work approval
        {
            "id": "GOLDEN-DOCX-NEG-02",
            "category": "NEGATION_INVERSION",
            "source_document": "NEXORA TECHNOLOGIES PVT.docx",
            "description": "International remote work is strictly NOT permitted without approval; cached answer says freely permitted.",
            "current_user_query": "Can I work remotely from another country during my vacation?",
            "cached_query": "work remotely from another country",
            "cached_answer": "Yes, employees are permitted to work remotely from another country freely without requiring prior written approval.",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "Employees can work remotely from another country freely without prior written approval.",
                    "is_material": True
                }
            ],
            "source_evidence_chunks": [
                {
                    "chunk_id": "nexora_handbook_chunk_1948",
                    "document_id": "NEXORA TECHNOLOGIES PVT.docx",
                    "chunk_hash": get_hash(p_intl_remote),
                    "text": p_intl_remote
                }
            ],
            "user_context": {"user_id": "usr_nex_05", "roles": ["employee"], "project_ids": ["default"], "is_admin": False},
            "cached_metadata": {"tenant_id": "nexora", "project_id": "default", "assigned_role": "employee", "risk_level": "HIGH", "intent": "POLICY"},
            "ground_truth_decision": "REJECT_FALLBACK_RAG",
            "current_pipeline_expected": {
                "action": "REUSE",
                "reason": "Overlap of terms ('work', 'remotely', 'country', 'approval') is >80%. Distance < 0.40. Passes C.R.E.A.T.E.",
                "is_correct": False,
                "failure_type": "FATAL_FALSE_REUSE"
            },
            "hybrid_pipeline_expected": {
                "nli_verdict": "CONTRADICTION",
                "nli_confidence": 0.98,
                "jev_decision": "REJECT",
                "action": "REJECT_FALLBACK_RAG",
                "is_correct": True,
                "explanation": "NLI detects direct conflict with 'Not without prior written approval'. Jev blocks high-risk tax/export compliance error."
            }
        },

        # 7. NEGATION: Vendor cash gifts
        {
            "id": "GOLDEN-DOCX-NEG-03",
            "category": "NEGATION_INVERSION",
            "source_document": "NEXORA TECHNOLOGIES PVT.docx",
            "description": "Cash gifts must NOT be accepted; cached answer says cash gifts under $50 are accepted.",
            "current_user_query": "Can I accept cash or gift card tokens from a vendor during festival season?",
            "cached_query": "accept cash gifts from vendors",
            "cached_answer": "Cash and cash-equivalent gifts may be accepted from vendors and business partners if they are below $50 in value.",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "Cash gifts may be accepted from vendors if below $50 in value.",
                    "is_material": True
                }
            ],
            "source_evidence_chunks": [
                {
                    "chunk_id": "nexora_handbook_chunk_1955",
                    "document_id": "NEXORA TECHNOLOGIES PVT.docx",
                    "chunk_hash": get_hash(p_vendor_gifts),
                    "text": p_vendor_gifts
                }
            ],
            "user_context": {"user_id": "usr_nex_06", "roles": ["employee"], "project_ids": ["default"], "is_admin": False},
            "cached_metadata": {"tenant_id": "nexora", "project_id": "default", "assigned_role": "employee", "risk_level": "HIGH", "intent": "ETHICS"},
            "ground_truth_decision": "REJECT_FALLBACK_RAG",
            "current_pipeline_expected": {
                "action": "REUSE",
                "reason": "Token overlap is high. Distance < 0.45. C.R.E.A.T.E. passes.",
                "is_correct": False,
                "failure_type": "FATAL_FALSE_REUSE"
            },
            "hybrid_pipeline_expected": {
                "nli_verdict": "CONTRADICTION",
                "nli_confidence": 0.98,
                "jev_decision": "REJECT",
                "action": "REJECT_FALLBACK_RAG",
                "is_correct": True,
                "explanation": "NLI catches contradiction: 'must not be accepted' vs 'may be accepted'."
            }
        },

        # 8. NEGATION: Manager investigating formal POSH complaint
        {
            "id": "GOLDEN-DOCX-NEG-04",
            "category": "NEGATION_INVERSION",
            "source_document": "POSH_Policy.docx",
            "description": "Managers must NOT independently investigate POSH complaints; cached answer says managers can investigate.",
            "current_user_query": "Can my direct reporting manager investigate a formal POSH sexual harassment complaint?",
            "cached_query": "can managers investigate posh complaints",
            "cached_answer": "Managers are authorized to independently investigate formal POSH complaints and reach disciplinary decisions.",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "Managers can independently investigate formal POSH complaints.",
                    "is_material": True
                }
            ],
            "source_evidence_chunks": [
                {
                    "chunk_id": "posh_policy_chunk_65",
                    "document_id": "POSH_Policy.docx",
                    "chunk_hash": get_hash(p_posh_manager),
                    "text": p_posh_manager
                }
            ],
            "user_context": {"user_id": "usr_posh_02", "roles": ["employee"], "project_ids": ["default"], "is_admin": False},
            "cached_metadata": {"tenant_id": "nexora", "project_id": "default", "assigned_role": "employee", "risk_level": "HIGH", "intent": "POSH"},
            "ground_truth_decision": "REJECT_FALLBACK_RAG",
            "current_pipeline_expected": {
                "action": "REUSE",
                "reason": "Keywords 'managers', 'investigate', 'formal', 'posh', 'complaints' match 100%. Gate passes.",
                "is_correct": False,
                "failure_type": "FATAL_FALSE_REUSE"
            },
            "hybrid_pipeline_expected": {
                "nli_verdict": "CONTRADICTION",
                "nli_confidence": 0.97,
                "jev_decision": "REJECT",
                "action": "REJECT_FALLBACK_RAG",
                "is_correct": True,
                "explanation": "NLI catches contradiction against 'Managers must not independently investigate a formal POSH complaint'."
            }
        },

        # 9. QUERY-ANSWER MISMATCH: Casual Leave vs Annual Leave
        {
            "id": "GOLDEN-DOCX-QA-01",
            "category": "QUERY_ANSWER_MISMATCH",
            "source_document": "NEXORA TECHNOLOGIES PVT.docx",
            "description": "User asked about Casual Leave carry forward, but cached answer answers Annual Leave carry forward.",
            "current_user_query": "Can I carry forward unused Casual Leave to next year?",
            "cached_query": "carry forward unused leave to next year",
            "cached_answer": "Yes. Up to 10 unused Annual Leave days may normally be carried forward to the following calendar year.",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "Up to 10 unused Annual Leave days may normally be carried forward.",
                    "is_material": True
                }
            ],
            "source_evidence_chunks": [
                {
                    "chunk_id": "nexora_handbook_chunk_1932",
                    "document_id": "NEXORA TECHNOLOGIES PVT.docx",
                    "chunk_hash": get_hash(p_carry_annual),
                    "text": p_carry_annual
                }
            ],
            "user_context": {"user_id": "usr_nex_07", "roles": ["employee"], "project_ids": ["default"], "is_admin": False},
            "cached_metadata": {"tenant_id": "nexora", "project_id": "default", "assigned_role": "employee", "risk_level": "LOW", "intent": "LEAVE"},
            "ground_truth_decision": "REJECT_FALLBACK_RAG",
            "current_pipeline_expected": {
                "action": "REUSE",
                "reason": "Evidence entails the cached answer 100%. Semantic search similarity > 0.85 (both about carrying leave forward). Leaks misleading answer.",
                "is_correct": False,
                "failure_type": "QUERY_ANSWER_SEMANTIC_GAP"
            },
            "hybrid_pipeline_expected": {
                "query_compatibility_verdict": "FAIL",
                "nli_verdict": "NEUTRAL_TO_QUERY",
                "jev_decision": "REJECT",
                "action": "REJECT_FALLBACK_RAG",
                "is_correct": True,
                "explanation": "Query ↔ Answer check catches subject shift: user asked for Casual Leave, cached answer is for Annual Leave."
            }
        },

        # 10. QUERY-ANSWER MISMATCH: Grace period vs Lunch Break
        {
            "id": "GOLDEN-DOCX-QA-02",
            "category": "QUERY_ANSWER_MISMATCH",
            "source_document": "NEXORA TECHNOLOGIES PVT.docx",
            "description": "User asked for afternoon lunch break duration, but cached answer gives morning arrival grace period.",
            "current_user_query": "How many minutes are allocated for lunch breaks during the work day?",
            "cached_query": "allowed break minutes during work day",
            "cached_answer": "Yes. A 15-minute grace period is provided for occasional delays. Arrival by 9:45 AM falls within the grace period.",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "A 15-minute grace period is provided for occasional delays arriving by 9:45 AM.",
                    "is_material": True
                }
            ],
            "source_evidence_chunks": [
                {
                    "chunk_id": "nexora_handbook_chunk_1942",
                    "document_id": "NEXORA TECHNOLOGIES PVT.docx",
                    "chunk_hash": get_hash(p_grace_period),
                    "text": p_grace_period
                }
            ],
            "user_context": {"user_id": "usr_nex_08", "roles": ["employee"], "project_ids": ["default"], "is_admin": False},
            "cached_metadata": {"tenant_id": "nexora", "project_id": "default", "assigned_role": "employee", "risk_level": "LOW", "intent": "ATTENDANCE"},
            "ground_truth_decision": "REJECT_FALLBACK_RAG",
            "current_pipeline_expected": {
                "action": "REUSE",
                "reason": "Evidence entails the answer, vector similarity passes threshold. Leaks irrelevant answer.",
                "is_correct": False,
                "failure_type": "QUERY_ANSWER_SEMANTIC_GAP"
            },
            "hybrid_pipeline_expected": {
                "query_compatibility_verdict": "FAIL",
                "nli_verdict": "NEUTRAL_TO_QUERY",
                "jev_decision": "REJECT",
                "action": "REJECT_FALLBACK_RAG",
                "is_correct": True,
                "explanation": "Query ↔ Answer check catches mismatch: user asked for lunch break, answer describes morning arrival grace period."
            }
        },

        # 11. DYNAMIC RBAC: POSH Internal Committee confidential records
        {
            "id": "GOLDEN-DOCX-RBAC-01",
            "category": "DYNAMIC_RBAC_REVOCATION",
            "source_document": "POSH_Policy.docx",
            "description": "User was removed from Internal Committee membership; cached answer contains IC internal committee protocols.",
            "current_user_query": "What are the internal committee deliberation notes for incident cases?",
            "cached_query": "internal committee inquiry notes",
            "cached_answer": "The Internal Committee maintains confidential deliberation logs and evidence transcripts accessible only to appointed IC members.",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "Internal Committee logs are accessible only to appointed IC members.",
                    "is_material": True
                }
            ],
            "source_evidence_chunks": [
                {
                    "chunk_id": "posh_policy_chunk_34",
                    "document_id": "POSH_Policy.docx",
                    "chunk_hash": get_hash(posh_paras[34]),
                    "text": posh_paras[34]
                }
            ],
            "user_context": {"user_id": "usr_emp_20", "roles": ["employee"], "project_ids": ["default"], "is_admin": False},
            "cached_metadata": {"tenant_id": "nexora", "project_id": "internal_committee", "assigned_role": "employee", "risk_level": "HIGH", "intent": "POSH"},
            "ground_truth_decision": "REJECT_FALLBACK_RAG",
            "current_pipeline_expected": {
                "action": "REUSE",
                "reason": "If checking role 'employee' == 'employee', cache serves answer despite lack of internal_committee project membership.",
                "is_correct": False,
                "failure_type": "SECURITY_RBAC_LEAK"
            },
            "hybrid_pipeline_expected": {
                "live_auth_verdict": "ACCESS_DENIED",
                "jev_decision": "REJECT",
                "action": "REJECT_FALLBACK_RAG",
                "is_correct": True,
                "explanation": "Live RBAC evaluation against AuthorizationService proves user lacks project_id internal_committee membership."
            }
        },

        # 12. HIGH RISK: Confidential Compensation Details
        {
            "id": "GOLDEN-DOCX-RISK-01",
            "category": "HIGH_RISK_POLICY_PII",
            "source_document": "NEXORA TECHNOLOGIES PVT.docx",
            "description": "Employee compensation confidentiality details must not be reused blindly from cache.",
            "current_user_query": "Can managers share an employee's salary and bonus details with peers?",
            "cached_query": "can managers share employee compensation details",
            "cached_answer": "An employee's compensation details are confidential and should be accessed only by the employee and authorized company personnel.",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "Compensation details are confidential and accessible only by authorized personnel.",
                    "is_material": True
                }
            ],
            "source_evidence_chunks": [
                {
                    "chunk_id": "nexora_handbook_chunk_677",
                    "document_id": "NEXORA TECHNOLOGIES PVT.docx",
                    "chunk_hash": get_hash(p_comp_confidential),
                    "text": p_comp_confidential
                }
            ],
            "user_context": {"user_id": "usr_mgr_05", "roles": ["manager"], "project_ids": ["default"], "is_admin": False},
            "cached_metadata": {"tenant_id": "nexora", "project_id": "default", "assigned_role": "manager", "risk_level": "HIGH", "intent": "COMPENSATION"},
            "ground_truth_decision": "REVALIDATE",
            "current_pipeline_expected": {
                "action": "REUSE",
                "reason": "Tokens match context, confidence > 0.60. Current cache has no risk engine and serves sensitive compensation data.",
                "is_correct": False,
                "failure_type": "HIGH_RISK_POLICY_LEAK"
            },
            "hybrid_pipeline_expected": {
                "nli_verdict": "ENTAILMENT",
                "jev_decision": "REVALIDATE",
                "action": "REVALIDATE",
                "is_correct": True,
                "explanation": "Jev policy engine intercepts intent=COMPENSATION and risk_level=HIGH, flagging REVALIDATE rather than blind cache reuse."
            }
        },

        # 13. STALE CHUNK PARTIAL UPDATE: Untouched Grace period chunk
        {
            "id": "GOLDEN-DOCX-STALE-01",
            "category": "STALE_CHUNK_PARTIAL_UPDATE",
            "source_document": "NEXORA TECHNOLOGIES PVT.docx",
            "description": "Leave section in Handbook was edited; but Grace Period chunk P1942 is 100% UNCHANGED.",
            "current_user_query": "Is there a grace period for late arrival in the morning?",
            "cached_query": "grace period for late arrival morning",
            "cached_answer": "Yes. A 15-minute grace period is provided for occasional delays. For the standard schedule, arrival by 9:45 AM falls within the grace period.",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "A 15-minute grace period is provided for occasional delays up to 9:45 AM.",
                    "is_material": True
                }
            ],
            "source_evidence_chunks": [
                {
                    "chunk_id": "nexora_handbook_chunk_1942",
                    "document_id": "NEXORA TECHNOLOGIES PVT.docx",
                    "chunk_hash": get_hash(p_grace_period),
                    "text": p_grace_period
                }
            ],
            "user_context": {"user_id": "usr_emp_30", "roles": ["employee"], "project_ids": ["default"], "is_admin": False},
            "cached_metadata": {"tenant_id": "nexora", "project_id": "default", "assigned_role": "employee", "risk_level": "LOW", "intent": "ATTENDANCE"},
            "ground_truth_decision": "REUSE",
            "current_pipeline_expected": {
                "action": "REJECT_FALLBACK_RAG",
                "reason": "Whole-document timestamp polling saw handbook file was updated today, purging this valid answer.",
                "is_correct": False,
                "failure_type": "FALSE_CACHE_MISS"
            },
            "hybrid_pipeline_expected": {
                "chunk_hash_match": True,
                "nli_verdict": "BYPASS_HASH_MATCH",
                "jev_decision": "REUSE",
                "action": "REUSE",
                "is_correct": True,
                "explanation": "ChunkHasher confirms chunk_1942 hash is unchanged. NLI bypassed in RAM, safe 1ms cache reuse."
            }
        },

        # 14. LEGITIMATE PARAPHRASE: Working hours true positive
        {
            "id": "GOLDEN-DOCX-PARAPHRASE-01",
            "category": "LEGITIMATE_PARAPHRASE_REUSE",
            "source_document": "NEXORA TECHNOLOGIES PVT.docx",
            "description": "Paraphrased question about work timings with identical underlying facts (True Positive).",
            "current_user_query": "What time does our workday start and end each day?",
            "cached_query": "what are the standard working hours",
            "cached_answer": "The standard schedule is 9:30 AM to 6:30 PM, Monday to Friday, unless a different schedule applies to your role.",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "Standard schedule is 9:30 AM to 6:30 PM, Monday to Friday.",
                    "is_material": True
                }
            ],
            "source_evidence_chunks": [
                {
                    "chunk_id": "nexora_handbook_chunk_1940",
                    "document_id": "NEXORA TECHNOLOGIES PVT.docx",
                    "chunk_hash": get_hash(p_work_hours),
                    "text": p_work_hours
                }
            ],
            "user_context": {"user_id": "usr_emp_31", "roles": ["employee"], "project_ids": ["default"], "is_admin": False},
            "cached_metadata": {"tenant_id": "nexora", "project_id": "default", "assigned_role": "employee", "risk_level": "LOW", "intent": "ATTENDANCE"},
            "ground_truth_decision": "REUSE",
            "current_pipeline_expected": {
                "action": "REUSE",
                "reason": "Vector distance < 0.40, passes C.R.E.A.T.E. rules.",
                "is_correct": True,
                "failure_type": None
            },
            "hybrid_pipeline_expected": {
                "chunk_hash_match": True,
                "nli_verdict": "ENTAILMENT",
                "jev_decision": "REUSE",
                "action": "REUSE",
                "is_correct": True,
                "explanation": "Hashes match, claims entailed, query compatible. Instant safe cache hit."
            }
        },

        # 15. NEGATIVE RESPONSE FILTER: Refusal string
        {
            "id": "GOLDEN-DOCX-NEG-FILTER-01",
            "category": "NEGATIVE_RESPONSE_FILTER",
            "source_document": "NEXORA TECHNOLOGIES PVT.docx",
            "description": "Cached entry is a refusal response that should never be reused.",
            "current_user_query": "Are employees allowed to bring pet dogs to the office?",
            "cached_query": "pet dog policy in office",
            "cached_answer": "I could not find any information regarding pet dogs in the Nexora Technologies employee handbook.",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "No information regarding pet dogs is present in handbook.",
                    "is_material": True
                }
            ],
            "source_evidence_chunks": [],
            "user_context": {"user_id": "usr_emp_32", "roles": ["employee"], "project_ids": ["default"], "is_admin": False},
            "cached_metadata": {"tenant_id": "nexora", "project_id": "default", "assigned_role": "employee", "risk_level": "LOW", "intent": "OFFICE"},
            "ground_truth_decision": "REJECT_FALLBACK_RAG",
            "current_pipeline_expected": {
                "action": "REJECT_FALLBACK_RAG",
                "reason": "Caught by is_negative_response() in app/core/cache_quality.py.",
                "is_correct": True,
                "failure_type": None
            },
            "hybrid_pipeline_expected": {
                "action": "REJECT_FALLBACK_RAG",
                "reason": "Caught by NegativeResponseValidator gate before NLI.",
                "is_correct": True,
                "explanation": "Deterministic NegativeResponseValidator rejects refusal strings before running NLI or Jev."
            }
        }
    ]

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(golden_cases, f, indent=2)

    print(f"[SUCCESS] Generated {len(golden_cases)} golden test cases directly from input/ docx files!")
    print(f"[PATH] Saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    build_dataset()
