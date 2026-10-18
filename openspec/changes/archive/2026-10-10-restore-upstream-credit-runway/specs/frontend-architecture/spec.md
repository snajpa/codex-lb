## ADDED Requirements
### Requirement: Preserve familiar upstream dashboard layout
The dashboard SHALL retain the upstream StatsGrid, usage-donut and WeeklyCreditsPaceCard layout and styling. It SHALL NOT render separate full-width quota-runway or API-spend sections. The Active Conversations overview statistic SHALL remain omitted and all account-list rows SHALL remain in normal document flow without a capped inner vertical scroller. Any supplemental estimate SHALL occupy the existing stat metadata, not a new layout section.

#### Scenario: Calibrated account pool uses existing projection
- **GIVEN** calibrated Pro Max accounts with fresh weekly observations and known reset timestamps
- **WHEN** the dashboard consumes the overview and projections
- **THEN** the existing weekly credit projection card is rendered with credit pace and runway
- **AND** no added full-width forecast sections or conversation statistic appears
- **AND** every account row can be reached through ordinary document scrolling

## MODIFIED Requirements
### Requirement: Truthful Pro Max usage presentation

The dashboard SHALL display `promax` as Pro 500 and retain its observed
percentage usage. Estimated-credit subtotals SHALL visibly identify
unquantified accounts. A window containing only unquantified accounts
SHALL indicate unknown allowance rather than zero or exhausted allowance.
Incomplete weekly coverage SHALL suppress fleet credit forecasts before
using retained projections or local fallback calculations.

#### Scenario: Mixed dashboard quota
- **GIVEN** the Pro Max credit calibration is unavailable
- **WHEN** a reported Pro Max weekly window is present alongside known plans
- **THEN** its observed remaining percentage is visible
- **AND** the subtotal excludes it explicitly
- **AND** no complete-fleet runway is presented

#### Scenario: Stale forecast cannot conceal incomplete coverage
- **WHEN** old forecast projections exist and current weekly coverage is incomplete
- **THEN** the dashboard does not resurrect a fleet forecast from those projections
- **AND** the unknown allowance explanation remains visible on desktop and mobile

#### Scenario: Search the displayed Pro Max plan
- **WHEN** an operator searches accounts by `Pro 500` or `promax`
- **THEN** the Pro Max account remains selectable
- **AND** the stored plan identifier is unchanged

### Requirement: Percentage quota burn remains useful without credit allowance
The quota-estimate API MUST retain explicitly labelled percentage-per-hour burn and account-level runway without requiring an absolute credit allowance. Unknown rates MUST remain distinct from measured zero. The dashboard MUST retain the existing upstream credit/runway card and MUST NOT add a separate percentage-runway section. Missing calibration MUST NOT fabricate credit totals or whole-pool forecasts.

#### Scenario: Pro Max with unknown credits has percentage estimates
- **GIVEN** fresh same-window percentage observations exist for a Pro Max account
- **AND** its absolute included-credit allowance is unknown
- **WHEN** quota estimates are requested through the existing dashboard API
- **THEN** measured percentage burn and account runway are returned with their units
- **AND** absolute credits and account-equivalent credit forecasts remain unknown

#### Scenario: A reset invalidates the previous rate
- **GIVEN** recent observations straddle a quota reset
- **WHEN** percentage burn is computed
- **THEN** pre-reset consumption is excluded from the current-window rate
- **AND** insufficient current-window observations show an unknown rate
