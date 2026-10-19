"""
Local Natural Language Inference (NLI) Grounding Evaluator
==========================================================
Zero-token, deterministic, high-throughput RAG evaluation running 100% locally.
Uses a CrossEncoder NLI model to classify premise-hypothesis relationships
between retrieved chunks and generated response statements into:
  - ENTAILMENT: Claim is directly supported by the context chunk.
  - CONTRADICTION: Claim directly conflicts with facts in the context (hallucination).
  - NEUTRAL: Claim introduces outside, unverified information.

Tokens Consumed: 0 (Local inference only)
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np

logger = logging.getLogger(__name__)

_LOCAL_NLI_INSTANCE = None


class LocalNLIEvaluator:
    """
    Offline NLI Evaluator for Grounding and Hallucination Assertion.
    """

    def __init__(self, model_path: Optional[str] = None):
        self._model = None
        self.model_path = model_path or self._resolve_model_path()

    def _resolve_model_path(self) -> str:
        """Finds local downloaded weights or standard hub identifier."""
        # 1. DeBERTa v3 small (CrossEncoder DeBERTa v3 NLI)
        deberta_dir = Path("models") / "nli-deberta-v3-small"
        deb_st = deberta_dir / "model.safetensors"
        if deberta_dir.exists() and deb_st.exists() and deb_st.stat().st_size > 500 * 1024 * 1024:
            return str(deberta_dir)

        # 2. DistilRoBERTa base fallback
        distil_dir = Path("models") / "nli-distilroberta-base"
        st_file = distil_dir / "model.safetensors"
        if distil_dir.exists() and st_file.exists() and st_file.stat().st_size > 300 * 1024 * 1024:
            return str(distil_dir)

        return ""

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            try:
                logger.info("Initializing Local NLI CrossEncoder: %s", self.model_path)
                self._model = CrossEncoder(self.model_path)
            except Exception as e:
                logger.warning("Could not load CrossEncoder %s: %s. Using heuristic NLI.", self.model_path, e)
                self._model = False
        return self._model

    def split_sentences(self, text: str) -> List[str]:
        """Splits response text into distinct claim statements."""
        cleaned = text.strip()
        if not cleaned:
            return []
        raw_sents = re.split(r"(?<=[.!?])\s+", cleaned)
        claims = [s.strip() for s in raw_sents if len(s.strip()) > 6]
        return claims if claims else [cleaned]

    def evaluate(self, query: str, chunk_text: str, response_text: str) -> Dict[str, Any]:
        """
        Evaluates candidate response statements against the retrieved context chunk.
        Consumes 0 API tokens.
        """
        claims = self.split_sentences(response_text)
        if not claims or not chunk_text.strip():
            return {
                "evaluator_type": "LOCAL_NLI",
                "model_name": Path(self.model_path).name,
                "tokens_consumed": 0,
                "faithfulness_rate": 0.0,
                "is_pass": False,
                "nli_claims": [],
                "geval_scores": {
                    "faithfulness": 1,
                    "relevance": "N/A",
                    "refusal_correctness": "FAIL",
                },
                "chain_of_thought": "Empty context or candidate response provided.",
            }

        pairs = [[chunk_text, claim] for claim in claims]

        # Use model if available, else heuristic
        if self.model and self.model is not False:
            try:
                raw_scores = self.model.predict(pairs)
                if len(claims) == 1 and len(raw_scores.shape) == 1:
                    raw_scores = np.expand_dims(raw_scores, axis=0)

                exp_scores = np.exp(raw_scores)
                probs = exp_scores / np.sum(exp_scores, axis=1, keepdims=True)
                id2label = getattr(self.model.config, "id2label", {0: "contradiction", 1: "entailment", 2: "neutral"})

                chunk_nums = set(re.findall(r"\b\d+\b", chunk_text))
                claim_results = []
                for claim, prob in zip(claims, probs):
                    best_idx = int(np.argmax(prob))
                    raw_label = str(id2label.get(best_idx) or id2label.get(str(best_idx)) or "neutral").upper()
                    conf = float(prob[best_idx])
                    claim_nums = set(re.findall(r"\b\d+\b", claim))

                    if "ENTAIL" in raw_label:
                        norm_label = "ENTAILMENT"
                        reason = f"Supported by context (Local NLI confidence: {conf*100:.1f}%)"
                    elif "CONTRA" in raw_label:
                        norm_label = "CONTRADICTION"
                        reason = f"Conflicts with context (Local NLI confidence: {conf*100:.1f}%)"
                    else:
                        norm_label = "NEUTRAL"
                        reason = f"Outside/unsupported claim (Local NLI confidence: {conf*100:.1f}%)"

                    # Numeric assertion: numbers in claim not present in chunk are direct hallucinations
                    if claim_nums and any(n not in chunk_nums for n in claim_nums) and norm_label != "ENTAILMENT":
                        norm_label = "CONTRADICTION"
                        reason = f"Numeric contradiction: {claim_nums - chunk_nums} contradicts context (Local NLI confidence: {conf*100:.1f}%)"

                    claim_results.append({
                        "statement": claim,
                        "nli_label": norm_label,
                        "confidence": round(conf, 4),
                        "reason": reason,
                    })
            except Exception as e:
                logger.warning("Local CrossEncoder prediction failed (%s). Falling back.", e)
                return self._heuristic_evaluate(chunk_text, claims, note=str(e))
        else:
            return self._heuristic_evaluate(chunk_text, claims, note="Local weights initializing")

        total_c = len(claim_results)
        entailed_c = sum(1 for c in claim_results if c["nli_label"] == "ENTAILMENT")
        contra_c = sum(1 for c in claim_results if c["nli_label"] == "CONTRADICTION")
        neutral_c = sum(1 for c in claim_results if c["nli_label"] == "NEUTRAL")

        faith_rate = (entailed_c / total_c) if total_c > 0 else 1.0
        is_pass = (contra_c == 0) and (faith_rate >= 0.70)

        cot = (
            f"Pure Local NLI Analysis (0 API Tokens Consumed): "
            f"{entailed_c}/{total_c} claims entailed ({faith_rate*100:.0f}%), "
            f"{contra_c} direct hallucinations (contradictions), {neutral_c} neutral outside statements."
        )

        return {
            "evaluator_type": "LOCAL_NLI",
            "model_name": Path(self.model_path).name,
            "tokens_consumed": 0,
            "faithfulness_rate": round(faith_rate, 4),
            "is_pass": is_pass,
            "nli_claims": claim_results,
            "geval_scores": {
                "faithfulness": 5 if is_pass else (1 if contra_c > 0 else 3),
                "relevance": "N/A (Pure Grounding Mode)",
                "refusal_correctness": "PASS" if is_pass else "FAIL",
            },
            "chain_of_thought": cot,
        }

    def _heuristic_evaluate(self, chunk_text: str, claims: List[str], note: str = "") -> Dict[str, Any]:
        """High-speed heuristic fallback using token intersection and numeric assertions."""
        chunk_words = set(re.findall(r"\b\w{3,}\b", chunk_text.lower()))
        chunk_nums = set(re.findall(r"\b\d+\b", chunk_text))

        claim_results = []
        for c in claims:
            c_words = set(re.findall(r"\b\w{3,}\b", c.lower()))
            c_nums = set(re.findall(r"\b\d+\b", c))

            # Numeric mismatch is an instant contradiction
            num_mismatch = any(n not in chunk_nums for n in c_nums) and len(c_nums) > 0
            overlap = len(c_words & chunk_words) / len(c_words) if c_words else 1.0

            if num_mismatch or overlap < 0.20:
                label = "CONTRADICTION"
                reason = "Numeric or factual contradiction detected against chunk."
            elif overlap >= 0.40:
                label = "ENTAILMENT"
                reason = f"Verified by chunk vocabulary overlap ({overlap*100:.0f}%)."
            else:
                label = "NEUTRAL"
                reason = "Outside knowledge claim not found in chunk."

            claim_results.append({
                "statement": c,
                "nli_label": label,
                "confidence": round(overlap, 4),
                "reason": reason,
            })

        total_c = len(claim_results)
        entailed_c = sum(1 for c in claim_results if c["nli_label"] == "ENTAILMENT")
        contra_c = sum(1 for c in claim_results if c["nli_label"] == "CONTRADICTION")

        faith_rate = (entailed_c / total_c) if total_c > 0 else 1.0
        is_pass = (contra_c == 0) and (faith_rate >= 0.70)

        return {
            "evaluator_type": "LOCAL_NLI",
            "model_name": f"Rule-Based Fallback ({note})",
            "tokens_consumed": 0,
            "faithfulness_rate": round(faith_rate, 4),
            "is_pass": is_pass,
            "nli_claims": claim_results,
            "geval_scores": {
                "faithfulness": 5 if is_pass else (1 if contra_c > 0 else 3),
                "relevance": "N/A (Pure Grounding Mode)",
                "refusal_correctness": "PASS" if is_pass else "FAIL",
            },
            "chain_of_thought": f"Local Fallback Evaluator (0 Tokens): {entailed_c}/{total_c} claims entailed, {contra_c} contradictions.",
        }


def get_local_nli_evaluator() -> LocalNLIEvaluator:
    """Returns singleton LocalNLIEvaluator instance."""
    global _LOCAL_NLI_INSTANCE
    if _LOCAL_NLI_INSTANCE is None:
        _LOCAL_NLI_INSTANCE = LocalNLIEvaluator()
    return _LOCAL_NLI_INSTANCE
