class ProvenanceService:
    def build_citations(self, results):
        citations = []
        for result in results:
            metadata = result.get("metadata", {})
            citations.append({
                "source": metadata.get("source", "NEXORA TECHNOLOGIES PVT.docx"),
                "section": metadata.get("section", "Policy"),
                "text": result.get("text", ""),
            })
        return citations
