"""
KnowLayer Test Studio — Component Registry
==========================================
Declares metadata, contracts, dependencies, and execution modes for every testable
subsystem in the RAG evaluation pipeline.
"""

from typing import Dict, List
from pydantic import BaseModel, Field


class ComponentDeclaration(BaseModel):
    name: str
    display_name: str
    description: str
    inputs: List[str]
    outputs: List[str]
    supported_assertions: List[str]
    dependencies: List[str] = Field(default_factory=list)
    supports_offline_strict: bool = True
    network_required: bool = False


COMPONENT_REGISTRY: Dict[str, ComponentDeclaration] = {
    "retrieval": ComponentDeclaration(
        name="retrieval",
        display_name="Vector Retrieval (Bi-Encoder)",
        description="Extracts candidate context chunks using dense cosine similarity over ChromaDB.",
        inputs=["query", "project_ids", "top_k"],
        outputs=["candidates", "retrieval_latency_ms"],
        supported_assertions=["recall_at_k", "min_candidates", "no_unauthorized_chunks"],
        dependencies=[],
        supports_offline_strict=True,
        network_required=False,
    ),
    "reranking": ComponentDeclaration(
        name="reranking",
        display_name="Reranker (Cross-Encoder)",
        description="Rescores Bi-Encoder candidate chunks using BAAI/bge-reranker-base.",
        inputs=["query", "candidates", "top_k"],
        outputs=["reranked_chunks", "needle_present", "target_chunk_rank", "rerank_latency_ms"],
        supported_assertions=["needle_present", "target_in_top_k", "mean_rerank_score"],
        dependencies=["retrieval"],
        supports_offline_strict=True,
        network_required=False,
    ),
    "generation": ComponentDeclaration(
        name="generation",
        display_name="Response Generator (LLM)",
        description="Generates an enterprise-compliant answer grounded in retrieved context passages.",
        inputs=["query", "context_chunks", "role", "conversation_history"],
        outputs=["response_text", "model_used", "generation_latency_ms", "tokens_prompt", "tokens_completion"],
        supported_assertions=["non_empty_response", "max_latency_ms", "format_validity"],
        dependencies=["reranking"],
        supports_offline_strict=False,  # Heuristic generator works offline; Remote API requires network
        network_required=True,
    ),
    "grounding": ComponentDeclaration(
        name="grounding",
        display_name="Grounding & Hallucination Guard",
        description="Assesses whether claims in the response are grounded in the retrieved context passages.",
        inputs=["response_text", "context_chunks"],
        outputs=["entailment_ratio", "contradiction_ratio", "unsupported_claims", "claims_breakdown"],
        supported_assertions=["min_entailment_ratio", "max_contradiction_ratio", "zero_hallucinations"],
        dependencies=["generation"],
        supports_offline_strict=True,  # Local DeBERTa / RoBERTa / Heuristic
        network_required=False,
    ),
    "policy_eval": ComponentDeclaration(
        name="policy_eval",
        display_name="Policy Playbook & Compliance Evaluator",
        description="Enforces policy mandates: required steps, prohibited claims, citation requirements, and refusal compliance.",
        inputs=["response_text", "test_case"],
        outputs=["prohibited_detected", "evidence_topics_covered", "refusal_correct", "compliance_score"],
        supported_assertions=["no_prohibited_claims", "evidence_coverage", "refusal_conformance"],
        dependencies=["generation"],
        supports_offline_strict=True,
        network_required=False,
    ),
    "ragas_eval": ComponentDeclaration(
        name="ragas_eval",
        display_name="Ragas Response Quality & Edge Case Evaluator (OpenRouter)",
        description="Evaluates Faithfulness, Answer Relevancy, Factual Correctness, Context Precision, and Recall using OpenRouter.",
        inputs=["user_input", "response", "retrieved_contexts", "reference"],
        outputs=["faithfulness", "answer_relevancy", "factual_correctness", "context_precision", "context_recall", "diagnosis"],
        supported_assertions=["faithfulness", "answer_relevancy", "factual_correctness", "context_precision", "context_recall"],
        dependencies=["generation"],
        supports_offline_strict=True,
        network_required=True,
    ),
}


def get_registered_component(name: str) -> ComponentDeclaration:
    if name not in COMPONENT_REGISTRY:
        raise KeyError(f"Component '{name}' is not registered in COMPONENT_REGISTRY.")
    return COMPONENT_REGISTRY[name]
