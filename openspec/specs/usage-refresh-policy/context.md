# Usage Refresh Policy Context

## Purpose

This context explains how codex-lb derives an account's usage and status, and
how to diagnose disagreements between codex-lb and Codex Desktop or the Codex
CLI quota pill.

codex-lb treats `/wham/usage` as the source of truth for account usage. Other
OpenAI account surfaces can display reset state earlier than `/wham/usage`,
especially during team reset windows, so the dashboard can temporarily show an
account as `rate_limited` even when Codex Desktop says the quota has reset.

## Access and refresh eligibility

A permanent refresh-token failure marks an account `reauth_required` and stops
proactive exchange of that refresh material, while ordinary requests may keep
using the stored access token until its known expiry. Claimless forced refresh
first reads current state: it adopts genuine peer rotation, uses fresh ciphertext
as the guard for unchanged non-terminal material, and fails closed without
exchange when terminal material is unchanged. Before access-token expiry, a
request that reaches this terminal failure may fail over after excluding the
account locally; it does not globally de-route it or move owner-bound continuity
to another account. At known expiry, selection and bridge reuse reject the
account before upstream I/O.

## Upstream Usage Source

codex-lb refreshes account usage by calling:

```http
GET https://chatgpt.com/backend-api/wham/usage
```

The call is made per account on the configured refresh tick, which defaults to
60 seconds. The client lives in
[`app/core/clients/usage.py`](../../../app/core/clients/usage.py), and the
scheduler lives in
[`app/core/usage/refresh_scheduler.py`](../../../app/core/usage/refresh_scheduler.py).

## Pro Max / Pro 500

The upstream identifier is `promax`; the dashboard displays Pro 500. The
account retains its own catalog, including Astra Ultrafast when explicitly
advertised. A Pro-family fallback does not override account-specific model
or service-tier exclusions.

On 2026-09-30, authenticated usage returned a weekly window in the primary
slot, no secondary slot, and percentages rather than an absolute included
allowance. Purchased credits were a separate field. OpenAI's
[Pro tiers](https://help.openai.com/en/articles/9793128-about-chatgpt-pro-tiers)
and [pricing](https://learn.chatgpt.com/docs/pricing) documentation distinguish
plan allowances from API token prices. Relative plan multipliers can support
estimates against a chosen reference, but do not establish an absolute
included-credit grant. Even Pro 200 can have grandfathered or reduced
allowances under the same identifier. The
[Ultrafast consumption multipliers](https://learn.chatgpt.com/codex/agent-configuration/speed)
describe speed-mode consumption, not plan size.

The initial Pro Max import omitted an absolute allowance. The current calibration uses the same modeled credit scale as the Pro Lite 5x tier at a 25x allowance: 5625 primary and 189000 weekly estimated credits. These are quota estimates, not provider-guaranteed monetary credits. Reported percentages and resets remain authoritative for exhaustion, and no absent short-window observation is invented. Scheduling continues to use the existing Pro reference; this calibration does not change admission caps or routing strategy.

For example, Pro at40%, Plus at50% and calibrated Pro Max at20% produce246960 estimated weekly capacity and185220 remaining credits. When calibration is unavailable, the original57960/34020 known subtotal, explicit unquantified count and suppressed fleet forecast still apply. Purchased credits remain separate. The ordinary upstream weekly runway consumes calibrated capacities with its existing observation/freshness/reset rules.
