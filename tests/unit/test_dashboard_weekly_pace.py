from __future__ import annotations

from datetime import datetime, timedelta
from typing import cast

import pytest
from sqlalchemy import Table

from app.core.utils.time import naive_utc_to_epoch
from app.db.models import Account, AccountStatus, ApiKey, RequestLog, UsageHistory
from app.db.session import SessionLocal
from app.modules.accounts.schemas import AccountSummary
from app.modules.dashboard.repository import DashboardRepository
from app.modules.dashboard.schemas import WeeklyPaceWindowMinutes
from app.modules.dashboard.weekly_pace import PRO_WEEKLY_CAPACITY_CREDITS, build_weekly_credit_pace

NOW = datetime(2026, 8, 17, 12, 0, 0)


def _account(account_id: str) -> Account:
    return Account(id=account_id, status=AccountStatus.ACTIVE)


def _summary(
    account_id: str,
    *,
    used_percent: float,
    reset_in_hours: float,
    capacity: float = PRO_WEEKLY_CAPACITY_CREDITS,
) -> AccountSummary:
    return AccountSummary(
        account_id=account_id,
        email=f"{account_id}@example.com",
        display_name=account_id,
        plan_type="pro",
        status="active",
        reset_at_secondary=NOW + timedelta(hours=reset_in_hours),
        window_minutes_secondary=10_080,
        capacity_credits_secondary=capacity,
        remaining_credits_secondary=capacity * (1.0 - used_percent / 100.0),
    )


def _row(account_id: str, used_percent: float, recorded_at: datetime) -> UsageHistory:
    return UsageHistory(
        account_id=account_id,
        used_percent=used_percent,
        recorded_at=recorded_at,
        window="secondary",
        reset_at=int(naive_utc_to_epoch(NOW + timedelta(days=1))),
        window_minutes=10_080,
    )


def _three_hour_history(account_id: str, *, final_used_percent: float, hourly_delta: float) -> list[UsageHistory]:
    values = [
        final_used_percent - 3 * hourly_delta,
        final_used_percent - 2 * hourly_delta,
        final_used_percent - 2 * hourly_delta,
        final_used_percent - hourly_delta,
        final_used_percent - hourly_delta,
        final_used_percent,
    ]
    offsets = [170, 130, 110, 70, 50, 1]
    return [_row(account_id, value, NOW - timedelta(minutes=offset)) for value, offset in zip(values, offsets)]


def _build(
    summaries: list[AccountSummary],
    histories: dict[str, list[UsageHistory]],
    *,
    trailing_demand_used_percent_by_account: dict[str, float] | None = None,
    burn_window_minutes: WeeklyPaceWindowMinutes | None = None,
):
    window_argument = {} if burn_window_minutes is None else {"burn_window_minutes": burn_window_minutes}
    pace = build_weekly_credit_pace(
        accounts=[_account(summary.account_id) for summary in summaries],
        account_summaries=summaries,
        secondary_history=histories,
        now=NOW,
        usage_refresh_interval_seconds=60,
        trailing_demand_used_percent_by_account=trailing_demand_used_percent_by_account,
        **window_argument,
    )
    assert pace is not None
    return pace


@pytest.mark.parametrize(
    ("used_percent", "reset_in_hours", "hourly_delta", "runway_status", "legacy_status"),
    [
        (90.0, 5.0, 10.0, "runs_dry", "danger"),
        (80.0, 1.0, 0.55, "tight", "ahead"),
        (20.0, 1.0, 0.1, "safe", "on_track"),
    ],
)
def test_weekly_pace_verdict_branches_and_legacy_status_mapping(
    used_percent: float,
    reset_in_hours: float,
    hourly_delta: float,
    runway_status: str,
    legacy_status: str,
) -> None:
    account_id = f"acc-{runway_status}"
    pace = _build(
        [_summary(account_id, used_percent=used_percent, reset_in_hours=reset_in_hours)],
        {account_id: _three_hour_history(account_id, final_used_percent=used_percent, hourly_delta=hourly_delta)},
    )

    assert pace.runway_status == runway_status
    assert pace.status == legacy_status
    assert pace.burn_rate_recent_credits_per_hour is not None
    assert pace.depletion_eta_hours is not None


