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
