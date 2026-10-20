## Why
Five-minute traffic remains substantial while provider quota percentages stay at
whole-percentage precision. Treating a flat rounded counter as a precise zero
makes the short-window forecast alternate between no burn and large quota steps.
The same delivery also exposed dialect-equivalent PostgreSQL defaults rejected by
the analytical snapshot migration's strict existing-layout validator.

## What changes
- Estimate short-window credit burn from actual recent priced request work, with
  an empirical per-account calibration against retained same-cycle quota changes.
- Label traffic-calibrated estimates, calibration span and observed request count;
  keep raw quota observations distinct and preserve unknown/zero semantics.
- Keep all computation in the existing bounded background snapshot producer.
- Correct PostgreSQL reflection compatibility without changing migration identity,
  applied DDL, strict incompatible-layout rejection or persisted accounting.

## Impact
Dashboard service/repository/pace calculation and existing card metadata; snapshot
schema fencing; additive response metadata; migration validation and regressions.
No new runtime dependency, configuration knob, external service or accounting DDL.