def test_weekly_pace_accepts_calibrated_promax_credit_summary():
    summary = _summary("max-calibrated", used_percent=20.0, reset_in_hours=24, capacity=189000.0)
    summary.plan_type = "promax"
    pace = _build(
        [summary],
        {summary.account_id: _three_hour_history(summary.account_id, final_used_percent=20.0, hourly_delta=5.0)},
    )
    assert pace.total_actual_remaining_credits == pytest.approx(151200.0)
    assert pace.burn_rate_recent_credits_per_hour > 0
    assert pace.depletion_eta_hours is not None


@pytest.mark.parametrize("missing_reset", [False, True])
@pytest.mark.parametrize("window_minutes", [10080, None, 0])
def test_weekly_pace_omits_fleet_forecast_with_fresh_max_weekly_usage(
    missing_reset: bool,
    window_minutes: int | None,
) -> None:
    known = _summary("pro", used_percent=40.0, reset_in_hours=24.0)
    unknown = _summary("max", used_percent=20.0, reset_in_hours=24.0, capacity=0.0)
    unknown.plan_type = "promax"
    unknown.window_minutes_secondary = window_minutes
    unknown_row = _row("max", 20.0, NOW - timedelta(minutes=1))
    unknown_row.window_minutes = window_minutes
    if missing_reset:
        unknown.reset_at_secondary = None

    result = build_weekly_credit_pace(
        accounts=[_account("pro"), _account("max")],
        account_summaries=[known, unknown],
        secondary_history={
            "pro": [_row("pro", 40.0, NOW - timedelta(minutes=1))],
            "max": [unknown_row],
        },
        now=NOW,
        usage_refresh_interval_seconds=60,
    )

    assert result is None


def test_weekly_pace_relief_clusters_resets_within_one_hour() -> None:
    summaries = [
        _summary("acc-first", used_percent=96.0, reset_in_hours=2.0),
        _summary("acc-clustered", used_percent=97.0, reset_in_hours=2.5),
        _summary("acc-later", used_percent=98.0, reset_in_hours=5.0),
    ]
    histories = {
        summary.account_id: [_row(summary.account_id, used, NOW - timedelta(minutes=1))]
        for summary, used in zip(summaries, (96.0, 97.0, 98.0))
    }

    pace = _build(summaries, histories)

    assert pace.next_relief_in_hours == pytest.approx(2.0)
    assert pace.next_relief_credits == pytest.approx(PRO_WEEKLY_CAPACITY_CREDITS * 1.93)
    assert len(pace.reset_events) == 3


def test_weekly_pace_relief_falls_back_to_all_accounts_below_cohort_threshold() -> None:
    summaries = [
        _summary("acc-low-a", used_percent=40.0, reset_in_hours=3.0),
        _summary("acc-low-b", used_percent=20.0, reset_in_hours=6.0),
    ]
    histories = {
        summary.account_id: [_row(summary.account_id, used, NOW - timedelta(minutes=1))]
        for summary, used in zip(summaries, (40.0, 20.0))
    }

    pace = _build(summaries, histories)

    assert pace.next_relief_in_hours == pytest.approx(3.0)
    assert pace.next_relief_credits == pytest.approx(PRO_WEEKLY_CAPACITY_CREDITS * 0.4)


def test_weekly_pace_recent_burn_counts_delta_across_hour_boundary() -> None:
    account_id = "acc-cross-hour"
    pace = _build(
        [_summary(account_id, used_percent=80.0, reset_in_hours=2.0)],
        {
            account_id: [
                _row(account_id, 70.0, NOW - timedelta(minutes=61)),
                _row(account_id, 80.0, NOW - timedelta(minutes=59)),
                _row(account_id, 80.0, NOW - timedelta(minutes=1)),
            ]
        },
    )

    assert pace.burn_rate_recent_credits_per_hour == pytest.approx(5_040.0)


