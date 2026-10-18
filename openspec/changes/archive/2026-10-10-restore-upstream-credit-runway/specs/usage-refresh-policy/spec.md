## ADDED Requirements
### Requirement: Calibrated Pro Max estimated credit scale
Pro Max primary and weekly credit capacities SHALL use the same estimated scale as Pro Lite with a 25x rather than 5x allowance, yielding five times its capacities: 5625 primary and 189000 weekly credits. Reported percentages and resets SHALL feed ordinary credit/runway consumers without changing upstream exhaustion, authorization, admission caps, recorded costs or persisted usage. Calibrated windows SHALL be known coverage. Missing calibration SHALL retain incomplete-coverage safeguards.

#### Scenario: Calibrated weekly usage contributes estimated credits
- **WHEN** a Pro Max weekly window reports 20 percent used
- **THEN** its estimated capacity is 189000 credits, used credits are 37800 and remaining credits are 151200
- **AND** its unquantified-account count is zero
- **AND** fresh timed observations permit the existing fleet pace forecast

#### Scenario: No invented short-window observation
- **WHEN** Pro Max reports only a weekly window in the primary API slot
- **THEN** it is normalized into the weekly summary
- **AND** no short-window observation is invented

#### Scenario: Missing calibration is still unknown
- **GIVEN** the estimated capacity is unavailable
- **WHEN** an eligible Pro Max account has a fresh weekly percentage observation
- **THEN** the whole-pool credit runway remains unavailable rather than treating that account as zero cost or known capacity

## MODIFIED Requirements
### Requirement: Pro Max percentage-only subscription usage

The system SHALL recognize and preserve the `promax` account plan. It SHALL
retain reported quota percentages, durations and reset times without
assigning an unverified absolute subscription allowance. Purchased credits
SHALL remain separate from included subscription capacity.

#### Scenario: Weekly-only Pro Max quota
- **WHEN** Pro Max reports a 604800-second primary-slot window at 20% used
  and no secondary slot
- **THEN** its normalized weekly remaining percentage is 80%
- **AND** its short-window usage remains absent
- **AND** its calibrated weekly estimated capacity is 189000 and remaining credits are 151200

### Requirement: Explicit unquantified usage coverage

Usage-window summaries SHALL report `unquantifiedAccountCount` for reported
Pro Max windows without a known allowance. Existing numeric credit fields
SHALL describe only the known-capacity subtotal. Per-account history and
window items SHALL expose `capacityKnown` so unknown credits are not
presented as zero allowance.

Dashboard overview and projections SHALL omit fleet weekly credit pace when
an eligible Pro Max account without a calibrated positive credit capacity has a fresh secondary usage observation, including when its optional window duration is missing or zero.

#### Scenario: Mixed weekly subtotal
- **GIVEN** the Pro Max credit calibration is unavailable
- **WHEN** Pro at 40%, Plus at 50% and Pro Max at 20% have reported weekly usage
- **THEN** weekly estimated capacity is 57960 and remaining credits are 34020
- **AND** the weekly unquantified-account count is 1
- **AND** an absent Pro Max short window does not increment the short count

#### Scenario: Recorded usage omits optional reset metadata
- **GIVEN** the Pro Max credit calibration is unavailable
- **WHEN** a persisted Pro Max percentage observation omits its reset timestamp
  or window duration
- **THEN** its absolute allowance remains unquantified
- **AND** its per-account capacity is not reported as known
- **AND** synthetic rows for absent usage do not count as observations

#### Scenario: Fresh secondary usage has no usable duration
- **GIVEN** the Pro Max credit calibration is unavailable
- **WHEN** an eligible Pro Max account has a fresh secondary percentage sample
  with a missing or zero duration alongside a known-capacity Pro weekly window
- **THEN** dashboard overview and projections return no fleet weekly credit pace
- **AND** the missing duration does not make the Max observation disappear
