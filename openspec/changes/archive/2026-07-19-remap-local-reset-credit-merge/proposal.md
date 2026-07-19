## Why

The production SQLite database was deployed with the local no-op merge revision
`20260716_010000_merge_reset_credit_and_retention_heads`. Upstream later merged
the same two parent revisions under
`20260717_000000_merge_retention_and_reset_credit_display_heads`. A current
upstream image therefore classifies the production revision as unknown and
cannot apply later reliability migrations even though the schemas are
equivalent.

## What Changes

- Remap the exact local merge revision to the equivalent upstream merge
  revision before Alembic upgrades.
- Cover migration-state inspection and a full upgrade from the local revision
  to current head.
- Keep the mapping narrow: no other unknown revision is accepted or stamped.

## Impact

Existing deployments stamped with the local reset-credit merge can upgrade to
current upstream migration heads without manual database edits. Fresh installs
and databases at any other revision are unchanged.