def test_weekly_pace_recent_burn_uses_floored_observed_span() -> None:
    account_id = "acc-short-span"
    pace = _build(
        [_summary(account_id, used_percent=80.0, reset_in_hours=2.0)],
        {
            account_id: [
                _row(account_id, 70.0, NOW - timedelta(minutes=6)),
                _row(account_id, 80.0, NOW - timedelta(minutes=1)),
            ]
        },
    )

    assert pace.burn_rate_recent_credits_per_hour == pytest.approx(10_080.0)


def test_weekly_pace_recent_burn_skips_reset_delta() -> None:
    account_id = "acc-reset"
    pace = _build(
        [_summary(account_id, used_percent=10.0, reset_in_hours=2.0)],
        {
            account_id: [
                _row(account_id, 80.0, NOW - timedelta(minutes=6)),
                _row(account_id, 10.0, NOW - timedelta(minutes=1)),
            ]
        },
    )

    assert pace.burn_rate_recent_credits_per_hour is None


def test_weekly_pace_recent_burn_ignores_single_sample_accounts() -> None:
    summaries = [
        _summary("acc-single-a", used_percent=70.0, reset_in_hours=2.0),
        _summary("acc-single-b", used_percent=80.0, reset_in_hours=3.0),
    ]
    pace = _build(
        summaries,
        {
            summary.account_id: [_row(summary.account_id, used, NOW - timedelta(minutes=1))]
            for summary, used in zip(summaries, (70.0, 80.0))
        },
    )

    assert pace.burn_rate_recent_credits_per_hour is None


def test_weekly_pace_near_reset_is_relief_not_runs_dry() -> None:
    summary = _summary("acc-near-reset", used_percent=99.0, reset_in_hours=1.68)
    pace = _build(
        [summary],
        {
            summary.account_id: _three_hour_history(
                summary.account_id,
                final_used_percent=99.0,
                hourly_delta=0.0,
            )
        },
    )

    assert pace.next_relief_in_hours == pytest.approx(1.68)
    assert pace.next_relief_credits == pytest.approx(PRO_WEEKLY_CAPACITY_CREDITS * 0.99)
    assert pace.depletion_eta_hours is None
    assert pace.runway_status == "tight"
    assert pace.status == "ahead"


def test_weekly_pace_counts_saturated_accounts() -> None:
    summaries = [
        _summary("acc-saturated", used_percent=99.5, reset_in_hours=2.0),
        _summary("acc-not-saturated", used_percent=99.49, reset_in_hours=2.0),
    ]
    histories = {
        summary.account_id: [_row(summary.account_id, used, NOW - timedelta(minutes=1))]
        for summary, used in zip(summaries, (99.5, 99.49))
    }

    pace = _build(summaries, histories)

    assert pace.saturated_account_count == 1


def _multi_window_history(account_id: str, final_used_percent: float) -> list[UsageHistory]:
    points = [
        (timedelta(days=6, hours=20), 0.0),
        (timedelta(days=6), 90.0),
        (timedelta(days=5), 1.0),
        (timedelta(days=4), 91.0),
        (timedelta(days=3), 2.0),
        (timedelta(days=2), 92.0),
        (timedelta(minutes=1), final_used_percent),
    ]
    return [_row(account_id, used, NOW - age) for age, used in points]


def test_weekly_pace_add_pro_accounts_is_gated_on_for_saturation() -> None:
    account_id = "acc-demand-saturated"
    pace = _build(
        [_summary(account_id, used_percent=99.5, reset_in_hours=2.0)],
        {account_id: _multi_window_history(account_id, 99.5)},
        trailing_demand_used_percent_by_account={account_id: 277.5},
    )

    assert pace.saturated_account_count == 1
    assert pace.add_pro_accounts == 2


