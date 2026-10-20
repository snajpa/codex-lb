## Shared background read model
- [x] Add durable normalized snapshot storage and migration/compatibility coverage.
- [x] Reuse fenced scheduler leases without sharing the older metadata-leader identity.
- [x] Own bounded background jobs/sessions, atomic publication and last-good retention.
- [x] Make dashboard and report HTTP reads snapshot-only, including cold/stale paths.

## Proactive views and truthful UI
- [x] Warm all averaging values and dashboard ranges independently of browser visits.
- [x] Warm 7/30/90-day report presets about every five minutes for known timezones.
- [x] Preserve filters/DST/coverage; distinguish warming from genuinely missing samples.
- [x] Show freshness and retain same-key last-good values without stale relabeling.
- [x] Cover retained-browser handoff and repeated five-minute page refresh.

## Cheap refresh and qualification
- [x] Measure cold/steady work and reuse existing rollups; defer faster cadence and additional incremental optimization until the deployable baseline is verified.
- [x] Verify report totals, distincts and available timing metrics against exact controls.
- [x] Prove cancellation/lease-loss/partial-failure/restart and bounded query behavior.
- [x] Run scoped backend/frontend/real-MariaDB/build/browser/spec checks and review.
- [x] Qualify immutable deployment, cached normal-address reads and forty-session coexistence.
- [ ] Publish matched fork source, preserve rollback and archive only verified work.
