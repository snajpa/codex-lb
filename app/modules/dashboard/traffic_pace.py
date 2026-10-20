"""Bounded empirical quota calibration, distinct from direct quota measurement."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite

from app.core.utils.time import naive_utc_to_epoch
from app.db.models import UsageHistory
from app.modules.dashboard.schemas import WeeklyPaceWindowMinutes

TRAFFIC_PACE_WINDOWS: tuple[WeeklyPaceWindowMinutes, ...] = (5, 15)
CALIBRATION_WINDOW = timedelta(hours=3)
MIN_CALIBRATION_SECONDS = 15 * 60


@dataclass(frozen=True)
class PaceCalibration:
    account_id: str
    start: datetime
    end: datetime
    used_percent: float


@dataclass(frozen=True)
class TrafficWindowWork:
    priced_work: float
    requests: int
    unpriced_requests: int


@dataclass(frozen=True)
class PaceTrafficWork:
    calibration_work: float
    calibration_unpriced_requests: int
    windows: Mapping[WeeklyPaceWindowMinutes, TrafficWindowWork]


def build_pace_calibrations(
    history: Mapping[str, Sequence[UsageHistory]],
    *,
    eligible_accounts: set[str],
    now: datetime,
) -> dict[str, PaceCalibration]:
    result: dict[str, PaceCalibration] = {}
    for account_id, observations in history.items():
        if account_id not in eligible_accounts:
            continue
        rows = [row for row in observations if now - CALIBRATION_WINDOW <= row.recorded_at <= now]
        # A reset, correction, invalid observation or changed window retires the
        # old calibration, even when the provider keeps the same reset marker.
        segment: list[UsageHistory] = []
        for row in rows:
            if not isfinite(row.used_percent) or not 0 <= row.used_percent <= 100:
                segment = []
                continue
            if segment:
                previous = segment[-1]
                if (
                    row.window_minutes != previous.window_minutes
                    or row.reset_at is None
                    or previous.reset_at is None
                    or abs(row.reset_at - previous.reset_at) > 60
                    or row.used_percent < previous.used_percent
                ):
                    segment = []
            segment.append(row)
        if len(segment) < 2:
            continue
        first, last = segment[0], segment[-1]
        span = (last.recorded_at - first.recorded_at).total_seconds()
        delta = last.used_percent - first.used_percent
        if (
            span < MIN_CALIBRATION_SECONDS
            or delta <= 0
            or last.window_minutes != 10080
            or last.reset_at is None
            or last.reset_at <= naive_utc_to_epoch(now)
            or (now - last.recorded_at).total_seconds() > 300
        ):
            continue
        result[account_id] = PaceCalibration(account_id, first.recorded_at, last.recorded_at, delta)
    return result


def traffic_burn_percent_per_hour(
    calibration: PaceCalibration | None,
    work: PaceTrafficWork | None,
    minutes: WeeklyPaceWindowMinutes,
) -> float | None:
    if calibration is None or work is None or minutes not in TRAFFIC_PACE_WINDOWS:
        return None
    recent = work.windows.get(minutes)
    if (
        recent is None
        or not isfinite(work.calibration_work)
        or work.calibration_work <= 0
        or not isfinite(recent.priced_work)
        or recent.priced_work < 0
    ):
        return None
    if recent.unpriced_requests and recent.priced_work == 0:
        return None  # Unknown current work cannot be a calibrated zero.
    # API price weights cached/model/tier work. The measured account-specific
    # ratio, not a fixed dollars-to-quota conversion, supplies quota units.
    rate = calibration.used_percent * recent.priced_work / work.calibration_work * 60 / minutes
    return rate if isfinite(rate) else None
