from datetime import datetime, timedelta

import pytest

from app.core.usage.pricing import ModelPrice
from app.modules.dashboard.repository import SpendProjectionInput
from app.modules.dashboard.spend_projection import build_spend_projection

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 10, 12)


def entry(cost: float | None = 0.1, **kwargs) -> SpendProjectionInput:
    fields = dict(
        model="synthetic-spend",
        service_tier="default",
        requested_service_tier="priority",
        actual_service_tier="default",
        input_tokens=100_000,
        cached_input_tokens=90_000,
        output_tokens=1000,
        reasoning_tokens=500,
        cost_usd=cost,
        model_source_kind=None,
    )
    fields.update(kwargs)
    return SpendProjectionInput(**fields)


def test_projection_preserves_recorded_cost_and_prices_full_input_without_double_reasoning(monkeypatch):
    price = ModelPrice(input_per_1m=2, cached_input_per_1m=0.1, output_per_1m=10)
    monkeypatch.setattr("app.modules.dashboard.spend_projection.get_pricing_for_model", lambda model: (model, price))
    result = build_spend_projection([entry()], since=NOW - timedelta(hours=1), now=NOW)
    assert result.projected_24h_usd == pytest.approx(2.4)
    assert result.projected_uncached_24h_usd == pytest.approx(5.04)
    assert result.cached_input_percent == 90
    assert result.requested_priority_delivered_default == 1


def test_missing_cost_is_unknown_and_partial_coverage_is_explicit(monkeypatch):
    monkeypatch.setattr("app.modules.dashboard.spend_projection.get_pricing_for_model", lambda model: None)
    unknown = build_spend_projection([entry(None)], since=NOW - timedelta(hours=1), now=NOW)
    assert unknown.recorded_cost_usd is None
    assert unknown.projected_24h_usd is None
    result = build_spend_projection([entry(), entry(None)], since=NOW - timedelta(hours=1), now=NOW)
    assert result.requests == 2 and result.requests_with_cost == 1
    assert result.projected_24h_usd == pytest.approx(2.4)
    assert result.projected_uncached_24h_usd is None


def test_projection_uses_individual_context_bands_not_aggregate_tokens(monkeypatch):
    price = ModelPrice(
        input_per_1m=2,
        output_per_1m=10,
        long_context_threshold_tokens=272_000,
        long_context_input_per_1m=4,
        long_context_output_per_1m=15,
    )
    monkeypatch.setattr("app.modules.dashboard.spend_projection.get_pricing_for_model", lambda model: (model, price))
    result = build_spend_projection([entry(), entry(), entry()], since=NOW - timedelta(hours=1), now=NOW)
    assert result.projected_uncached_24h_usd == pytest.approx(15.12)


def test_short_collection_interval_does_not_extrapolate(monkeypatch):
    monkeypatch.setattr("app.modules.dashboard.spend_projection.get_pricing_for_model", lambda model: None)
    result = build_spend_projection([entry()], since=NOW - timedelta(minutes=5), now=NOW)
    assert result.observed_minutes == 5
    assert result.projected_24h_usd is None
