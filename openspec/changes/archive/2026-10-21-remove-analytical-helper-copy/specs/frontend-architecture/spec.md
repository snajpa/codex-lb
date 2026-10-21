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
- **AND** SHALL NOT add rounded-quota explanatory commentary

#### Scenario: The server cannot measure weekly pace
- **WHEN** the current overview explicitly reports unavailable pace
- **THEN** the selectable card MUST preserve that unavailable state for every averaging window
- **AND** MUST NOT substitute a cumulative-week local estimate or retained projection under the 3 h label

#### Scenario: Retained one-minute preference
- **WHEN** the browser has a persisted one-minute averaging selection
- **THEN** the dashboard MUST select and persist five minutes instead
- **AND** an unset preference MUST still default to three hours

#### Scenario: Reset-aware depletion versus a counterfactual
- **WHEN** the server supplies reset-aware projection metadata
- **THEN** the card MUST display that modeled depletion time, or no depletion in the modeled horizon
- **AND** legacy no-reset ETAs MUST be explicitly qualified when projection metadata is absent
- **AND** any displayed recommended load MUST be rounded down, never above the feasible load

#### Scenario: Every window is ready before its button is clicked
- **WHEN** the dashboard loads its background projections
- **THEN** it MUST eagerly cache values for all four averaging windows
- **AND** selecting an already-loaded window MUST update its values immediately without a new request or loading flash
- **AND** a selection made while the shared request is pending MUST be honored when it completes
- **AND** refresh and failure MUST preserve correct window identity and the existing polling/hidden-tab policy

### Requirement: Prepared analytical views distinguish cache state from data coverage
Dashboard and Reports SHALL consume published background results and display
a concise delayed-update state only when data is stale or refresh has failed, without starting measurement on page refresh. Normal fresh results SHALL NOT show prepared timestamps, refresh cadence or background-refresh commentary. Detailed freshness and retained-history metadata SHALL remain available in the API without extra UI history paragraphs. Cold preparation,
refresh failure, actual insufficient observations and unsupported historical
coverage SHALL be distinct states. Cached data for another window, date range,
filter or timezone SHALL NOT be relabeled as the requested view.

#### Scenario: A report refresh is still running
- **GIVEN** a complete same-key report snapshot
- **WHEN** its scheduled refresh is running or has failed
- **THEN** the page SHALL retain that result and show a concise delayed-update state only when stale or failed; a fresh in-progress refresh SHALL remain visually quiet

#### Scenario: An old connection returns an incompatible generation
- **WHEN** a retained connection returns a response without the selected averaging contract
- **THEN** the system SHALL NOT claim that real quota samples are missing
- **AND** rolling-deployment verification SHALL cover this retained-connection path

### Requirement: Short-window traffic-calibrated credit pace
The dashboard SHALL avoid equating flat rounded quota percentages with the absence
of observed request work. For five- and fifteen-minute selections it SHALL provide
a traffic-calibrated estimate when fresh same-account/same-cycle quota changes and
positive priced request work permit calibration. Any omitted unpriced work SHALL be
counted separately for the calibration and selected windows in the API as incomplete
request-work coverage, and SHALL lower confidence. Unknown work SHALL NOT be
coerced into a measured zero. Calibration SHALL use a bounded
retained history, while the forecast traffic SHALL belong to the selected window.
The response SHALL distinguish the estimate from direct quota
measurement and expose calibration duration and observed request count. The existing card SHALL retain its approximate numeric formatting without calibration, request-count, omitted-work or rounded-quota explanatory paragraphs. Direct
quota observations SHALL remain available separately. All rate-dependent runway
and recommendations SHALL use the same selected rate.

#### Scenario: Heavy five-minute traffic has flat rounded quota counters
- **GIVEN** fresh flat quota observations in five minutes, substantial priced requests in that interval and a valid positive longer calibration episode for every eligible account
- **WHEN** the background dashboard snapshot is published and the card selects five minutes
- **THEN** a positive traffic-calibrated burn estimate SHALL be displayed with approximate numeric formatting; basis and request count SHALL remain API metadata rather than extra UI text
- **AND** the card SHALL NOT claim that the rounded counters directly measured that burn or substitute fifteen-minute traffic under the five-minute label

#### Scenario: Calibration is incomplete or crosses a reset
- **WHEN** an account lacks sufficient fresh same-cycle calibration or request prices
- **THEN** the fleet SHALL NOT fabricate that account's calibrated rate or relabel partial coverage as complete
- **AND** reset, unknown and directly observed zero states SHALL remain distinct

#### Scenario: A longer averaging window is selected
- **WHEN** the operator selects one or three hours
- **THEN** the existing direct quota-window calculation SHALL remain unchanged
- **AND** no retained short-window estimate SHALL appear under the longer selection

#### Scenario: A disconnected request has no final usage counters
- **GIVEN** positive priced work supports a same-cycle estimate but some requests have unknown or unpriced work
- **WHEN** that estimate is displayed
- **THEN** selected-window and calibration-window omitted counts SHALL be exposed in the API without explanatory UI paragraphs
- **AND** confidence SHALL be low, the card SHALL retain approximate numeric formatting, and omitted work SHALL NOT be presented as zero consumption
- **AND** an all-unpriced selected window SHALL NOT fabricate a calibrated rate
