## ADDED Requirements

### Requirement: Native compaction preserves its upstream request contract
The service MUST preserve the requested reasoning effort and client-supplied tool definitions when adapting native compact requests to the upstream Responses-v2 compaction-trigger protocol. It MUST preserve tool ordering and unknown tool fields, and MUST NOT manufacture a local summary when native compaction fails.

#### Scenario: Native compact request carries a foreground tool prefix
- **WHEN** a native compact request includes reasoning effort and tool definitions
- **THEN** the upstream Responses-v2 request retains those values and their ordering
- **AND** its input ends with exactly one compaction trigger
- **AND** completed output remains the native compact context window

#### Scenario: A trigger caller omits tool declarations
- **WHEN** a native trigger request omits tools or explicitly sends an empty tool list
- **THEN** upstream preserves that field's absence or explicit empty value respectively

#### Scenario: Retained objects have non-string type values
- **WHEN** a valid native window includes an opaque retained JSON object whose type is an array, object, null or number
- **THEN** capsule recognition uses a string guard and retains that object's fields unchanged without a transport or internal error
- **AND** standalone JSON, compaction-trigger SSE and the signed internal bridge preserve the complete window with HTTP 200 after settlement

#### Scenario: A native window continues an ordinary turn
- **WHEN** a validated native window is reused for an ordinary Responses turn, directly or through a bridge
- **THEN** its retained messages and capsule reach upstream unchanged, even when message text matches a former local fallback marker

#### Scenario: A retained opaque type is reused for compaction
- **WHEN** a returned window containing an array or object type is submitted for another compact operation
- **THEN** file-owner extraction and forwarding preserve the object without an internal error

### Requirement: Compaction uses its configured operation deadline
The default compact operation budget MUST be 600 seconds. The upstream compact call MUST receive its remaining operation budget without a percentage-based or fixed-duration deduction. Cancellation and finalization MUST preserve owned admission and quota settlement.

#### Scenario: An expensive compact call completes within the operation budget
- **WHEN** an upstream compact call finishes after the former shortened deadline but before the configured deadline
- **THEN** the service returns the completed compact response
- **AND** its admission and quota ownership are settled exactly once

#### Scenario: Cancellation follows completed upstream work
- **WHEN** upstream has completed but cancellation interrupts admission cleanup or account-success handling
- **THEN** the completed upstream usage is finalized exactly once before cancellation propagates
- **AND** request logs retain that completed usage

#### Scenario: A completed operation expires during teardown
- **WHEN** the operation deadline expires after a validated result is retained but during response, owned-client or shared HTTP-lease teardown
- **THEN** known usage and the returned service tier are settled exactly once before the timeout is surfaced
- **AND** completed work is not retried or classified as an upstream health failure

#### Scenario: Cancellation precedes SOCKS response ownership transfer
- **WHEN** a compact caller is cancelled or reaches its deadline while Python SOCKS fallback waits for response headers
- **THEN** the temporary session and connector are closed under joined cancellation protection before cancellation propagates
- **AND** no ownerless response or session survives the request

#### Scenario: SOCKS JSON fallback completes before session teardown
- **WHEN** Python SOCKS fallback receives a valid compact JSON body and cancellation or deadline expiry interrupts session close
- **THEN** validation and completion handoff precede teardown; known usage and tier are persisted once without replaying completed automation work
- **AND** other response readers retain their existing ownership contract

#### Scenario: Cancellation contends with shared HTTP generation release
- **WHEN** edge or level cancellation interrupts compact teardown while the shared HTTP-client lock is contended
- **THEN** the owned generation lease release is joined and decremented exactly once, allowing a retired generation to close
- **AND** the original cancellation propagates after completed usage and its log are persisted

#### Scenario: Cancellation interrupts completed transport teardown
- **WHEN** a native response is parsed but edge or level cancellation interrupts response release or owned client close
- **THEN** the parsed response and actual service tier reach the settlement owner before transport teardown starts
- **AND** transport cleanup is joined, completed usage is finalized and logged, then the original cancellation propagates

#### Scenario: Background compact consumers retain completed work
- **WHEN** automation or warmup compaction completes before cancellation or deadline expiry during transport teardown
- **THEN** its known usage and actual tier are retained before teardown and logged under joined cancellation protection
- **AND** automation does not retry completed work on another account and warmup does not classify it as an upstream health failure
- **AND** warmup logs keep their warmup kind and existing quota-accounting exclusion

