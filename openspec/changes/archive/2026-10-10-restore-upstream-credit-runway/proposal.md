# Restore upstream credit runway and familiar dashboard

## Why
The dashboard added unnecessary full-width forecast sections instead of keeping the familiar upstream projection. A supplied 25x credit-scale calibration permits the normal Pro Max credit runway.

## What Changes
- Restore the existing dashboard layout and WeeklyCreditsPaceCard unchanged; retain omitted conversation statistic and full-height account list.
- Use the existing Pro Lite 5x credit scale for a 25x Pro Max estimate, five times its capacities.
- Permit calibrated Pro Max summaries through normal credit forecasts and known-coverage responses; keep missing-calibration safeguards.
- Preserve accounting API fields and recorded costs; optionally show one compact recent cost pace in the existing estimate stat.

## Impact
Affected capabilities: frontend-architecture, usage-refresh-policy. No new dependencies, migrations, config flags or billing writes. Existing account scope, model eligibility, admission caps and soft-affinity policy are unchanged.
