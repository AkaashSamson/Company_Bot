import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import sqlite3
from app.core.settings import COLLECTION_NAME
from app.infrastructure.vector.chroma_client import ChromaVectorStore


def reset_sqlite():
    db_path = BASE_DIR / "instance" / "knowlayer.db"
    if not db_path.exists():
        print(f"[SQL] Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Tables to clear
    tables_to_clear = [
        "document_access",
        "documents",
        "projects",
        "authentication_audit_events",
        "conversation_logs",
    ]

    for table in tables_to_clear:
        try:
            cur.execute(f"DELETE FROM {table}")
            print(f"[SQL] Cleared table: {table}")
        except sqlite3.OperationalError:
            pass  # table might not exist

    # Clear users except admin
    cur.execute("DELETE FROM users WHERE username != 'admin'")
    print("[SQL] Cleared non-admin users. Preserved 'admin'.")

    # Clear non-admin departments
    try:
        cur.execute("DELETE FROM departments WHERE department_id != 'admin'")
        print("[SQL] Cleared non-admin departments. Preserved 'admin'.")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()
    print("[SQL] SQLite reset complete.")


def reset_chroma():
    persist_dir = str(BASE_DIR / ".chroma")
    store = ChromaVectorStore(collection_name=COLLECTION_NAME, persist_directory=persist_dir)
    count_before = store.collection.count()
    print(f"[CHROMA] Existing vector count: {count_before}")

    try:
        store.client.delete_collection(COLLECTION_NAME)
        store.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        print(f"[CHROMA] Deleted and recreated empty collection '{COLLECTION_NAME}'. Count is now 0.")
    except Exception as e:
        print(f"[CHROMA] Error resetting collection: {e}")


def main():
    print("--- Resetting SQL and Chroma DB ---")
    reset_sqlite()
    reset_chroma()
    print("--- Done ---")


if __name__ == "__main__":
    main()
