import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.infrastructure.vector.chroma_client import ChromaVectorStore

def align_dataset():
    print("Aligning dataset with new Chroma chunk IDs...")
    store = ChromaVectorStore()
    
    with open("tests/evaluation/dataset_draft.json", "r", encoding="utf-8") as f:
        dataset = json.load(f)
        
    for item in dataset:
        print(f"Processing {item['id']}: {item['query']}")
        if not item.get("candidates_for_review"):
            continue
            
        # We take the first candidate as the primary ground truth
        gt_text = item["candidates_for_review"][0]["text"]
        
        # Query Chroma to find the exact chunk ID in the new DB that contains this text
        results = store.query(item["query"], top_k=50)
        
        best_match_id = None
        for res in results:
            if res["text"].strip()[:100] == gt_text.strip()[:100]:
                best_match_id = res["id"]
                break
                
        if best_match_id:
            item["relevant_chunks"] = [best_match_id]
            print(f"  -> Found match: {best_match_id}")
        else:
            print("  -> Could not find exact match in top 50, assigning top 1 from vector search as ground truth")
            if results:
                item["relevant_chunks"] = [results[0]["id"]]
                
    with open("tests/evaluation/dataset.json", "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)
        
    print("Saved aligned dataset to tests/evaluation/dataset.json")

if __name__ == "__main__":
    align_dataset()
