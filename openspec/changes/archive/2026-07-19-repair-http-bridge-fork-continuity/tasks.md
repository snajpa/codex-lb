## 1. Contract and resolver

- [x] 1.1 Classify turn-state and previous-response aliases as hard anchors and session-header as fallback.
- [x] 1.2 Preserve fail-closed behavior for genuine hard-anchor conflicts.
- [x] 1.3 Add hashed conflict/fallback diagnostics without raw continuity values.

## 2. Gate lifecycle

- [x] 2.1 Retire zero-progress anchored gate owners after the configured threshold.
- [x] 2.2 Preserve response-progress, drain, and ambiguous-submission safeguards.

## 3. Regression coverage

- [x] 3.1 Cover fork turn-state plus broader parent session-header aliases at the HTTP bridge route.
- [x] 3.2 Cover conflicting turn-state and previous-response aliases.
- [x] 3.3 Cover anchored stale-gate retirement and fresh-session recovery at the HTTP bridge route.
- [x] 3.4 Run focused tests, broader bridge/proxy tests, Ruff, strict OpenSpec validation, and diff checks.

## 4. Production acceptance

- [x] 4.1 Back up the live database and validate the candidate on alternate ports.
- [x] 4.2 Drain/release the old owner before atomic cutover and verify one active ring member.
- [x] 4.3 Resume a pre-cutover session and exercise shared-parent subagent lanes.
- [x] 4.4 Pass at least eight concurrent multi-turn/resumed Sol/max clients with no reconnect, SSE idle timeout, 502, 503, stale gate, or false no-account selection.
- [x] 4.5 Correct durable host state and investigation documentation from observed production evidence.
