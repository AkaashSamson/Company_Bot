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


def clear_semantic_cache():
    cache_file = BASE_DIR / "cache" / "semantic_cache.json"
    if cache_file.exists():
        cache_file.write_text("{}", encoding="utf-8")
        print("[Cache] Reset 'cache/semantic_cache.json' to empty {}.")
    else:
        print("[Cache] 'cache/semantic_cache.json' not found.")


def clear_conversation_logs():
    log_dir = BASE_DIR / "conversation_logs"
    if not log_dir.exists():
        print("[Logs] 'conversation_logs/' folder does not exist.")
        return

    deleted = 0
    for f in log_dir.iterdir():
        if f.is_file() and f.suffix == ".json":
            f.unlink()
            deleted += 1
    print(f"[Logs] Cleared {deleted} conversation log file(s).")


def clear_sqlite():
    for db_name in ["instance/knowlayer.db3", "instance/knowlayer.db"]:
        db_path = BASE_DIR / db_name
        if not db_path.exists():
            continue

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

        # 1. Clear document permissions
        if "document_permissions" in tables:
            cur.execute("DELETE FROM document_permissions")
            print(f"[SQLite] Cleared table 'document_permissions' in {db_name}.")

        # 2. Clear documents table
        if "documents" in tables:
            cur.execute("DELETE FROM documents")
            print(f"[SQLite] Cleared table 'documents' in {db_name}.")

        # 3. Reset document business id sequence counter so next document is DOC-001
        if "business_id_sequences" in tables:
            cur.execute("UPDATE business_id_sequences SET last_value = 0 WHERE sequence_key = 'document'")
            print(f"[SQLite] Reset 'business_id_sequences' for 'document' to 0 in {db_name}.")

        conn.commit()
        conn.close()
    print("[SQLite] SQLite document data reset complete.")


if __name__ == "__main__":
    print("=== Clearing ChromaDB, Input Folder, SQLite Document Records, Semantic Cache, and Conversation Logs ===")
    clear_chromadb()
    clear_input_folder()
    clear_sqlite()
    clear_semantic_cache()
    clear_conversation_logs()
    print("=== All Cleared Successfully ===")

