import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiSpendProjectionCard } from "@/features/dashboard/components/api-spend-projection-card";
import { QuotaPercentageRunwayCard } from "@/features/dashboard/components/quota-percentage-runway-card";
import type { AccountQuotaBurn, ApiSpendProjection } from "@/features/dashboard/schemas";
import { createAccountSummary } from "@/test/mocks/factories";

const now = Date.parse("2026-10-10T12:00:00Z");
afterEach(() => vi.restoreAllMocks());

const quota: AccountQuotaBurn = {
  accountId: "max-quota", window: "secondary", windowMinutes: 10080,
  remainingPercent: 80, ratePercentPerHour: 10, observationMinutes: 60,
  generatedAt: "2026-10-10T12:00:00Z", sampleAgeSeconds: 60,
  freshnessSeconds: 300, stale: false, resetAt: "2026-10-16T12:00:00Z",
  projectedExhaustionAt: "2026-10-10T20:00:00Z",
};
const spend: ApiSpendProjection = {
  lookbackMinutes: 60, observedMinutes: 60, requests: 10, requestsWithCost: 10,
  requestsWithUncachedComparison: 10, recordedCostUsd: 1,
  projected24hUsd: 24, projectedUncached24hUsd: 48, cachedInputPercent: 90,
  requestedPriorityDeliveredDefault: 5,
};

describe("accounting projection cards", () => {
  it("shows measured percentages for a Max account without claiming credits", () => {
    vi.spyOn(Date, "now").mockReturnValue(now);
    render(<QuotaPercentageRunwayCard accounts={[createAccountSummary({ accountId: "max-quota", planType: "promax", displayName: "Max Account" })]} estimates={[quota]} />);
    expect(screen.getByText("10.00% quota/h")).toBeInTheDocument();
    expect(screen.getByText(/80.0%/)).toBeInTheDocument();
    expect(screen.getByText(/Estimated exhaustion/)).toBeInTheDocument();
    expect(screen.getByText(/do not assume an absolute credit allowance/)).toBeInTheDocument();
  });

  it("does not show a retained rate once its observations are stale", () => {
    vi.spyOn(Date, "now").mockReturnValue(now + 600_000);
    render(<QuotaPercentageRunwayCard accounts={[]} estimates={[quota]} />);
    expect(screen.queryByText("10.00% quota/h")).not.toBeInTheDocument();
    expect(screen.getByText("Stale quota observations")).toBeInTheDocument();
  });

  it("keeps measured zero distinct from insufficient observations", () => {
    vi.spyOn(Date, "now").mockReturnValue(now);
    render(<QuotaPercentageRunwayCard accounts={[]} estimates={[
      { ...quota, accountId: "flat", ratePercentPerHour: 0, projectedExhaustionAt: null },
      { ...quota, accountId: "new", ratePercentPerHour: null, projectedExhaustionAt: null },
    ]} />);
    expect(screen.getByText("0.00% quota/h")).toBeInTheDocument();
    expect(screen.getByText("Collecting same-window observations")).toBeInTheDocument();
  });

  it("labels current measured and hypothetical uncached costs separately", () => {
    render(<ApiSpendProjectionCard projection={spend} />);
    expect(screen.getByTestId("api-spend-daily")).toHaveTextContent("$24.00 / 24h");
    expect(screen.getByTestId("api-spend-uncached")).toHaveTextContent("$48.00 / 24h");
    expect(screen.getByText(/Hypothetical uncached-input comparison/)).toBeInTheDocument();
    expect(screen.getByText(/Neither is a subscription bill/)).toBeInTheDocument();
    expect(screen.getByText(/5 requests asked for Priority/)).toBeInTheDocument();
  });

  it("marks partial recorded cost coverage as a subtotal", () => {
    render(<ApiSpendProjectionCard projection={{ ...spend, requests: 12 }} />);
    expect(screen.getByTestId("api-spend-daily")).toHaveTextContent("≥ $24.00 / 24h");
    expect(screen.getByText(/10 \/ 12 requests/)).toBeInTheDocument();
  });
});
