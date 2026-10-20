## Mechanism
The provider exposes rounded quota percentages. A five-minute window can contain
hundreds of completed requests without one percentage-point increment. A quota
counter delta of zero is therefore not proof of zero traffic or actual quota burn.

For each eligible account, use the latest uninterrupted quota episode inside the
existing three-hour history. Reset markers, duration changes or counter decreases
start a new episode. Require fresh observations, at least fifteen minutes and a
positive quota delta before calibrating. Match actual priced request work between
the episode's observation timestamps to that quota delta. Apply the resulting
per-account credit/work ratio to requests in the selected five- or fifteen-minute
window, not to a longer-window traffic average. Stored API price is a weighting
measure for model/cache/tier work; it is NOT a fixed USD-to-quota exchange rate.
This remains an estimate of observed proxy traffic; external consumption and
changing model economics limit the calibration, so never label it direct quota
measurement or high-confidence historical truth.

A single bounded grouped query returns calibration work plus all requested-window
work/counts for the current eligible account set. Reuse loaded quota histories and
retain the existing background lanes and five-minute cadence. Do not add work to
HTTP, rescan full history, share sessions across tasks or widen a selected window.
Require complete eligible-account calibration and priced-work coverage before
using the fleet estimate; otherwise preserve the direct quota result with truthful
basis/coverage. Genuine reset/stale/uncalibrated cases remain unavailable rather
than fabricated. One-hour and three-hour direct quota semantics remain unchanged.

Use one chosen rate consistently for burn, depletion, max-flow load advice and
capacity recommendations. Include observed quota rate separately so a rounded zero
is not silently replaced or presented as a measurement. Add response metadata for
basis, calibration duration and observed request count. The existing card explains
that a traffic-calibrated value is an estimate; no new full-width forecast section.

Fence changed background payload semantics with the snapshot schema version so a
new reader never relabels an old cached result. Preserve last-good within its exact
key/version, readiness, cold warming and independent inference availability.

## Migration repair
Retain revision/parent and every intended column/index/constraint. Normalize only
literal defaults with dialect-equivalent PostgreSQL integer/bigint/boolean casts;
never accept arbitrary expressions, computed columns or alien defaults. Check the
SQLAlchemy DefaultClause type explicitly. Prove real PostgreSQL fresh upgrade,
partial-create retry, downgrade/re-upgrade and incompatible-layout refusal, plus
MariaDB/SQLite regressions. Deploy a newly qualified immutable artifact rather
than editing the running build.

## Qualification and rollout
Prove the rounded-flat/high-traffic case through real HTTP snapshot reads and the
built card, preserve actual selected-window traffic boundaries, compare the formula
with an independent fixed-SQL oracle, measure query cost, and exercise missing
prices, absent calibration, external account traffic, resets and cancellation.
Keep at most two actual backends and protected live request ownership. Qualify
actual private-client TLS/API/assets before selection, then normal-address browser,
native continuation and forty-session/background-refresh coexistence. Publication
to the authorized fork main and deployment are both required for delivery.

## Real-data coverage correction
The bounded production probe also found 27 cancelled/error requests with no final
usage among roughly 15,700 priced requests in three hours. Treat missing counters
as unknown work, not zero. A positive priced-work estimate can remain useful, but
its selected-window and calibration omitted counts must be visible and confidence
must be low. Do not infer an exact total from that subset, use a silent coverage
threshold, or calibrate an all-unpriced current window to zero. This is distinct
from account coverage: every included eligible account still needs a valid
same-cycle calibration and priced calibration work.

## Full-registry rolling admission
Per-kind capacity is version-specific but the 64-row global bound remains shared.
Pinned old canonical last-good is never sacrificed to prime the new contract.
When fresh old filter entries fill the registry, a new canonical key preempts the
oldest idle unpinned prior-version entry (not an actively refreshing entry), even
if its last interest was recent. This is bounded cache eviction, not promise of
unlimited filter history retention. An old reader of an evicted key receives its
own truthful warming status. Current-version filters cannot use this preemption
privilege, and no payload is relabelled across versions.
