# Add session token-rate admission

## Why

A single valid session can create a cost-heavy cache-residency failure even when
routing, session-header affinity, and bridge TTL are correct. On September 15,
2026, session `df366def465db13684cca49ccec6d0b3` processed about 20.06 million
input tokens in under 30 minutes, with repeated warm/cold cache flips. Global
response-create concurrency does not limit that session's input-token cadence.

The mitigation must be reversible and narrowly local: pace only a configured
session header after the proxy has observed real provider usage. It must not
change account selection, affinity, prompt-cache keys, bridge TTLs, request
content, or the live deployment configuration.

## What Changes

- Add an opt-in process-local setting,
  `proxy_session_input_token_rate_per_minute`; `0` remains the default and
  disables the policy.
- For a normal Responses create carrying an existing canonical session key,
  reject a new request with the existing local overload envelope until the
  cooldown recorded from the prior successful response's `input_tokens` has
  elapsed.
- Arm the cooldown only after a successful terminal response supplies
  provider-reported input usage. Requests with no session key or no usable
  input usage remain unchanged.
- Keep the limiter in-process and monotonic-clock based. Restarting the proxy
  clears pending cooldowns; no durable state, database migration, affinity
  change, or new routing behavior is introduced.

## Capabilities

### Modified Capabilities

- `proxy-admission-control`: configured sessions may receive explicit local
  token-rate backpressure before account and upstream response-create work.

## Impact

- Code: proxy settings, `WorkAdmissionController`, and normal streaming
  response-create finalization.
- Tests: controller timing plus a Responses ingress regression proving the
  blocked attempt does not reach upstream admission.
- Operations: no live setting is changed by this work. A later separately
  authorized experiment may set one environment value and can roll back by
  restoring `0`/removing that value and restarting the candidate only.