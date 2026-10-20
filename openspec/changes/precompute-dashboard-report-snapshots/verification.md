# Verification — background analytical snapshots

Checkpoint: October 20, 2026. This records qualified application behavior, not a
claim that every production replica has already been replaced.

## Scorecard

| Dimension | Result |
| --- | --- |
| Completeness | 14/15 tasks; final publication/rollback/archive closure remains open |
| Correctness | All 10 delta requirements have implementation and regression coverage; 26 scenarios reviewed |
| Coherence | Durable read model, independent fenced lease, owned bounded lanes, existing rollup reuse and explicit coverage follow the design |

## Requirement and scenario mapping

- **Persistent dashboard read snapshots:** `app/modules/read_snapshots/repository.py:186`,
  `repository.py:299`, `repository.py:313`, `scheduler.py:82` and `service.py` keep
  HTTP reads separate from collection. `tests/integration/test_read_snapshots.py:42`
  checks misses cannot run collectors; lines 70, 103, 141, 182, 209 and 321 cover
  proactive warmup, shared last-good, fencing, independent leadership,
  cancellation and explicit cold failure.
- **Projection transfer caps:** `app/modules/usage/repository.py` applies the
  existing capped older tail plus uncapped recent floor in MySQL/MariaDB.
  `tests/integration/test_mysql_projection_history_cap.py` checks exact selected
  observations, batching and the cap boundary. Fixed-snapshot whole-bundle and
  independent quota/rate/reset-aware max-flow checks also passed.
- **Independent analytical readiness:** `app/modules/health/api.py:96` and
  `repository.py:239` read bounded metadata without collecting or registering
  interest. `tests/integration/test_read_snapshot_readiness.py` covers missing,
  stale, wrong-version, known-zone and local-midnight values. Inference readiness
  is unchanged; deployment qualification separately exercised the analytical gate.
- **Retryable, fail-closed derived-table migration:** the additive migration and
  `tests/integration/test_read_snapshot_migration.py` cover upgrade/downgrade,
  preserved accounting, partial DDL and alien layouts. Generated expressions are
  refused even when their physical storage type resembles the expected column.
- **Prepared-view freshness and identity:** the dashboard/report hooks, schemas
  and `frontend/src/components/read-snapshot-status.tsx` preserve exact keys and
  distinguish warming, stale/failure and real coverage. Hook/component and real
  built-page tests cover eager choices, cache-only clicks, pending selection,
  retry, mobile layout and preference migration. The externally incompatible
  old-window response is not reported as missing quota samples.
- **Dashboard-only HTTP pool retirement:**
  `app/modules/read_snapshots/connection_middleware.py:14` and
  `tests/unit/test_dashboard_connection_middleware.py` cover HTTP/1 completion,
  root paths and inference/internal/HTTP2/WebSocket exclusions. Real retained
  old-backend UI TCP was observed and connection-specific UI reconnection was
  qualified without touching protected inference connections.
- **Bounded background report caching:** `scheduler.py:74`, `scheduler.py:109`,
  the read service and report handlers prepare canonical/known-zone presets and
  cheaply register bounded custom interest. `test_read_snapshots.py:240`, 274,
  379, 416, 567 and 604 cover admission, scope, lane isolation, lease-loss joins,
  rejected-zone fallback and filter progress. HTTP and frontend regressions cover
  same-key stale values, failures, polling and no request-owned aggregation.
- **Retained-history disclosure:** report schemas/repository and the Reports page
  expose the earliest retained filtered activity without claiming continuity.
  `test_read_snapshots.py:468` covers long-window disclosure and HTTP query work.
  Long reports retain explicit speed/thread unavailability rather than invented
  historical medians.
- **Consistent empty-day bound:** the report collector uses its own repeatable
  transaction; `tests/integration/test_report_history_bound.py` checks exact
  optimized/untrimmed parity, backfill, read-committed fallback and isolation
  restoration. Requested dates and the original timing guard remain unchanged.
- **Oversized filters:** the normalized 16-KiB admission limit returns a bounded
  client error without collector execution or registration; the regression is
  `test_read_snapshots.py:630`.

## Executed qualification

- Complete scoped run: 178 SQLite/lifecycle tests (two MariaDB-only skips),
  129 numerical/permission tests, 61 real-MariaDB cases, 519 frontend tests,
  frontend lint/type/build and strict OpenSpec validation.
- Follow-up migration/control run: 19 SQLite and 19 MariaDB cases, 51 deployment
  controls, old/new cold database roundtrip, format/lint and strict spec checks.
- Both exact immutable application artifacts ran real cold lifespans against an
  owned MariaDB schema. Workers published complete values, the second process
  read persisted first-process payloads, accounting controls survived and owned
  children joined. Separate two-process takeover/restart coverage passed.
- Production background publication occurred before a browser visit. A safe
  candidate-only restart retained all four canonical payload digests/generations
  while the producer was stopped, then returned the same persisted generations.
- Fixed repeatable-snapshot collector/raw-SQL oracles matched 7/30/90-day core
  totals, tokens, cost and exact account/conversation distincts. Published HTTP
  responses were separately checked against persisted generations, not newer
  live counters. The measured dashboard HTTP maximum in that API check was
  0.008583 seconds; this is not a universal latency guarantee.
- A real normal-address built page waited 311.34 seconds and then read the next
  automatically published dashboard generation with the five-minute selection
  preserved. Forty real native generations fully overlapped and completed in
  4.865 seconds while an automatic seven-day report refresh was SQL-observed;
  forty distinct response IDs and streamed/completed text equality were verified.
- Actual verified-TLS normal-address checks covered tool/result continuation,
  native compaction, encrypted continuation in an isolated new session with the
  plaintext marker omitted, plus Mac authentication, all windows, pinned assets
  and a real generation. No universal historical exactly-once or arbitrary-context
  service-level claim is made.

## Review, failures and limits

Independent completed reviews led to clock-domain, admission/fairness, initial
readiness, migration-layout and recovery-boundary corrections with separate
regression tests. The focused final source review had no actionable findings;
it is not evidence of a production power-failure experiment. An interrupted
review is not counted as clean.

Original failures are retained privately. One API harness incorrectly compared
an older published total with newer live traffic; another expected the projection
window map on Overview. A retained-browser harness captured old TCP correctly
but failed while reading a response body during navigation: it is not counted as
a continuous old-page five-minute success. The retained-TCP evidence and later
normal-address cadence test are distinct qualifications.

A genuine deployment defect was also found: the VPN firewall allowlist omitted
the new backend port after server-local qualification. The private-peer-only live
and persistent rule was corrected without public exposure, reload or flow flush;
subsequent Mac API/asset/native checks passed. Future selections require an actual
external-peer preflight, not only a server-local readiness check.

Existing baseline cloud lint/type/native/security and fork publishing-configuration
failures are not claimed green by the scoped qualification above. No unrelated
dependency or native churn was used to conceal them.

## Critical closure item — do not archive yet

The final task remains open. Publish the verified application-matching fork source,
then finish the protected two-replica rolling replacement and preserve its qualified
rollback record before archiving. Existing protected client owners on the old
replica must not be killed to manufacture an idle proof or to start a third backend.
The new worker and selected endpoint are delivered; this does not imply the second
new production replica or a host power-failure exercise is already complete.
