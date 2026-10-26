import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import sqlite3
import chromadb
from app.core.settings import COLLECTION_NAME



def clear_chromadb():
    # 1. Try HttpClient if server is running
    cleared_via_http = False
    for port in [8001, 8000]:
        try:
            hc = chromadb.HttpClient(host="localhost", port=port)
            hc.heartbeat()
            collections = hc.list_collections()
            for col in collections:
                count_before = col.count()
                hc.delete_collection(col.name)
                hc.get_or_create_collection(name=col.name, metadata={"hnsw:space": "cosine"})
                print(f"[ChromaDB (HttpClient:{port})] Cleared collection '{col.name}' (removed {count_before} vectors). Count is now 0.")
            cleared_via_http = True
            break
        except Exception:
            continue

    # 2. Also ensure PersistentClient on .chroma is updated
    for folder in [".chroma", "chroma_db"]:
        persist_dir = BASE_DIR / folder
        if not persist_dir.exists():
            continue
        try:
            client = chromadb.PersistentClient(path=str(persist_dir))
            collections = client.list_collections()
            for col in collections:
                count_before = col.count()
                if count_before > 0 or not cleared_via_http:
                    client.delete_collection(col.name)
                    client.get_or_create_collection(name=col.name, metadata={"hnsw:space": "cosine"})
                    print(f"[ChromaDB ({folder})] Cleared collection '{col.name}' (removed {count_before} vectors). Count is now 0.")
                else:
                    print(f"[ChromaDB ({folder})] Collection '{col.name}' already at 0 vectors.")
        except Exception as e:
            print(f"[ChromaDB ({folder})] Note: {e}")


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


def clear_caches():
    cache_targets = [
        BASE_DIR / "cache" / "semantic_cache.json",
        BASE_DIR / "data" / "semantic_cache.json",
        BASE_DIR / "data" / "response_cache.json",
        BASE_DIR / "data" / "faqs_cache.json",
    ]
    for cache_file in cache_targets:
        if cache_file.exists():
            cache_file.write_text("{}", encoding="utf-8")
            print(f"[Cache] Reset '{cache_file.relative_to(BASE_DIR)}' to empty {{}}.")
        else:
            print(f"[Cache] '{cache_file.relative_to(BASE_DIR)}' not present.")


def clear_citation_pdfs():
    cit_dir = BASE_DIR / "data" / "citation_pdfs"
    if cit_dir.exists():
        deleted = 0
        for f in cit_dir.glob("**/*"):
            if f.is_file():
                f.unlink()
                deleted += 1
        print(f"[Citation PDFs] Deleted {deleted} cached citation PDF(s).")


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
            deleted_perms = cur.execute("DELETE FROM document_permissions").rowcount
            print(f"[SQLite] Cleared table 'document_permissions' ({deleted_perms} rows) in {db_name}.")

        # 2. Clear documents table
        if "documents" in tables:
            deleted_docs = cur.execute("DELETE FROM documents").rowcount
            print(f"[SQLite] Cleared table 'documents' ({deleted_docs} rows) in {db_name}.")

        # 3. Reset document business id sequence counter so next document is DOC-001
        if "business_id_sequences" in tables:
            cur.execute("UPDATE business_id_sequences SET last_value = 0 WHERE sequence_key = 'document'")
            print(f"[SQLite] Reset 'business_id_sequences' for 'document' to 0 in {db_name}.")

        conn.commit()
        conn.close()
    print("[SQLite] SQLite document data reset complete.")


if __name__ == "__main__":
    print("=== Clearing ChromaDB, Input Folder, SQLite Document Records, Caches, and Conversation Logs ===")
    clear_chromadb()
    clear_input_folder()
    clear_sqlite()
    clear_caches()
    clear_citation_pdfs()
    clear_conversation_logs()
    print("=== All Cleared Successfully ===")


