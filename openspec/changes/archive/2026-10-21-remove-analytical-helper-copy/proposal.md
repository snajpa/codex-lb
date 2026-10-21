## Why
The operator requested removing unsolicited explanatory UI copy, including snapshot timestamps/cadence, traffic/calibration prose, unpriced-work warnings and rounded-quota notes, and auditing related additions.

## What Changes
- Remove the normal-operation explanatory paragraphs from Dashboard and Reports, including retained-history commentary.
- Keep existing numeric values, controls, estimate formatting and concise error/unavailable states.
- Keep server computation and API metadata unchanged; do not relocate the removed prose into tooltips or accessibility-only text.

## Capabilities
### New Capabilities
None.
### Modified Capabilities
- `frontend-architecture`: minimal analytical presentation; API-only detailed calibration/coverage metadata rather than unsolicited UI commentary.

## Impact
Frontend components, localized strings and UI regressions only. No backend, database, native, authentication or dependency changes.
