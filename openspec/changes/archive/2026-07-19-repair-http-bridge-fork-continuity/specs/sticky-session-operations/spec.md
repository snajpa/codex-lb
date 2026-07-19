## ADDED Requirements

### Requirement: Durable bridge aliases distinguish lane anchors from process fallback

For HTTP bridge durable lookup, `x-codex-turn-state` and
`previous_response_id` aliases MUST be independent hard continuation anchors.
A session-header alias MUST be treated as broader process-session fallback and
MUST NOT conflict with or override a resolved hard anchor. If both hard anchors
resolve to different durable bridge session identities, the service MUST fail
closed with `continuity_owner_conflict` before upstream dispatch. Diagnostics
for either a genuine hard-anchor conflict or an ignored fallback mismatch MUST
contain only hashed continuity identifiers and MUST NOT expose raw turn states,
response IDs, session headers, or prompt content.

#### Scenario: Fork turn state overrides its parent session header

- **GIVEN** a request carries a turn-state alias for a child fork bridge
- **AND** its session header resolves to a different parent bridge
- **WHEN** the durable HTTP bridge owner is resolved
- **THEN** the child turn-state bridge is selected
- **AND** the broader parent session alias does not produce `continuity_owner_conflict`

#### Scenario: Previous response overrides a broader session header

- **GIVEN** a request carries a previous-response alias for one bridge
- **AND** its session header resolves to a different broader bridge
- **WHEN** the durable HTTP bridge owner is resolved
- **THEN** the previous-response bridge is selected
- **AND** the broader session alias does not veto it

#### Scenario: Conflicting hard anchors still fail closed

- **GIVEN** a request's turn-state alias and previous-response alias resolve to different durable bridge sessions
- **WHEN** the durable HTTP bridge owner is resolved
- **THEN** the service fails with `continuity_owner_conflict` before dispatch
- **AND** diagnostics contain hashes instead of raw continuity values