def test_weekly_pace_add_pro_accounts_uses_fleet_capacity_on_mixed_fleets() -> None:
    pro_id = "acc-mixed-pro"
    plus_id = "acc-mixed-plus"
    summaries = [
        _summary(pro_id, used_percent=99.5, reset_in_hours=2.0),
        _summary(plus_id, used_percent=99.5, reset_in_hours=2.0, capacity=7_560.0),
    ]
    histories = {
        summary.account_id: [_row(summary.account_id, 99.5, NOW - timedelta(minutes=1))] for summary in summaries
    }

    pace = _build(
        summaries,
        histories,
        trailing_demand_used_percent_by_account={pro_id: 110.0, plus_id: 300.0},
    )

    # Demand is 78,120 credits (1.55 Pro-weeks) against 57,960 credits of fleet
    # capacity (1.15 Pro-weeks). A seat-count basis would treat the Plus account
    # as a full Pro seat (1.55 - 2 < 0) and suppress the recommendation; the
    # capacity basis recommends one extra Pro account.
    assert pace.saturated_account_count == 2
    assert pace.add_pro_accounts == 1


def test_weekly_pace_add_pro_accounts_is_gated_off_without_distress() -> None:
    account_id = "acc-demand-safe"
    pace = _build(
        [_summary(account_id, used_percent=20.0, reset_in_hours=1.0)],
        {account_id: _multi_window_history(account_id, 20.0)},
    )

    assert pace.runway_status == "safe"
    assert pace.saturated_account_count == 0
    assert pace.add_pro_accounts is None


def test_weekly_pace_add_pro_accounts_is_none_without_demand_surplus() -> None:
    account_id = "acc-no-surplus"
    pace = _build(
        [_summary(account_id, used_percent=99.5, reset_in_hours=2.0)],
        {account_id: [_row(account_id, 99.5, NOW - timedelta(minutes=1))]},
        trailing_demand_used_percent_by_account={account_id: 100.0},
    )

    assert pace.saturated_account_count == 1
    assert pace.add_pro_accounts is None


def test_weekly_pace_add_pro_accounts_is_none_without_sql_demand_mapping() -> None:
    account_id = "acc-demand-without-mapping"
    pace = _build(
        [_summary(account_id, used_percent=99.5, reset_in_hours=2.0)],
        {account_id: _multi_window_history(account_id, 99.5)},
        trailing_demand_used_percent_by_account=None,
    )

    assert pace.saturated_account_count == 1
    assert pace.add_pro_accounts is None


