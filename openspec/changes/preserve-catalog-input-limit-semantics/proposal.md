# Preserve catalog input-limit semantics

## Why

The generic models adapter copies the normal context window into
`metadata.input_context_window`. Consumers treat that field as a hard input
ceiling even when `max_context_window` sanctions a larger selected window.
This makes a 550000-token selection stop at a synthesized 272000-token input
limit. The native catalog carries the normal and maximum windows separately.

## What Changes

- Keep the normal/default window and its generic aliases unchanged.
- Report an input ceiling only from explicit upstream input-window or
  maximum-input declarations; retain the tighter declaration when both exist.
- Preserve maximum context, output limits, operator window preferences, model
  access, and client learned ceilings. Reject malformed explicit input bounds.
- Cover the actual generic models route and existing override consumers.

## Impact

The optional input-window field is unknown when upstream declares no input
ceiling. No default window, routing, credential, retry, timeout, or quota policy
changes. Loaded client catalogs need their normal explicit refresh/adoption path.
