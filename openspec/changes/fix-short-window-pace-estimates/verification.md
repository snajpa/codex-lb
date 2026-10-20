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

The running production application is still the prior build at this checkpoint.
Immutable staging, real new-build browser/API/native checks, safe retained-client
handoff, two-new-replica shared recovery and normal-address forty-session coexistence
remain rollout work. A synthetic encrypted-context exchange across existing backends
does not prove every native client can reconnect with process-local previous-response
state intact. Do not describe source publication or cold staging as deployment.

Broader inherited native complexity, security/dependency and test seams remain
separate from introduced failures; no full cloud-CI-green or full MySQL claim follows.
Archive only after the outstanding consumer and rollout evidence exists.
