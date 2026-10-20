from __future__ import annotations

import asyncio
import os
import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.engine import make_url

from app.core.config.settings import get_settings
from app.core.crypto import TokenEncryptor
from app.core.utils.time import naive_utc_to_epoch, utcnow
from app.db.models import Account, AccountStatus, ReadSnapshot, RequestLog
from app.db.session import SessionLocal
from app.modules.accounts.repository import AccountsRepository
from app.modules.usage.repository import UsageRepository


async def main() -> None:
    root = Path(os.environ["CODEX_LB_DATA_DIR"])
    database = make_url(get_settings().database_url)
    assert root.name.startswith("codex-lb-dashboard-browser-smoke-")
    assert root.joinpath("store.db").is_file()
    assert database.get_backend_name() == "sqlite"
    assert Path(database.database or "").resolve() == root.joinpath("store.db").resolve()
    now = utcnow()
    encryptor = TokenEncryptor()
    reset = int(naive_utc_to_epoch(now + timedelta(days=6)))
    async with SessionLocal() as session:
        accounts = AccountsRepository(session)
        usage = UsageRepository(session)
        for index in range(12):
            account_id = f"fixture-max-{index:02d}"
            account = await accounts.get_by_id(account_id)
            if account is None:
                await accounts.upsert(
                    Account(
                        id=account_id,
                        email=f"max{index}@example.test",
                        alias=f"Max Account {index:02d}",
                        plan_type="promax",
                        status=AccountStatus.ACTIVE,
                        access_token_encrypted=encryptor.encrypt("synthetic"),
                        refresh_token_encrypted=encryptor.encrypt("synthetic"),
                        id_token_encrypted=encryptor.encrypt("synthetic"),
                        last_refresh=now,
                    )
                )
            else:
                account.last_refresh = now
            for minutes, used in [(180, 10.0), (60, 11.0), (15, 12.0), (5, 13.0), (0, 14.0)]:
                await usage.add_entry(
                    account_id,
                    used + index,
                    window="primary",
                    window_minutes=10080,
                    reset_at=reset,
                    recorded_at=now - timedelta(minutes=minutes),
                )
        session.add(
            RequestLog(
                account_id="fixture-max-00",
                request_id="fixture-history",
                model="gpt-5.6-sol",
                requested_at=now - timedelta(hours=18),
                status="success",
                cost_usd=0,
            )
        )
        for index in range(10):
            session.add(
                RequestLog(
                    account_id="fixture-max-00",
                    request_id=f"fixture-spend-{index}",
                    model="gpt-5.6-sol",
                    requested_at=now - timedelta(minutes=30),
                    status="success",
                    input_tokens=100000,
                    cached_input_tokens=90000,
                    output_tokens=0,
                    cost_usd=0.1,
                    service_tier="default",
                    requested_service_tier="priority",
                    actual_service_tier="default",
                )
            )
        await session.commit()
        # The fixture changes historical inputs out of band. Mark existing
        # derived values due, then wait for the REAL lifespan-owned worker.
        # No collector is run by this helper or by the browser's HTTP reads.
        due_at = utcnow()
        await session.execute(update(ReadSnapshot).values(refresh_at=due_at))
        await session.commit()
    async with asyncio.timeout(30):
        while True:
            async with SessionLocal() as session:
                generated = (
                    await session.execute(select(ReadSnapshot.generated_at).where(ReadSnapshot.kind == "dashboard"))
                ).scalar_one_or_none()
            if generated is not None and generated >= due_at:
                break
            await asyncio.sleep(0.2)


async def observe() -> None:
    # Only synthetic observations in the same owned SQLite smoke fixture.
    # Without continued observations a five-minute test SHOULD eventually
    # report stale/insufficient data; browser refresh must not conceal that.
    root = Path(os.environ["CODEX_LB_DATA_DIR"])
    database = make_url(get_settings().database_url)
    assert root.name.startswith("codex-lb-dashboard-browser-smoke-")
    assert database.get_backend_name() == "sqlite"
    assert Path(database.database or "").resolve() == root.joinpath("store.db").resolve()
    reset = int(naive_utc_to_epoch(utcnow() + timedelta(days=6)))
    for tick in range(1, 7):
        await asyncio.sleep(60)
        async with SessionLocal() as session:
            usage = UsageRepository(session)
            for index in range(12):
                await usage.add_entry(
                    f"fixture-max-{index:02d}",
                    14.0 + index + tick * 0.1,
                    window="primary",
                    window_minutes=10080,
                    reset_at=reset,
                    recorded_at=utcnow(),
                )
            await session.commit()


asyncio.run(observe() if sys.argv[1:] == ["--observe"] else main())
