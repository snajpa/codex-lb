from __future__ import annotations

import asyncio
import gc
import logging

import pytest

from app.core.clients.proxy import ProxyResponseError
from app.modules.proxy import work_admission
from app.modules.proxy.work_admission import AdmissionLease, WorkAdmissionController

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_work_admission_rejects_after_wait_timeout() -> None:
    controller = WorkAdmissionController(
        token_refresh_limit=1,
        websocket_connect_limit=0,
        response_create_limit=0,
        compact_response_create_limit=0,
        admission_wait_timeout_seconds=0.3,
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def holder() -> None:
        lease = await controller.acquire_token_refresh()
        started.set()
        try:
            await release.wait()
        finally:
            lease.release()

    first = asyncio.create_task(holder())
    await started.wait()

    with pytest.raises(ProxyResponseError) as exc_info:
        await controller.acquire_token_refresh()

    release.set()
    await first

    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_admission_lease_context_manager_releases() -> None:
    """AdmissionLease used as a context manager releases the semaphore on exit."""
    sem = asyncio.Semaphore(1)
    await sem.acquire()

    lease = AdmissionLease(sem)
    with lease:
        assert sem.locked()
    assert not sem.locked()
    lease.release()
    assert not sem.locked()


@pytest.mark.asyncio
async def test_admission_lease_context_manager_releases_on_exception() -> None:
    """AdmissionLease releases the semaphore even when the with-block raises."""
    sem = asyncio.Semaphore(1)
    await sem.acquire()

    lease = AdmissionLease(sem)
    with pytest.raises(RuntimeError):
        with lease:
            raise RuntimeError("boom")
    assert not sem.locked()


@pytest.mark.asyncio
async def test_admission_lease_del_releases_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    """__del__ safety net releases the semaphore and logs a warning."""
    sem = asyncio.Semaphore(1)
    await sem.acquire()
    assert sem.locked()

    lease = AdmissionLease(sem, stage="unit_stage", request_id="req_unit")
    with caplog.at_level(logging.WARNING, logger="app.modules.proxy.work_admission"):
        del lease
        gc.collect()

    assert not sem.locked()
    assert "garbage-collected without release()" in caplog.text
    assert "stage=unit_stage" in caplog.text
    assert "request_id=req_unit" in caplog.text


@pytest.mark.asyncio
async def test_admission_lease_del_noop_after_release() -> None:
    """__del__ does nothing if the lease was already released."""
    sem = asyncio.Semaphore(1)
    await sem.acquire()

    lease = AdmissionLease(sem)
    lease.release()
    assert not sem.locked()

    del lease
    gc.collect()
    assert sem._value == 1  # noqa: SLF001


@pytest.mark.asyncio
async def test_admission_lease_none_semaphore_is_noop() -> None:
    """AdmissionLease with None semaphore (disabled gate) is always safe."""
    lease = AdmissionLease(None)
    lease.release()
    with lease:
        pass
    del lease
    gc.collect()


def _session_rate_controller(*, rate: int = 0) -> WorkAdmissionController:
    return WorkAdmissionController(
        token_refresh_limit=0,
        websocket_connect_limit=0,
        response_create_limit=0,
        compact_response_create_limit=0,
        session_input_token_rate_per_minute=rate,
    )


def test_session_input_token_rate_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(work_admission.time, "monotonic", lambda: 100.0)
    controller = _session_rate_controller()

    controller.record_session_input_tokens("session-a", 400_000)
    controller.enforce_session_input_token_rate("session-a")


def test_session_input_token_rate_rejects_only_the_cooled_session(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 100.0
    monkeypatch.setattr(work_admission.time, "monotonic", lambda: now)
    controller = _session_rate_controller(rate=400_000)

    controller.record_session_input_tokens("session-a", 400_000)
    now = 105.0

    with pytest.raises(ProxyResponseError) as raised:
        controller.enforce_session_input_token_rate("session-a")

    assert raised.value.status_code == 429
    assert raised.value.payload["error"]["code"] == "session_token_rate_limited"
    controller.enforce_session_input_token_rate("session-b")


def test_session_input_token_rate_expires_and_ignores_missing_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 100.0
    monkeypatch.setattr(work_admission.time, "monotonic", lambda: now)
    controller = _session_rate_controller(rate=400_000)

    controller.record_session_input_tokens(None, 400_000)
    controller.record_session_input_tokens("session-a", None)
    controller.record_session_input_tokens("session-a", 0)
    controller.enforce_session_input_token_rate("session-a")

    controller.record_session_input_tokens("session-a", 400_000)
    now = 160.0
    controller.enforce_session_input_token_rate("session-a")


def test_session_input_token_rate_purges_expired_other_session(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 100.0
    monkeypatch.setattr(work_admission.time, "monotonic", lambda: now)
    controller = _session_rate_controller(rate=400_000)

    controller.record_session_input_tokens("session-a", 400_000)
    now = 160.0
    controller.enforce_session_input_token_rate("session-b")

    assert controller._session_token_rate_states == {}  # noqa: SLF001
