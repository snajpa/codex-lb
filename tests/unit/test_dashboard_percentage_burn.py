from datetime import datetime, timedelta

import pytest

from app.core.utils.time import naive_utc_to_epoch
from app.db.models import AccountStatus, UsageHistory
from app.modules.dashboard.percentage_burn import build_percentage_burn
from tests.unit.test_load_balancer_concurrency import _make_account

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 10, 12)
RESET = int(naive_utc_to_epoch(NOW + timedelta(days=6)))


def row(minutes: int, used: float, reset: int = RESET) -> UsageHistory:
    return UsageHistory(
        account_id="percent-account",
        recorded_at=NOW - timedelta(minutes=minutes),
        window="primary",
        window_minutes=10080,
        used_percent=used,
        reset_at=reset,
    )


def estimate(rows: list[UsageHistory]):
    account = _make_account("percent-account")
    account.plan_type = "promax"
    result = build_percentage_burn([account], {}, {account.id: rows}, now=NOW, usage_refresh_interval_seconds=60)
    assert len(result) == 1
    return result[0]


def test_percentage_rate_and_eta_do_not_require_credit_capacity():
    result = estimate([row(121, 10), row(1, 20)])
    assert result.rate_percent_per_hour == pytest.approx(5)
    assert result.remaining_percent == 80
    assert result.projected_exhaustion_at == NOW + timedelta(hours=16)


def test_flat_measured_rate_is_zero_not_unknown():
    result = estimate([row(61, 20), row(1, 20)])
    assert result.rate_percent_per_hour == 0
    assert result.projected_exhaustion_at is None


def test_reset_requires_new_segment_observations():
    result = estimate([row(61, 90, RESET - 86400), row(1, 10)])
    assert result.rate_percent_per_hour is None


def test_decrease_without_reset_marker_retires_previous_segment():
    result = estimate([row(61, 90), row(2, 10), row(1, 11)])
    assert result.rate_percent_per_hour is None


def test_short_or_stale_observations_do_not_create_forecasts():
    assert estimate([row(2, 10), row(1, 20)]).rate_percent_per_hour is None
    stale = estimate([row(70, 10), row(10, 20)])
    assert stale.stale is True
    assert stale.rate_percent_per_hour is None


def test_expired_window_is_stale_and_inactive_accounts_are_excluded():
    reset = int(naive_utc_to_epoch(NOW - timedelta(seconds=1)))
    assert estimate([row(61, 10, reset), row(1, 20, reset)]).stale is True
    account = _make_account("percent-account")
    account.status = AccountStatus.PAUSED
    assert (
        build_percentage_burn(
            [account], {}, {account.id: [row(61, 10), row(1, 20)]}, now=NOW, usage_refresh_interval_seconds=60
        )
        == []
    )
