## Verification and implementation

- [x] Add permanent real-TCP and public-route regressions that fail on the current buffered final-event path.
- [x] Drain received Python HTTP body chunks before propagating the original incomplete-transfer error.
- [ ] Verify direct and routed streaming, valid terminal success/error, genuine truncation, cancellation, and exactly-once settlement.
- [ ] Run affected Python and native transport gates, strict OpenSpec validation, formatting, lint, and typing checks.
- [ ] Qualify the existing pinned native helper and corrected fallback in the deployed runtime packaging.
- [ ] Complete author review, synchronize the normative specification, and archive only after verification and delivery.
