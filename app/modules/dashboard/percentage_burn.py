from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Literal, Protocol

from app.core.utils.time import naive_utc_to_epoch
from app.db.models import Account
from app.modules.dashboard.schemas import AccountQuotaBurnResponse
from app.modules.dashboard.weekly_pace import (
    FLEET_BURN_WINDOW,
    FRESHNESS_MISSED_REFRESH_CYCLES,
    MIN_FRESHNESS_SECONDS,
    PACE_ELIGIBLE_ACCOUNT_STATUSES,
)

MIN_OBSERVATION_SECONDS = 15 * 60


class QuotaObservation(Protocol):
    @property
    def recorded_at(self) -> datetime | None: ...
    @property
    def used_percent(self) -> float | None: ...
    @property
    def reset_at(self) -> int | None: ...
    @property
    def window_minutes(self) -> int | None: ...


@dataclass(frozen=True)
class _QuotaSample:
    recorded_at: datetime
    used_percent: float
    reset_at: int | None
    window_minutes: int | None


def build_percentage_burn(
    accounts: Sequence[Account],
    primary_history: Mapping[str, Sequence[QuotaObservation]],
    secondary_history: Mapping[str, Sequence[QuotaObservation]],
    *,
    now: datetime,
    usage_refresh_interval_seconds: int,
) -> list[AccountQuotaBurnResponse]:
    freshness = max(
        MIN_FRESHNESS_SECONDS,
        usage_refresh_interval_seconds * FRESHNESS_MISSED_REFRESH_CYCLES,
    )
    eligible = {account.id for account in accounts if account.status in PACE_ELIGIBLE_ACCOUNT_STATUSES}
    result: list[AccountQuotaBurnResponse] = []
    windows: tuple[tuple[Literal["primary", "secondary"], Mapping[str, Sequence[QuotaObservation]]], ...] = (
        ("primary", primary_history),
        ("secondary", secondary_history),
    )
    for window, history in windows:
        for account_id, observations in history.items():
            if account_id not in eligible:
                continue
            rows: list[_QuotaSample] = []
            for observation in observations:
                at, used = observation.recorded_at, observation.used_percent
                if at is not None and used is not None and at <= now and isfinite(used):
                    rows.append(_QuotaSample(at, used, observation.reset_at, observation.window_minutes))
            rows.sort(key=lambda row: row.recorded_at)
            if not rows:
                continue
            latest = rows[-1]
            if latest.window_minutes == 0 and latest.reset_at is None:
                continue
            reset = datetime.fromtimestamp(latest.reset_at, timezone.utc) if latest.reset_at is not None else None
            if reset is not None:
                reset = reset.replace(tzinfo=None) if now.tzinfo is None else reset.astimezone(now.tzinfo)
            age = max(0.0, (now - latest.recorded_at).total_seconds())
            stale = age > freshness or (reset is not None and reset <= now)
            remaining = max(0.0, min(100.0, 100.0 - latest.used_percent))
            segment = [
                row
                for row in rows
                if row.recorded_at >= now - FLEET_BURN_WINDOW
                and row.reset_at == latest.reset_at
                and row.window_minutes == latest.window_minutes
            ]
            # A decrease retires the old accumulation even if the provider did
            # not change its reset marker (rolling/reset-correction windows).
            start = 0
            for index in range(1, len(segment)):
                if segment[index].used_percent < segment[index - 1].used_percent:
                    start = index
            segment = segment[start:]
            span = (segment[-1].recorded_at - segment[0].recorded_at).total_seconds() if segment else 0.0
            rate: float | None = None
            exhaustion: datetime | None = None
            if not stale and len(segment) >= 2 and span >= MIN_OBSERVATION_SECONDS:
                rate = max(0.0, (segment[-1].used_percent - segment[0].used_percent) * 3600.0 / span)
                if remaining == 0:
                    exhaustion = now
                elif rate > 0:
                    seconds = remaining * 3600.0 / rate
                    # Do not predict depletion beyond a known intervening reset.
                    if reset is not None and seconds <= max(0.0, naive_utc_to_epoch(reset) - naive_utc_to_epoch(now)):
                        exhaustion = now + timedelta(seconds=seconds)
            result.append(
                AccountQuotaBurnResponse(
                    account_id=account_id,
                    window=window,
                    window_minutes=latest.window_minutes,
                    remaining_percent=remaining,
                    rate_percent_per_hour=rate,
                    observation_minutes=span / 60.0,
                    sample_age_seconds=age,
                    generated_at=now,
                    freshness_seconds=freshness,
                    stale=stale,
                    reset_at=reset,
                    projected_exhaustion_at=exhaustion,
                )
            )
    return result
