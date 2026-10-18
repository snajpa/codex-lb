# Honor upstream burst Retry-After

## Why

Owner-bound HTTP 429 recovery caps the entire retry delay at ten seconds,
including a longer upstream Retry-After. This redispatches a request before
the upstream permits it and can exhaust the bounded retry count needlessly.

## What changes

Cap only the locally generated exponential delay. Preserve the upstream
Retry-After as a minimum wait, bounded by the existing request budget. Keep
account ownership, retry counts, cancellation, held startup headers, and
usage/health settlement unchanged. Add service-boundary regression coverage.

## Impact

The HTTP streaming retry path and sticky-session-operations specification.
No settings, schema, dependencies, account migration, or client restart needed.
