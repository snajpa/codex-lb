from __future__ import annotations

import asyncio
import gc
import time
from datetime import datetime, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.dashboard import repository as dashboard_repository_module
from app.modules.dashboard.repository import DashboardRepository


class _RecordingUsageRepo:
    def __init__(self, deltas: dict[str, float]) -> None:
        self.calls: list[tuple[tuple[tuple[str, str], ...], datetime, datetime]] = []
        self._deltas = deltas

    async def positive_used_percent_deltas_by_account(self, account_windows, *, since, until):
        self.calls.append((tuple(account_windows.items()), since, until))
        return dict(self._deltas) if account_windows else {}


def _repo(deltas: dict[str, float] | None = None) -> tuple[DashboardRepository, _RecordingUsageRepo]:
    repo = DashboardRepository(MagicMock())
    usage_repo = _RecordingUsageRepo(deltas or {"acc_a": 12.5})
    cast(Any, repo)._usage_repo = usage_repo
    return repo, usage_repo


_NOW = datetime(2026, 9, 9, 12, 0, 0)
_WINDOW = {"since": _NOW - timedelta(days=7), "until": _NOW}
_WEEK_SECONDS = 7 * 24 * 3600


def test_autouse_fixture_zeroes_ttl_and_clears_cache() -> None:
    assert dashboard_repository_module._TRAILING_DEMAND_TTL_SECONDS == 0.0
    assert dashboard_repository_module._trailing_demand_cache == {}


@pytest.mark.asyncio
async def test_zero_ttl_disables_memoization() -> None:
    repo, usage_repo = _repo()

    await repo.positive_used_percent_deltas_by_account({"acc_a": "secondary"}, **_WINDOW)
    await repo.positive_used_percent_deltas_by_account({"acc_a": "secondary"}, **_WINDOW)

    assert len(usage_repo.calls) == 2
    assert dashboard_repository_module._trailing_demand_cache == {}


@pytest.mark.asyncio
async def test_same_signature_within_ttl_queries_once(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_repository_module, "_TRAILING_DEMAND_TTL_SECONDS", 60.0)
    repo, usage_repo = _repo()

    first = await repo.positive_used_percent_deltas_by_account({"acc_a": "secondary", "acc_b": "primary"}, **_WINDOW)
    # Insertion order and the drifting window must not defeat the memo.
    drifted = {"since": _WINDOW["since"] + timedelta(seconds=15), "until": _WINDOW["until"] + timedelta(seconds=15)}
    second = await repo.positive_used_percent_deltas_by_account({"acc_b": "primary", "acc_a": "secondary"}, **drifted)

    assert len(usage_repo.calls) == 1
    assert first == second == {"acc_a": 12.5}


@pytest.mark.asyncio
async def test_miss_forwards_signature_and_window_bounds(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_repository_module, "_TRAILING_DEMAND_TTL_SECONDS", 60.0)
    repo, usage_repo = _repo()

    await repo.positive_used_percent_deltas_by_account({"acc_a": "secondary"}, **_WINDOW)

    assert usage_repo.calls == [((("acc_a", "secondary"),), _WINDOW["since"], _WINDOW["until"])]


@pytest.mark.asyncio
async def test_different_window_span_is_its_own_entry(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_repository_module, "_TRAILING_DEMAND_TTL_SECONDS", 60.0)
    repo, usage_repo = _repo()

    await repo.positive_used_percent_deltas_by_account({"acc_a": "secondary"}, **_WINDOW)
    await repo.positive_used_percent_deltas_by_account(
        {"acc_a": "secondary"}, since=_NOW - timedelta(hours=3), until=_NOW
    )

    assert len(usage_repo.calls) == 2
    assert set(dashboard_repository_module._trailing_demand_cache) == {
        (_WEEK_SECONDS, (("acc_a", "secondary"),)),
        (3 * 3600, (("acc_a", "secondary"),)),
    }


@pytest.mark.asyncio
async def test_empty_signature_is_memoized_as_empty(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_repository_module, "_TRAILING_DEMAND_TTL_SECONDS", 60.0)
    repo, usage_repo = _repo()

    first = await repo.positive_used_percent_deltas_by_account({}, **_WINDOW)
    second = await repo.positive_used_percent_deltas_by_account({}, **_WINDOW)

    assert first == second == {}
    assert len(usage_repo.calls) == 1
    assert (_WEEK_SECONDS, ()) in dashboard_repository_module._trailing_demand_cache


@pytest.mark.asyncio
async def test_hit_returns_a_copy(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_repository_module, "_TRAILING_DEMAND_TTL_SECONDS", 60.0)
    repo, _ = _repo()

    first = await repo.positive_used_percent_deltas_by_account({"acc_a": "secondary"}, **_WINDOW)
    first["acc_a"] = -1.0
    second = await repo.positive_used_percent_deltas_by_account({"acc_a": "secondary"}, **_WINDOW)

    assert second == {"acc_a": 12.5}


@pytest.mark.asyncio
async def test_different_signature_queries_independently(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_repository_module, "_TRAILING_DEMAND_TTL_SECONDS", 60.0)
    repo, usage_repo = _repo()

    await repo.positive_used_percent_deltas_by_account({"acc_a": "secondary"}, **_WINDOW)
    await repo.positive_used_percent_deltas_by_account({"acc_a": "primary"}, **_WINDOW)
    await repo.positive_used_percent_deltas_by_account({"acc_a": "secondary", "acc_b": "secondary"}, **_WINDOW)

    assert len(usage_repo.calls) == 3


