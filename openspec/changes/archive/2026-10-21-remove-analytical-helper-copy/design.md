## Context
The existing frontend renders snapshot/calibration details as paragraphs. The operator explicitly rejected this added copy. See proposal.md for scope.

## Goals / Non-Goals
**Goals:** remove the added commentary without changing data or core layout.
**Non-Goals:** computation, API/schema, dependencies, native handling or unrelated older explanatory UI.

## Decisions
- Fresh snapshot status renders nothing; keep only concise existing delayed/warming signals for exceptional states.
- Delete the extra pace paragraphs and Reports retained-history paragraph plus their unused locale keys in all three locales. Do not hide the prose in titles, tooltips or screen-reader text.
- Preserve existing pre-change Reports speed-unavailable handling and approximate rates, error/retry states and averaging controls.

## Risks / Trade-offs
Less visible calculation detail is intentional; the API retains it. Regression tests cover absent copy, unchanged numeric values and exceptional states.

## Migration Plan
Build/test the frontend, review the diff, publish to the user fork and deploy immutable assets through existing two-backend controls. Preserve selected owners and rollback artifact; no database migration.
