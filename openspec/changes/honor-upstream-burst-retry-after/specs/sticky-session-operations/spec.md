## ADDED Requirements

### Requirement: Upstream burst retry delay is a lower bound

An owner-bound HTTP streaming request retrying a code-less HTTP 429 MUST wait
`max(retry_after, min(10 seconds, 1 second * 2^(n-1)))` before retry `n`.
The ten-second cap MUST apply only to generated exponential backoff, not to a
positive upstream Retry-After. Initial and post-refresh retries MUST follow
this rule with existing ownership, retry-count, and settlement contracts.

#### Scenario: Retry-After exceeds generated backoff cap

- **GIVEN** an owner-bound request rejected with HTTP 429 and Retry-After 18
- **WHEN** the first same-account retry is permitted by the request budget
- **THEN** the proxy waits at least 18 seconds before dispatching again
- **AND** it does not move the request to another account

### Requirement: Cooldown waits remain bounded by the request budget

Cooldown waits MUST recheck elapsed time through the clock seam between chunks.
Each sleep MUST be clipped to both the recovery-wait deadline and request-budget
deadline after downstream delivery resumes; an elapsed deadline MUST cause no
additional sleep.
Budget exhaustion MUST surface the original 429 and Retry-After without another
dispatch or sleep. Cancellation MUST preserve existing resource cleanup.

#### Scenario: Budget cannot accommodate the upstream cooldown

- **GIVEN** an owner-bound request with 12 seconds remaining and Retry-After 18
- **WHEN** the wait exhausts the remaining request budget
- **THEN** there is no second upstream dispatch
- **AND** the original HTTP 429 and Retry-After 18 are surfaced

#### Scenario: Cancellation during a long upstream cooldown

- **GIVEN** an owner-bound request waiting after HTTP 429 and Retry-After 18
- **WHEN** the downstream request is cancelled during the wait
- **THEN** the wait is cancelled and no additional dispatch occurs
- **AND** admitted leases and usage reservations retain their existing cleanup


#### Scenario: Downstream backpressure consumes part of a capacity-recovery wait

- **GIVEN** a capacity-recovery wait of 30 seconds within a 32-second request budget
- **WHEN** delivery of its keepalive suspends the generator for 25 seconds
- **THEN** the remaining sleep is at most 5 seconds and same-owner retry retains 2 seconds
- **AND** if delivery resumes after the recovery deadline, no extra sleep occurs
