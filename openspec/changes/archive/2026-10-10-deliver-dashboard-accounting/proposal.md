## Why

Pro Max quota observations have no absolute credit allowance, but useful measured
percentage burn and account runway should remain visible. The dashboard also
shows an unwanted conversation statistic and caps the account list at eight rows.
Its selected-window spend average is easily mistaken for a current run rate,
especially when collection began inside a seven-day window and cache/tier
assumptions differ from another API workload.

## What Changes

- Integrate pinned upstream Pro Max support without replacing existing database
  and proxy fixes or inventing included-credit allowances.
- Add explicitly percentage-based quota burn/account-runway data and display.
- Omit the Active Conversations dashboard statistic, retaining APIs and reports.
- Display every dashboard account row without a capped inner vertical scroller.
- Audit pricing and show a measured recent API-equivalent spend run rate with
  observation/coverage and cache assumptions distinct from historical totals.

## Impact

Dashboard producer, schemas and frontend consumers, supported Pro Max surfaces,
and relevant tests/specifications. No new settings, schema migration, billing
mutation, navigation item or conversation-feature removal is intended.
