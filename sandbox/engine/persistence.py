"""
KnowLayer Test Studio — Run Persistence
=======================================
Stores test execution results and traces locally using standard SQLite and JSONL
artifacts without requiring an external database server.
"""

import sqlite3
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from sandbox.engine.schema import SuiteRunResult, TestCaseResult, RunConfig

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "runs.db"
TRACES_DIR = Path(__file__).resolve().parent.parent / "data" / "traces"


def get_db_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    _init_db(conn)
    return conn


def _init_db(conn: sqlite3.Connection):
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                suite_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                execution_mode TEXT NOT NULL,
                components TEXT NOT NULL,
                total_tests INTEGER NOT NULL,
                passed INTEGER NOT NULL,
                failed INTEGER NOT NULL,
                pass_rate REAL NOT NULL,
                config_json TEXT NOT NULL,
                component_metrics_json TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                test_id TEXT NOT NULL,
                status TEXT NOT NULL,
                failure_stage TEXT,
                latency_ms REAL,
                assertions_json TEXT,
                FOREIGN KEY (run_id) REFERENCES runs (run_id)
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_test_results_run ON test_results (run_id);")


def save_suite_run(run_result: SuiteRunResult) -> str:
    """
    Saves a completed SuiteRunResult to SQLite and writes a full JSONL trace artifact.
    """
    conn = get_db_connection()
    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO runs (
                run_id, suite_id, created_at, execution_mode, components,
                total_tests, passed, failed, pass_rate, config_json, component_metrics_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_result.run_id,
            run_result.suite_id,
            run_result.created_at,
            run_result.config.execution_mode,
            ",".join(run_result.config.components),
            run_result.total_tests,
            run_result.passed,
            run_result.failed,
            run_result.pass_rate,
            run_result.config.model_dump_json(),
            json.dumps(run_result.component_metrics),
        ))

        for tr in run_result.test_results:
            conn.execute("""
                INSERT INTO test_results (
                    run_id, test_id, status, failure_stage, latency_ms, assertions_json
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                run_result.run_id,
                tr.test_id,
                tr.status,
                tr.failure_stage,
                tr.metrics.get("latency_ms", 0.0),
                json.dumps([a.model_dump() for a in tr.assertion_results]),
            ))

    # Write trace file (Level 4 detail)
    trace_file = TRACES_DIR / f"{run_result.run_id}.json"
    with open(trace_file, "w", encoding="utf-8") as f:
        f.write(run_result.model_dump_json(indent=2))

    return run_result.run_id


def list_recent_runs(limit: int = 15) -> List[Dict[str, Any]]:
    """
    Retrieves summary records of recent test runs.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT run_id, suite_id, created_at, execution_mode, components,
               total_tests, passed, failed, pass_rate
        FROM runs
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    return [dict(r) for r in rows]


def get_run_by_id(run_id: str) -> Optional[Dict[str, Any]]:
    """
    Loads full run artifact including traces if available.
    """
    trace_file = TRACES_DIR / f"{run_id}.json"
    if trace_file.exists():
        try:
            with open(trace_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    d["component_metrics"] = json.loads(d["component_metrics_json"])
    d["config"] = json.loads(d["config_json"])
    return d


def compare_two_runs(run_id_a: str, run_id_b: str) -> Dict[str, Any]:
    """
    Computes delta and regression analysis between two runs.
    """
    a = get_run_by_id(run_id_a)
    b = get_run_by_id(run_id_b)
    if not a or not b:
        return {"error": "One or both run IDs not found."}

    delta_pass_rate = round(b.get("pass_rate", 0) - a.get("pass_rate", 0), 1)

    # Compare individual test statuses if detailed results are present
    regressions = []
    improvements = []
    results_a = {r["test_id"]: r["status"] for r in a.get("test_results", [])}
    results_b = {r["test_id"]: r["status"] for r in b.get("test_results", [])}

    for tid, status_b in results_b.items():
        status_a = results_a.get(tid)
        if status_a == "PASS" and status_b == "FAIL":
            regressions.append(tid)
        elif status_a == "FAIL" and status_b == "PASS":
            improvements.append(tid)

    return {
        "run_a": {"id": run_id_a, "pass_rate": a.get("pass_rate")},
        "run_b": {"id": run_id_b, "pass_rate": b.get("pass_rate")},
        "delta_pass_rate": delta_pass_rate,
        "regressions": regressions,
        "improvements": improvements,
    }