@pytest.mark.asyncio
async def test_weekly_pace_attribution_merges_rankings_and_dedupes_unnamed_key(db_setup) -> None:
    del db_setup
    async with SessionLocal() as session:
        session.add(ApiKey(id="key-alpha", name="Alpha", key_hash="hash-alpha", key_prefix="alpha"))
        session.add_all(
            [
                RequestLog(
                    api_key_id="key-alpha",
                    request_id=f"alpha-{index}",
                    requested_at=NOW - timedelta(minutes=index + 1),
                    model="gpt-alpha" if index < 3 else "gpt-other",
                    status="success",
                    input_tokens=10,
                    output_tokens=5,
                    reasoning_tokens=2,
                    cached_input_tokens=3,
                )
                for index in range(4)
            ]
        )
        session.add_all(
            [
                RequestLog(
                    api_key_id="missing-key",
                    request_id=f"unnamed-{index}",
                    requested_at=NOW - timedelta(minutes=10 + index),
                    model="gpt-unnamed",
                    status="success",
                    input_tokens=20,
                    output_tokens=1,
                    reasoning_tokens=0,
                    cached_input_tokens=4,
                )
                for index in range(3)
            ]
        )
        session.add(
            RequestLog(
                api_key_id="key-token-heavy",
                request_id="token-heavy",
                requested_at=NOW - timedelta(minutes=20),
                model="gpt-heavy",
                status="success",
                input_tokens=1_000,
                output_tokens=500,
                reasoning_tokens=250,
                cached_input_tokens=100,
            )
        )
        session.add(
            RequestLog(
                api_key_id="key-alpha",
                request_id="deleted-alpha",
                requested_at=NOW - timedelta(minutes=1),
                deleted_at=NOW,
                model="gpt-deleted",
                status="success",
                input_tokens=50_000,
            )
        )
        session.add(
            RequestLog(
                api_key_id="key-alpha",
                request_id="future-alpha",
                requested_at=NOW + timedelta(minutes=1),
                model="gpt-future",
                status="success",
                input_tokens=50_000,
            )
        )
        session.add_all(
            [
                RequestLog(
                    api_key_id="key-warmup-only",
                    request_id=f"warmup-{kind}",
                    requested_at=NOW - timedelta(minutes=5),
                    request_kind=kind,
                    model="gpt-warmup",
                    status="success",
                    input_tokens=900_000,
                    output_tokens=900_000,
                )
                for kind in ("warmup", "limit_warmup")
            ]
        )
        await session.commit()

        rows = await DashboardRepository(session).top_api_key_attribution_since(
            NOW - timedelta(hours=2),
            now=NOW,
        )

    assert [row.name for row in rows] == ["Alpha", "(unnamed)", "(unnamed)"]
    assert [row.api_key_id for row in rows] == ["key-alpha", "missing-key", "key-token-heavy"]
    # Warmup probes are internal traffic and never rank, even with dominant volume.
    assert all(row.api_key_id != "key-warmup-only" for row in rows)
    assert sum(row.name == "Alpha" for row in rows) == 1
    alpha = rows[0]
    assert alpha.requests == 4
    assert alpha.billable_tokens == 60
    assert alpha.cached_tokens == 12
    assert alpha.dominant_model == "gpt-alpha"
    assert any(row.billable_tokens == 1_500 for row in rows)
    request_logs_table = cast(Table, RequestLog.__table__)
    assert "idx_logs_dash_usage_covering" in {index.name for index in request_logs_table.indexes}


def _assert_close(actual: object, expected: object, path: str = "") -> None:
    if isinstance(expected, dict):
        assert isinstance(actual, dict), path
        assert actual.keys() == expected.keys(), path
        for key in expected:
            _assert_close(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), path
        for index, (left, right) in enumerate(zip(actual, expected)):
            _assert_close(left, right, f"{path}[{index}]")
    elif isinstance(expected, float) and not isinstance(expected, bool):
        assert actual == pytest.approx(expected, rel=1e-12, abs=1e-12), path
    else:
        assert actual == expected, path


def test_weekly_pace_is_unchanged_by_ewma_tail_cap_under_fleet_burn_floor() -> None:
    """The projections fetch returns every row inside the 3h fleet-burn floor
    plus only the newest 64 older rows. The equal-weight consumers (fleet
    burn, smoothing mean, latest) read nothing older than the floor, so they
    are exact; the 6h recent-burn EWMA sees a 64-row tail instead of the full
    3h..6h stretch and must agree to floating-point noise (the per-minute
    cadence here gives the tail one EWMA update per row)."""
    from app.modules.dashboard.service import _PROJECTION_EWMA_TAIL_ROWS
    from app.modules.dashboard.weekly_pace import FLEET_BURN_WINDOW

    account_id = "acc-dense"
    # One row per minute for 7 days (denser than the cap inside 3h..6h).
    rows: list[UsageHistory] = []
    used = 2.0
    for index in range(7 * 24 * 60, 0, -1):
        used += 0.0045 + 0.002 * ((index * 7919) % 11) / 11.0
        rows.append(_row(account_id, round(used, 6), NOW - timedelta(minutes=index)))
    floor = NOW - FLEET_BURN_WINDOW
    older = [row for row in rows if row.recorded_at < floor]
    tail_bounded = older[-_PROJECTION_EWMA_TAIL_ROWS:] + [row for row in rows if row.recorded_at >= floor]
    assert len(tail_bounded) < len(rows)

    summaries = [_summary(account_id, used_percent=round(used, 6), reset_in_hours=30.0)]
    full_pace = _build(summaries, {account_id: rows})
    tail_pace = _build(summaries, {account_id: tail_bounded})

    assert full_pace.burn_rate_recent_credits_per_hour is not None
    assert full_pace.burn_rate_recent_credits_per_hour > 0
    _assert_close(tail_pace.model_dump(), full_pace.model_dump())


