"""Compare MySQL column widths against the real maximum lengths in the snapshot.

Prints every text column whose production values exceed (or come close to) the
MySQL width, i.e. the columns the port must widen.
"""

from __future__ import annotations

import sqlite3
import sys

from sqlalchemy import create_engine, text

SAMPLE_LIMIT = 300_000
NEAR = 0.9


def main() -> int:
    snapshot, url = sys.argv[1], sys.argv[2]
    sqlite = sqlite3.connect(f"file:{snapshot}?mode=ro", uri=True, timeout=120)
    engine = create_engine(url, future=True)
    rows_out: list[tuple[str, str, str, int, int]] = []
    with engine.connect() as conn:
        tables = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = DATABASE() ORDER BY table_name"
                )
            )
        ]
        for table in tables:
            snapshot_cols = {r[1]: str(r[2]).upper() for r in sqlite.execute(f'PRAGMA table_info("{table}")')}
            if not snapshot_cols:
                continue
            mysql_cols = {
                r[0]: (str(r[1]).lower(), int(r[2] or 0))
                for r in conn.execute(
                    text(
                        "SELECT column_name, column_type, character_maximum_length "
                        "FROM information_schema.columns "
                        "WHERE table_schema = DATABASE() AND table_name = :t"
                    ),
                    {"t": table},
                )
            }
            for column, (mysql_type, width) in mysql_cols.items():
                if width <= 0 or column not in snapshot_cols:
                    continue
                if not mysql_type.startswith(("varchar", "char")):
                    continue
                try:
                    max_len = sqlite.execute(
                        f'SELECT MAX(LENGTH("{column}")) FROM (SELECT "{column}" FROM "{table}" LIMIT {SAMPLE_LIMIT})'
                    ).fetchone()[0]
                except sqlite3.Error:
                    continue
                if max_len is None:
                    continue
                if max_len >= width * NEAR:
                    rows_out.append((table, column, mysql_type, width, int(max_len)))
    sqlite.close()
    rows_out.sort(key=lambda item: item[4] / item[3], reverse=True)
    print(f"columns at or near their MySQL width: {len(rows_out)}")
    for table, column, mysql_type, width, max_len in rows_out:
        flag = "OVER" if max_len > width else "near"
        print(f"  {flag:5} {table}.{column}: mysql={mysql_type} max_len={max_len}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
