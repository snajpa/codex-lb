import asyncio,os,sys
from pathlib import Path
from datetime import timedelta
root=Path(os.environ["CODEX_LB_DATA_DIR"])
assert root.name.startswith("codex-lb-dashboard-browser-smoke-")
assert root.joinpath("store.db").is_file()
from app.core.crypto import TokenEncryptor
from app.core.utils.time import utcnow,naive_utc_to_epoch
from app.db.models import Account,AccountStatus,RequestLog
from app.db.session import SessionLocal
from app.modules.accounts.repository import AccountsRepository
from app.modules.usage.repository import UsageRepository
async def main():
 now=utcnow();enc=TokenEncryptor();reset=int(naive_utc_to_epoch(now+timedelta(days=6)))
 async with SessionLocal() as session:
  accounts=AccountsRepository(session);usage=UsageRepository(session)
  for i in range(12):
   key=f"fixture-max-{i:02d}"
   await accounts.upsert(Account(id=key,email=f"max{i}@example.test",alias=f"Max Account {i:02d}",plan_type="promax",status=AccountStatus.ACTIVE,access_token_encrypted=enc.encrypt("synthetic"),refresh_token_encrypted=enc.encrypt("synthetic"),id_token_encrypted=enc.encrypt("synthetic"),last_refresh=now))
   for minutes,used in [(61,10.0+i),(1,20.0+i)]:
    await usage.add_entry(key,used,window="primary",window_minutes=10080,reset_at=reset,recorded_at=now-timedelta(minutes=minutes))
  session.add(RequestLog(account_id="fixture-max-00",request_id="fixture-history",model="gpt-5.6-sol",requested_at=now-timedelta(hours=18),status="success",cost_usd=0))
  for i in range(10):
   session.add(RequestLog(account_id="fixture-max-00",request_id=f"fixture-spend-{i}",model="gpt-5.6-sol",requested_at=now-timedelta(minutes=30),status="success",input_tokens=100000,cached_input_tokens=90000,output_tokens=0,cost_usd=.1,service_tier="default",requested_service_tier="priority",actual_service_tier="default"))
  await session.commit()
asyncio.run(main())
