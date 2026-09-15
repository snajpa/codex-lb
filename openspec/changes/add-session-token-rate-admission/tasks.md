# Tasks: add-session-token-rate-admission

## 1. Implementation

- [x] 1.1 Add the disabled-by-default process setting and pass it to the
      existing work-admission controller.
- [x] 1.2 Record a per-session next-admission time from successful
      provider-reported Responses input usage, using the canonical existing
      owner/session-header key.
- [x] 1.3 Reject an early next normal Responses create before account and
      upstream admission with `session_token_rate_limited` and the existing
      local-overload response behavior.
- [x] 1.4 Remove expired cooldown state opportunistically; preserve no-session,
      no-usage, compact, and disabled-policy behavior.

## 2. Regression coverage

- [x] 2.1 Prove disabled, no-session, and no-usage paths are unchanged.
- [x] 2.2 Prove an observed-input cooldown rejects the same session with the
      stable local-overload code and the established Retry-After behavior,
      without blocking a different session.
- [x] 2.3 Prove the public Responses streaming path does not call upstream or
      acquire account response-create capacity for a rate-blocked attempt.

## 3. Verification

- [x] 3.1 Run focused proxy admission/Responses tests and Ruff.
- [ ] 3.2 Run strict OpenSpec validation when the repository-provided command
      is available; `openspec` is absent from this checkout's PATH today.
- [x] 3.3 Record that no runtime environment, routing, bridge TTL, or affinity
      setting was changed during implementation.