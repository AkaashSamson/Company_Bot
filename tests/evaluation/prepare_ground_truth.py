import json
import os

def main():
    draft_file = os.path.join(os.path.dirname(__file__), "dataset_draft.json")
    out_file = os.path.join(os.path.dirname(__file__), "reranking_dataset.json")
    
    with open(draft_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    for item in data:
        # We assign the highest ranked vector search result as the ground truth
        # for this synthetic test, ensuring we use actual chunk IDs.
        if item["candidates_for_review"]:
            # Special manual overrides for better evaluation based on quick inspection:
            query = item["query"]
            chunk_id = item["candidates_for_review"][0]["id"]
            
            if "remote work" in query.lower():
                chunk_id = item["candidates_for_review"][3]["id"] # picking a specific one
            elif "laptop" in query.lower():
                chunk_id = item["candidates_for_review"][1]["id"]
                
            item["relevant_chunks"] = [chunk_id]
        else:
            item["relevant_chunks"] = []
            
        del item["candidates_for_review"]
        
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        
    print(f"Ground truth dataset created at {out_file}")

if __name__ == "__main__":
    main()
