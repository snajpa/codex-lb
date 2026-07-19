## ADDED Requirements

### Requirement: Anchored zero-progress HTTP bridge gates retire within the configured bound

An HTTP bridge request that owns a response-create gate but has received no
`response.created` or other response lifecycle progress MUST remain eligible
for stuck-gate retirement after the configured threshold even when it carries
`previous_response_id` or an explicit turn-state continuity anchor and the
upstream socket remains open. Anchor presence alone MUST NOT be treated as
upstream progress. Retirement and transparent fresh-bridge submission MUST
retain the existing no-output, no-ambiguous-submission, deadline, and account
ownership safeguards.

#### Scenario: Silent anchored gate owner is retired

- **GIVEN** an anchored HTTP bridge request owns the response-create gate
- **AND** its upstream socket remains open without any response lifecycle event
- **AND** its gate wait age exceeds the configured retirement threshold
- **WHEN** another request times out waiting for that gate
- **THEN** the proxy retires the silent bridge and releases its lifecycle state

#### Scenario: Fresh request recovers after anchored retirement

- **GIVEN** a definitively unsubmitted HTTP bridge waiter discovers and retires a silent anchored gate owner
- **WHEN** the waiter remains within its original deadline and its owner constraints can be preserved
- **THEN** the proxy submits it once on a fresh bridge without requiring a client reconnect

#### Scenario: Anchored response progress remains protected

- **GIVEN** an anchored gate owner has received `response.created` or another response lifecycle event
- **WHEN** a later gate waiter times out
- **THEN** anchor-independent stale retirement does not classify that progressing request as zero-progress
