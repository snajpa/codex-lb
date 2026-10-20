from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import event, insert

from app.core.utils.time import utcnow
from app.db.dialect_sql import is_mysql
from app.db.models import Account, UsageHistory
from app.db.session import SessionLocal, engine
from app.modules.usage.repository import UsageRepository

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
@pytest.mark.parametrize("window", ["primary", "secondary"])
async def test_mysql_sql_cap_matches_full_history_oracle_and_preserves_recent_floor(db_setup, window):
    if not is_mysql(engine.dialect.name):
        pytest.skip("MySQL/MariaDB SQL-bound history regression")
    now = utcnow().replace(microsecond=0)
    ids = [f"projection-{i:03}" for i in range(65)]  # Cross the sequential SQL batch boundary.
    async with SessionLocal() as session:
        session.add_all(
            [
                Account(
                    id=key,
                    email=key + "@example.test",
                    plan_type="pro",
                    access_token_encrypted=b"synthetic",
                    refresh_token_encrypted=b"synthetic",
                    id_token_encrypted=b"synthetic",
                    last_refresh=now,
                )
                for key in ids
            ]
        )
        await session.flush()
        await session.execute(
            insert(UsageHistory),
            [
                {
                    "account_id": key,
                    "window": None if window == "primary" and i % 2 else window,
                    "used_percent": float(i),
                    "recorded_at": now - timedelta(minutes=200 - (i // 2) * 4),
                    "window_minutes": 10080,
                    "reset_at": 2_000_000_000,
                }
                for key in ids
                for i in range(100)
            ],
        )
        await session.commit()
    since, floor = now - timedelta(hours=4), now - timedelta(hours=1)
    cutoffs = {key: now - timedelta(minutes=30 if i % 3 == 0 else 150) for i, key in enumerate(ids)}
    async with SessionLocal() as session:
        repo = UsageRepository(session)
        full = await repo.bulk_history_since(ids, window, since, cutoffs=cutoffs)
        expected = {}
        for key, rows in full.items():
            effective_floor = max(since, cutoffs[key], floor)
            recent = [row for row in rows if row.recorded_at >= effective_floor]
            older = [row for row in rows if row.recorded_at < effective_floor]
            expected[key] = older[-5:] + recent
        statements = []

        def capture(_conn, _cursor, statement, _params, _context, _executemany):
            if "bounded_projection_history" in statement:
                statements.append(statement)

        event.listen(engine.sync_engine, "before_cursor_execute", capture)
        try:
            actual = await repo.bulk_history_since(
                ids, window, since, cutoffs=cutoffs, per_account_row_cap=5, uncapped_recent_floor=floor
            )
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", capture)
        assert actual == expected
        assert sum(map(len, actual.values())) < sum(map(len, full.values()))
        assert len(statements) == 2
        assert all("LIMIT" in statement and "UNION ALL" in statement for statement in statements)
        only_tail = await repo.bulk_history_since(ids, window, since, cutoffs=cutoffs, per_account_row_cap=5)
        assert only_tail == {key: rows[-5:] for key, rows in full.items()}
        assert await repo.bulk_history_since(ids, window, since, per_account_row_cap=0) == {}
