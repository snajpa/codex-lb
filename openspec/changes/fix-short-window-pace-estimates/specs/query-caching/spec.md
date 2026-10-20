## ADDED Requirements

### Requirement: Bounded background short-window calibration
Traffic calibration SHALL run only in the owned background dashboard collector,
reuse its loaded quota histories, and bound request work to the retained calibration
and selected averaging windows for eligible accounts. One grouped sequential query
SHALL return calibration and all-window work/counts without transferring every raw
request. Snapshot versioning SHALL prevent incompatible old/new payload reuse.
HTTP reads SHALL remain snapshot-only and inference readiness independent.

#### Scenario: Several windows share a background refresh
- **WHEN** the dashboard producer prepares all averaging windows
- **THEN** request calibration SHALL execute once on its owned session and return bounded per-account aggregates
- **AND** selecting or refreshing a browser window SHALL NOT execute calibration SQL

#### Scenario: A PostgreSQL server reflects a literal default with a type cast
- **GIVEN** the analytical snapshot table has exactly the intended columns, defaults, constraints and index
- **WHEN** migration retry or downgrade encounters equivalent PostgreSQL literal casts
- **THEN** it SHALL accept that layout without changing intended DDL or unrelated data
- **AND** incompatible defaults, expressions, generated columns and constraints SHALL still be refused before mutation

### Requirement: Bounded mixed-version canonical admission
During a rolling snapshot-contract upgrade, the registry SHALL retain the fixed
global row bound and prior-version pinned last-good snapshots. A current-version
canonical dashboard or admitted report preset SHALL be able to preempt the oldest
idle, unpinned previous-version cache entry when the global registry is full,
without requiring that old entry to be a day old. Active producers SHALL remain
fenced and their entries SHALL NOT be deleted during a refresh.

#### Scenario: Prior-version fresh filter cache fills the registry
- **GIVEN** a full prior-version registry including pinned dashboard and UTC presets plus recent idle unpinned filter entries
- **WHEN** a new-version canonical dashboard registers
- **THEN** the oldest idle unpinned previous-version entry SHALL be preempted
- **AND** both versions' pinned last-good entries and the global row bound SHALL be preserved
- **AND** a read of an evicted old exact key SHALL be honestly warming, not relabelled from the new version
