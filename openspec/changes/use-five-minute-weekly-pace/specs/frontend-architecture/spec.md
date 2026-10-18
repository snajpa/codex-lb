## MODIFIED Requirements

### Requirement: Weekly credit burn averaging controls
The weekly credit pace card MUST offer accessible 5 min, 15 min, 1 h and 3 h
buttons directly in the card, defaulting to 3 h and remembering the choice in
browser-local preferences. Selection MUST update burn, runway and rate-dependent
recommendations together without changing other dashboard timeframes or settings.

#### Scenario: Switching while a request is pending
- **WHEN** the operator switches from 3 h to 5 min and then to 15 min
- **THEN** the controls remain available
- **AND** only a response for 15 min may populate the selected card
- **AND** loading or failure MUST NOT relabel old-window values as 15 min

#### Scenario: No observed quota change
- **WHEN** a selected window has no positive burn or insufficient samples
- **THEN** the card MUST distinguish no observed change from unavailable data
- **AND** MUST NOT claim a measured safe runway
- **AND** MUST explain rounded quota percentages make short windows noisy

#### Scenario: The server cannot measure weekly pace
- **WHEN** the current overview explicitly reports unavailable pace
- **THEN** the selectable card MUST preserve that unavailable state for every averaging window
- **AND** MUST NOT substitute a cumulative-week local estimate or retained projection under the 3 h label

#### Scenario: Retained one-minute preference
- **WHEN** the browser has a persisted one-minute averaging selection
- **THEN** the dashboard MUST select and persist five minutes instead
- **AND** an unset preference MUST still default to three hours
