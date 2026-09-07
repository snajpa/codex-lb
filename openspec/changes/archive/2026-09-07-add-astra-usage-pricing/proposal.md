# Astra usage pricing

## Why
The deployed request log records GPT-6 Astra token usage but no USD estimate.

## What Changes
Recognize Astra and dated Astra snapshots using OpenAI Platform API prices.
Apply Standard 10/1/50 USD per million input/cache/output tokens, Flex at half
rates, Fast/Priority at twice rates, and full-request 2x input/cache and 1.5x
output above 272,000 input tokens, including Fast long-context calls.
These are API-equivalent estimates. The stored usage does not distinguish
cache writes and does not measure subscription-credit deductions.

## Impact
Pricing calculation and regression coverage. No schema or routing change.
Historical NULL Astra costs will be filled on the isolated deployment copy,
with corresponding existing lifetime rollup cost deltas.
