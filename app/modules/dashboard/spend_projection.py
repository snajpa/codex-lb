from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from math import isfinite

from app.core.usage.pricing import ModelPrice, UsageTokens, calculate_cost_from_usage, get_pricing_for_model
from app.modules.dashboard.repository import SpendProjectionInput
from app.modules.dashboard.schemas import ApiSpendProjectionResponse

MIN_OBSERVED_MINUTES = 15.0


def build_spend_projection(
    rows: Sequence[SpendProjectionInput],
    *,
    since: datetime,
    now: datetime,
) -> ApiSpendProjectionResponse:
    minutes = max(0.0, (now - since).total_seconds() / 60.0)
    costs: list[float] = []
    uncached_costs: list[float] = []
    total_input = total_cached = 0
    downgraded = 0
    prices: dict[str, ModelPrice | None] = {}
    for row in rows:
        if row.requested_service_tier in ("priority", "fast") and row.actual_service_tier == "default":
            downgraded += 1
        if row.cost_usd is not None and isfinite(row.cost_usd) and row.cost_usd >= 0:
            costs.append(row.cost_usd)
        if row.input_tokens is not None and row.input_tokens >= 0:
            total_input += row.input_tokens
            total_cached += max(0, min(row.cached_input_tokens or 0, row.input_tokens))
        output = row.output_tokens if row.output_tokens is not None else row.reasoning_tokens
        if row.input_tokens is None or output is None or row.cost_usd is None or row.model_source_kind is not None:
            continue
        if row.model not in prices:
            resolved = get_pricing_for_model(row.model)
            prices[row.model] = resolved[1] if resolved is not None else None
        price = prices[row.model]
        if price is None:
            continue
        comparison = calculate_cost_from_usage(
            UsageTokens(input_tokens=row.input_tokens, output_tokens=output, cached_input_tokens=0),
            price,
            service_tier=row.service_tier,
        )
        if comparison is not None:
            uncached_costs.append(comparison)
    measured = minutes >= MIN_OBSERVED_MINUTES
    recorded = sum(costs) if costs else (0.0 if not rows else None)
    projected = recorded * 1440.0 / minutes if measured and recorded is not None else None
    comparison = (
        sum(uncached_costs) * 1440.0 / minutes if measured and costs and len(uncached_costs) == len(costs) else None
    )
    return ApiSpendProjectionResponse(
        observed_minutes=minutes,
        requests=len(rows),
        requests_with_cost=len(costs),
        requests_with_uncached_comparison=len(uncached_costs),
        recorded_cost_usd=recorded,
        projected_24h_usd=projected,
        projected_uncached_24h_usd=comparison,
        cached_input_percent=(total_cached * 100.0 / total_input if total_input > 0 else None),
        requested_priority_delivered_default=downgraded,
    )