#### Scenario: Warmup waits for compact response headers
- **WHEN** warmup upstream accepts a request but does not send response headers
- **THEN** the remaining configured compact budget bounds transport response-head waiting and the caller
- **AND** timeout joins the owned compact cleanup before releasing the warmup slot

#### Scenario: Repeated cancellation overlaps quota persistence
- **WHEN** edge or level cancellation occurs while compact quota settlement is pending
- **THEN** the service joins its owned settlement task before propagating the original cancellation
- **AND** cleanup-ready is signalled only after the owned reservation persistence attempts finish, not as proof that failed writes succeeded

#### Scenario: Both compact settlement writes fail after upstream completion
- **WHEN** finalization and fallback release both fail after compact upstream work completed
- **THEN** forwarded SSE retains HTTP 200 and emits response.failed with usage_settlement_failed
- **AND** the original reservation is not falsely marked released and the origin cannot replay or take over settlement

### Requirement: Compact endpoint logs identify the real operation and session
Calls to a compact endpoint MUST be logged with request kind compaction and the supplied session identity, even when the caller omits Codex turn metadata. Compact cleanup MUST join the database insert before returning, including under repeated edge or level cancellation. Ordinary response-stream logging MUST retain its asynchronous ownership.

#### Scenario: An OpenAI-style native client supplies only session identity
- **WHEN** a client calls the compact endpoint with a session_id header and no turn metadata
- **THEN** its request log identifies that session and request kind compaction
- **AND** response usage remains upstream-derived

#### Scenario: Cancellation overlaps compact log persistence
- **WHEN** the compact log database insert is pending and edge or level cancellation occurs
- **THEN** the compact caller joins that insert before cancellation propagates
- **AND** insertion failures keep the existing observational failure policy

### Requirement: Compaction preserves complete validated history
Compact preparation MUST preserve every supplied validated history item in order,
including tool pairs, Lite state, inline images and file references. It MUST NOT
estimate a token ceiling from JSON bytes, select a smaller history, or replace
content with an omission marker. Actual ingress limits and upstream capacity
errors MUST retain their existing error and ownership semantics.

#### Scenario: Large history reaches the native compactor intact
- **WHEN** a validated compact input exceeds the former estimated history budget
- **THEN** the complete input is forwarded in its original order
- **AND** historical file references still constrain account ownership

#### Scenario: A validated compact window resembles an old fallback marker
- **WHEN** a retained assistant message matches the old local-fallback text and precedes a nonempty opaque native capsule
- **THEN** another compact request forwards both items unchanged and in order
- **AND** marker text alone does not establish that a native capsule is invalid or authorize deleting history

### Requirement: Native compact output is a validated upstream window
A successful compact response MUST contain exactly one compaction item with
nonempty opaque encrypted content. Plaintext messages MUST NOT be relabelled as
encrypted compaction. Both compact JSON endpoints and the Codex compaction-trigger
SSE endpoint MUST preserve the complete returned native context window and usage.
Every retained output item MUST be a JSON object, validated before synthetic SSE starts.

#### Scenario: A retained message accompanies the native capsule
- **WHEN** upstream returns a retained message and one encrypted compaction item
- **THEN** every downstream compact surface preserves both in order
- **AND** SSE emits added and done events for every retained item and capsule at contiguous output indexes

#### Scenario: A provider returns plaintext or multiple capsules
- **WHEN** native output contains no encrypted capsule, multiple capsules, or an empty capsule
- **THEN** the service returns invalid_compaction_response
- **AND** it does not manufacture a successful native context window

#### Scenario: An invalid retained item accompanies a valid capsule
- **WHEN** upstream output includes a non-object retained item and a valid encrypted capsule
- **THEN** compact handling fails with invalid_compaction_response before emitting response.created
- **AND** no partial successful SSE window is constructed

### Requirement: Native compact capability follows backend provenance
Model metadata MUST advertise native_compaction_protocol responses_v2 only for
subscription-backed native Responses models. Generic OpenAI-compatible model
sources MUST NOT inherit that advertisement merely by being supported_in_api.

#### Scenario: A generic model source appears in the model catalog
- **WHEN** an OpenAI-compatible model source is included in the public catalog
- **THEN** it has no subscription-native compaction protocol advertisement

## REMOVED Requirements

### Requirement: Compact requests drop tool-only fields
**Reason**: Native Responses-v2 compaction accepts the foreground tool prefix.
**Migration**: Retain tools, tool selection and parallel policy in native adaptation.

