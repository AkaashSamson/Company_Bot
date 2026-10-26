import threading
import time
from pathlib import Path
from app.infrastructure.persistence.sqlalchemy.session import create_engine_and_session_factory
from app.infrastructure.vector.chroma_client import ChromaVectorStore

def test_sqlite_wal_and_busy_timeout(tmp_path: Path):
    db_file = tmp_path / "test_wal.db"
    db_url = f"sqlite:///{db_file}"
    engine, _ = create_engine_and_session_factory(db_url)
    
    with engine.connect() as conn:
        journal_mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
        assert journal_mode.lower() == "wal"
        timeout = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
        assert timeout >= 30000

def test_concurrent_read_while_writing_in_wal_mode(tmp_path: Path):
    db_file = tmp_path / "test_concurrency.db"
    db_url = f"sqlite:///{db_file}"
    engine, _ = create_engine_and_session_factory(db_url)
    
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT);")
        conn.exec_driver_sql("INSERT INTO items (name) VALUES ('initial');")

    write_started = threading.Event()
    read_completed = threading.Event()
    read_result = []

    def writer_thread():
        with engine.begin() as conn:
            conn.exec_driver_sql("INSERT INTO items (name) VALUES ('in_progress');")
            write_started.set()
            time.sleep(0.4)

    def reader_thread():
        write_started.wait()
        with engine.connect() as conn:
            rows = conn.exec_driver_sql("SELECT name FROM items;").fetchall()
            read_result.extend(r[0] for r in rows)
            read_completed.set()

    t1 = threading.Thread(target=writer_thread)
    t2 = threading.Thread(target=reader_thread)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert read_completed.is_set()
    assert "initial" in read_result

def test_chroma_persistent_client_is_process_singleton(tmp_path: Path):
    chroma_dir = str(tmp_path / ".chroma")
    store1 = ChromaVectorStore(collection_name="test_col", persist_directory=chroma_dir)
    store2 = ChromaVectorStore(collection_name="test_col", persist_directory=chroma_dir)
    assert store1.client is store2.client

def test_concurrent_chroma_read_and_write(tmp_path: Path):
    chroma_dir = str(tmp_path / ".chroma")
    store = ChromaVectorStore(collection_name="test_concurrency_col", persist_directory=chroma_dir)
    
    # Pre-populate one chunk
    store.add_documents([{"id": "doc0-chunk0", "text": "baseline information", "metadata": {"status": "active"}}])

    write_started = threading.Event()
    read_success = threading.Event()
    read_errors = []

    def writer():
        write_started.set()
        docs = [{"id": f"batch-{i}", "text": f"concurrent document payload number {i}", "metadata": {"status": "active"}} for i in range(5)]
        store.add_documents(docs)

    def reader():
        write_started.wait()
        try:
            results = store.query("baseline information", top_k=2)
            if len(results) > 0:
                read_success.set()
        except Exception as e:
            read_errors.append(e)

    t1 = threading.Thread(target=writer)
    t2 = threading.Thread(target=reader)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not read_errors
    assert read_success.is_set()
