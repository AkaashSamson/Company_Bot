import json
import os
import sys

# Ensure the root directory is in the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app.infrastructure.vector.chroma_client import ChromaVectorStore

QUERIES = [
    "What is the policy for remote work?",
    "How many days of paid leave do I get?",
    "What is the procedure for performance reviews?",
    "Who do I contact for IT support?",
    "Can I expense my home internet bill?",
    "What are the core hours for the engineering team?",
    "Is there a maternity leave policy?",
    "How do I request a new laptop?",
    "What are the benefits for part-time employees?",
    "What is the severance pay if I am laid off?",
    "Are there any allowances for training and development?",
    "What is the dress code in the office?",
    "How does the promotion cycle work?",
    "Can I work from a different country?",
    "What is the process for onboarding new hires?",
    "How are annual bonuses calculated?",
    "What is the policy on workplace harassment?",
    "How do I claim travel expenses?",
    "What is the company's policy on intellectual property?",
    "Are there any mental health resources available?"
]

def main():
    store = ChromaVectorStore(collection_name="hr_policy_docs")
    
    draft_data = []
    
    print("Generating ground truth helper data...")
    for idx, query in enumerate(QUERIES, 1):
        print(f"Query {idx}/{len(QUERIES)}: {query}")
        candidates = store.query(query, top_k=15)
        
        draft = {
            "id": f"Q{idx:03d}",
            "query": query,
            "relevant_chunks": [], # To be filled manually
            "candidates_for_review": []
        }
        
        for c in candidates:
            draft["candidates_for_review"].append({
                "id": c["id"],
                "text": c["text"][:300].replace("\n", " ") + "..."
            })
            
        draft_data.append(draft)
        
    out_file = os.path.join(os.path.dirname(__file__), "dataset_draft.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(draft_data, f, indent=2)
        
    print(f"Draft saved to {out_file}. Please review and copy relevant chunk IDs into 'relevant_chunks'.")

if __name__ == "__main__":
    main()
