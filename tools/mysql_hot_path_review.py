"""MySQL hot-path reviewer for a disposable database (never the live one).

Seeds a disposable MySQL database with production-shaped data, drives the
per-request and dashboard query paths the way the application does, captures the
SQL each path emits, and runs ``EXPLAIN ANALYZE`` over every captured statement.
Index usage and timing therefore come out as recorded evidence rather than an
index checklist.

Usage (disposable databases only; refuses anything that does not look disposable):

    CODEX_LB_PERF_DATABASE_URL=mysql+asyncmy://codex_lb:codex_lb@127.0.0.1:3306/codex_lb_perf \
        uv run python tools/mysql_hot_path_review.py

Results are printed and written to the JSON report path given by
``CODEX_LB_PERF_REPORT`` (default: ./mysql-perf-review.json).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_REQUIRED_SUFFIXES = ("_perf", "_probe", "_smoke", "_review")


def _require_disposable_url() -> str:
    url = (os.environ.get("CODEX_LB_PERF_DATABASE_URL") or "").rstrip("/")
    if not url:
        raise SystemExit("CODEX_LB_PERF_DATABASE_URL is required (mysql+asyncmy://... for a disposable database)")
    if not url.endswith(_REQUIRED_SUFFIXES):
        raise SystemExit(
            f"refusing to run against {url!r}: the database name must end with one of "
            f"{_REQUIRED_SUFFIXES} so the live database can never be touched"
        )
    os.environ["CODEX_LB_DATABASE_URL"] = url
    return url


_URL = _require_disposable_url()

from sqlalchemy import event  # noqa: E402

from app.core.utils.time import utcnow  # noqa: E402
from app.db.migrate import run_upgrade  # noqa: E402
from app.db.models import (  # noqa: E402
    Account,
    AccountStatus,
    AdditionalUsageHistory,
    ApiKey,
    RequestLog,
    StickySession,
    StickySessionKind,
    UsageHistory,
)
from app.db.session import SessionLocal  # noqa: E402
from app.modules.api_keys.repository import ApiKeysRepository  # noqa: E402
from app.modules.proxy.sticky_repository import StickySessionsRepository  # noqa: E402
from app.modules.request_logs.repository import RequestLogsRepository  # noqa: E402
from app.modules.usage.repository import UsageRepository  # noqa: E402

_ACCOUNT_COUNT = 5
_API_KEY_COUNT = 20
_USAGE_ROWS = 40_000
_REQUEST_LOG_ROWS = 60_000
_STICKY_ROWS = 5_000
_ADDITIONAL_USAGE_ROWS = 10_000
#: Seeded history spans a month while the driven queries look back a week (or a
#: day), so a plan that fails to prune shows up as a full scan instead of being
#: hidden behind a filter that matches every row.
_HISTORY_MINUTES = 30 * 24 * 60


def _required_columns(table: Any) -> list[str]:
    """Columns the schema insists on that neither Python nor the server defaults."""

    required: list[str] = []
    for column in table.columns:
        if column.nullable or column.primary_key:
            continue
        if column.default is not None or column.server_default is not None:
            continue
        required.append(column.name)
    return required


def _auto_value(column: Any, now: datetime, index: int) -> Any:
    try:
        python_type = column.type.python_type
    except Exception:  # noqa: BLE001 - exotic types fall back to text
        python_type = str
    if python_type is bool:
        return True
    if python_type is int:
        return index % 1000
    if python_type is float:
        return float(index % 100)
    if python_type is datetime:
        return now - timedelta(minutes=index % _HISTORY_MINUTES)
    if python_type is bytes:
        return b"sealed"
    return f"perf-{column.name}-{index % 97}"


def _complete(table: Any, rows: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """Fill any required column a row does not set, so seeding never drifts."""

    required = _required_columns(table)
    for index, row in enumerate(rows):
        for name in required:
            row.setdefault(name, _auto_value(table.c[name], now, index))
    return rows


async def _wipe() -> None:
    """Empty the seeded tables so repeated runs measure the same dataset."""

    async with SessionLocal() as session:
        for table in (
            RequestLog.__table__,
            UsageHistory.__table__,
            AdditionalUsageHistory.__table__,
            StickySession.__table__,
            ApiKey.__table__,
            Account.__table__,
        ):
            await session.execute(table.delete())
        await session.commit()


async def _seed() -> None:
    """Insert production-shaped rows through Core so the plans see real widths."""

    await _wipe()
    now = utcnow()
    async with SessionLocal() as session:
        accounts = [
            Account(
                id=f"perf-acc-{index}",
                chatgpt_account_id=f"perf-upstream-{index}",
                email=f"perf{index}@example.invalid",
                plan_type="plus",
                access_token_encrypted=b"sealed",
                refresh_token_encrypted=b"sealed",
                id_token_encrypted=b"sealed",
                last_refresh=now,
                status=AccountStatus.ACTIVE,
            )
            for index in range(_ACCOUNT_COUNT)
        ]
        session.add_all(accounts)
        session.add_all(
            [
                ApiKey(
                    id=f"perf-key-{index}",
                    name=f"perf key {index}",
                    key_hash=f"sha256:perf-{index:04d}",
                    key_prefix=f"sk-perf-{index:04d}",
                    is_active=True,
                )
                for index in range(_API_KEY_COUNT)
            ]
        )
        await session.commit()

    usage_rows = _complete(
        UsageHistory.__table__,
        [
            {
                "account_id": f"perf-acc-{index % _ACCOUNT_COUNT}",
                "window": "primary" if index % 2 == 0 else "secondary",
                "used_percent": float(index % 100),
                "window_minutes": 300,
                "recorded_at": now - timedelta(minutes=index % _HISTORY_MINUTES),
            }
            for index in range(_USAGE_ROWS)
        ],
        now,
    )
    log_rows = _complete(
        RequestLog.__table__,
        [
            {
                "account_id": f"perf-acc-{index % _ACCOUNT_COUNT}",
                "request_id": f"req-{index:06d}",
                "requested_at": now - timedelta(minutes=index % _HISTORY_MINUTES),
                "model": f"gpt-{index % 7}",
                "input_tokens": index % 5000,
                "output_tokens": index % 900,
                "cached_input_tokens": 0,
                "reasoning_tokens": 0,
                "latency_ms": index % 3000,
                "status": "success" if index % 11 else "error",
                "api_key_id": f"perf-key-{index % _API_KEY_COUNT}",
                "conversation_id": f"conv-{index % 500:04d}",
            }
            for index in range(_REQUEST_LOG_ROWS)
        ],
        now,
    )
    sticky_rows = _complete(
        StickySession.__table__,
        [
            {
                "key": f"sticky-{index:05d}",
                "account_id": f"perf-acc-{index % _ACCOUNT_COUNT}",
                "kind": StickySessionKind.PROMPT_CACHE if index % 3 == 0 else StickySessionKind.STICKY_THREAD,
                "created_at": now - timedelta(minutes=index % 600),
                "updated_at": now - timedelta(minutes=index % 600),
            }
            for index in range(_STICKY_ROWS)
        ],
        now,
    )
    additional_rows = _complete(
        AdditionalUsageHistory.__table__,
        [
            {
                "account_id": f"perf-acc-{index % _ACCOUNT_COUNT}",
                "quota_key": f"spark-{index % 3}",
                "limit_name": "spark",
                "metered_feature": "spark",
                "window": "primary" if index % 2 == 0 else "secondary",
                "used_percent": float(index % 100),
                "window_minutes": 300,
                "recorded_at": now - timedelta(minutes=index % _HISTORY_MINUTES),
            }
            for index in range(_ADDITIONAL_USAGE_ROWS)
        ],
        now,
    )

    async with SessionLocal() as session:
        for table, rows in (
            (UsageHistory.__table__, usage_rows),
            (RequestLog.__table__, log_rows),
            (StickySession.__table__, sticky_rows),
            (AdditionalUsageHistory.__table__, additional_rows),
        ):
            for offset in range(0, len(rows), 5_000):
                await session.execute(table.insert(), rows[offset : offset + 5_000])
        await session.commit()


class _Captured:
    __slots__ = ("statement", "parameters", "elapsed_ms")

    def __init__(self, statement: str, parameters: Any, elapsed_ms: float) -> None:
        self.statement = statement
        self.parameters = parameters
        self.elapsed_ms = elapsed_ms


def _attach_recorder(engine: Any, captured: list[_Captured]) -> None:
    sync_engine = engine.sync_engine
    started: dict[Any, float] = {}

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        del cursor, statement, parameters, context, executemany
        started[conn] = time.perf_counter()

    @event.listens_for(sync_engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        del cursor, context, executemany
        begin = started.pop(conn, None)
        elapsed_ms = (time.perf_counter() - begin) * 1000 if begin is not None else float("nan")
        captured.append(_Captured(statement=statement, parameters=parameters, elapsed_ms=elapsed_ms))


async def _drive() -> None:
    """Exercise the per-request and dashboard paths against the seeded data."""

    now = utcnow()
    accounts = [f"perf-acc-{index}" for index in range(_ACCOUNT_COUNT)]
    async with SessionLocal() as session:
        usage = UsageRepository(session)
        await usage.bulk_history_since(
            accounts,
            "primary",
            now - timedelta(days=7),
            cutoffs={account: now - timedelta(hours=5) for account in accounts},
        )
        await usage.bulk_history_since(accounts, "secondary", now - timedelta(days=7))

        keys = ApiKeysRepository(session)
        await keys.get_by_hash("sha256:perf-0007")

        sticky = StickySessionsRepository(session)
        await sticky.get_entry("sticky-00123", kind=StickySessionKind.STICKY_THREAD)
        await sticky.get_account_id_and_abandonment("sticky-00123", kind=StickySessionKind.STICKY_THREAD)

        logs = RequestLogsRepository(session)
        await logs.aggregate_activity_since(now - timedelta(days=1))
        await logs.aggregate_by_bucket(since=now - timedelta(days=2), bucket_seconds=3600)


async def _explain(captured: list[_Captured], report: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    async with SessionLocal() as session:
        connection = await session.connection()
        for entry in captured:
            statement = " ".join(entry.statement.split())
            if not statement.lower().startswith(("select", "insert", "update", "delete")):
                continue
            if statement in seen:
                continue
            seen.add(statement)
            started = time.perf_counter()
            try:
                result = await connection.exec_driver_sql(f"EXPLAIN ANALYZE {statement}", entry.parameters)
                plan_rows = [str(row[0]) for row in result.fetchall()]
            except Exception as exc:  # noqa: BLE001 - report, never abort the review
                plan_rows = [f"EXPLAIN failed: {exc!r}"]
            elapsed_ms = (time.perf_counter() - started) * 1000
            report.append(
                {
                    "statement": statement,
                    "driver_time_ms": round(entry.elapsed_ms, 3),
                    "explain_analyze_ms": round(elapsed_ms, 3),
                    "plan": plan_rows,
                }
            )
            print(f"\n--- {statement[:200]}")
            print(f"    driver {entry.elapsed_ms:.3f} ms | explain-analyze {elapsed_ms:.3f} ms")
            for line in plan_rows[:10]:
                print(f"    {line}")


async def main() -> None:
    print(f"perf review against {_URL}")
    print("building schema from migrations ...")
    run_upgrade(_URL, "head", bootstrap_legacy=True)
    print("seeding ...")
    await _seed()

    from app.db.session import engine

    captured: list[_Captured] = []
    _attach_recorder(engine, captured)
    print("driving hot paths ...")
    await _drive()
    print(f"captured {len(captured)} statements")

    report: list[dict[str, Any]] = []
    await _explain(captured, report)

    out_path = Path(os.environ.get("CODEX_LB_PERF_REPORT", "mysql-perf-review.json"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {"url": _URL, "generated_at": datetime.now(UTC).isoformat(), "statements": report},
            indent=2,
        )
    )
    print(f"\nreport written to {out_path} ({len(report)} statements)")


if __name__ == "__main__":
    asyncio.run(main())
