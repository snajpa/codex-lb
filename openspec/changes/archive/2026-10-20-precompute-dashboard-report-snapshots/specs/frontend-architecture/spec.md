## ADDED Requirements

### Requirement: Prepared analytical views distinguish cache state from data coverage
Dashboard and Reports SHALL consume published background results and display
freshness without starting measurement on page refresh. Cold preparation,
refresh failure, actual insufficient observations and unsupported historical
coverage SHALL be distinct states. Cached data for another window, date range,
filter or timezone SHALL NOT be relabeled as the requested view.

#### Scenario: A report refresh is still running
- **GIVEN** a complete same-key report snapshot
- **WHEN** its scheduled refresh is running or has failed
- **THEN** the page SHALL retain that result and show its age or delayed-update state

#### Scenario: An old connection returns an incompatible generation
- **WHEN** a retained connection returns a response without the selected averaging contract
- **THEN** the system SHALL NOT claim that real quota samples are missing
- **AND** rolling-deployment verification SHALL cover this retained-connection path

### Requirement: Dashboard HTTP pools do not retain retired backend generations
HTTP/1.x dashboard pages, assets and API responses SHALL close their connection
after completing the response. Inference, internal bridge, health, metrics, SCIM
and WebSocket traffic SHALL retain their existing transport behavior.

#### Scenario: A completed dashboard response precedes a backend switch
- **WHEN** the next dashboard request follows an atomic backend selection
- **THEN** it SHALL establish a connection to the selected generation rather than reuse an old dashboard pool

#### Scenario: An inference response is still streaming
- **WHEN** dashboard connection retirement is enabled
- **THEN** inference headers and body streaming SHALL remain unchanged
- **AND** HTTP/2 responses SHALL NOT receive forbidden connection headers
