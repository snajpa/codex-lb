# Design

## Contracts and ownership
A completed snapshot is a value, not an expiring permission to compute on the
request task. Persist normalized keys, payload/version, generation/as-of time,
refresh scheduling and bounded interest metadata. Keep last-good payloads when
refresh fails. Publish atomically, never replace data with a partial generation,
and fence a cancelled or superseded producer. API reads may cheaply register a
previously unseen filter/timezone, but cannot execute the worker or use its SQL
session. Cold reads return an explicit retryable warming state.

Use independent scheduler-lease identity for this capability: an older replica
holding the existing metadata-leader lease must not prevent a new producer from
warming snapshots during a rolling upgrade. Reuse the existing database-clock,
heartbeat, cancellation and release machinery with the original lease remaining
the default. Separate latency-sensitive dashboard refresh from slower reports,
with bounded jobs and dedicated, request-independent sessions.

## Dashboard
The background producer loads one history/settings/demand context for all four
averaging windows and preserves exact window identity. Overview responses reuse
that completed pace generation; selecting a window does not calculate again.
Quota observations remain collected by the existing independent ingestion path.
A refresh cannot clear observed history or transform an unready cache into an
assertion that samples are absent. Keep a compact generated-at/stale indication.

## Reports
Prewarm 7/30/90-day presets approximately every five minutes, including current
and previous comparison periods, options and the diagnostic sections. Honor
IANA timezone/DST and filter identity. UTC works zero-config; persist known
viewer timezone interest so schedules survive application restarts. Browser
initialization can advertise timezone before Reports is opened, without doing
heavy work on that request. Bound uncommon filter registrations and eviction;
canonical presets cannot be starved by arbitrary filter combinations.

Reuse the existing permanent hourly report aggregates and their disjoint raw
tail. Measure the refresh before optimizing. Reuse overlapping daily work and
avoid recomputing unchanged closed history where invalidation is provable.
Do not sum daily distinct counts or average medians to invent window statistics.
The existing seven-day timing/thread guard must be revisited for background
execution, with real coverage disclosed when retained raw history cannot supply
an older metric; no manufactured zeros or claims of reconstructed observations.

## Failure and rollout
Retain prior completed snapshots through worker failure, cancellation, replica
changes and cold browser caches. Lease loss prevents late publication; shutdown
joins workers before disposing their sessions. Prime required snapshots before
traffic selection. Test an existing browser connection across a version handoff,
not just a fresh browser, and prevent retained old APIs/assets from being labeled
as missing quota samples. Keep inference streams and warm rollback protected.

## Evidence
Prove HTTP reads cannot call aggregation, including misses and expiry. Verify
all three report presets, all averaging windows, shared-replica reads, restart,
midnight/DST, filtering, stale/error behavior and producer ownership. Compare
numerical results against raw observations and exact report controls; measure
query count, rows examined, duration and event-loop/inference impact under the
forty-session workload. Preserve original failures and independent review.

## Delivery priority
Start both analytical snapshot refreshes at approximately five minutes. Deliver
the background/read-only architecture with existing rollups first, measuring its
load and correctness. A faster cadence or additional incremental aggregation is
subsequent work, not a reason to delay this deployable correction.

The first deployable baseline preserves the existing explicit timing/thread
coverage guard while preparing complete 7/30/90-day core report responses. It
does not silently lift a raw-history scan limit or invent unavailable medians.
Further historical metric expansion and faster cadence follow measured coverage
and refresh-cost work. Dashboard HTTP/1.x responses close after completion;
inference streams are not buffered or closed by this policy. The first handoff
from a predecessor without that policy still requires the retained-browser audit.


## Measured baseline — October 19, 2026 03:16 UTC
The read-only production-data probe used one MariaDB connection, a consistent
read-only transaction, 15-second statement and 32-MiB temporary-table limits.
No HTTP handler, background scheduler or migration was started by the probe.
All 7/30/90-day core totals and exact account/conversation distincts matched an
independent raw SQL oracle in both passes. Timing/thread metrics remain explicitly
unavailable beyond seven days; this is not a ninety-day timing-history claim.

