import { useTranslation } from "react-i18next";

import type { ApiSpendProjection } from "@/features/dashboard/schemas";
import { formatCurrency } from "@/utils/formatters";

export function ApiSpendProjectionCard({ projection }: { projection: ApiSpendProjection | null | undefined }) {
  const { t } = useTranslation();
  if (!projection) return null;
  return (
    <section className="rounded-xl border bg-card p-4" data-testid="api-spend-projection">
      <h3 className="text-sm font-semibold">{t("dashboard.apiSpend.title", { defaultValue: "Recent API-equivalent spend" })}</h3>
      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        <div>
          <p className="text-xs text-muted-foreground">{t("dashboard.apiSpend.measured", { defaultValue: "At the recent measured pace" })}</p>
          <p className="text-2xl font-semibold" data-testid="api-spend-daily">
            {projection.projected24hUsd == null
              ? t("dashboard.apiSpend.collecting", { defaultValue: "Collecting cost samples" })
              : `${projection.requestsWithCost < projection.requests ? "≥ " : ""}${formatCurrency(projection.projected24hUsd)} / 24h`}
          </p>
          <p className="text-xs text-muted-foreground">
            {t("dashboard.apiSpend.observation", {
              defaultValue: "Last {{minutes}} min · costs reported for {{known}} / {{requests}} requests",
              minutes: projection.observedMinutes.toFixed(0), known: projection.requestsWithCost, requests: projection.requests,
            })}
          </p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">{t("dashboard.apiSpend.uncached", { defaultValue: "Hypothetical uncached-input comparison" })}</p>
          <p className="text-lg font-semibold" data-testid="api-spend-uncached">
            {projection.projectedUncached24hUsd == null ? "—" : `${formatCurrency(projection.projectedUncached24hUsd)} / 24h`}
          </p>
          <p className="text-xs text-muted-foreground">
            {t("dashboard.apiSpend.cached", {
              defaultValue: "{{percent}}% of reported input was cached",
              percent: projection.cachedInputPercent == null ? "—" : projection.cachedInputPercent.toFixed(1),
            })}
          </p>
        </div>
      </div>
      <p className="mt-3 text-xs text-muted-foreground">{t("dashboard.apiSpend.assumptions", {
        defaultValue: "Assumes this recent pace continues. Known-cost subtotal uses reported cache discounts and delivered service tiers; the comparison assumes full-priced input. Neither is a subscription bill.",
      })}</p>
      {projection.requestedPriorityDeliveredDefault > 0 ? <p className="mt-1 text-xs text-muted-foreground">{t("dashboard.apiSpend.tier", {
        defaultValue: "{{count}} requests asked for Priority but reported Default delivery; recorded cost uses the delivered tier.",
        count: projection.requestedPriorityDeliveredDefault,
      })}</p> : null}
    </section>
  );
}
