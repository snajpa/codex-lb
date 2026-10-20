import { useTranslation } from "react-i18next";
import type { ReadSnapshotMetadata } from "@/schemas/read-snapshot";

export function ReadSnapshotStatus({
  snapshot,
  warming = false,
}: {
  snapshot?: ReadSnapshotMetadata | null;
  warming?: boolean;
}) {
  const { t } = useTranslation();
  if (warming && !snapshot) {
    return <p role="status" className="text-xs text-muted-foreground">{t("readSnapshot.warming")}</p>;
  }
  if (!snapshot?.generatedAt) return null;
  const time = new Date(snapshot.generatedAt).toLocaleString();
  return (
    <p role="status" className="text-xs text-muted-foreground" data-testid="read-snapshot-status">
      {t("readSnapshot.prepared", { time, minutes: Math.ceil(snapshot.refreshIntervalSeconds / 60) })}
      {snapshot.stale || snapshot.lastError
        ? ` · ${t("readSnapshot.delayed")}`
        : snapshot.refreshing ? ` · ${t("readSnapshot.refreshing")}` : ""}
    </p>
  );
}
