## ADDED Requirements

### Requirement: Equivalent local reset-credit merge revisions are remapped

The migration system SHALL remap the exact legacy revision
`20260716_010000_merge_reset_credit_and_retention_heads` to the schema-equivalent
upstream revision
`20260717_000000_merge_retention_and_reset_credit_display_heads` before applying
later migrations. The remap MUST NOT accept any other unknown revision.

#### Scenario: Production local merge upgrades to current head

- **GIVEN** a database schema contains both reset-credit display and dashboard
  retention migrations
- **AND** `alembic_version` contains the local merge revision
- **WHEN** the migration runner upgrades the database to head
- **THEN** it remaps the equivalent merge revision
- **AND** applies every later upstream migration exactly once
- **AND** finishes with a single current Alembic head

#### Scenario: Unrelated unknown revision remains fail-closed

- **GIVEN** `alembic_version` contains an unknown revision other than the exact
  local merge revision
- **WHEN** migration state is inspected or upgraded
- **THEN** the revision remains classified as unknown
- **AND** the migration runner requires manual intervention instead of stamping
  it as the upstream merge
