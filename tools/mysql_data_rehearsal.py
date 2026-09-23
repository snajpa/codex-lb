"""Load the production SQLite snapshot into the MySQL test database.

Part of the MySQL port (side branch): it answers two questions with real data
rather than theory --

* do the VARCHAR/VARBINARY widths chosen for MySQL hold every value the
  production snapshot actually contains (a too-small column fails loudly with a
  data-too-long error), and
* does the planner see representative cardinalities, so EXPLAIN is meaningful.

Usage: python tools/mysql_data_rehearsal.py <snapshot.db> <mysql_url> [table ...]
"""

from __future__ import annotations

import sqlite3
import sys
import time
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, create_engine
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.db.models import Base

BATCH_SIZE = 500


def _coerce(value: Any, column: Any) -> Any:
    if value is None:
        return None
    column_type = column.type
    if isinstance(column_type, DateTime) and isinstance(value, str):
        text = value.replace("Z", "+00:00")
        if " " in text and "T" not in text:
            text = text.replace(" ", "T", 1)
        return datetime.fromisoformat(text)
    if isinstance(column_type, Boolean) and isinstance(value, int):
        return bool(value)
    return value


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    snapshot_path, mysql_url = sys.argv[1], sys.argv[2]
    requested = sys.argv[3:]

    sqlite = sqlite3.connect(f"file:{snapshot_path}?mode=ro", uri=True, timeout=60)
    sqlite.row_factory = sqlite3.Row
    engine = create_engine(mysql_url, future=True)

    names = requested or [table.name for table in Base.metadata.sorted_tables]
    failures: list[str] = []
    for name in names:
        table = Base.metadata.tables.get(name)
        if table is None:
            print(f"{name}: no model table", flush=True)
            continue
        snapshot_columns = [row[1] for row in sqlite.execute(f'PRAGMA table_info("{name}")')]
        if not snapshot_columns:
            print(f"{name}: absent from snapshot", flush=True)
            continue
        columns = [column.name for column in table.columns if column.name in snapshot_columns]
        if not columns:
            print(f"{name}: no shared columns", flush=True)
            continue

        total = 0
        started = time.monotonic()
        batch: list[dict[str, Any]] = []
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
                cursor = sqlite.execute(f'SELECT {", ".join(columns)} FROM "{name}"')
                for row in cursor:
                    batch.append({column: _coerce(row[column], table.c[column]) for column in columns})
                    if len(batch) >= BATCH_SIZE:
                        connection.execute(mysql_insert(table).values(batch))
                        total += len(batch)
                        batch = []
                if batch:
                    connection.execute(mysql_insert(table).values(batch))
                    total += len(batch)
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - started
            print(f"{name}: FAILED after {total} rows in {elapsed:.1f}s: {type(exc).__name__}: {exc}", flush=True)
            failures.append(name)
            continue
        elapsed = time.monotonic() - started
        print(f"{name}: loaded {total} rows in {elapsed:.1f}s", flush=True)

    if failures:
        print("failed tables:", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
