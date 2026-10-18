## MODIFIED Requirements

### Requirement: Dashboard and report metrics count distinct conversations
Dashboard overview statistics MUST NOT render an Active Conversations card.
Report summaries MUST retain their distinct non-empty conversation count card
immediately after Requests. A conversation spanning days MUST count once per
applicable daily row and once in the report-wide total. Existing conversation
views, filters and API fields MUST remain available.

#### Scenario: Dashboard count deduplicates IDs
- **GIVEN** overview metrics contain repeated, null and empty conversation IDs
- **WHEN** any overview timeframe is returned and rendered
- **THEN** the API retains its distinct non-empty count and no Active Conversations statistic is shown
- **AND** conversation views and request filtering remain usable

#### Scenario: Report summary and daily counts use distinct IDs
- **GIVEN** one conversation spans two report days and another appears once
- **WHEN** report metrics are rendered
- **THEN** the summary counts two conversations overall
- **AND** daily rows retain their applicable distinct counts

### Requirement: Dashboard conversation trends are bucketed distinctly
The overview API MUST retain bucketed distinct non-empty conversation counts,
with missing buckets zero-filled and repeated IDs counted once per bucket.
The timeframe summary MUST remain an exact distinct aggregate, not a sum of
buckets. Removing the dashboard count card MUST NOT remove these API contracts.

#### Scenario: Conversation trend de-duplicates model groups
- **GIVEN** repeated IDs occur across models in one bucket
- **WHEN** overview trends are returned
- **THEN** that bucket counts each ID once
- **AND** the series has every configured bucket with absent counts zero-filled

#### Scenario: Empty conversation buckets are zero-filled
- **GIVEN** the selected timeframe has no valid IDs in one or more buckets
- **WHEN** overview conversation trends are returned
- **THEN** each empty bucket remains zero-filled

## ADDED Requirements

### Requirement: Dashboard account list uses page scrolling
The dashboard account table MUST render all supplied account rows without a
fixed or maximum body height or inner vertical scroll limit. It MUST retain
sorting, actions, responsive layout and horizontal overflow where required.
Normal page scrolling MAY be used to reach lower rows.

#### Scenario: More than eight accounts remain visible in document flow
- **GIVEN** the dashboard receives twelve accounts
- **WHEN** account list view is rendered
- **THEN** all twelve rows exist in normal document flow
- **AND** the table body has no capped height or vertical scroll container

### Requirement: Percentage quota burn remains useful without credit allowance
When quota observations support a measured percentage rate, the dashboard MUST
show explicitly labelled percentage-per-hour burn and account-level runway
without requiring an absolute credit allowance. Unknown rates MUST remain
distinct from measured zero. Credit totals and whole-pool forecasts MUST NOT be
fabricated from those percentages.

#### Scenario: Pro Max with unknown credits has percentage estimates
- **GIVEN** fresh same-window percentage observations exist for a Pro Max account
- **AND** its absolute included-credit allowance is unknown
- **WHEN** quota estimates are rendered
- **THEN** measured percentage burn and account runway are shown with their units
- **AND** absolute credits and account-equivalent credit forecasts remain unknown

#### Scenario: A reset invalidates the previous rate
- **GIVEN** recent observations straddle a quota reset
- **WHEN** percentage burn is computed
- **THEN** pre-reset consumption is excluded from the current-window rate
- **AND** insufficient current-window observations show an unknown rate
