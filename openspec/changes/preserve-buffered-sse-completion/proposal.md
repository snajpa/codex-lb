## Why

The Python HTTP fallback can raise an incomplete-transfer error before its consumer drains body bytes already received from the socket. A complete final SSE event larger than one body-read chunk can therefore be discarded and replaced by a synthetic transport failure. The same response succeeds when the peer closes slightly later. Valid response completion and usage must not depend on that scheduling difference.

## What Changes

- Preserve already-buffered aiohttp body chunks after an incomplete-transfer error, in order, through the existing SSE parser.
- Stop only when the existing response consumer validates a terminal event; propagate the original transport error when received data contains no complete terminal.
- Cover direct and routed Python streaming paths, true truncation, terminal error events, cancellation, and resource settlement at real TCP and route boundaries.
- Classify JSON before header/native shortcuts and validate terminal payloads with the existing event contract before settlement; no SSE header is completion proof.
- Reuse the parsed payload through the existing carrier so legitimate deltas remain byte-identical without repeated JSON decoding.
- Keep the locked native egress helper's terminal classification equivalent to the corrected portable fallback; native availability must not conceal a fallback regression.

## Impact

The change affects HTTP body consumption and terminal classification, not account selection, replay eligibility, request identity, authentication, quotas, or public response schemas. It does not manufacture missing response data or retry a possibly dispatched operation. Non-streaming JSON and valid nonterminal framing retain their existing behavior. Header-trusting shortcuts are removed: escaped JSON error keys now receive the same normalization as data-only events.
