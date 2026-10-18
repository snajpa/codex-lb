# Design

Change the existing four-value API/type/button contract from 1 to 5 minutes.
Keep the query keys parameterized by their actual interval. A stored value of 1
maps once to 5 and is persisted under the same browser-local preference key;
other invalid values still fall back to 180. The rate integration already clips
arbitrary supported elapsed-time windows, so retain that mechanism unchanged.

Prove five-minute numerical rates/boundary clipping, both HTTP routes accepting
5 and rejecting 1, preference migration, real built-browser rendered values and
rapid/error switching. Qualify a separate immutable build, retain the current
selected revision as rollback, and verify the normal address after cutover.

## Numerical consistency across resets

Quota history is rounded and sampled. Integrate only continuous, nondecreasing
intervals within the selected window and divide by their covered elapsed time,
not by skipped reset/decrease gaps. Retain the existing sparse-data floor
(minimum of the selected window and thirty minutes). The latest positive-time
interval must be usable; a pre-reset zero must not masquerade as a measured
post-reset zero. Exclude future observations and expired-cycle balances rather
than advancing an old balance into the new week. An expired eligible balance
makes pool pace unavailable until it is refreshed, not a partial-fleet estimate.

Keep depletionEtaHours as the compatible remaining/rate counterfactual. Derive
the actual verdict and rendered depletion ETA from the existing reset-aware,
earliest-expiring-balance simulation, over two longest quota windows. A later
cohort reset is informational and cannot override earlier material resets.
Any modeled depletion yields runs_dry; otherwise a minimum pool balance below
12% is tight. Unknown/zero rates still must not claim measured safety.

When depletion is projected, find a feasible constant load using 32 bounded
bisection steps through that same monotone simulation. Return the feasible lower
bound, not the nominal weekly allowance divided by the observed rate. Floor the
displayed load percentage to avoid rounding above a safe recommendation. This
reuses the actual balance/refill mechanism instead of introducing a second
budget model; measure its bounded cost on the real fleet. Pause duration remains
an estimate for the first modeled gap, not a perpetual safety guarantee.

The card uses projectedDepletionHours when supplied. Explicit null with positive
burn means no depletion in the modeled horizon; absent metadata from an older
server retains a clearly labeled no-reset counterfactual. Only say relief
arrives after depletion when the actual timestamps have that ordering. Preserve
rounded-percentage warnings and unavailable/observed-zero distinction.

Acceptance includes independent constant-slope reset-gap examples; an exhausted
old cycle; unsafe nominal throttling; earlier non-cohort relief; depletion after
the first reset; rendered feasible load/ETA; same-time raw live history replay;
both HTTP routes and real MariaDB; bounded actual built-browser and native
continuation qualification before guarded immutable deployment.

Take the pace evaluation clock after the asynchronous quota/history reads and
use it for both weekly pace and percentage-burn generatedAt. A snapshot arriving
normally after request start is not a future-clock error. Keep the original
request clock for unrelated activity/timeframe aggregates.

## Eager background values for every averaging button

Load all four rates before selection. Extend the existing projections response
with a typed four-window pace map, computed from the same quota histories,
settings and completed-read clock. Read history, demand and API-key attribution
once; reuse the selected result and attribution instead of repeating database
queries. Preserve the existing selected weeklyCreditPace response and direct
burnWindowMinutes query for older clients. No new endpoint, setting or timer.

The dashboard projection query caches this one complete response independently
of the selected button. A selector exposes the exact chosen map entry, including
explicit null. Switching after the initial background read must not start a new
request or enter a selected-window loading state. Initial loading and genuine
refresh errors remain truthful; interval polling, hidden-tab behavior and cache
invalidation keep the existing cadence. A change of selection while the shared
request is pending must select from its result when it arrives, never apply the
window captured when the request started. Four-window computation adds only
bounded pure projections, not four full DB history/attribution scans.

Validate a single eager request contains all four independently calculated
window values at both default and explicit-window projections queries, identical
read counts and evaluation timestamps, immediate cached switching, selection
while loading, explicit null/unknown windows, shared refresh/error recovery and
actual built-browser behavior. Measure real endpoint cost before deployment.

Start the eager projections read when dashboard authentication is initialized,
in parallel with overview rather than waiting for the overview response. The
overview still controls whether weekly quota coverage is available for display.

Concurrent overview/projection startup can race the trailing-demand cache fill.
Use a weak per-event-loop, per-signature lock around cache misses, recheck after
acquisition, and run the owning request's database read inline. Idle locks drop
automatically; cancellation/failure releases the lock without caching partial
results. Keep TTL-disabled exact reads independent and avoid background tasks
that could outlive their request-scoped database session.
