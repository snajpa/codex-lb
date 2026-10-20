import { isSnapshotWarming } from "@/schemas/read-snapshot";
import { useQuery } from "@tanstack/react-query";

import { getDashboardOverview, getDashboardProjections } from "@/features/dashboard/api";
import {
  DEFAULT_OVERVIEW_TIMEFRAME,
  type OverviewTimeframe,
  type WeeklyPaceWindowMinutes,
} from "@/features/dashboard/schemas";
import { useDashboardPreferencesStore } from "@/hooks/use-dashboard-preferences";

export function useDashboard(timeframe: OverviewTimeframe = DEFAULT_OVERVIEW_TIMEFRAME) {
  const refreshSeconds = useDashboardPreferencesStore((state) => state.refreshSeconds);
  return useQuery({
    queryKey: ["dashboard", "overview", timeframe],
    queryFn: () => getDashboardOverview({ timeframe }),
    refetchInterval: (query) => isSnapshotWarming(query.state.error) ? 2_000 : refreshSeconds * 1_000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  });
}

export function useDashboardProjections(enabled = true, burnWindowMinutes: WeeklyPaceWindowMinutes = 180) {
  const refreshSeconds = useDashboardPreferencesStore((state) => state.refreshSeconds);
  return useQuery({
    queryKey: ["dashboard", "projections", "all-windows"],
    queryFn: () => getDashboardProjections(),
    select: (data) => ({
      ...data,
      windowCompatible: data.weeklyCreditPaceWindows
        ? Object.prototype.hasOwnProperty.call(data.weeklyCreditPaceWindows, burnWindowMinutes)
        : (data.weeklyCreditPace?.burnWindowMinutes ?? 180) === burnWindowMinutes,
      weeklyCreditPace: data.weeklyCreditPaceWindows
        ? data.weeklyCreditPaceWindows[burnWindowMinutes]
        : (data.weeklyCreditPace?.burnWindowMinutes ?? 180) === burnWindowMinutes
          ? data.weeklyCreditPace
          : null,
    }),
    enabled,
    refetchInterval: (query) => isSnapshotWarming(query.state.error) ? 2_000 : refreshSeconds * 1_000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  });
}
