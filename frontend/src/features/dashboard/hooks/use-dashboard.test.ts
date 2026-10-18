import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { createElement, type PropsWithChildren } from "react";
import { describe, expect, it } from "vitest";

import { useDashboard, useDashboardProjections } from "@/features/dashboard/hooks/use-dashboard";
import { server } from "@/test/mocks/server";
import { createDashboardProjections } from "@/test/mocks/factories";
import type { WeeklyPaceWindowMinutes } from "@/features/dashboard/schemas";
import { useDashboardPreferencesStore } from "@/hooks/use-dashboard-preferences";

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
    expect(refetchInterval).toBe(15_000);
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

    const query = queryClient.getQueryCache().find({ queryKey: ["dashboard", "projections", 180] });
    const refetchInterval = (query?.options as { refetchInterval?: unknown } | undefined)
      ?.refetchInterval;
    expect(refetchInterval).toBe(5_000);
  });

  it("keeps a late response in its own averaging-window cache", async () => {
    let releaseShort!: () => void;
    const shortResponse = new Promise<void>((resolve) => { releaseShort = resolve; });
    const requested: number[] = [];
    server.use(http.get("/api/dashboard/projections", async ({ request }) => {
      const minutes = Number(new URL(request.url).searchParams.get("burnWindowMinutes") ?? 180);
      requested.push(minutes);
      if (minutes === 1) await shortResponse;
      return HttpResponse.json({ ...createDashboardProjections(), quotaBurn: [],
        depletionPrimary: { risk: minutes, riskLevel: "safe", burnRate: minutes,
          safeUsagePercent: 50, projectedExhaustionAt: null, secondsUntilExhaustion: null } });
    }));
    const queryClient = createTestQueryClient();
    queryClient.setQueryDefaults(["dashboard", "projections"], { gcTime: Infinity });
    const { result, rerender } = renderHook(
      ({ minutes }: { minutes: WeeklyPaceWindowMinutes }) => useDashboardProjections(true, minutes),
      { wrapper: createWrapper(queryClient), initialProps: { minutes: 1 as WeeklyPaceWindowMinutes } },
    );
    await waitFor(() => expect(requested).toContain(1));
    rerender({ minutes: 15 });
    await waitFor(() => expect(result.current.data?.depletionPrimary?.burnRate).toBe(15));
    releaseShort();
    await waitFor(() => expect(queryClient.getQueryData(["dashboard", "projections", 1])).toBeDefined());
    expect(result.current.data?.depletionPrimary?.burnRate).toBe(15);
    expect(requested).toEqual([1, 15]);
  });

  it("does not retain another window's result when the selected request fails", async () => {
    server.use(http.get("/api/dashboard/projections", ({ request }) => {
      return new URL(request.url).searchParams.get("burnWindowMinutes") === "1"
        ? HttpResponse.json({ error: { code: "failed", message: "unavailable" } }, { status: 503 })
        : HttpResponse.json(createDashboardProjections());
    }));
    const queryClient = createTestQueryClient();
    const { result, rerender } = renderHook(
      ({ minutes }: { minutes: WeeklyPaceWindowMinutes }) => useDashboardProjections(true, minutes),
      { wrapper: createWrapper(queryClient), initialProps: { minutes: 180 as WeeklyPaceWindowMinutes } },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    rerender({ minutes: 1 });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined();
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
