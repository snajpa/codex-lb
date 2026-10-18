import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type { AccountQuotaBurn, AccountSummary } from "@/features/dashboard/schemas";
import { usePrivacyStore } from "@/hooks/use-privacy";
import { cn } from "@/lib/utils";
import { formatDateTimeInline } from "@/utils/formatters";

export function QuotaPercentageRunwayCard({ accounts, estimates }: {
  accounts: AccountSummary[];
  estimates: AccountQuotaBurn[];
}) {
  const { t } = useTranslation();
  const blurred = usePrivacyStore((s) => s.blurred);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 15_000);
    return () => window.clearInterval(timer);
  }, []);
  const weekly = estimates.filter((row) => row.window === "secondary");
  if (weekly.length === 0) return null;
  return (
    <section className="rounded-xl border bg-card p-4" data-testid="quota-percentage-runway">
      <h3 className="text-sm font-semibold">{t("dashboard.quotaPercent.title", { defaultValue: "Quota burn and account runway" })}</h3>
      <p className="mt-1 text-xs text-muted-foreground">{t("dashboard.quotaPercent.units", {
        defaultValue: "Measured in percentage points of quota per hour, over up to three hours. These account-level estimates do not assume an absolute credit allowance.",
      })}</p>
      <div className="mt-3 divide-y">
        {weekly.map((row) => {
          const account = accounts.find((candidate) => candidate.accountId === row.accountId);
          const elapsed = Math.max(0, (now - Date.parse(row.generatedAt)) / 1000);
          const stale = row.stale || row.sampleAgeSeconds + elapsed > row.freshnessSeconds;
          const rate = stale ? null : row.ratePercentPerHour;
          const runway = stale
            ? t("dashboard.quotaPercent.stale", { defaultValue: "Stale quota observations" })
            : rate == null
              ? t("dashboard.quotaPercent.collecting", { defaultValue: "Collecting same-window observations" })
              : row.remainingPercent === 0
                ? t("dashboard.quotaPercent.exhausted", { defaultValue: "Quota exhausted" })
                : row.projectedExhaustionAt
                  ? t("dashboard.quotaPercent.exhausts", { defaultValue: "Estimated exhaustion: {{at}}", at: formatDateTimeInline(row.projectedExhaustionAt) })
                  : rate === 0
                    ? t("dashboard.quotaPercent.zero", { defaultValue: "No depletion at the measured rate" })
                    : row.resetAt
                      ? t("dashboard.quotaPercent.resetsFirst", { defaultValue: "Reset arrives before projected exhaustion" })
                      : t("dashboard.quotaPercent.unknownReset", { defaultValue: "Runway unknown without a reset deadline" });
          return <div key={row.accountId} className="grid gap-1 py-2 text-sm sm:grid-cols-[minmax(8rem,1fr)_8rem_9rem_minmax(12rem,2fr)]" data-testid="quota-percentage-row">
            <span className={cn("truncate", blurred && "select-none blur-sm")}>{account?.displayName || account?.email || row.accountId}</span>
            <span>{row.remainingPercent.toFixed(1)}% {t("dashboard.quotaPercent.remaining", { defaultValue: "remaining" })}</span>
            <span>{rate == null ? "—" : `${rate.toFixed(2)}% quota/h`}</span>
            <span className="text-xs text-muted-foreground">{runway}</span>
          </div>;
        })}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{t("dashboard.quotaPercent.caveat", {
        defaultValue: "Runway assumes the measured rate continues until the account's reset. Included-credit totals and whole-pool credit forecasts remain unknown where upstream does not disclose an allowance.",
      })}</p>
    </section>
  );
}
