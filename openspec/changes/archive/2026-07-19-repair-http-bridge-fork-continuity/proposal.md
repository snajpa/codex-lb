# Repair HTTP bridge fork continuity

## Why

Real Codex follow-ups and subagent lanes can carry a turn-state token that
identifies one fork while also carrying the parent process `session_id`.
Durable bridge lookup currently treats the turn-state alias, previous-response
alias, and broader session-header alias as equally hard evidence. When the fork
and parent legitimately have distinct durable bridge rows, the proxy returns
`continuity_owner_conflict` before dispatch instead of following the fork's
specific anchor.

Separately, a pending HTTP bridge request with `previous_response_id` or an
explicit turn-state anchor is exempt from stuck-gate retirement while its
upstream socket remains open. A silent socket can therefore hold the
response-create gate far beyond the configured retirement threshold, causing
downstream SSE idle timeouts and reconnect loops.

## What Changes

- Resolve turn-state and previous-response durable aliases as independent hard
  anchors and fail closed when those two resolve to different bridge sessions.
- Treat a session-header durable alias as a broader fallback. Once either hard
  alias resolves, a different session-header row cannot veto it.
- Emit hashed diagnostics for both genuine hard-anchor conflicts and ignored
  broader fallback mismatches without logging raw continuity tokens.
- Apply zero-progress stuck-gate retirement to anchored requests even while the
  upstream socket remains open, retaining all response-progress safeguards.
- Add regressions at the HTTP `/backend-api/codex/responses` surface for fork
  alias precedence and anchored stale-gate recovery.

## Impact

- Affected capabilities: `sticky-session-operations` and
  `proxy-admission-control`.
- Existing forked and resumed Codex sessions can continue through their most
  specific durable anchor instead of entering a 502 reconnect loop.
- Silent anchored bridge requests release their gate after the configured
  bound, allowing a fresh bridge to serve later work.
- Genuine turn-state versus previous-response conflicts remain fail-closed.
