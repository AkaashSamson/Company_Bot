import json

def fix_dataset():
    with open("tests/evaluation/dataset_draft.json", "r", encoding="utf-8") as f:
        dataset = json.load(f)
        
    for item in dataset:
        if item.get("candidates_for_review"):
            # Set the ground truth to the exact chunk ID from the first candidate
            item["relevant_chunks"] = [item["candidates_for_review"][0]["id"]]
            
    with open("tests/evaluation/dataset.json", "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)
        
    print("Fixed dataset with exact chunk IDs.")

if __name__ == "__main__":
    fix_dataset()
