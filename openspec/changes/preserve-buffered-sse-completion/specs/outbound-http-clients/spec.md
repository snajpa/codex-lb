## ADDED Requirements

### Requirement: Received SSE completion survives transfer-framing failure

Direct and routed Python HTTP SSE consumers MUST deliver received body bytes in order through normal framing and validation before propagating an incomplete-transfer error. A validated terminal MUST retain its outcome. With no complete terminal or independent payload-validation error they MUST propagate the original error, without manufacturing completion, replaying the request, or changing settlement ownership.

#### Scenario: Large valid completion is buffered before early close

- **GIVEN** a chunked HTTP response contains a complete final SSE event larger than a body-read chunk
- **WHEN** the peer closes without the HTTP chunk terminator before the consumer has drained the received body
- **THEN** the complete terminal event reaches the response consumer
- **AND** its response output and usage retain their original values
- **AND** the gateway does not append a synthetic transfer failure

#### Scenario: Received body is truly incomplete

- **GIVEN** the peer closes without a complete terminal SSE event
- **WHEN** all already-received body bytes have been consumed
- **THEN** the original incomplete-transfer failure is propagated
- **AND** no successful completion or usage is invented

#### Scenario: Buffered terminal is a model failure

- **GIVEN** the received body contains a complete terminal response failure
- **WHEN** the peer closes without the HTTP chunk terminator
- **THEN** the original model failure remains the terminal result
- **AND** the gateway neither converts it into success nor replaces it with a framing error

### Requirement: HTTP terminal classification validates payloads

Python and native HTTP consumers MUST classify JSON before header/native shortcuts. A Responses terminal without a response object valid under the existing event contract MUST fail as an invalid upstream response, never settle as successful. Malformed JSON or a nonterminal payload under a terminal header MUST NOT terminate consumption or suppress a later transfer failure.

#### Scenario: Buffered completed event has a non-object response

- **GIVEN** a received event declares response.completed but its response value is an array
- **WHEN** the event reaches either HTTP consumer
- **THEN** the gateway reports an invalid upstream response
- **AND** the request cannot settle as successful

#### Scenario: Terminal header does not match JSON

- **GIVEN** an SSE header declares response.completed but the JSON is malformed or describes a nonterminal event
- **WHEN** the event reaches either HTTP consumer
- **THEN** the event does not terminate the stream
- **AND** a later valid terminal or original transfer failure remains observable

#### Scenario: Nonterminal header conceals an invalid terminal

- **GIVEN** an SSE header declares response.created but the JSON describes response.completed with a non-object response
- **WHEN** the event is received and the downstream disconnects
- **THEN** payload validation reports an invalid upstream response before forwarding
- **AND** settlement remains an error on canonical and equivalent public routes

### Requirement: Downstream cancellation closes suspended response bodies

The downstream Responses writer MUST close its owned body iterator after streaming exits, including cancellation during a pending terminal send or before the first body iteration. Each wrapper MUST close and join the child iterators it drives; cleanup MUST finish under cancellation before returning. An already-validated terminal MUST retain its outcome and usage exactly once; invalid terminal rejection MUST remain an error.

#### Scenario: Disconnect cancels a valid terminal write

- **GIVEN** an upstream terminal is valid and carries original usage
- **WHEN** http.disconnect cancels a pending downstream send
- **THEN** the suspended body iterator is closed and service persistence is drained
- **AND** the validated outcome and usage settle exactly once without replay

#### Scenario: Disconnect cancels the response start before body iteration

- **GIVEN** the startup probe is still driving the upstream service
- **WHEN** http.disconnect cancels a pending response start before the body is iterated
- **THEN** the probe is cancelled and joined before its source is closed
- **AND** upstream resource and settlement cleanup complete before returning

#### Scenario: Closing a yielded wrapper joins child finalization

- **GIVEN** a bridge or retry wrapper is suspended after yielding a child event
- **WHEN** that wrapper is closed, including cancellation during its close
- **THEN** its child's finalizer completes before wrapper cleanup returns
- **AND** cancellation remains observable after required cleanup completes

### Requirement: Joined cleanup preserves the terminal and caller cancellation

Material child cleanup MUST finish before close returns. Failure MUST NOT replace a validated terminal, add a failed event, change original usage, or penalize a healthy account. Ordinary iteration MUST propagate cleanup failure. An active close/cancellation signal MUST retain precedence with that failure as its cause; absorbed close faults MUST produce a payload-free warning. Retry callers MUST settle the validated outcome before propagating a finalizer fault.

#### Scenario: Child cleanup fails after validated completion

- **GIVEN** the service has yielded a validated terminal with original usage
- **WHEN** its child finalizer fails during joined close
- **THEN** the terminal outcome and usage settle exactly once without an additional failed event
- **AND** the cleanup failure does not mark an otherwise healthy account unhealthy
- **AND** ordinary iteration observes the cleanup failure, while explicit close retains its signal and records a payload-free warning

#### Scenario: Cleanup fails while closing a nonterminal stream

- **GIVEN** the service has yielded a created event or delta without a terminal
- **WHEN** downstream close joins a child finalizer that fails
- **THEN** close completes without yielding a synthetic upstream event
- **AND** persistence records downstream cancellation without an account-health penalty

#### Scenario: Deferred cancellation coincides with cleanup failure

- **GIVEN** a closing caller is cancelled while its owned cleanup is still running
- **WHEN** that cleanup finishes with an error
- **THEN** the caller observes its preserved cancellation only after cleanup finishes
- **AND** the cleanup error remains available as the cancellation's cause

#### Scenario: Refreshed stream finalizer fails after completion

- **GIVEN** a 401 was refreshed and its replacement yielded a validated completed response
- **WHEN** ordinary iteration cleanup raises an untyped or typed provider fault
- **THEN** original usage is settled before fault propagation without releasing the successful reservation
- **AND** the public and backend Responses routes emit no second terminal

#### Scenario: Failed terminal retains one settlement owner

- **GIVEN** a validated failed terminal is yielded with retry unavailable
- **WHEN** the service's terminal control-flow signal reaches retry callers
- **THEN** original error usage and account health are settled exactly once
