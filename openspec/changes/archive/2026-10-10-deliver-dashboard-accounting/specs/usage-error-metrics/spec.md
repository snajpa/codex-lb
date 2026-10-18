## ADDED Requirements

### Requirement: Dashboard separates historical costs from recent spend projections
The dashboard MUST distinguish recorded API-equivalent cost over a selected
window from a recent measured run rate and its extrapolation. Run rates MUST
declare their observation window, price/usage coverage and cache assumptions.
Missing prices or usage MUST remain unknown, not zero. Comparisons assuming
uncached input MUST be labelled hypothetical, not billed cost or subscription spend.

#### Scenario: New collection does not imply a seven-day current burn rate
- **GIVEN** usage collection began inside the selected seven-day window
- **WHEN** the dashboard presents current spend projections
- **THEN** the projection uses its declared recent observation interval
- **AND** the seven-day historical average is not labelled as that current rate

#### Scenario: Cached input is accounted exactly once
- **GIVEN** reported input includes a cached-input subset and output includes reasoning
- **WHEN** API-equivalent spend is calculated
- **THEN** uncached and cached input use their verified applicable rates
- **AND** reasoning is not added to output again
- **AND** delivered service tier governs the recorded cost

#### Scenario: Uncached comparison preserves recorded accounting
- **GIVEN** most reported input is cached
- **WHEN** a full-input-price comparison is displayed
- **THEN** the comparison states that it assumes uncached input
- **AND** actual recorded costs and API-key limits are not rewritten by that comparison