@pytest.mark.parametrize(("minutes", "expected_rate"), [(5, 6048), (15, 4032), (60, 1512), (180, 672)])
def test_selected_window_drives_displayed_burn_and_forecast(
    minutes: WeeklyPaceWindowMinutes, expected_rate: float
) -> None:
    account_id = "selected-window"
    rows = [
        _row(account_id, used, NOW - timedelta(minutes=offset))
        for offset, used in [(180, 10), (60, 11), (15, 12), (5, 13), (0, 14)]
    ]
    pace = _build(
        [_summary(account_id, used_percent=14, reset_in_hours=145)], {account_id: rows}, burn_window_minutes=minutes
    )
    assert pace.burn_window_minutes == minutes
    assert pace.burn_rate_recent_credits_per_hour == pytest.approx(expected_rate)
    assert pace.forecast_burn_rate_credits_per_hour == pytest.approx(expected_rate)
    assert pace.depletion_eta_hours == pytest.approx(pace.headroom_credits / expected_rate)
    assert pace.pace_multiplier == pytest.approx(expected_rate / pace.scheduled_burn_rate_credits_per_hour)


def test_repeated_unchanged_snapshots_do_not_decay_forecast() -> None:
    account_id = "sample-cadence"
    summary = _summary(account_id, used_percent=14, reset_in_hours=145)
    baseline = [
        _row(account_id, 10, NOW - timedelta(hours=3)),
        _row(account_id, 14, NOW - timedelta(minutes=10)),
        _row(account_id, 14, NOW),
    ]
    dense = baseline[:2] + [_row(account_id, 14, NOW - timedelta(seconds=seconds)) for seconds in range(599, -1, -1)]
    sparse_pace = _build([summary], {account_id: baseline})
    dense_pace = _build([summary], {account_id: dense})
    assert dense_pace.forecast_burn_rate_credits_per_hour == pytest.approx(672)
    assert dense_pace.forecast_burn_rate_credits_per_hour == pytest.approx(
        sparse_pace.forecast_burn_rate_credits_per_hour
    )
    assert dense_pace.forecast_burn_rate_credits_per_hour == dense_pace.burn_rate_recent_credits_per_hour


def test_five_minute_clips_boundary_interval_without_thirty_minute_dilution() -> None:
    account_id = "boundary-window"
    rows = [_row(account_id, 10, NOW - timedelta(minutes=10)), _row(account_id, 12, NOW)]
    pace = _build(
        [_summary(account_id, used_percent=12, reset_in_hours=145)], {account_id: rows}, burn_window_minutes=5
    )
    assert pace.burn_rate_recent_credits_per_hour == pytest.approx(6048)


def test_incomplete_pool_observations_do_not_report_partial_fleet_burn() -> None:
    summaries = [_summary(name, used_percent=14, reset_in_hours=145) for name in ("covered", "missing")]
    histories = {
        "covered": [_row("covered", 10, NOW - timedelta(minutes=1)), _row("covered", 14, NOW)],
        "missing": [_row("missing", 14, NOW)],
    }
    pace = _build(summaries, histories, burn_window_minutes=5)
    assert pace.burn_rate_recent_credits_per_hour is None
    assert pace.forecast_burn_rate_credits_per_hour is None
    assert pace.depletion_eta_hours is None
    assert pace.throttle_to_percent is None


