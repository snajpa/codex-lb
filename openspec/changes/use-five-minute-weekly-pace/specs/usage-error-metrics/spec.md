## MODIFIED Requirements

### Requirement: Consistent selectable weekly quota burn
Dashboard overview and projections MUST accept `burnWindowMinutes` with integer
values 5, 15, 60 or 180, default to 180 when omitted, reject other values, and
report the selected window in weekly credit pace metadata. One elapsed-time
average for that window MUST drive displayed burn, depletion ETA, shortfall
simulation and rate-dependent recommendations.

#### Scenario: Frequent unchanged usage snapshots
- **WHEN** unchanged quota snapshots are inserted inside the same fully observed averaging interval
- **THEN** the selected-window average MUST NOT decay with the sample count
- **AND** forecast burn MUST equal displayed burn rather than decay per sample

#### Scenario: Five-minute averaging
- **WHEN** the operator selects five minutes
- **THEN** the rate MUST use observed quota changes in that interval, with
  boundary interpolation when an observation spans its start
- **AND** its denominator MUST NOT be padded to thirty minutes

#### Scenario: Incomplete data or quota reset
- **WHEN** an eligible account lacks a usable observation interval
- **THEN** pool burn MUST be unknown rather than a partial-fleet estimate
- **AND** quota decreases, real reset discontinuities and changed window
  durations MUST NOT create artificial burn

#### Scenario: Only discontinuous intervals are available
- **WHEN** every observed interval crosses a quota decrease, real reset or duration change
- **THEN** that account's rate and the complete-fleet rate MUST be unknown, not measured zero
- **AND** no depletion ETA or rate-dependent recommendation may use a partial-fleet rate

#### Scenario: Retired one-minute HTTP query
- **WHEN** either dashboard route receives `burnWindowMinutes=1`
- **THEN** it MUST reject the query with HTTP 422 rather than relabel another interval

#### Scenario: One-minute averaging
- **WHEN** a client uses the retired one-minute interval
- **THEN** the HTTP query MUST be rejected with 422
- **AND** a persisted browser preference of 1 MUST migrate to 5 minutes

#### Scenario: Skipped reset gaps are not zero consumption
- **WHEN** a discontinuous history interval is excluded from its quota delta
- **THEN** its duration MUST also be excluded from measured coverage
- **AND** the existing selected-window sparse-data floor MUST still apply
- **AND** an unusable latest interval MUST produce unknown rather than a pre-reset zero

## ADDED Requirements

### Requirement: Reset-aware weekly runway and feasible load
The weekly pace verdict and actual depletion display MUST use the selected burn
rate and all eligible balances and resets over two longest quota windows.
`depletionEtaHours` MUST remain the no-reset remaining/rate counterfactual for
compatibility. `projectedDepletionHours` MUST represent actual modeled depletion.
A throttle recommendation MUST be feasible through that same model horizon,
with a conservatively rounded display, not merely equal to nominal weekly supply.

#### Scenario: Remaining credits constrain throttling
- **GIVEN** 5040 credits remain, the next refill is in 100 hours, and burn is 1008 credits/hour
- **WHEN** a load reduction is recommended
- **THEN** the modeled load MUST NOT exceed 50.4 credits/hour or 5 percent of current load

#### Scenario: Earlier relief outside the saturated cohort
- **GIVEN** a less-saturated account refills before the saturated cohort
- **WHEN** those earlier credits prevent modeled depletion
- **THEN** the verdict MUST NOT claim the pool runs dry before relief

#### Scenario: Depletion after an early reset
- **WHEN** the first reset arrives before the no-reset ETA but the pool depletes later in the horizon
- **THEN** the verdict MUST report runs dry and the card MUST show that later modeled depletion
- **AND** it MUST NOT say the first relief arrives after depletion

#### Scenario: Expired and future quota observations
- **WHEN** an eligible balance belongs to an already elapsed reset cycle or a future observation
- **THEN** complete-fleet pace MUST be unavailable rather than advancing that balance into a new cycle
