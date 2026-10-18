## Payload-first completion and framing recovery

aiohttp raises the incomplete-transfer exception before a public read can drain
bytes already received. The narrow recovery path uses its original buffered read
implementation, preserving ordering, offsets, flow control and the saved exception.
Without a valid terminal or an independent payload error, that exception still
propagates. This is qualified against the installed aiohttp version, not a promise
of private-API compatibility with every future dependency update.

Receiving additional validly framed bytes also exposes malformed terminal payloads
that the old read error concealed. Both terminal and nonterminal event headers can
mislabel JSON. For example, `event: response.created` with a completed payload whose
response is an array must fail before the service can stamp success, including when
the downstream disconnects immediately. Classification therefore parses JSON first;
the existing event model validates terminals, rather than introducing a new complete
Response schema.

Valid deltas retain their original bytes. The existing parsed-block carrier avoids
redundant Python JSON decoding through the normalizer/service chain; native raw-value
classification also uses payload type rather than headers. No new transport knob,
retry, account policy or settlement owner is introduced. Escaped error keys now
receive SDK normalization consistently with data-only events. Metadata-only warnings
identify buffered incomplete-transfer observations, not proven historic failures or
recovery success: correlate them with the request's independently recorded outcome.

The ASGI writer also owns the lifetime of its suspended body iterator. A disconnect
can cancel `send` while an async generator is paused at `yield`, rather than cancel
the generator's own pending operation. Closing that iterator explicitly lets the
existing service finalizers persist the already-validated terminal and release
resources; queueing a disconnect or relying on eventual garbage collection is not
that lifetime guarantee. The permanent route test observes both `http.disconnect`
delivery and cancellation of the stalled send before checking persisted settlement.

Historic production errors do not retain terminal provenance, and some last about
900 seconds. The reproduced buffered-terminal class is concrete, but this correction
alone does not attribute every historic error or establish the cause of those true
partial/lifetime failures.

Joined child finalization may itself fail after a valid terminal was yielded.
That failure remains a finalizer error instead of becoming another response or
changing completed settlement and account health. Retry consumers finalize the
validated usage before propagating an ordinary iteration fault. Explicit close
or caller cancellation keeps its primary signal, with the cleanup failure as its
cause; a payload-free warning makes close faults observable even when aclose
absorbs GeneratorExit. This also prevents a pre-terminal close fault from being
misclassified as an upstream failure or yielding during close.
