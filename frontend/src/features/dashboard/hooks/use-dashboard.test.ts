import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { createElement, type PropsWithChildren } from "react";
import { describe, expect, it } from "vitest";

import { useDashboard, useDashboardProjections } from "@/features/dashboard/hooks/use-dashboard";
import { server } from "@/test/mocks/server";
import { createAccountSummary, createDashboardProjections } from "@/test/mocks/factories";
import type { WeeklyPaceWindowMinutes } from "@/features/dashboard/schemas";
import { useDashboardPreferencesStore } from "@/hooks/use-dashboard-preferences";
import { buildWeeklyCreditPace } from "@/features/dashboard/utils";

function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: PropsWithChildren) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

function eagerProjection() {
  const estimate = buildWeeklyCreditPace([createAccountSummary({
    resetAtSecondary: new Date(Date.now() + 3 * 86400000).toISOString(),
  })]);
  if (!estimate) throw new Error("Missing pace fixture");
  const pace = (minutes: WeeklyPaceWindowMinutes) => ({
    ...estimate, burnWindowMinutes: minutes, paceGapSmoothingMinutes: 30,
    burnRateRecentCreditsPerHour: minutes, forecastBurnRateCreditsPerHour: minutes,
  });
  return createDashboardProjections({ weeklyCreditPace: pace(180),
    weeklyCreditPaceWindows: { 5: pace(5), 15: pace(15), 60: pace(60), 180: pace(180) } });
}