@pytest.mark.parametrize("change", ["decrease", "reset", "duration"])
def test_quota_discontinuities_do_not_create_burn(change: str) -> None:
    account_id = "discontinuity"
    previous = _row(account_id, 10, NOW - timedelta(minutes=1))
    current = _row(account_id, 12, NOW)
    if change == "decrease":
        current.used_percent = 1
    elif change == "reset":
        current.reset_at = cast(int, previous.reset_at) + 604800
    else:
        current.window_minutes = 300
    pace = _build(
        [_summary(account_id, used_percent=current.used_percent, reset_in_hours=145)],
        {account_id: [previous, current]},
        burn_window_minutes=5,
    )
    assert pace.burn_rate_recent_credits_per_hour is None
    assert pace.forecast_burn_rate_credits_per_hour is None


def test_reset_countdown_jitter_does_not_hide_real_burn() -> None:
    account_id = "countdown-jitter"
    previous = _row(account_id, 10, NOW - timedelta(minutes=1))
    current = _row(account_id, 11, NOW)
    current.reset_at = cast(int, previous.reset_at) + 1
    pace = _build(
        [_summary(account_id, used_percent=11, reset_in_hours=145)],
        {account_id: [previous, current]},
        burn_window_minutes=5,
    )
    assert pace.burn_rate_recent_credits_per_hour == pytest.approx(6048)


@pytest.mark.parametrize("change", ["decrease", "reset", "duration"])
def test_discontinuous_account_prevents_partial_fleet_forecast(change: str) -> None:
    summaries = [_summary(name, used_percent=14, reset_in_hours=145) for name in ("covered", "discontinuous")]
    previous = _row("discontinuous", 12, NOW - timedelta(minutes=1))
    current = _row("discontinuous", 14, NOW)
    if change == "decrease":
        previous.used_percent = 90
    elif change == "reset":
        current.reset_at = cast(int, previous.reset_at) + 604800
    else:
        current.window_minutes = 300
    pace = _build(
        summaries,
        {
            "covered": [_row("covered", 10, NOW - timedelta(minutes=1)), _row("covered", 14, NOW)],
            "discontinuous": [previous, current],
        },
        burn_window_minutes=5,
    )
    assert pace.burn_rate_recent_credits_per_hour is None
    assert pace.forecast_burn_rate_credits_per_hour is None
    assert pace.depletion_eta_hours is None
    assert pace.throttle_to_percent is None


def test_stable_unchanged_interval_remains_measured_zero() -> None:
    account_id = "stable-no-change"
    pace = _build(
        [_summary(account_id, used_percent=14, reset_in_hours=145)],
        {
            account_id: [_row(account_id, 14, NOW - timedelta(minutes=1)), _row(account_id, 14, NOW)],
        },
        burn_window_minutes=5,
    )
    assert pace.burn_rate_recent_credits_per_hour == 0
    assert pace.forecast_burn_rate_credits_per_hour == 0
    assert pace.depletion_eta_hours is None


def test_throttle_respects_remaining_budget_before_reset() -> None:
    name = "limited-budget"
    pace = _build(
        [_summary(name, used_percent=90, reset_in_hours=100)],
        {name: [_row(name, 84, NOW - timedelta(hours=3)), _row(name, 90, NOW)]},
    )
    assert pace.burn_rate_recent_credits_per_hour == pytest.approx(1008)
    assert pace.projected_depletion_hours == pytest.approx(5)
    assert pace.runway_status == "runs_dry"
    assert pace.throttle_to_percent is not None
    # 5040 remaining / 100 hours = 50.4/h, rather than nominal 300/h.
    assert pace.throttle_to_percent == pytest.approx(5, abs=1e-7)
    advised_rate = 1008 * pace.throttle_to_percent / 100
    assert advised_rate <= 50.4
    assert advised_rate * 100 <= pace.headroom_credits


