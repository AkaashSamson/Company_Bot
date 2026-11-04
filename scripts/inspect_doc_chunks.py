import chromadb
import json
import sqlite3

def inspect_doc(doc_id="DOC-001"):
    print(f"==================================================")
    print(f"       INSPECTING CHUNKS FOR {doc_id}")
    print(f"==================================================")
    
    # 1. Check SQLite metadata
    conn = sqlite3.connect("instance/knowlayer.db3")
    cur = conn.cursor()
    row = cur.execute("SELECT document_id, document_name, project_id, status, file_type, storage_location, created_at FROM documents WHERE document_id = ?", (doc_id,)).fetchone()
    if row:
        print(f"SQLite Record:")
        print(f"  Document ID:      {row[0]}")
        print(f"  Document Name:    {row[1]}")
        print(f"  Project ID:       {row[2]}")
        print(f"  Status:           {row[3]}")
        print(f"  File Type:        {row[4]}")
        print(f"  Storage Location: {row[5]}")
        print(f"  Created At:       {row[6]}")
    else:
        print(f"No SQLite record found for {doc_id}")
    conn.close()

    # 2. Check ChromaDB
    client = chromadb.PersistentClient(".chroma")
    try:
        col = client.get_collection("hr_policy_docs")
    except Exception as e:
        print(f"Error opening ChromaDB collection: {e}")
        return

    res = col.get(where={"document_id": doc_id})
    ids = res.get("ids", [])
    docs = res.get("documents", [])
    metas = res.get("metadatas", [])

    print(f"\nTotal Chunks Stored in ChromaDB: {len(ids)}\n")
    # Sort by chunk_index
    items = sorted(zip(ids, docs, metas), key=lambda x: x[2].get("chunk_index", 0))
    for idx, (cid, doc, meta) in enumerate(items):
        prod = meta.get("produced_by", "docling")
        vtype = meta.get("visual_type", meta.get("content_type", "text"))
        pic = meta.get("picture_ref", "-")
        print(f"--------------------------------------------------")
        print(f"CHUNK #{idx} | ID: {cid} | Type: {vtype} | ProducedBy: {prod} | PicRef: {pic}")
        print(f"--------------------------------------------------")
        print("METADATA:")
        print(json.dumps(meta, indent=2))
        print("\nSTORED TEXT / SEARCHABLE CONTENT:")
        print(doc)
        print()

if __name__ == "__main__":
    inspect_doc("DOC-001")
