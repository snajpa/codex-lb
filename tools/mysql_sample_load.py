"""Load a bounded sample of the two big tables (enough for meaningful EXPLAIN)."""

from __future__ import annotations

import sqlite3
import sys
import time
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, create_engine
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.db.models import Base

SAMPLE_ROWS = 300_000
BATCH = 1000


def coerce(value: Any, column: Any) -> Any:
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
    snapshot, url = sys.argv[1], sys.argv[2]
    sqlite = sqlite3.connect(f"file:{snapshot}?mode=ro", uri=True, timeout=60)
    sqlite.row_factory = sqlite3.Row
    engine = create_engine(url, future=True)
    for name in ("request_logs", "usage_history"):
        table = Base.metadata.tables[name]
        cols = [r[1] for r in sqlite.execute(f'PRAGMA table_info("{name}")')]
        columns = [c.name for c in table.columns if c.name in cols]
        cursor = sqlite.execute(f'SELECT {", ".join(columns)} FROM "{name}" LIMIT {SAMPLE_ROWS}')
        total = 0
        started = time.monotonic()
        batch: list[dict[str, Any]] = []
        with engine.begin() as conn:
            conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
            for row in cursor:
                batch.append({c: coerce(row[c], table.c[c]) for c in columns})
                if len(batch) >= BATCH:
                    conn.execute(mysql_insert(table).values(batch))
                    total += len(batch)
                    batch = []
            if batch:
                conn.execute(mysql_insert(table).values(batch))
                total += len(batch)
        print(f"{name}: sampled {total} rows in {time.monotonic() - started:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
