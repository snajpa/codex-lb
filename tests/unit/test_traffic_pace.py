"""Rounded quota is not the selected window's traffic measurement."""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta

import pytest

from app.core.utils.time import naive_utc_to_epoch
from app.db.models import Account, AccountStatus, UsageHistory
from app.modules.accounts.schemas import AccountSummary
from app.modules.dashboard.traffic_pace import (
    PaceCalibration,
    PaceTrafficWork,
    TrafficWindowWork,
    build_pace_calibrations,
    traffic_burn_percent_per_hour,
)
from app.modules.dashboard.weekly_pace import PRO_WEEKLY_CAPACITY_CREDITS, build_weekly_credit_pace

NOW = datetime(2026, 10, 20, 1, 30)
RESET = int(naive_utc_to_epoch(NOW + timedelta(days=5)))


def rows() -> list[UsageHistory]:
    return [
        UsageHistory(
            account_id="a",
            window="primary",
            window_minutes=10080,
            used_percent=used,
            reset_at=RESET,
            recorded_at=NOW - timedelta(minutes=minutes),
        )
        for minutes, used in [(120, 10), (60, 15), (6, 20), (4, 20), (0.1, 20)]
    ]


def test_flat_five_minute_quota_uses_selected_traffic_not_longer_average():
    history = rows()
    calibration = build_pace_calibrations({"a": history}, eligible_accounts={"a"}, now=NOW)
    work = {"a": PaceTrafficWork(10, 0, {5: TrafficWindowWork(1, 465, 0), 15: TrafficWindowWork(3, 1400, 0)})}
    summary = AccountSummary(
        account_id="a",
        email="a@example.invalid",
        display_name="a",
        plan_type="pro",
        status="active",
        reset_at_secondary=NOW + timedelta(days=5),
        window_minutes_secondary=10080,
        capacity_credits_secondary=PRO_WEEKLY_CAPACITY_CREDITS,
        remaining_credits_secondary=PRO_WEEKLY_CAPACITY_CREDITS * 0.8,
    )

    def build(minutes):
        return build_weekly_credit_pace(
            accounts=[Account(id="a", status=AccountStatus.ACTIVE)],
            account_summaries=[summary],
            secondary_history={"a": history},
            now=NOW,
            usage_refresh_interval_seconds=60,
            burn_window_minutes=minutes,
            traffic_calibrations=calibration,
            traffic_work=work,
        )

    five, fifteen, sixty = build(5), build(15), build(60)
    assert five is not None and fifteen is not None and sixty is not None
    assert five.observed_quota_burn_rate_credits_per_hour == 0
    assert five.burn_rate_basis == "traffic_calibrated"
    assert five.burn_rate_recent_credits_per_hour == pytest.approx(PRO_WEEKLY_CAPACITY_CREDITS * 0.12)
    assert five.forecast_burn_rate_credits_per_hour == five.burn_rate_recent_credits_per_hour
    assert five.burn_observed_request_count == 465
    assert five.burn_calibration_minutes == pytest.approx(119.9)
    assert five.confidence == "medium"
    assert five.depletion_eta_hours is not None
    assert fifteen.burn_window_minutes == 15
    assert fifteen.burn_rate_recent_credits_per_hour == pytest.approx(PRO_WEEKLY_CAPACITY_CREDITS * 0.12)
    assert sixty.burn_rate_basis == "quota" and sixty.burn_calibration_minutes is None
    assert sixty.burn_rate_recent_credits_per_hour == sixty.observed_quota_burn_rate_credits_per_hour


@pytest.mark.parametrize(
    "problem", ["reset", "correction", "duration", "stale", "short", "invalid", "missing-reset", "expired"]
)
def test_calibration_never_bridges_invalid_or_inadequate_observations(problem):
    history = rows()
    if problem == "reset":
        history[-2].reset_at = RESET + 1000
        history[-1].reset_at = RESET + 1000
    elif problem == "correction":
        history[-2].used_percent = 1
        history[-1].used_percent = 2
    elif problem == "duration":
        history[-2].window_minutes = history[-1].window_minutes = 300
    elif problem == "stale":
        history = history[:-2]
    elif problem == "short":
        history = history[-2:]
    elif problem == "invalid":
        history[-1].used_percent = float("nan")
    elif problem == "missing-reset":
        history[-1].reset_at = None
    else:
        for row in history:
            row.reset_at = int(naive_utc_to_epoch(NOW - timedelta(seconds=1)))
    assert build_pace_calibrations({"a": history}, eligible_accounts={"a"}, now=NOW) == {}


