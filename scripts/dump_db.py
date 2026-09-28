"""Dump the contents of the KnowLayer SQLite database.

Usage:
    .\.venv\Scripts\python.exe scripts\dump_db.py [table_name] [--db instance/knowlayer.db3]

With no arguments, lists every table and its row counts, then prints
the full contents of each table (this is a read-only operation).
Pass a table name to see only that table.
"""



# .\.venv\Scripts\python.exe scripts\dump_db.py                 # all tables
# .\.venv\Scripts\python.exe scripts\dump_db.py documents       # just one table
# .\.venv\Scripts\python.exe scripts\dump_db.py --db other.db3  # different DB file


import argparse
import sqlite3
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("table", nargs="?", default=None, help="Only dump this table")
    parser.add_argument("--db", default="instance/knowlayer.db3", help="Path to the SQLite DB")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]

    if args.table:
        if args.table not in tables:
            print(f"Table '{args.table}' not found. Available: {', '.join(tables)}", file=sys.stderr)
            return 1
        tables = [args.table]

    for table in tables:
        count = cur.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        print(f"\n{'=' * 70}")
        print(f"TABLE: {table}  ({count} rows)")
        print(f"{'=' * 70}")

        rows = cur.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
        if not rows:
            print("(empty)")
            continue

        cols = list(rows[0].keys())
        # Column headers
        print(" | ".join(cols))
        print("-" * 70)
        for r in rows:
            vals = []
            for c in cols:
                v = r[c]
                if v is None:
                    vals.append("NULL")
                else:
                    s = str(v)
                    vals.append(s if len(s) <= 120 else s[:117] + "...")
            print(" | ".join(vals))

    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())