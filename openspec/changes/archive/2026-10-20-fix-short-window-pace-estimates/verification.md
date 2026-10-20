# Verification checkpoint — October 20, 2026

## Summary

| Dimension | Result |
| --- | --- |
| Completeness | 10/10 tasks; three delta requirements implemented |
| Correctness | Seven scenarios covered by regressions and numerical/API/built-browser checks |
| Coherence | Bounded owned query, exact window identity, truthful coverage and version fencing follow the design |

The traffic estimate is implemented in `app/modules/dashboard/traffic_pace.py`,
its repository/service/weekly-pace integration and the existing dashboard card;
`tests/unit/test_traffic_pace.py` and
`tests/integration/test_dashboard_traffic_pace.py` cover calibration, resets,
unknown work and longer-window preservation. The shared query and mixed-version
admission are covered by the read-snapshot integration tests; the migration cases
exercise real PostgreSQL literal defaults, retry, downgrade and alien-layout refusal.
No critical implementation or rollout issue remains in these scoped requirements.
The broader inherited cloud failures below are not waived.

## Established behavior

The real incident reproduced hundreds of requests in five minutes while fresh
provider counters stayed flat. The corrected background calculation uses current
window work and a bounded same-account/same-cycle calibration, not a hard-coded
currency conversion. Direct quota observations remain separate. Unknown cancelled
or failed work is counted and disclosed; incomplete pricing forces low confidence.

The second complete serial qualification passed all fourteen gates: scoped format,
lint and typing; 156 SQLite tests (four MariaDB-only skips); 129 numerical/API tests;
83 MariaDB tests; 53 PostgreSQL tests; four native-drain unit and two external-route
tests; frontend lint/type/build; 521 dashboard/report frontend tests; and strict
validation of this change and the original snapshot change. PostgreSQL proves the
approved literal-default validator correction without changing emitted DDL, revision
or parent. Three independent source reviews found and corrected version-capacity,
unknown-usage, confidence and fixture defects; the final full source review found no
actionable issue. This is source review, not independent production execution.

A separate read-only production transaction compared grouped SQL with raw request
and quota observations for ten accounts and 15,688 requests. The added grouped query
took 83 ms and the collector 2.45 seconds. The five-minute sample contained 440
requests; 27 calibration requests had unknown usage and correctly lowered confidence.
These timestamp-specific measurements are examples, not fixed performance promises.

## Preserved failures and limits

Earlier fixture runs failed because of PostgreSQL virtual generated-column syntax,
a wrong query parameter, an overview-map assumption, expired ORM attributes after
rollback and a scheduler lease literal tied to the prior contract. Those failures
remain evidence; they are not retroactively counted as passes.

The corrected immutable application is now selected on the normal endpoint.
Candidate and normal-address checks verified TLS, authentication, every built asset,
both dashboard routes and all four averaging windows against independent raw-data
rate, reset-aware depletion and feasible-load calculations. A real built browser
remained open for 311.428 seconds and observed the dashboard advance from generation
2 to 3 at the five-minute cadence without browser-started collection or a loading
state. Forty native generations all overlapped and completed in 4.614 seconds while
the automatic seven-day report SQL refresh was active; all stream text matched its
completed payload. These are observed samples, not universal latency guarantees.
Real tool-result continuation and encrypted compaction into an isolated session
also passed on the normal endpoint.

Before selection, an unused candidate was safely stopped and restarted. Seven
published generation/payload hashes stayed identical while it was stopped and on
authenticated reads after restart. Both exact immutable artifacts also passed real
application lifespans against the shared qualification database. Those checks alone do not
prove two new production replicas or a host-power-failure recovery. A further
real two-worker qualification killed and joined its owned leader, observed natural
lease-expiry takeover, preserved exact last-good report payloads on collector
failure, and restarted all workers without losing persistent generations or the
accounting control row. Separately, 34 authenticated reads on the selected new
production replica matched every business field of its persistent dashboard and
report bundles across the required ranges, averaging windows, and admitted zones.
Those earlier single-replica reads were not a two-new-production-replica claim.
The operator subsequently authorized client disconnection and reconnection. Only the
old replica's 27 exact ownership-fenced sockets were closed, then actual in-flight,
cleanup and durable ownership were allowed to settle before its fenced retirement.
The selected replica was not restarted or disconnected. Its qualified standby was
installed through the journaled cold-member controls, without live DDL or a third
backend. Both new production replicas passed 68 complete persisted-business-payload
comparisons before and 68 after the unused standby's safe restart. All seven
published generation/payload hashes stayed identical before, while stopped and
after restart. Final inference and analytical readiness were healthy on both
replicas and the normal endpoint. This proves shared production reads and standby
restart persistence, not an actual production power failure or universal client
context continuity. The standby separately passed actual private-client TLS,
assets, all windows, a real built browser and native tool/result plus isolated
encrypted-compaction continuation checks.

Cloud PostgreSQL tests and all three database migration checks now pass. Cloud
frontend, browser, end-to-end, integration-bridge and first core-shard checks also
pass. Current unit failures exactly match the eleven failures on the earlier base.
A stricter diagnostic-location comparison corrected an earlier classification:
130 of 132 reported type diagnostics match that base, but two were introduced in
the existing pace-test helper by its untyped expanded keyword dictionary. An exact
optional-key TypedDict now fixes those diagnostics without changing application
code, omitting-default behavior, or assertions; focused typing, formatting, lint,
and all 47 pace tests pass, with a separate source-only review finding no action.
The corrected head's actual cloud typing log now reports 128 diagnostics, all
matching the earlier base by header, location and multiplicity; the two introduced
pace-helper diagnostics are gone. This does not restore the earlier incorrect
claim that the preceding head's 132 diagnostics were all inherited.
The third core shard retains the same model-source failure, and four second-shard
retry seams are inherited. A further introduced compaction fixture still expected an
immediately computed dashboard after account-state mutation: it now explicitly
runs the real producer outside HTTP, preserving all native failover assertions and
checking fresh/error-free snapshot state. That focused fixture passes on SQLite
and MariaDB and received a separate source-only review with no actionable findings.
No application code changed for this fixture correction. Broader native complexity,
security/dependency and test seams remain separate; no full cloud-CI-green or full
MySQL claim follows. The full MySQL run completed with 2,161 passes, 50 skips,
six failures and one setup error, with all failure/error names exactly matching
the earlier base. This compares names, not a guarantee of identical causes.
The two-new-replica rollout, shared reads, persistence and
matched fork publication are now verified; archive preserves the evidence and
these explicit limits.
