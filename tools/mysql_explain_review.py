"""EXPLAIN review of codex-lb's hot queries on MySQL.

Part of the MySQL port (side branch). Each entry is one of the app's hot query
shapes against the rehearsal data; the script reports the index MySQL picks,
the estimated rows, and whether the access is a full scan — the evidence the
port's review phase asks for.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime

from sqlalchemy import create_engine

QUERIES: list[tuple[str, str, tuple[object, ...]]] = [
    (
        "sticky session lookup (per sticky request)",
        "SELECT account_id FROM sticky_sessions WHERE kind='prompt_cache' AND `key`=%s",
        ("probe-key",),
    ),
    (
        "request_logs: account + time window (dashboard list)",
        "SELECT id, requested_at FROM request_logs WHERE account_id=%s ORDER BY requested_at DESC, id DESC LIMIT 50",
        ("probe",),
    ),
    (
        "request_logs: retention cutoff scan (retention job)",
        "SELECT id FROM request_logs WHERE requested_at < %s ORDER BY requested_at ASC, id ASC LIMIT 200",
        (datetime(2026, 1, 1),),
    ),
    (
        "request_logs: live facet (status + error)",
        "SELECT id FROM request_logs WHERE status=%s AND error_code=%s LIMIT 20",
        ("success", "probe"),
    ),
    (
        "request_logs: api key + time",
        "SELECT id FROM request_logs WHERE api_key_id=%s ORDER BY requested_at DESC, id DESC LIMIT 50",
        ("probe",),
    ),
    (
        "usage_history: latest window row",
        "SELECT id FROM usage_history WHERE `window`=%s AND account_id=%s ORDER BY recorded_at DESC, id DESC LIMIT 1",
        ("primary", "probe"),
    ),
    (
        "usage_history: account + time aggregate (rollup)",
        "SELECT account_id, SUM(input_tokens) FROM usage_history "
        "WHERE account_id=%s AND recorded_at >= %s GROUP BY account_id",
        ("probe", datetime(2026, 1, 1)),
    ),
    (
        "additional_usage_history: quota + window latest",
        "SELECT id FROM additional_usage_history WHERE quota_key=%s AND `window`=%s AND account_id=%s "
        "ORDER BY recorded_at DESC, used_percent DESC, id DESC LIMIT 1",
        ("probe", "primary", "probe"),
    ),
    (
        "quota_planner_decisions: due warmups",
        "SELECT id FROM quota_planner_decisions WHERE action='warmup' AND status='executing' "
        "ORDER BY scheduled_at ASC LIMIT 100",
        (),
    ),
    (
        "accounts: dashboard listing order",
        "SELECT id, email FROM accounts ORDER BY created_at DESC LIMIT 50",
        (),
    ),
    (
        "api_keys: owner listing",
        "SELECT id FROM api_keys WHERE owner_user_id=%s ORDER BY created_at DESC LIMIT 50",
        ("probe",),
    ),
    (
        "http_bridge_sessions: latest turn scope lookup",
        "SELECT id FROM http_bridge_sessions WHERE latest_turn_state=%s AND api_key_scope=%s AND state='active' "
        "ORDER BY last_seen_at DESC LIMIT 1",
        ("probe", "probe"),
    ),
]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    engine = create_engine(sys.argv[1], future=True)
    with engine.connect() as connection:
        for label, sql, params in QUERIES:
            explain = f"EXPLAIN FORMAT=JSON {sql}"
            try:
                payload = connection.exec_driver_sql(explain, params).scalar()
            except Exception as exc:  # noqa: BLE001
                print(f"{label}: EXPLAIN failed: {type(exc).__name__}: {exc}")
                continue
            data = json.loads(payload)
            plan = data.get("query_block", {})
            print(f"\n== {label}")
            before = len(printed)
            _walk(plan)
            if len(printed) == before:
                print("   (no table node found; raw plan follows)")
                print("   " + json.dumps(plan)[:400])
    return 0


printed: list[str] = []


def _walk(node: dict) -> None:
    table = node.get("table")
    if table:
        printed.append(str(table.get("table_name")))
        print(
            f"   table={table.get('table_name')} access={table.get('access_type')} "
            f"key={table.get('key')} rows={table.get('rows_examined_per_scan')} "
            f"filtered={table.get('filtered')} "
            f"using_index={'using_index' in table}"
        )
    for key in ("nested_loop", "grouping_operation", "ordering_operation", "duplicates_removal"):
        child = node.get(key)
        if isinstance(child, list):
            for item in child:
                _walk(item)
        elif isinstance(child, dict):
            _walk(child)


if __name__ == "__main__":
    raise SystemExit(main())