@pytest.mark.asyncio
async def test_expired_entry_is_recomputed(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_repository_module, "_TRAILING_DEMAND_TTL_SECONDS", 60.0)
    repo, usage_repo = _repo()

    await repo.positive_used_percent_deltas_by_account({"acc_a": "secondary"}, **_WINDOW)
    key = (_WEEK_SECONDS, (("acc_a", "secondary"),))
    deltas, _expires_at = dashboard_repository_module._trailing_demand_cache[key]
    dashboard_repository_module._trailing_demand_cache[key] = (deltas, time.monotonic() - 1.0)

    await repo.positive_used_percent_deltas_by_account({"acc_a": "secondary"}, **_WINDOW)

    assert len(usage_repo.calls) == 2
    _deltas, refreshed_expires_at = dashboard_repository_module._trailing_demand_cache[key]
    assert refreshed_expires_at > time.monotonic()


@pytest.mark.asyncio
async def test_clear_forces_recompute(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_repository_module, "_TRAILING_DEMAND_TTL_SECONDS", 60.0)
    repo, usage_repo = _repo()

    await repo.positive_used_percent_deltas_by_account({"acc_a": "secondary"}, **_WINDOW)
    dashboard_repository_module._clear_trailing_demand_cache()
    await repo.positive_used_percent_deltas_by_account({"acc_a": "secondary"}, **_WINDOW)

    assert len(usage_repo.calls) == 2


@pytest.mark.asyncio
async def test_cache_evicts_oldest_entry_at_capacity(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_repository_module, "_TRAILING_DEMAND_TTL_SECONDS", 60.0)
    repo, usage_repo = _repo()
    capacity = dashboard_repository_module._TRAILING_DEMAND_MAX_ENTRIES

    for index in range(capacity + 1):
        await repo.positive_used_percent_deltas_by_account({f"acc_{index}": "secondary"}, **_WINDOW)
    await repo.positive_used_percent_deltas_by_account({"acc_0": "secondary"}, **_WINDOW)

    assert len(dashboard_repository_module._trailing_demand_cache) == capacity
    assert len(usage_repo.calls) == capacity + 2


@pytest.mark.asyncio
@pytest.mark.parametrize("expired", [False, True])
async def test_concurrent_cache_fill_queries_once(monkeypatch, expired: bool) -> None:
    monkeypatch.setattr(dashboard_repository_module, "_TRAILING_DEMAND_TTL_SECONDS", 60.0)
    key = (_WEEK_SECONDS, (("acc_a", "secondary"),))
    if expired:
        dashboard_repository_module._trailing_demand_cache[key] = ({"acc_a": -1}, time.monotonic() - 1)
    repo, usage = _repo()
    started, release = asyncio.Event(), asyncio.Event()

    async def fetch(*args, **kwargs):
        started.set()
        await release.wait()
        return {"acc_a": 12.5}

    fetch_mock = AsyncMock(side_effect=fetch)
    monkeypatch.setattr(usage, "positive_used_percent_deltas_by_account", fetch_mock)
    first = asyncio.create_task(repo.positive_used_percent_deltas_by_account({"acc_a": "secondary"}, **_WINDOW))
    second = None
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        second = asyncio.create_task(repo.positive_used_percent_deltas_by_account({"acc_a": "secondary"}, **_WINDOW))
        await asyncio.sleep(0)
        assert fetch_mock.await_count == 1
        release.set()
        assert await first == await second == {"acc_a": 12.5}
        assert fetch_mock.await_count == 1
        assert not dashboard_repository_module._trailing_demand_locks
    finally:
        release.set()
        for task in (first, second):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*(t for t in (first, second) if t is not None), return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["error", "cancel"])
async def test_failed_cache_fill_releases_waiter_without_caching_partial_result(monkeypatch, failure: str) -> None:
    monkeypatch.setattr(dashboard_repository_module, "_TRAILING_DEMAND_TTL_SECONDS", 60.0)
    repo, usage = _repo()
    started, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def fetch(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await release.wait()
            raise RuntimeError("read failed")
        return {"acc_a": 12.5}

    monkeypatch.setattr(usage, "positive_used_percent_deltas_by_account", fetch)
    first = asyncio.create_task(repo.positive_used_percent_deltas_by_account({"acc_a": "secondary"}, **_WINDOW))
    second = None
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        second = asyncio.create_task(repo.positive_used_percent_deltas_by_account({"acc_a": "secondary"}, **_WINDOW))
        await asyncio.sleep(0)
        assert calls == 1
        assert not dashboard_repository_module._trailing_demand_cache
        if failure == "cancel":
            first.cancel()
        else:
            release.set()
        with pytest.raises(asyncio.CancelledError if failure == "cancel" else RuntimeError):
            await first
        assert await asyncio.wait_for(second, timeout=1) == {"acc_a": 12.5}
        assert calls == 2
        # Failed tasks retain the read frame through their exception traceback.
        # Release that finished task before checking idle lock reclamation.
        first = None
        await asyncio.sleep(0)
        gc.collect()
        assert not dashboard_repository_module._trailing_demand_locks
    finally:
        release.set()
        for task in (first, second):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*(t for t in (first, second) if t is not None), return_exceptions=True)
