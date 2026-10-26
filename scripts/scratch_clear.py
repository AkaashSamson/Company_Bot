import sqlite3
from pathlib import Path

# 1. Clear files from input folder
input_dir = Path("input")
deleted_files = []
if input_dir.exists():
    for f in input_dir.iterdir():
        if f.is_file():
            deleted_files.append(f.name)
            f.unlink()
print(f"Deleted {len(deleted_files)} files from input folder: {deleted_files}")

# 2. Clear documents and document_permissions from SQLite databases
for db_name in ["instance/knowlayer.db3", "instance/knowlayer.db"]:
    db_path = Path(db_name)
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        tables = [r[1] for r in cur.execute("PRAGMA table_list").fetchall()]
        if "document_permissions" in tables:
            cur.execute("DELETE FROM document_permissions")
            print(f"Cleared table 'document_permissions' in {db_name}")
        if "documents" in tables:
            cur.execute("DELETE FROM documents")
            print(f"Cleared table 'documents' in {db_name}")
        if "business_id_sequences" in tables:
            cur.execute("UPDATE business_id_sequences SET last_value = 0 WHERE sequence_key = 'document'")
            print(f"Reset 'document' sequence counter to 0 in {db_name}")
            
        conn.commit()
        conn.close()
