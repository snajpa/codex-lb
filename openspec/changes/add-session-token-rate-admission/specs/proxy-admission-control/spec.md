# proxy-admission-control Delta

## ADDED Requirements

### Requirement: Configured session input-token rates receive local admission backpressure

When `proxy_session_input_token_rate_per_minute` is positive, the proxy MUST
track the canonical existing session identity for normal Responses creates after
a successful terminal response reports a positive `input_tokens` value. The
next normal create with that same identity MUST be rejected locally until the
observed input-token interval at the configured per-minute rate has elapsed.

The rejection MUST occur before account response-create leasing and upstream
response creation. It MUST use HTTP 429, the existing OpenAI-style local
rate-limit envelope, and stable code `session_token_rate_limited`. It MUST NOT
be reported as an upstream rate limit or alter account/affinity selection.

The limiter is process-local and monotonic-clock based. `0` disables it. A
missing canonical session identity, absent/zero usage, compact traffic, and a
process restart MUST leave no pending rate cooldown.

#### Scenario: Disabled setting preserves admission

- **GIVEN** `proxy_session_input_token_rate_per_minute` is 0
- **WHEN** normal Responses requests share a session identity
- **THEN** session-token admission adds no rejection or delay
- **AND** existing global and account admission behavior remains authoritative

#### Scenario: Observed usage paces the next same-session request

- **GIVEN** a successful normal Responses response for session `S` reports
  400,000 input tokens
- **AND** the configured session rate is 400,000 input tokens per minute
- **WHEN** another normal Responses create for `S` arrives 5 seconds later
- **THEN** the proxy rejects it locally before account/upstream admission
- **AND** the error code is `session_token_rate_limited`
- **AND** the existing local-overload `Retry-After` behavior applies

#### Scenario: A different session remains eligible

- **GIVEN** a cooldown is pending for session `S`
- **WHEN** a normal Responses create for distinct session `T` arrives
- **THEN** `T` follows ordinary admission
- **AND** `S`'s cooldown does not consume global or account capacity

#### Scenario: Missing usage does not invent a token charge

- **GIVEN** a terminal Responses result has no usable input-token usage
- **WHEN** a later normal Responses create carries the same session identity
- **THEN** session-token admission does not reject it from that result

#### Scenario: Restart clears process-local cooldowns

- **GIVEN** a process has recorded a session-token cooldown
- **WHEN** the proxy process restarts
- **THEN** the new process has no retained cooldown for that session
- **AND** no database or durable session state is consulted for the policy