"""Exercise the real background producer and the externally failing HTTP surface."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.crypto import TokenEncryptor
from app.core.utils.time import naive_utc_to_epoch, utcnow
from app.db.models import Account, AccountStatus, ReadSnapshot, RequestLog
from app.db.session import SessionLocal
from app.modules.accounts.repository import AccountsRepository
from app.modules.dashboard.repository import DashboardRepository
from app.modules.dashboard.service import DashboardService
from app.modules.dashboard.weekly_pace import PRO_WEEKLY_CAPACITY_CREDITS
from app.modules.read_snapshots.repository import SCHEMA_VERSION
from app.modules.read_snapshots.scheduler import ReadSnapshotScheduler
from app.modules.usage.repository import UsageRepository
from tests.snapshot_helpers import prepare_read_snapshot

pytestmark = pytest.mark.integration


async def seed(now, *, unpriced=False, weekly_primary=False):
    encryptor = TokenEncryptor()
    reset = int(naive_utc_to_epoch(now + timedelta(days=5)))
    async with SessionLocal() as session:
        for name in ("pace-account", "foreign"):
            await AccountsRepository(session).upsert(
                Account(
                    id=name,
                    email=f"{name}@example.invalid",
                    plan_type="pro",
                    status=AccountStatus.ACTIVE,
                    access_token_encrypted=encryptor.encrypt("access"),
                    refresh_token_encrypted=encryptor.encrypt("refresh"),
                    id_token_encrypted=encryptor.encrypt("id"),
                    last_refresh=now,
                )
            )
        usage = UsageRepository(session)
        for minutes, used in [(120, 10), (60, 15), (6, 20), (4, 20), (0.1, 20)]:
            await usage.add_entry(
                "pace-account",
                used,
                window="primary" if weekly_primary else "secondary",
                window_minutes=10080,
                reset_at=reset,
                recorded_at=now - timedelta(minutes=minutes),
            )
        for request_id, minutes, cost, deleted, kind, account in [
            ("calibration", 119, 9, False, "normal", "pace-account"),
            ("five-minute", 2, None if unpriced else 1, False, "normal", "pace-account"),
            ("deleted", 1, 1000, True, "normal", "pace-account"),
            ("warmup", 1, 1000, False, "warmup", "pace-account"),
            ("foreign", 1, 1000, False, "normal", "foreign"),
            ("future", -1, 1000, False, "normal", "pace-account"),
            ("too-old", 181, 1000, False, "normal", "pace-account"),
        ]:
            session.add(
                RequestLog(
                    account_id=account,
                    request_id=request_id,
                    requested_at=now - timedelta(minutes=minutes),
                    model="synthetic-priced-work",
                    status="success",
                    input_tokens=1000,
                    output_tokens=10,
                    cost_usd=cost,
                    deleted_at=now if deleted else None,
                    request_kind=kind,
                )
            )
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("weekly_primary", [True, False])
async def test_heavy_traffic_flat_quota_forecast_is_background_only_and_exact_window(
    async_client, db_setup, monkeypatch, weekly_primary
):
    now = utcnow().replace(microsecond=0)
    monkeypatch.setattr("app.modules.dashboard.service.utcnow", lambda: now)
    await seed(now, weekly_primary=weekly_primary)
    calls = []
    original = DashboardRepository.traffic_pace_work

    async def counted(self, calibrations, *, now):
        result = await original(self, calibrations, now=now)
        calls.append(result)
        return result

    monkeypatch.setattr(DashboardRepository, "traffic_pace_work", counted)
    await prepare_read_snapshot("/api/dashboard/projections")
    assert len(calls) == 1  # All four averaging values + three overview ranges reuse one bounded grouped read.
    work = calls[0]["pace-account"]
    assert work.calibration_work == pytest.approx(10)
    assert work.windows[5].priced_work == 1
    assert work.windows[5].requests == 1
    assert work.windows[5].unpriced_requests == 0

    async def forbidden(*args, **kwargs):
        pytest.fail("An HTTP read performed analytical collection")

    monkeypatch.setattr(DashboardRepository, "traffic_pace_work", forbidden)
    monkeypatch.setattr(DashboardService, "get_projections", forbidden)
    monkeypatch.setattr(DashboardService, "get_overview", forbidden)
    for route in ("overview", "projections"):
        response = await async_client.get(f"/api/dashboard/{route}?burnWindowMinutes=5")
        assert response.status_code == 200, response.text
        payload = response.json()
        pace = payload["weeklyCreditPace"]
        assert pace["burnWindowMinutes"] == 5
        assert pace["burnRateBasis"] == "traffic_calibrated"
        assert pace["observedQuotaBurnRateCreditsPerHour"] == 0
        assert pace["burnRateRecentCreditsPerHour"] == pytest.approx(PRO_WEEKLY_CAPACITY_CREDITS * 0.12)
        assert pace["forecastBurnRateCreditsPerHour"] == pace["burnRateRecentCreditsPerHour"]
        assert pace["burnObservedRequestCount"] == 1
        assert pace["burnCalibrationMinutes"] == pytest.approx(119.9)
        assert pace["confidence"] == "medium"
        assert payload["snapshot"]["stale"] is False
        for minutes in (60, 180):
            direct = await async_client.get(f"/api/dashboard/{route}?burnWindowMinutes={minutes}")
            assert direct.status_code == 200
            assert direct.json()["weeklyCreditPace"]["burnWindowMinutes"] == minutes
            assert direct.json()["weeklyCreditPace"]["burnRateBasis"] == "quota"
    async with SessionLocal() as session:
        snapshot = (await session.execute(select(ReadSnapshot).where(ReadSnapshot.kind == "dashboard"))).scalar_one()
        assert snapshot.schema_version == SCHEMA_VERSION == 2
    scheduler = ReadSnapshotScheduler()
    assert scheduler.leader._lease_id == 100 + SCHEMA_VERSION
    assert await scheduler.stop()


@pytest.mark.asyncio
async def test_missing_priced_usage_keeps_honest_direct_quota_basis(async_client, db_setup, monkeypatch):
    now = utcnow().replace(microsecond=0)
    monkeypatch.setattr("app.modules.dashboard.service.utcnow", lambda: now)
    await seed(now, unpriced=True)
    await prepare_read_snapshot("/api/dashboard/projections")
    response = await async_client.get("/api/dashboard/projections?burnWindowMinutes=5")
    assert response.status_code == 200
    pace = response.json()["weeklyCreditPace"]
    assert pace["burnWindowMinutes"] == 5
    assert pace["burnRateBasis"] == "quota"
    assert pace["burnRateRecentCreditsPerHour"] == 0
    assert pace["burnObservedRequestCount"] is None
    assert pace["burnCalibrationMinutes"] is None


@pytest.mark.asyncio
async def test_unknown_disconnected_work_is_disclosed_not_free(async_client, db_setup, monkeypatch):
    now = utcnow().replace(microsecond=0)
    monkeypatch.setattr("app.modules.dashboard.service.utcnow", lambda: now)
    await seed(now)
    async with SessionLocal() as session:
        session.add(
            RequestLog(
                account_id="pace-account",
                request_id="disconnected",
                requested_at=now - timedelta(minutes=1),
                model="synthetic-priced-work",
                status="cancelled",
            )
        )
        await session.commit()
    await prepare_read_snapshot("/api/dashboard/projections")
    response = await async_client.get("/api/dashboard/projections?burnWindowMinutes=5")
    assert response.status_code == 200
    pace = response.json()["weeklyCreditPace"]
    assert pace["burnWindowMinutes"] == 5
    assert pace["burnRateBasis"] == "traffic_calibrated"
    assert pace["burnUnpricedRequestCount"] == 1
    assert pace["burnCalibrationUnpricedRequestCount"] == 1
    assert pace["burnObservedRequestCount"] == 2
    assert pace["confidence"] == "low"
    assert pace["forecastBurnRateCreditsPerHour"] > 0


@pytest.mark.asyncio
async def test_version_two_registration_preserves_pinned_version_one_lastgood(db_setup):
    import hashlib

    from app.modules.read_snapshots.repository import SnapshotRepository

    now = utcnow()
    key = hashlib.sha256(b"1:dashboard:{}").hexdigest()
    async with SessionLocal() as session:
        session.add(
            ReadSnapshot(
                snapshot_key=key,
                kind="dashboard",
                schema_version=1,
                parameters_json="{}",
                payload_json='{"legacy":true}',
                generation=7,
                published_generation=7,
                generated_at=now,
                refresh_at=now,
                requested_at=now,
                pinned=True,
            )
        )
        await session.commit()
        new_key = await SnapshotRepository(session).register("dashboard", {}, pinned=True)
        assert new_key != key
        legacy = await session.get(ReadSnapshot, key)
        assert legacy is not None and legacy.payload_json == '{"legacy":true}' and legacy.published_generation == 7
        new = await session.get(ReadSnapshot, new_key)
        assert new is not None and new.schema_version == 2 and new.payload_json is None


@pytest.mark.asyncio
async def test_full_recent_prior_registry_admits_canonical_but_not_filter_preemption(db_setup):
    import hashlib
    import json

    from sqlalchemy import func

    from app.modules.read_snapshots.repository import MAX_ENTRIES, SnapshotCapacityError, SnapshotRepository

    now = utcnow()
    zones = [
        "Europe/Prague",
        "America/New_York",
        "Asia/Seoul",
        "Asia/Tokyo",
        "Australia/Sydney",
        "Europe/London",
        "Asia/Kolkata",
    ]

    def row(kind, parameters, *, pinned=False, version=1, busy=False):
        encoded = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
        key = "0" * 64 if kind == "registry" else hashlib.sha256(f"{version}:{kind}:{encoded}".encode()).hexdigest()
        return ReadSnapshot(
            snapshot_key=key,
            kind=kind,
            schema_version=version,
            parameters_json=encoded,
            requested_at=now,
            refresh_at=now,
            generated_at=now,
            payload_json='{"lastGood":true}',
            published_generation=4,
            generation=4,
            pinned=pinned,
            refresh_started_at=now if busy else None,
        )

    legacy_pinned = [row("dashboard", {}, pinned=True)] + [
        row("report-preset", {"days": days, "timezone": "UTC"}, pinned=True) for days in (7, 30, 90)
    ]
    entries = [row("registry", {}, pinned=True, version=0), *legacy_pinned]
    entries += [row("report-zone", {"timezone": zone}, version=0) for zone in zones]
    entries += [row("report-preset", {"days": days, "timezone": zone}) for zone in zones for days in (7, 30, 90)]
    ranges = [
        row(
            "report-range",
            {"start": "2026-10-01", "end": "2026-10-02", "timezone": "UTC", "model": str(i)},
            busy=i == 0,
        )
        for i in range(31)
    ]
    entries += ranges
    assert len(entries) == MAX_ENTRIES == 64
    pinned_keys = [entry.snapshot_key for entry in legacy_pinned]
    busy_key = ranges[0].snapshot_key
    async with SessionLocal() as session:
        session.add_all(entries)
        await session.commit()
        repository = SnapshotRepository(session)
        with pytest.raises(SnapshotCapacityError):
            await repository.register("report-range", {"start": "2026-10-03", "end": "2026-10-04", "timezone": "UTC"})
        for kind, parameters in [("dashboard", {})] + [
            ("report-preset", {"days": days, "timezone": "UTC"}) for days in (7, 30, 90)
        ]:
            await repository.register(kind, parameters, pinned=True)
        assert (await session.execute(select(func.count()).select_from(ReadSnapshot))).scalar_one() == 64
        for key in pinned_keys:
            retained = await session.get(ReadSnapshot, key, populate_existing=True)
            assert (
                retained is not None
                and retained.payload_json == '{"lastGood":true}'
                and retained.published_generation == 4
            )
        assert await session.get(ReadSnapshot, busy_key) is not None  # busy producer not preempted
        assert (
            await session.execute(
                select(func.count()).select_from(ReadSnapshot).where(ReadSnapshot.schema_version == 2)
            )
        ).scalar_one() == 4
