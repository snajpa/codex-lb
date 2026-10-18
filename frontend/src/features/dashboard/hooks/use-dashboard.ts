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
    refetchInterval: refreshSeconds * 1_000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  });
}

export function useDashboardProjections(enabled = true, burnWindowMinutes: WeeklyPaceWindowMinutes = 180) {
  const refreshSeconds = useDashboardPreferencesStore((state) => state.refreshSeconds);
  return useQuery({
    queryKey: ["dashboard", "projections", burnWindowMinutes],
    queryFn: () => getDashboardProjections(burnWindowMinutes),
    enabled,
    refetchInterval: refreshSeconds * 1_000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  });
}