Steady background collector durations were 14.39 / 4.53 / 12.70 seconds for
7/30/90-day bundles, and 3.51 seconds for the all-window/all-range dashboard.
Reports already use the permanent hourly aggregates and disjoint raw tail.
Nevertheless seven-day diagnostics read about 2.88 million rows and sort about
1.35 million rows; the ninety-day daily-window CTE alone takes about 12 seconds.
The dashboard transfers about 385,490 rows before its existing Python-side caps.
These are collector measurements, not HTTP response times or forty-session proof.

Measured targets selected for implementation:
- Honor the existing projection tail cap and exact uncapped recent floor inside
  MySQL/MariaDB SQL, rather than transferring the full history and then applying
  the already-existing cap in Python. Preserve identical returned observations.
- Avoid constructing daily report windows before the earliest retained matching
  activity, if its existing query and transaction semantics establish that bound.
  Preserve the requested dates, exact results and original speed-availability guard.
- Re-measure before adding further aggregation/invalidation machinery. Seven-day
  thread diagnostics dominate the short preset; do not combine daily distincts
  or medians incorrectly to avoid that cost.

Independent review first three findings are corrected and pass the complete
qualification run, including real non-UTC MariaDB lease tests. The traffic gate
must still verify initial published canonical/known-used snapshots, not merely
proxy health. The real retained-browser handoff remains an outstanding delivery
gate. The new additive schema also requires a migration-aware cold rollback/boot
plan: an already-running old binary is not proof that it can restart on a newer
Alembic head. No production schema or selected immutable source has been changed.


The application normally uses READ COMMITTED on MariaDB. Report workers therefore
select REPEATABLE READ only on their fresh owned analytical connection, restored
on return to the pool. The repository checks the actual server isolation before
using an earlier history bound. Inference/accounting defaults are unchanged;
SQLite retains the untrimmed path rather than assuming driver-level snapshot
semantics from an ORM transaction object. Real backfill/isolation-reset tests
qualify this boundary.


## Measured optimization and readiness qualification — October 19, 2026
The MySQL projection SQL cap returns exactly the prior Python-selected complete
bundle in a fixed SQL snapshot/evaluation clock. Steady dashboard duration fell
from 3.513s to 1.284s; rows transferred 386,702 to 61,295, rows read 1,481,374 to
407,196 and sort rows 338,211 to 12,804. This changes no numerical sampling cap.

A separate REPEATABLE READ production-data transaction compared whole report
bundles, excluding only their response-generation clocks: 30-day 4.656s to
2.250s, 90-day 12.039s to 2.233s. Requested windows, daily results, totals,
distincts, options, history boundary and timing/thread availability were exact.
Independent raw SQL core totals/distincts passed for all three presets. The
7-day bundle remains about 15 seconds because its existing diagnostic metrics
remain enabled; no new daily-distinct summing, median approximation or historic
sample reconstruction was introduced. These are background collector timings,
not HTTP or inference latency measurements.

The separate `/health/read-snapshots` endpoint reads two bounded metadata result
sets, extracting only a preset's end date in SQL, never transferring JSON values
or registering interest. It requires current-schema published dashboard/known
7/30/90-day snapshots and current local days/freshness. It does not affect the
ordinary inference readiness endpoint. SQLite and MariaDB tests cover empty,
stale, wrong-version/unpublished/missing-payload, known-zone admission and local
midnight cases; installed traffic-control integration is a separate delivery gate.

The browser smoke harness deliberately leaves only the real analytical producer
running while neutralizing upstream pollers. Its seed helper marks changed input
snapshots due and waits for that owned producer; neither a browser GET nor a seed
helper invokes the analytical collectors. The real five-minute built-page test
uses the production 300-second cadence, not fake clocks. This is distinct from
the retained old-backend TCP handoff gate.

A QA-only MariaDB upgrade/downgrade experiment imported both original immutable
18/19 startup paths: both pass on parent, both reject the unknown new revision,
both pass after the derived-table downgrade; the new source passes new/re-upgraded
head with drift checks. Every existing non-cache table row was preserved. This
proves the migration primitive, NOT installed mixed-version cold-boot recovery.
The private deployment transition is maintained outside the published source tree.