### Requirement: Responses Lite follow-up transformations fail closed
**Reason**: The byte-derived compact budget and content elision do not reflect an upstream capacity contract.
**Migration**: Preserve validated Lite history, retain non-Lite model policy rejection and existing replay safeguards.

### Requirement: Compact trimming preserves prioritised historical side effects
**Reason**: Native compaction owns history reduction; selecting historical records locally loses context.
**Migration**: Forward every validated historical side-effect record and matching output unchanged.

## MODIFIED Requirements

### Requirement: Codex compaction triggers are bridged into compact output

Codex terminal top-level triggers MUST invoke compact handling with one terminal wire trigger; malformed placement MUST be rejected locally. Trigger SSE and standalone compact JSON MUST preserve the complete native window, usage and one encrypted capsule. SSE MUST emit created, indexed added/done pairs, then completed with monotonic sequences. Valid capsule ID/status and opaque content MUST be preserved; invalid capsule IDs MUST be omitted. Upstream SHALL use Responses streaming.

#### Scenario: terminal trigger emits a complete compact lifecycle

- **WHEN** a `POST /backend-api/codex/responses` request ends with exactly one top-level `compaction_trigger`
- **THEN** the proxy strips the trigger and invokes compact handling
- **AND** it emits created, added, done, and completed events in that order
- **AND** their sequence numbers increase monotonically from zero
- **AND** the done events and completed response preserve every returned native item in order, including exactly one encrypted capsule

#### Scenario: terminal trigger becomes one compact-wire trigger

- **WHEN** a `POST /backend-api/codex/responses` request ends with exactly one
  top-level `compaction_trigger`
- **THEN** the proxy strips that trigger before compact-input preparation
- **AND** the internal compact request contains exactly one terminal
  `compaction_trigger` item on its `input` array

#### Scenario: encrypted compaction item identity survives trigger streaming

- **WHEN** compaction handling for a terminal trigger returns encrypted content with a non-empty upstream `cmp_*` ID and terminal status
- **THEN** the added event exposes that ID with in-progress status
- **AND** the done event and completed response preserve the exact upstream ID, terminal status, and encrypted content
- **AND** the proxy does not synthesize a replacement item ID

#### Scenario: malformed trigger placement is rejected

- **WHEN** a `POST /backend-api/codex/responses` or
  `POST /backend-api/codex/responses/compact` request contains duplicate or
  non-terminal top-level `compaction_trigger` items
- **THEN** the proxy returns HTTP 400 with `invalid_request_error`
- **AND** it does not attempt upstream compact handling

#### Scenario: Codex compact transport uses the Responses stream

- **WHEN** a valid terminal compaction trigger is submitted through a Codex
  compact flow
- **THEN** the proxy sends the compact request to
  `POST /backend-api/codex/responses` with `stream=true` and `store=false`
- **AND** it accepts upstream SSE and reconstructs the complete validated native
  window from the terminal response lifecycle
- **AND** it does not require the legacy `/backend-api/codex/responses/compact`
  upstream route to be available

#### Scenario: Plaintext cannot manufacture encrypted compact output

- **WHEN** upstream returns messages without a valid encrypted compaction capsule
- **THEN** compact handling fails with invalid_compaction_response
- **AND** no plaintext message is relabelled as encrypted compaction

#### Scenario: Standalone Codex compact remains a compatibility endpoint

- **WHEN** a client calls `POST /backend-api/codex/responses/compact`
- **THEN** codex-lb preserves the endpoint and its subscription-backed compact
  routing contract
- **AND** malformed duplicate or non-terminal top-level triggers are rejected
  locally before any upstream compact attempt

#### Scenario: Codex-affinity standalone compact normalizes remote v2 output

- **WHEN** a Codex-affinity `POST /backend-api/codex/responses/compact` request receives upstream output that contains historical message items and one compaction summary item
- **THEN** the JSON response preserves historical message items and the compaction summary in their original order
- **AND** the normalized item preserves the compaction summary's valid `cmp_`-prefixed upstream ID and status
- **AND** it does not discard or rewrite the retained native history

#### Scenario: OpenAI-compatible compact normalizes duplicate triggers

- **WHEN** a client calls `POST /v1/responses/compact` with duplicate
  top-level `compaction_trigger` items
- **THEN** codex-lb preserves the existing compatibility behavior and returns
  HTTP 200 when the compact operation succeeds
- **AND** the forwarded compact input contains one terminal trigger
