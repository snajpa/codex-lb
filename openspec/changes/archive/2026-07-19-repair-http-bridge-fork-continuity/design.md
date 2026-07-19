# Design: Repair HTTP bridge fork continuity

## Context

The Codex client may reuse one parent `session_id` across parallel child
threads while giving each child its own `prompt_cache_key`, thread identity,
and accepted `x-codex-turn-state`. The session header describes the broader
client process lineage; the turn state and `previous_response_id` identify the
specific continuation lane.

Durable bridge rows intentionally model those lanes separately. Comparing all
three alias kinds as equivalent identities turns valid parent/fork topology
into a false owner conflict.

## Alias Classification

The coordinator resolves all supplied aliases in one database session, then
classifies the results:

- `turn_state` and `previous_response_id` are hard anchors.
- If both hard anchors resolve and their durable session identities differ,
  lookup fails with `continuity_owner_conflict`.
- If at least one hard anchor resolves without a hard-hard conflict, the most
  specific result is returned in turn-state then previous-response order.
- `session_header` is consulted only as the durable fallback when neither hard
  anchor resolves. A differing session-header result is diagnostic context,
  not a veto.
- Existing canonical-key and legacy latest-field fallbacks remain unchanged
  when no alias resolves.

Diagnostics include alias kind and truncated SHA-256 digests of supplied alias
values and resolved durable session IDs. They never include raw turn states,
response IDs, session headers, or prompt content.

## Stale Gate Retirement

Anchor presence does not prove upstream progress. The stale predicate therefore
uses the same protocol milestones for anchored and unanchored HTTP requests:

- the request acquired the response-create gate and still awaits
  `response.created`;
- no response ID, response event, or response-created latency exists;
- the request is not a skipped/internal log state; and
- gate wait age meets the configured threshold.

The existing response lifecycle, downstream ambiguity, drain, and replacement
submission guards continue to decide whether a session may be retired and
whether an unsubmitted waiter can move to a fresh bridge.

## Deployment

Build and validate a candidate on alternate ports using the production data
volume only after a locked database backup. Before redirecting live traffic,
drain and release the old instance's durable ownership so only the candidate
owns active leases. Acceptance must include a session established before
cutover and resumed after it, real shared-parent subagent behavior, and at least
eight concurrent `gpt-5.6-sol` clients at max reasoning across multiple turns
and resumes.

## Rollback

Keep the prior container stopped with restart disabled and retain the matching
database backup. Roll back atomically through the scoped live-port redirect;
do not run two non-forwarding active bridge owners against the same volume.