describe("useDashboard", () => {
  it("loads dashboard overview via MSW and configures the selected refetch cadence", async () => {
    useDashboardPreferencesStore.setState({ refreshSeconds: 15 });
    const queryClient = createTestQueryClient();
    const { result } = renderHook(() => useDashboard("30d"), {
      wrapper: createWrapper(queryClient),
    });

    expect(result.current.isLoading || result.current.isPending).toBe(true);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.accounts.length).toBeGreaterThan(0);

    const query = queryClient.getQueryCache().find({ queryKey: ["dashboard", "overview", "30d"] });
    const refetchInterval = (query?.options as { refetchInterval?: unknown } | undefined)
      ?.refetchInterval;
    expect(typeof refetchInterval).toBe("function");
    expect((refetchInterval as (q: unknown) => number)(query)).toBe(15_000);
  });

  it("passes timeframe to the overview endpoint", async () => {
    let requestedTimeframe: string | null = null;
    server.use(
      http.get("/api/dashboard/overview", ({ request }) => {
        requestedTimeframe = new URL(request.url).searchParams.get("timeframe");
        return HttpResponse.json({
          lastSyncAt: "2026-01-01T00:00:00Z",
          timeframe: { key: "1d", windowMinutes: 1440, bucketSeconds: 3600, bucketCount: 24 },
          accounts: [],
          summary: {
            primaryWindow: {
              remainingPercent: 80,
              capacityCredits: 100,
              remainingCredits: 80,
              resetAt: "2026-01-01T00:00:00Z",
              windowMinutes: 300,
            },
            secondaryWindow: null,
            cost: { currency: "USD", totalUsd: 0 },
            metrics: null,
          },
          windows: {
            primary: { windowKey: "primary", windowMinutes: 300, accounts: [] },
            secondary: null,
          },
          trends: { requests: [], tokens: [], cost: [], errorRate: [] },
        });
      }),
    );

    const queryClient = createTestQueryClient();
    const { result } = renderHook(() => useDashboard("1d"), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(requestedTimeframe).toBe("1d");
  });

  it("applies the selected cadence to projection polling", () => {
    useDashboardPreferencesStore.setState({ refreshSeconds: 5 });
    const queryClient = createTestQueryClient();

    renderHook(() => useDashboardProjections(false), {
      wrapper: createWrapper(queryClient),
    });

    const query = queryClient.getQueryCache().find({ queryKey: ["dashboard", "projections", "all-windows"] });
    const refetchInterval = (query?.options as { refetchInterval?: unknown } | undefined)
      ?.refetchInterval;
    expect(typeof refetchInterval).toBe("function");
    expect((refetchInterval as (q: unknown) => number)(query)).toBe(5_000);
  });

  it("loads every window in one request before selection and switches from cache", async () => {
    const requested: string[] = [];
    server.use(http.get("/api/dashboard/projections", ({ request }) => {
      requested.push(request.url);
      return HttpResponse.json(eagerProjection());
    }));
    const queryClient = createTestQueryClient();
    const { result, rerender } = renderHook(
      ({ minutes }: { minutes: WeeklyPaceWindowMinutes }) => useDashboardProjections(true, minutes),
      { wrapper: createWrapper(queryClient), initialProps: { minutes: 180 as WeeklyPaceWindowMinutes } },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.weeklyCreditPaceWindows).toBeDefined();
    for (const minutes of [5, 15, 60, 180] as const) {
      rerender({ minutes });
      expect(result.current.data?.weeklyCreditPace?.burnRateRecentCreditsPerHour).toBe(minutes);
      expect(result.current.data?.weeklyCreditPace?.burnWindowMinutes).toBe(minutes);
      expect(result.current.isLoading).toBe(false);
      expect(result.current.isFetching).toBe(false);
    }
    expect(requested).toHaveLength(1);
    expect(new URL(requested[0]).searchParams.has("burnWindowMinutes")).toBe(false);
  });

  it("honors selection made while the shared background read is pending", async () => {
    let release!: () => void;
    const held = new Promise<void>(resolve => { release = resolve; });
    let requests = 0;
    server.use(http.get("/api/dashboard/projections", async () => {
      requests += 1;
      await held;
      return HttpResponse.json(eagerProjection());
    }));
    const queryClient = createTestQueryClient();
    const { result, rerender } = renderHook(
      ({ minutes }: { minutes: WeeklyPaceWindowMinutes }) => useDashboardProjections(true, minutes),
      { wrapper: createWrapper(queryClient), initialProps: { minutes: 180 as WeeklyPaceWindowMinutes } },
    );
    await waitFor(() => expect(requests).toBe(1));
    rerender({ minutes: 5 });
    rerender({ minutes: 60 });
    expect(result.current.isLoading).toBe(true);
    release();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.weeklyCreditPace?.burnWindowMinutes).toBe(60);
    expect(requests).toBe(1);
  });

  it("keeps correct cached values during a shared refresh error and recovers", async () => {
    let fail = false;
    server.use(http.get("/api/dashboard/projections", () => fail
      ? HttpResponse.json({ error: { code: "failed", message: "unavailable" } }, { status: 503 })
      : HttpResponse.json(eagerProjection())));
    const queryClient = createTestQueryClient();
    const { result, rerender } = renderHook(
      ({ minutes }: { minutes: WeeklyPaceWindowMinutes }) => useDashboardProjections(true, minutes),
      { wrapper: createWrapper(queryClient), initialProps: { minutes: 180 as WeeklyPaceWindowMinutes } },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    fail = true;
    await result.current.refetch();
    await waitFor(() => expect(result.current.isError).toBe(true));
    rerender({ minutes: 5 });
    expect(result.current.data?.weeklyCreditPace?.burnWindowMinutes).toBe(5);
    expect(result.current.isLoading).toBe(false);
    fail = false;
    await result.current.refetch();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.weeklyCreditPace?.burnRateRecentCreditsPerHour).toBe(5);
  });

  it("does not replace an explicitly unavailable window with the default value", async () => {
    const data = eagerProjection();
    data.weeklyCreditPaceWindows![5] = null;
    server.use(http.get("/api/dashboard/projections", () => HttpResponse.json(data)));
    const queryClient = createTestQueryClient();
    const { result } = renderHook(() => useDashboardProjections(true, 5), { wrapper: createWrapper(queryClient) });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.weeklyCreditPace).toBeNull();
  });

  it("exposes error state on request failure", async () => {
    server.use(
      http.get("/api/dashboard/overview", () =>
        HttpResponse.json(
          {
            error: {
              code: "overview_failed",
              message: "overview failed",
            },
          },
          { status: 500 },
        ),
      ),
    );

    const queryClient = createTestQueryClient();
    const { result } = renderHook(() => useDashboard("7d"), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

it("marks an old retained backend response as incompatible instead of missing quota samples", async () => {
  const legacy = { ...eagerProjection(), weeklyCreditPaceWindows: undefined };
  server.use(http.get("*/api/dashboard/projections", () => HttpResponse.json(legacy)));
  const client = createTestQueryClient();
  const { result, unmount } = renderHook(() => useDashboardProjections(true, 5), { wrapper: createWrapper(client) });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.windowCompatible).toBe(false);
  expect(result.current.data?.weeklyCreditPace).toBeNull();
  unmount();
  client.clear();
});
