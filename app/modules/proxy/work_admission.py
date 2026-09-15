from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from app.core.clients.proxy import ProxyResponseError
from app.core.resilience.overload import local_overload_error
from app.core.utils.request_id import get_request_id

logger = logging.getLogger(__name__)

_DEFAULT_ADMISSION_WAIT_TIMEOUT_SECONDS = 10.0


@dataclass(slots=True)
class AdmissionLease:
    _semaphore: asyncio.Semaphore | None
    stage: str = "disabled"
    request_id: str | None = None
    _released: bool = False

    def release(self) -> None:
        if self._released or self._semaphore is None:
            return
        self._released = True
        self._semaphore.release()

    def __enter__(self) -> AdmissionLease:
        return self

    def __exit__(self, *args: object) -> None:
        self.release()

    def __del__(self) -> None:
        if self._released or self._semaphore is None:
            return
        self._released = True
        self._semaphore.release()
        logger.warning(
            "AdmissionLease was garbage-collected without release() — this indicates a bug in the caller "
            "stage=%s request_id=%s",
            self.stage,
            self.request_id,
        )


@dataclass(slots=True)
class _AdmissionGate:
    semaphore: asyncio.Semaphore
    wait_timeout_seconds: float


@dataclass(slots=True)
class _SessionTokenRateState:
    next_admission_at: float


class WorkAdmissionController:
    def __init__(
        self,
        *,
        token_refresh_limit: int,
        websocket_connect_limit: int,
        response_create_limit: int,
        compact_response_create_limit: int,
        admission_wait_timeout_seconds: float = _DEFAULT_ADMISSION_WAIT_TIMEOUT_SECONDS,
        session_input_token_rate_per_minute: int = 0,
    ) -> None:
        self._token_refresh = _make_gate(token_refresh_limit, admission_wait_timeout_seconds)
        self._websocket_connect = _make_gate(websocket_connect_limit, admission_wait_timeout_seconds)
        self._response_create = _make_gate(response_create_limit, admission_wait_timeout_seconds)
        self._compact_response_create = _make_gate(compact_response_create_limit, admission_wait_timeout_seconds)
        self._session_input_token_rate_per_minute = session_input_token_rate_per_minute
        self._session_token_rate_states: dict[str, _SessionTokenRateState] = {}
        self._next_session_token_rate_expiry = 0.0

    async def acquire_token_refresh(self) -> AdmissionLease:
        return await self._acquire(self._token_refresh, stage="token_refresh")

    async def acquire_websocket_connect(self) -> AdmissionLease:
        return await self._acquire(self._websocket_connect, stage="upstream_websocket_connect")

    async def acquire_response_create(self, *, compact: bool = False) -> AdmissionLease:
        semaphore = self._compact_response_create if compact else self._response_create
        stage = "compact_response_create" if compact else "response_create"
        return await self._acquire(semaphore, stage=stage)

    def enforce_session_input_token_rate(self, session_id: str | None) -> None:
        if self._session_input_token_rate_per_minute <= 0:
            return
        now = time.monotonic()
        self._purge_expired_session_token_rates(now)
        if not session_id:
            return
        if session_id not in self._session_token_rate_states:
            return
        raise ProxyResponseError(
            429,
            local_overload_error(
                "codex-lb is temporarily rate limited for this session",
                code="session_token_rate_limited",
            ),
        )

    def record_session_input_tokens(self, session_id: str | None, input_tokens: int | None) -> None:
        if self._session_input_token_rate_per_minute <= 0 or not session_id or not input_tokens or input_tokens < 0:
            return
        now = time.monotonic()
        self._purge_expired_session_token_rates(now)
        next_admission_at = now + 60.0 * input_tokens / self._session_input_token_rate_per_minute
        state = self._session_token_rate_states.get(session_id)
        if state is None:
            self._session_token_rate_states[session_id] = _SessionTokenRateState(next_admission_at)
        else:
            state.next_admission_at = max(state.next_admission_at, next_admission_at)
        if not self._next_session_token_rate_expiry or next_admission_at < self._next_session_token_rate_expiry:
            self._next_session_token_rate_expiry = next_admission_at

    def _purge_expired_session_token_rates(self, now: float) -> None:
        if now < self._next_session_token_rate_expiry:
            return
        next_expiry = 0.0
        for session_id, state in list(self._session_token_rate_states.items()):
            if state.next_admission_at <= now:
                del self._session_token_rate_states[session_id]
            elif not next_expiry or state.next_admission_at < next_expiry:
                next_expiry = state.next_admission_at
        self._next_session_token_rate_expiry = next_expiry

    async def _acquire(self, gate: _AdmissionGate | None, *, stage: str) -> AdmissionLease:
        if gate is None:
            return AdmissionLease(None, stage=stage, request_id=get_request_id())
        try:
            await asyncio.wait_for(gate.semaphore.acquire(), timeout=gate.wait_timeout_seconds)
        except asyncio.TimeoutError:
            available = gate.semaphore._value  # noqa: SLF001
            message = f"codex-lb is temporarily overloaded during {stage}"
            logger.warning(
                "proxy_admission_rejected request_id=%s stage=%s status=429 available=%s "
                "wait_timeout_seconds=%.1f message=%s",
                get_request_id(),
                stage,
                available,
                gate.wait_timeout_seconds,
                message,
            )
            raise ProxyResponseError(429, local_overload_error(message, code="global_admission_timeout"))
        return AdmissionLease(gate.semaphore, stage=stage, request_id=get_request_id())


def _make_gate(limit: int, wait_timeout_seconds: float) -> _AdmissionGate | None:
    if limit <= 0:
        return None
    return _AdmissionGate(
        semaphore=asyncio.Semaphore(limit),
        wait_timeout_seconds=wait_timeout_seconds,
    )
