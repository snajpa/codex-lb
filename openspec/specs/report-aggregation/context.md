Reports use permanent UTC-hour aggregates assembled into the requested timezone's days, plus the unfurled raw complement. The storage grain retains account, API key, model, User-Agent and normalized conversation dimensions so filtering and distinct counts remain valid after retention. The report fold and account lifecycle mirrors share the existing fold-state lock.

The report watermark starts at epoch and advances in paced six-hour slices, at most eight per existing 15-minute scheduler tick. Retention waits for every watermark, including reports. Backfill covers surviving raw data only; do not drop the aggregate once raw pruning has made it the only copy. Partial-hour timezone boundaries still require raw edge data, matching the existing hourly statistics limitation.

A 90-day report returns additive totals and exact conversation counts without raw speed median calculations. Up to seven days retains the existing exact speed query. The UI discloses omitted speed metrics and shows the server generation time. Reports now read durable background snapshots; expiry retains last-good values rather than making the next browser request rebuild the report.

For measured performance, regression evidence, screenshots and rollout constraints, see the [verified implementation record](../../changes/archive/2026-09-09-harden-reports-performance/context.md).

## Background preparation and scope

The standard 7/30/90-day presets, options and thread diagnostics are prepared
about every five minutes for UTC and known viewer timezones. Browser polls only
retrieve prepared values; cold preparation may poll more frequently without
starting aggregation. Uncommon normalized filters register bounded interest.
Last-good results stay tied to their original dates, filters, timezone and clock
through failures; unsupported historical timing remains explicitly unavailable.

Workers use a repeatable read-only SQL snapshot for the report bundle. Within
that guarantee, the earliest retained matching activity can bound empty SQL day
prefixes. Read-committed consumers keep the untrimmed path: an earlier backfill
could otherwise appear between the boundary query and the daily query. Exact
conversation/account distincts are computed over the requested scope, never by
adding daily distincts or averaging daily medians.

For example, a ninety-day result with only seventeen retained days still names
the requested ninety-day range and discloses the observed-history start; this
boundary is not proof of uninterrupted measurement. Core totals continue using
permanent hourly aggregates plus the disjoint raw tail. The seven-day diagnostic
bundle is still the expensive preset; this change does not reconstruct older
speed history or silently lift its guard.

A raw-data oracle must compare collector and raw SQL in the same fixed database
snapshot. Comparing a five-minute-old published total to a newer live counter
is invalid during traffic. HTTP qualification separately compares returned values
with their persisted generations. Normative contracts are in [`spec.md`](./spec.md).
