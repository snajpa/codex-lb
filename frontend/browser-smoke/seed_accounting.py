from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config.settings import get_settings
from app.core.crypto import TokenEncryptor
from app.core.utils.time import naive_utc_to_epoch, utcnow
from app.db.models import Account, AccountStatus, RequestLog
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
            for minutes, used in [(180, 10.0), (60, 11.0), (15, 12.0), (1, 13.0), (0, 14.0)]:
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


asyncio.run(main())
