## ADDED Requirements

### Requirement: Short-window traffic-calibrated credit pace
The dashboard SHALL avoid equating flat rounded quota percentages with the absence
of observed request work. For five- and fifteen-minute selections it SHALL provide
a traffic-calibrated estimate when fresh same-account/same-cycle quota changes and
positive priced request work permit calibration. Any omitted unpriced work SHALL be
counted separately for the calibration and selected windows, disclosed as incomplete
request-work coverage, and SHALL lower confidence. Unknown work SHALL NOT be
coerced into a measured zero. Calibration SHALL use a bounded
retained history, while the forecast traffic SHALL belong to the selected window.
The response and existing card SHALL distinguish the estimate from direct quota
measurement and expose calibration duration and observed request count. Direct
quota observations SHALL remain available separately. All rate-dependent runway
and recommendations SHALL use the same selected rate.

#### Scenario: Heavy five-minute traffic has flat rounded quota counters
- **GIVEN** fresh flat quota observations in five minutes, substantial priced requests in that interval and a valid positive longer calibration episode for every eligible account
- **WHEN** the background dashboard snapshot is published and the card selects five minutes
- **THEN** a positive traffic-calibrated burn estimate SHALL be displayed with its basis and request count
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
- **THEN** selected-window and calibration-window omitted counts SHALL be exposed and displayed
- **AND** confidence SHALL be low, the rate SHALL be labelled an estimate, and omitted work SHALL NOT be presented as zero consumption
- **AND** an all-unpriced selected window SHALL NOT fabricate a calibrated rate
