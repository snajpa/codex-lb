# Verification checkpoint — October 20, 2026

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
application lifespans against the shared qualification database. That does not yet
prove two new production replicas or a host-power-failure recovery. The unselected
prior replica still owns connections and remains protected; its replacement waits
for natural idle and the fenced retirement checks. No active client was forcibly
disconnected. A synthetic encrypted-context exchange across backends does not prove
every native client can reconnect with process-local previous-response state intact.

Cloud PostgreSQL tests and all three database migration checks now pass. Cloud
frontend, browser, end-to-end, integration-bridge and first core-shard checks also
pass. Current unit failures exactly match the eleven failures on the earlier base;
all 132 reported type diagnostics are also present on that base (134 there). The
third core shard retains the same model-source failure, and four second-shard retry
seams are inherited. A further introduced compaction fixture still expected an
immediately computed dashboard after account-state mutation: it now explicitly
runs the real producer outside HTTP, preserving all native failover assertions and
checking fresh/error-free snapshot state. That focused fixture passes on SQLite
and MariaDB and received a separate source-only review with no actionable findings.
No application code changed for this fixture correction. Broader native complexity,
security/dependency and test seams remain separate; no full cloud-CI-green or full
MySQL claim follows. Archive only after the outstanding two-new-replica rollout
evidence exists.
