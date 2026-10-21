import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import sqlite3
import chromadb
from app.core.settings import COLLECTION_NAME


def clear_chromadb():
    persist_dir = str(BASE_DIR / ".chroma")
    client = chromadb.PersistentClient(path=persist_dir)
    collections = client.list_collections()
    for col in collections:
        count_before = col.count()
        client.delete_collection(col.name)
        client.get_or_create_collection(name=col.name, metadata={"hnsw:space": "cosine"})
        print(f"[ChromaDB] Cleared collection '{col.name}' (removed {count_before} vectors). Count is now 0.")


def clear_input_folder():
    input_dir = BASE_DIR / "input"
    if not input_dir.exists():
        print("[Input] Input folder does not exist.")
        return

    deleted = []
    for file_path in input_dir.iterdir():
        if file_path.is_file():
            deleted.append(file_path.name)
            file_path.unlink()
    print(f"[Input] Deleted {len(deleted)} file(s) from 'input/': {deleted}")


def clear_sqlite():
    db_path = BASE_DIR / "instance" / "knowlayer.db3"
    if not db_path.exists():
        print(f"[SQLite] Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. Clear document permissions
    cur.execute("DELETE FROM document_permissions")
    print("[SQLite] Cleared table 'document_permissions'.")

    # 2. Clear documents table
    cur.execute("DELETE FROM documents")
    print("[SQLite] Cleared table 'documents'.")

    # 3. Reset document business id sequence counter so next document is DOC-001
    cur.execute("UPDATE business_id_sequences SET last_value = 0 WHERE sequence_key = 'document'")
    print("[SQLite] Reset 'business_id_sequences' for 'document' to 0.")

    conn.commit()
    conn.close()
    print("[SQLite] SQLite document data reset complete.")


if __name__ == "__main__":
    print("=== Clearing ChromaDB, Input Folder, and SQLite Document Records ===")
    clear_chromadb()
    clear_input_folder()
    clear_sqlite()
    print("=== All Cleared Successfully ===")