def test_earlier_noncohort_refill_prevents_false_exhaustion() -> None:
    summaries = [
        _summary("saturated-later", used_percent=99, reset_in_hours=100),
        _summary("available-earlier", used_percent=80, reset_in_hours=1),
    ]
    histories = {
        summary.account_id: [
            _row(summary.account_id, used - 1.5, NOW - timedelta(hours=3)),
            _row(summary.account_id, used, NOW),
        ]
        for summary, used in zip(summaries, [99, 80])
    }
    pace = _build(summaries, histories)
    assert pace.burn_rate_recent_credits_per_hour == pytest.approx(504)
    assert pace.depletion_eta_hours == pytest.approx(21)
    assert pace.next_relief_in_hours == pytest.approx(100)  # Informational saturated cohort.
    assert pace.projected_depletion_hours is None
    assert pace.projected_minimum_remaining_credits == pytest.approx(1008)
    assert pace.runway_status == "tight"
    assert pace.throttle_to_percent is None


def test_exhaustion_after_first_refill_is_not_safe() -> None:
    name = "later-exhaustion"
    # 500/h; first reset restores 50400 after one hour, then lasts 100.8h.
    pace = _build(
        [_summary(name, used_percent=50, reset_in_hours=1)],
        {name: [_row(name, 50 - 1500 / 504, NOW - timedelta(hours=3)), _row(name, 50, NOW)]},
    )
    assert pace.burn_rate_recent_credits_per_hour == pytest.approx(500)
    assert pace.depletion_eta_hours == pytest.approx(50.4)
    assert pace.projected_depletion_hours == pytest.approx(101.8)
    assert pace.runway_status == "runs_dry"
    assert pace.throttle_to_percent is not None
    assert pace.throttle_to_percent == pytest.approx(60, abs=1e-7)


def test_discontinuity_gap_is_not_counted_as_zero_burn_time() -> None:
    name = "reset-gap"
    rows = [_row(name, 99, NOW - timedelta(hours=3)), _row(name, 1, NOW - timedelta(hours=1)), _row(name, 2, NOW)]
    rows[0].reset_at = int(naive_utc_to_epoch(NOW - timedelta(hours=2)))
    for row in rows[1:]:
        row.reset_at = int(naive_utc_to_epoch(NOW + timedelta(hours=166)))
    pace = _build([_summary(name, used_percent=2, reset_in_hours=166, capacity=189000)], {name: rows})
    assert pace.burn_rate_recent_credits_per_hour == pytest.approx(1890)
    assert pace.depletion_eta_hours == pytest.approx(98)
    assert pace.runway_status == "runs_dry"


def test_pre_reset_zero_does_not_measure_new_cycle_burn() -> None:
    name = "new-cycle-singleton"
    rows = [_row(name, 99, NOW - timedelta(hours=3)), _row(name, 99, NOW - timedelta(minutes=150)), _row(name, 10, NOW)]
    rows[-1].reset_at = int(naive_utc_to_epoch(NOW + timedelta(hours=166)))
    pace = _build([_summary(name, used_percent=10, reset_in_hours=166)], {name: rows})
    assert pace.burn_rate_recent_credits_per_hour is None
    assert pace.forecast_burn_rate_credits_per_hour is None
    assert pace.throttle_to_percent is None


@pytest.mark.parametrize("invalid", ["expired", "future"])
def test_unavailable_cycle_balance_never_becomes_partial_fleet_pace(invalid: str) -> None:
    summaries = [
        _summary("current", used_percent=50, reset_in_hours=100),
        _summary("invalid", used_percent=100, reset_in_hours=100),
    ]
    histories = {
        "current": [_row("current", 44, NOW - timedelta(hours=3)), _row("current", 50, NOW)],
        "invalid": [_row("invalid", 94, NOW - timedelta(hours=3)), _row("invalid", 100, NOW - timedelta(minutes=1))],
    }
    if invalid == "expired":
        summaries[1].reset_at_secondary = NOW - timedelta(seconds=30)
        histories["invalid"][-1].reset_at = int(naive_utc_to_epoch(NOW - timedelta(seconds=30)))
    else:
        histories["invalid"][-1].recorded_at = NOW + timedelta(seconds=60)
    pace = build_weekly_credit_pace(
        accounts=[_account(s.account_id) for s in summaries],
        account_summaries=summaries,
        secondary_history=histories,
        now=NOW,
        usage_refresh_interval_seconds=60,
    )
    assert pace is None
