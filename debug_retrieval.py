import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.append(str(project_root))

from app.use_cases.chat.retrieval_service import RetrievalService

def debug_retrieval(query: str):
    """Developer tool to see the top retrieved chunks from the vector DB for a given query."""
    print(f"--- Debugging Retrieval for Query: '{query}' ---")
    
    retrieval_service = RetrievalService()
    
    # We pass authorized_project_ids=None to bypass RBAC and search everything globally.
    results = retrieval_service.retrieve(
        query_text=query,
        top_k=5,  # Fetch top 5 chunks
        authorized_project_ids=None 
    )
    
    if not results:
        print("No results found. (The vector database might be empty or distance threshold too low).")
        return
        
    print(f"Found {len(results)} chunks passing the threshold.\n")
    
    for i, result in enumerate(results, 1):
        metadata = result.get('metadata', {})
        distance = result.get('distance', 'N/A')
        print(f"--- Result #{i} (Distance: {distance}) ---")
        print(f"Source: {metadata.get('source')}")
        print(f"Project ID: {metadata.get('project_id')}")
        print(f"Text:\n{result.get('text')}\n")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        debug_retrieval(" ".join(sys.argv[1:]))
    else:
        print("Usage: python debug_retrieval.py <your search query>")
        print("Example: python debug_retrieval.py maternity leave policy")
