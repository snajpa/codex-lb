## ADDED Requirements

### Requirement: GPT-6 Astra API-equivalent usage estimates
The system MUST recognize gpt-6-astra and dated snapshots and estimate USD
costs from recorded input, cached-input and output tokens using Standard rates
of 10, 1 and 50 USD per million tokens. Flex MUST apply half rates.
Fast and priority MUST apply twice the applicable rates. Above 272,000 input
tokens, the full request MUST use twice the input/cache rates and 1.5 times
the output rates. Estimates MUST NOT be represented as measured subscription
charges or as including separately unrecorded cache-write premiums.

#### Scenario: Cached standard request
- **WHEN** Astra uses 100000 input, 80000 cached and 1000 output tokens
- **THEN** the estimated cost is 0.33 USD

#### Scenario: Fast long-context request
- **WHEN** Astra uses 300000 input, 200000 cached and 1000 output tokens at priority tier
- **THEN** the estimated cost is 4.95 USD
