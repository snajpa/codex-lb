## Why

Stream selection checks stream capacity, but ordinary prompt-cache and unbound
requests can still choose an account whose response-create slots are full while
another eligible account has room. The next admission then fails locally.

## What Changes

- Prefer candidates with room for both the stream and its response-create stage
  before honoring movable affinity or making a fresh selection.
- Keep hard continuity and non-spillable session ownership constrained.
- Preserve current capacity errors when no candidate can satisfy both stages.
- Reuse existing in-flight weighting and soft pressure thresholds for proactive
  load-before-affinity tuning; add no settings, schema or transport changes.

## Impact

Affected owner: proxy load-balancer sticky and unbound selection. Existing lease
reservation, final admission rechecks, scope, health and quota gates remain intact.
