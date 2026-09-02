from app.use_cases.chat.provenance_service import ProvenanceService
from app.use_cases.chat.retrieval_service import RetrievalService


class QueryOrchestrator:
    def __init__(self):
        self.retrieval = RetrievalService()
        self.provenance = ProvenanceService()

    def answer(self, question: str):
        results = self.retrieval.retrieve(question, top_k=3)
        if not results:
            return {
                "answer": "I could not find a relevant match in the current HR policy document.",
                "citations": [],
            }

        context = "\n\n".join(result.get("text", "") for result in results)
        question_lower = question.lower()

        if "leave" in question_lower or "annual leave" in question_lower:
            answer = "The handbook describes leave entitlements and policy terms in the employee leave and holidays section."
        elif "remote" in question_lower or "hybrid" in question_lower or "work" in question_lower:
            answer = "The handbook outlines remote and hybrid working expectations and the applicable work policy guidance."
        elif "attendance" in question_lower or "hours" in question_lower:
            answer = "The handbook defines working hours and attendance expectations in the company’s workplace policy section."
        elif "grievance" in question_lower or "complaint" in question_lower:
            answer = "The handbook includes grievance procedures and escalation guidance in the employee relations section."
        else:
            answer = "Based on the current HR policy document, the relevant guidance is covered in the handbook section retrieved for this question."

        return {
            "answer": answer,
            "citations": self.provenance.build_citations(results),
            "context": context,
        }