def test_calibration_is_bounded_to_current_eligible_account():
    assert build_pace_calibrations({"a": rows()}, eligible_accounts={"other"}, now=NOW) == {}
    history = rows()
    history[0].recorded_at = NOW - timedelta(hours=4)
    calibrated = build_pace_calibrations({"a": history}, eligible_accounts={"a"}, now=NOW)
    assert calibrated["a"].used_percent == 5
    assert calibrated["a"].start == NOW - timedelta(hours=1)


@pytest.mark.parametrize(
    ("calibration_work", "calibration_unpriced", "recent_work", "recent_unpriced"),
    [(0, 0, 1, 0), (float("nan"), 0, 1, 0), (10, 1, 0, 1), (10, 0, 0, 1), (10, 0, -1, 0), (10, 0, float("inf"), 0)],
)
def test_incomplete_pricing_does_not_invent_quota(calibration_work, calibration_unpriced, recent_work, recent_unpriced):
    calibration = PaceCalibration("a", NOW - timedelta(hours=1), NOW, 10)
    work = PaceTrafficWork(
        calibration_work, calibration_unpriced, {5: TrafficWindowWork(recent_work, 10, recent_unpriced)}
    )
    assert traffic_burn_percent_per_hour(calibration, work, 5) is None
    assert traffic_burn_percent_per_hour(calibration, work, 60) is None


@pytest.mark.parametrize("literal", ["'0'::bigint", "(0::integer)", "false", "'false'::boolean", "((0))"])
def test_postgres_reflected_zero_default_is_literal_only(literal):
    migration = importlib.import_module("app.db.alembic.versions.20261019_020000_add_read_snapshots")
    assert migration._normalized_default(literal) == "0"


@pytest.mark.parametrize("expression", ["0+0", "'0'::text", "2::bigint", "coalesce(null,0)", "(SELECT 0)"])
def test_postgres_expression_not_accepted_as_literal(expression):
    migration = importlib.import_module("app.db.alembic.versions.20261019_020000_add_read_snapshots")
    assert migration._normalized_default(expression) != "0"


def test_positive_priced_subset_is_estimate_not_complete_work():
    c = PaceCalibration("a", NOW - timedelta(hours=1), NOW, 10)
    w = PaceTrafficWork(10, 2, {5: TrafficWindowWork(1, 20, 3)})
    assert traffic_burn_percent_per_hour(c, w, 5) == pytest.approx(12)


def test_omitted_work_never_gains_confidence_from_a_stale_fleet_member():
    history = rows()
    summary = AccountSummary(
        account_id="a",
        email="a@example.invalid",
        display_name="a",
        plan_type="pro",
        status="active",
        reset_at_secondary=NOW + timedelta(days=5),
        window_minutes_secondary=10080,
        capacity_credits_secondary=PRO_WEEKLY_CAPACITY_CREDITS,
        remaining_credits_secondary=PRO_WEEKLY_CAPACITY_CREDITS * 0.8,
    )
    stale = summary.model_copy(update={"account_id": "stale"})
    pace = build_weekly_credit_pace(
        accounts=[Account(id=name, status=AccountStatus.ACTIVE) for name in ("a", "stale")],
        account_summaries=[summary, stale],
        secondary_history={"a": history, "stale": history[:2]},
        now=NOW,
        usage_refresh_interval_seconds=60,
        burn_window_minutes=5,
        traffic_calibrations=build_pace_calibrations({"a": history}, eligible_accounts={"a"}, now=NOW),
        traffic_work={"a": PaceTrafficWork(10, 1, {5: TrafficWindowWork(1, 20, 1)})},
    )
    assert pace is not None and pace.burn_rate_basis == "traffic_calibrated"
    assert pace.stale_account_count == 1 and pace.burn_unpriced_request_count == 1
    assert pace.confidence == "low"
