## ADDED Requirements

### Requirement: Movable stream selection prefers paired admission capacity
Stream account selection MUST prefer candidates with both stream and
response-create capacity before fresh selection or movable affinity. This
preference MUST use stream admission's runtime/cap snapshot, preserve eligibility
and ownership scope, and retain the response-create stage's final admission
recheck. If no candidate has both kinds of capacity, existing admission errors
MUST remain.

#### Scenario: Busy soft owner has a usable sibling
- **GIVEN** a prompt-cache owner has stream capacity but full response-create slots
- **AND** an eligible sibling has both kinds of capacity
- **WHEN** an HTTP streaming request selects its upstream account
- **THEN** the sibling serves the request without a local response-create-cap error
- **AND** transient capacity pressure does not replace the existing soft mapping

#### Scenario: Fresh stream binding avoids response-create saturation
- **GIVEN** an unbound stream can choose a full-create account or a usable sibling
- **WHEN** selection runs before response-create admission
- **THEN** it selects the usable sibling

#### Scenario: Hard ownership is not overridden
- **GIVEN** a hard continuity constraint requires a full-create account
- **WHEN** a sibling has spare capacity
- **THEN** selection remains constrained to the required owner

#### Scenario: Every account has full response-create slots
- **GIVEN** no candidate has available response-create capacity
- **WHEN** stream selection runs
- **THEN** existing response-create admission failure behavior is preserved
